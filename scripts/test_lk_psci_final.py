"""Allowlist/privacy and section provenance for PSCI boot-log evidence."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from inspect_bugreport_boot import HEADING
from inspect_lk_psci_final import boot_observation

MESSAGE = b'[0:    2.946751 ] Change PSCI method to HVC\n'


def archive(body):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as output:
        output.writestr('dumpstate-2026-10-27-18-23-28.txt', body)
    return stream.getvalue()


class PsciObservationTests(unittest.TestCase):
    def inspect_fixture(self, body):
        data = archive(body)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.zip'
            path.write_bytes(data)
            # Production still requires the actual archive hash; only this test admits its fixture.
            with patch('inspect_bugreport_boot.ARCHIVE_SHA256', hashlib.sha256(data).hexdigest()):
                return boot_observation(path)

    def test_exact_event_provenance_and_private_text_excluded(self):
        body = b'PRIVATE identifier\n' + HEADING + b'\nPRIVATE secret\n' + MESSAGE + b'------ end ------\n'
        result = self.inspect_fixture(body)
        self.assertEqual(result['events'], [dict(kind='psci_method_changed_to_hvc_message',
            source_line=4, boot_seconds='2.946751')])
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('secret', json.dumps(result))
        self.assertEqual(result['last_kmsg_sha256'], hashlib.sha256(b'PRIVATE secret\n'+MESSAGE).hexdigest())

    def test_event_outside_last_kmsg_is_not_accepted(self):
        with self.assertRaises(ValueError):
            self.inspect_fixture(MESSAGE + HEADING + b'\nother\n------ end ------\n')

    def test_duplicate_or_missing_event(self):
        for content in (MESSAGE*2, b'no target event\n'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.inspect_fixture(HEADING + b'\n' + content + b'------ end ------\n')

    def test_unterminated_section_is_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect_fixture(HEADING + b'\n' + MESSAGE)

    def test_wrong_archive_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'private.zip'
            path.write_bytes(b'PRIVATE')
            with self.assertRaisesRegex(ValueError, 'exact received bugreport'):
                boot_observation(path)


if __name__ == '__main__':
    unittest.main()
