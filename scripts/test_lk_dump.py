from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from inspect_lk_dump_hzc2 import templates, span, overlaps, encoded_end, LIMIT


class DumpTemplateTests(unittest.TestCase):
    def fixture(self,base=0x80000000,size=0x1000,name=b'fixture'):
        return name.ljust(16,b'\0')+struct.pack('<3Q',base,size,1)

    def test_independent_template_layout(self):
        row=templates(self.fixture(),offset=0,count=1)[0]
        self.assertEqual((row['name'],row['base'],row['bytes'],row['end_exclusive']),
                         ('fixture','0x80000000',4096,'0x80001000'))
        self.assertEqual(row['initial_flag'],1)

    def test_consecutive_records(self):
        data=self.fixture()+self.fixture(0x90000000,name=b'next')
        self.assertEqual(templates(data,0,2)[1]['file_offset'],'0x28')

    def test_truncation(self):
        with self.assertRaises(ValueError):templates(self.fixture()[:-1],0,1)

    def test_invalid_table_bounds(self):
        for offset,count in ((-1,1),(0,0),(0,129),(True,1)):
            with self.assertRaises(ValueError):templates(self.fixture(),offset,count)

    def test_unterminated_or_non_ascii_name(self):
        for name in (b'x'*16,b'\xff',b'',b'line\n'):
            with self.assertRaises((ValueError,UnicodeError)):templates(self.fixture(name=name),0,1)

    def test_nonzero_name_padding(self):
        with self.assertRaises(ValueError):templates(self.fixture(name=b'ok\0bad'),0,1)

    def test_zero_size_is_host_rejection(self):
        with self.assertRaises(ValueError):templates(self.fixture(size=0),0,1)

    def test_overflow_is_host_rejection(self):
        with self.assertRaises(ValueError):templates(self.fixture(LIMIT-8,16),0,1)

    def test_span_and_half_open_boundaries(self):
        self.assertEqual(span(LIMIT-8,8),(LIMIT-8,LIMIT))
        self.assertTrue(overlaps((10,20),(19,30)))
        self.assertFalse(overlaps((10,20),(20,30)))
        with self.assertRaises(ValueError):overlaps((10,10),(20,30))

    def test_boolean_span_is_not_an_address(self):
        with self.assertRaises(ValueError):span(True,8)

    def test_writer_inclusive_end(self):self.assertEqual(encoded_end(100,8),107)
    def test_writer_zero_size_wraps(self):self.assertEqual(encoded_end(0,0),LIMIT-1)
    def test_writer_overflow_wraps(self):self.assertEqual(encoded_end(LIMIT-4,8),3)

    def test_cli_rejects_nonmatching_firmware_before_gnu(self):
        script=Path(__file__).with_name('inspect_lk_dump_hzc2.py')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.bin'
            for data in (b'',bytes(0x400000)):
                path.write_bytes(data)
                result=subprocess.run([sys.executable,str(script),str(path)],capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,2)
                self.assertIn('unsupported image',result.stderr)
                self.assertEqual(result.stdout,'')
                self.assertEqual(path.read_bytes(),data)


if __name__=='__main__':unittest.main()
