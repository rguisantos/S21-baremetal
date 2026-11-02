#!/usr/bin/env python3
"""Controls for final import coverage and instruction-backed SSP evidence."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from capture_a0_stack_versions import coverage_delta, offsets, stack_sites, version_rows
from check_capture_a0_stack_versions import inspect
from test_capture_a0_module_policy import fixture


def generated(rows):
    return '__used __section(__versions) = {\n'+''.join(
        f'\t{{ {crc}, "{name}" }},\n' for name,crc in rows)+'};\n'


def ssp_fixture():
    data, loc, table = fixture(imports=(('__stack_chk_guard',1),('__stack_chk_fail',1)),debug=32)
    data = bytearray(data)
    struct.pack_into('<Q',data,table+11*64+24,loc['.debug.fixture'])
    struct.pack_into('<Q',data,table+11*64+32,32)
    struct.pack_into('<Q',data,loc['.symtab']+2*24+16,32)
    struct.pack_into('<II',data,loc['.debug.fixture'],0x90000008,0x94000000)
    struct.pack_into('<I',data,table+9*64+44,11)
    struct.pack_into('<QQq',data,loc['.rela.exports'],0,(4<<32)|275,0)
    struct.pack_into('<QQq',data,loc['.rela.exports']+24,4,(5<<32)|283,0)
    return data,loc,table


class StackVersionTests(unittest.TestCase):
    def test_generated_rows_are_read_from_versions_only(self):
        text='{ 0x9, "unrelated" },\n'+generated([('module_layout','0x11'),('__stack_chk_fail','0xf0fdf6cb')])
        self.assertEqual(version_rows(text),{'module_layout':'0x00000011','__stack_chk_fail':'0xf0fdf6cb'})

    def test_generated_printf_zero_crc_has_no_hex_prefix(self):
        self.assertEqual(version_rows(generated([('module_layout','0')])),{'module_layout':'0x00000000'})

    def test_generated_duplicate_overflow_and_ambiguous_sections_refused(self):
        good=generated([('module_layout','0x11')])
        for text in (good+good,generated([('module_layout','0x11'),('module_layout','0x12')]),
                     generated([('module_layout','0x100000000')]),generated([('only','0x1')])):
            with self.subTest(text=text),self.assertRaises(ValueError):version_rows(text)

    def test_generated_nonrecord_content_refused(self):
        with self.assertRaises(ValueError):version_rows('__used __section(__versions) = {\nunknown\n};')

    def test_delta_preserves_consumer_records_and_requires_final_imports(self):
        original=dict(versions={'module_layout':'0x00000011'},imports={'__stack_chk_fail':'strong'})
        self.assertEqual(coverage_delta(original,{'module_layout':'0x00000011','__stack_chk_fail':'0xf0fdf6cb'}),
                         {'__stack_chk_fail':'0xf0fdf6cb'})
        for changed in ({'module_layout':'0x00000012','__stack_chk_fail':'0xf0fdf6cb'},
                        {'__stack_chk_fail':'0xf0fdf6cb'}, {'module_layout':'0x00000011'},
                        {'module_layout':'0x00000011','__stack_chk_fail':'0xf0fdf6cb','extra':'0x00000000'}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):coverage_delta(original,changed)

    def test_offset_markers_accept_arm_and_host_immediates(self):
        self.assertEqual(offsets('->SIZE_x #16 sizeof(x)\n->OFF_x $8 offsetof(x) '),
                         '#define SIZE_x 16\n#define OFF_x 8\n')

    def test_missing_duplicate_and_oversize_offset_markers_refused(self):
        for text in ('', '->SIZE_x #16 x\n->SIZE_x #16 x', 'x'*(256*1024+1)):
            with self.subTest(length=len(text)),self.assertRaises(ValueError):offsets(text)

    def test_ssp_sites_require_actual_undefined_relocations_and_function_ranges(self):
        data,_,_=ssp_fixture();rows=stack_sites(data)
        self.assertEqual([(r['symbol'],r['relocation'],r['function'],r['function_offset']) for r in rows],
                         [('__stack_chk_guard',275,'exp',0),('__stack_chk_fail',283,'exp',4)])

    def test_ssp_wrong_instruction_refused(self):
        data,loc,_=ssp_fixture();struct.pack_into('<I',data,loc['.debug.fixture'],0xd503201f)
        with self.assertRaisesRegex(ValueError,'instruction'):stack_sites(data)

    def test_ssp_relocation_escape_and_unexpected_kind_refused(self):
        for off,kind in ((32,275),(0,257)):
            data,loc,_=ssp_fixture();struct.pack_into('<QQq',data,loc['.rela.exports'],off,(4<<32)|kind,0)
            with self.subTest(off=off,kind=kind),self.assertRaises(ValueError):stack_sites(data)

    def test_ssp_defined_helper_or_missing_owner_refused(self):
        data,loc,_=ssp_fixture();struct.pack_into('<H',data,loc['.symtab']+4*24+6,11)
        with self.assertRaises(ValueError):stack_sites(data)
        data,loc,_=ssp_fixture();struct.pack_into('<Q',data,loc['.symtab']+2*24+16,0)
        with self.assertRaisesRegex(ValueError,'ownership'):stack_sites(data)

    def test_existing_output_refused_before_native_execution(self):
        with tempfile.TemporaryDirectory() as d,patch('check_capture_a0_stack_versions.subprocess.run') as run:
            p=Path(d)
            with self.assertRaisesRegex(ValueError,'must be new'):inspect(p,p,p,p,p)
            run.assert_not_called()

    def test_unverified_clang_refused_before_source_or_native_execution(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with patch('check_capture_a0_stack_versions.verify_file',side_effect=[None,None,None,ValueError('bad clang')]),\
                 patch('check_capture_a0_stack_versions.source_members') as source,\
                 patch('check_capture_a0_stack_versions.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError,'bad clang'):inspect(p,p,p,p,p/'new')
                source.assert_not_called();run.assert_not_called()


if __name__=='__main__':unittest.main()
