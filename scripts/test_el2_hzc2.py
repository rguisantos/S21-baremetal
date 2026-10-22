"""Host tests for the offline inspector's fail-closed input boundaries."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from inspect_el2_hzc2 import pointer_offset, read_exact


class ImageBoundaryTests(unittest.TestCase):
    def test_exact_identity_and_corruption(self):
        data = b'fixture-image'
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.bin'
            path.write_bytes(data)
            self.assertEqual(read_exact(path, len(data), digest), data)
            for damaged in (data[:-1], data + b'X', b'F' + data[1:]):
                path.write_bytes(damaged)
                with self.subTest(damaged=damaged), self.assertRaises(ValueError):
                    read_exact(path, len(data), digest)

    def test_read_is_bounded(self):
        class Stream:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, count):
                self.count = count
                return b'x' * count

        from unittest.mock import patch
        stream = Stream()
        with patch.object(Path, 'open', return_value=stream):
            with self.assertRaises(ValueError):
                read_exact('untrusted', 16, 'unused')
        self.assertEqual(stream.count, 17)

    def test_pointer_must_have_file_backing(self):
        base, length = 0xc1400000, 0x100
        self.assertEqual(pointer_offset(base, base, length), 0)
        self.assertEqual(pointer_offset(base + 0xfc, base, length), 0xfc)
        for pointer, width in ((base - 4, 4), (base + 2, 4),
                               (base + 0x100, 4), (base + 0xfc, 8),
                               (base, 0)):
            with self.subTest(pointer=pointer, width=width), self.assertRaises(ValueError):
                pointer_offset(pointer, base, length, width)


if __name__ == '__main__':
    unittest.main()
