"""Privacy boundary, section provenance and fail-closed parsing of boot evidence."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_bugreport_boot import HEADING, parse_main


def fixture(body=None):
    if body is None:
        fields = dict(SEC_DRAM_BASE='0xb8a00000', SEC_DRAM_SIZE='0x7600000',
                      SEC_PGTBL_BASE='0xe0000000', SEC_PGTBL_SIZE='0x1300000',
                      HARX_BASE='0xc0000000', HARX_SIZE='0x1400000')
        body = ''.join(f'[0:    2.648648 ] {k}[{v}]\n' for k, v in fields.items())
    props = ('[ro.boot.bootloader]: [G998BXXSJHZC2]\n'
             '[ro.boot.flash.locked]: [1]\n'
             '[ro.boot.vbmeta.device_state]: [locked]\n'
             '[ro.boot.verifiedbootstate]: [green]\n')
    return (props.encode() + HEADING + b'\n' + body.encode() + b'------ 0.005s was LAST KMSG ------\n')


class BugreportBootTests(unittest.TestCase):
    def test_lines_hashes_and_adjacency(self):
        data = fixture()
        r = parse_main(io.BytesIO(data))
        self.assertEqual(r['main_member_sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(r['section']['first_line'], 6)
        self.assertEqual(r['section']['last_line'], 11)
        self.assertEqual(r['boot']['events'][0]['source_line'], 6)
        self.assertEqual(r['boot']['logged_intervals']['SEC_DRAM']['end_exclusive'], '0xc0000000')
        self.assertTrue(r['boot']['derived_relations']['sec_dram_end_equals_harx_base'])

    def test_allowlist_does_not_copy_private_or_spoofed_text(self):
        data = fixture().replace(HEADING + b'\n', HEADING + b'\n' +
            b'PRIVATE serial=123456\n[0:    1.000000 ] PRIVATE token=secret\n' +
            b'[0:    1.000001 ] SEC_DRAM_BASE[0xb8a00000] PRIVATE\n')
        result = json.dumps(parse_main(io.BytesIO(data)))
        for secret in ('PRIVATE', '123456', 'secret'):
            self.assertNotIn(secret, result)

    def test_unstamped_avb_message_has_no_invented_timestamp(self):
        data = fixture().replace(HEADING + b'\n', HEADING + b'\n' +
            b'avb_slot_verify.c:566: DEBUG: harx: hash verification succeed.\n')
        event = parse_main(io.BytesIO(data))['boot']['events'][0]
        self.assertEqual(event['kind'], 'harx_hash_success_message')
        self.assertIsNone(event['boot_seconds'])

    def test_missing_and_unterminated_section(self):
        for data in (fixture().replace(HEADING, b'other'), fixture().split(b'------ 0.005')[0]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_main(io.BytesIO(data))

    def test_duplicate_section_and_duplicate_memory(self):
        for data in (fixture() + HEADING + b'\n', fixture().replace(
                HEADING + b'\n', HEADING + b'\n[0:    1.0 ] HARX_SIZE[0x1400000]\n')):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_main(io.BytesIO(data))

    def test_missing_or_conflicting_properties(self):
        for data in (fixture().replace(b'[ro.boot.flash.locked]: [1]\n', b''),
                     fixture() + b'[ro.boot.flash.locked]: [0]\n'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_main(io.BytesIO(data))

    def test_missing_memory_and_overflow(self):
        for data in (fixture().replace(b'HARX_SIZE[0x1400000]', b'other'),
                     fixture().replace(b'HARX_BASE[0xc0000000]', b'HARX_BASE[0xffffffffffffffff]')):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_main(io.BytesIO(data))

    def test_host_bounds(self):
        for name in ('MAX_LINE', 'MAX_MEMBER', 'MAX_SECTION'):
            with self.subTest(name=name), patch('inspect_bugreport_boot.' + name, 16):
                with self.assertRaises(ValueError):
                    parse_main(io.BytesIO(fixture()))

    def test_wrong_archive_rejected_without_stdout_or_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private.zip'
            path.write_bytes(b'PRIVATE')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('inspect_bugreport_boot.py')), str(path)],
                capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')
        self.assertNotIn(b'PRIVATE', result.stderr)


if __name__ == '__main__':
    unittest.main()
