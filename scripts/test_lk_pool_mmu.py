#!/usr/bin/env python3
"""Test selected LK mapping geometry, attributes, bounded walks and refusals."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_lk_pool_mmu import (DELTA,FLAGS,LAB_DELTAS,MASK,TABLE_LOW,TABLE_HIGH,
    build_lk_tables,inspect,leaf_attributes,records,register_bindings,walk_tables)


def fixture():
    return {
        0x18a1b0: 0x90000cd3,
        0x18a1b4: 0x91000273,
        0x18a224: 0x90000cd6,
        0x18a228: 0x910002d6,
        0x189fdc: 0xd0000cc9,
        0x189fe0: 0x91000129,
        0x18a038: 0xb0000e4d,
        0x18a054: 0x910001a1,
        0x189ff0: 0xf0fffb03,
        0x18a010: 0x91000063,
        0x189ff8: 0xf000bb17,
        0x18a01c: 0x910002f7,
        0x18a1d0: 0xd286a380,
        0x18a1d4: 0xf2b6a380,
        0x18a1d8: 0xf2c00220,
        0x189e18: 0xd29fe880,
    }


class BuildTests(unittest.TestCase):
    def test_nominal_pool_all_3043_pages_identity_and_same_attributes(self):
        data=build_lk_tables(DELTA);root=DELTA+TABLE_LOW;count=0
        for va in range(0xe8c1d000,0xe9800000,4096):
            r=walk_tables(data,root,root,va)
            self.assertEqual(r['physical_address'],hex(va));self.assertEqual(r['level'],3)
            a=r['attributes'];self.assertEqual((a['attr_index'],a['mair_byte'],a['shareability'],a['ap_bits']),(1,'0xff',3,1))
            self.assertTrue(a['access_flag']);self.assertFalse(a['read_only']);self.assertTrue(a['privileged_execute_never'])
            count+=1
        self.assertEqual(count,3043)

    def test_text_and_tables_have_distinct_ro_pxn_attributes(self):
        data=build_lk_tables(DELTA);root=DELTA+TABLE_LOW
        text=walk_tables(data,root,root,DELTA+0xec000)['attributes']
        tables=walk_tables(data,root,root,root)['attributes']
        self.assertTrue(text['read_only']);self.assertFalse(text['privileged_execute_never'])
        self.assertTrue(tables['read_only']);self.assertTrue(tables['privileged_execute_never'])

    def test_two_laboratory_placements_keep_pool_identity(self):
        for delta in LAB_DELTAS:
            data=build_lk_tables(delta);root=delta+TABLE_LOW;va=delta+0x18ebfff
            with self.subTest(delta=delta):self.assertEqual(walk_tables(data,root,root,va)['physical_address'],hex(va))

    def test_root_has_48_table_links_and_zero_remaining_entries(self):
        data=build_lk_tables(DELTA)
        self.assertEqual(len(data),TABLE_HIGH-TABLE_LOW)
        self.assertEqual(struct.unpack_from('<Q',data,47*8)[0],(DELTA+0x323000+47*4096)|3)
        self.assertEqual(data[48*8:4096],bytes((512-48)*8))

    def test_other_placement_and_bad_types_refused(self):
        for delta in (0,-1,True,float(DELTA),DELTA+4096):
            with self.subTest(delta=delta),self.assertRaises(ValueError):build_lk_tables(delta)


class WalkTests(unittest.TestCase):
    def setUp(self):
        self.delta=LAB_DELTAS[0];self.base=self.delta+TABLE_LOW
        self.data=bytearray(build_lk_tables(self.delta));self.va=self.delta+0xd09000

    def test_l2_nonidentity_control_preserves_page_offset(self):
        va=0x80000000
        struct.pack_into('<Q',self.data,0x1000+(va >> 21)*8,0x90000000|FLAGS)
        r=walk_tables(self.data,self.base,self.base,va+0x1234)
        self.assertEqual((r['level'],r['physical_address']),(2,'0x90001234'))

    def test_invalid_l1_and_out_of_image_table_refused(self):
        for value in (0,1,((self.base+len(self.data))|3),((self.base+4096)|3|(1 << 53))):
            data=bytearray(self.data);struct.pack_into('<Q',data,((self.va >> 30)&511)*8,value)
            with self.subTest(value=value),self.assertRaises(ValueError):walk_tables(data,self.base,self.base,self.va)

    def test_invalid_l2_descriptor_refused(self):
        entry=0x1000+(self.va >> 21)*8
        for value in (0,2,((self.base+4096)|3|0x80)):
            data=bytearray(self.data);struct.pack_into('<Q',data,entry,value)
            with self.subTest(value=value),self.assertRaises(ValueError):walk_tables(data,self.base,self.base,self.va)

    def test_invalid_l3_leaf_refused(self):
        l3=struct.unpack_from('<Q',self.data,0x1000+(self.va >> 21)*8)[0]&MASK
        entry=l3-self.base+((self.va >> 12)&511)*8
        for value in (0,1,self.va|3|8):
            data=bytearray(self.data);struct.pack_into('<Q',data,entry,value)
            with self.subTest(value=value),self.assertRaises(ValueError):walk_tables(data,self.base,self.base,self.va)

    def test_walk_bounds_and_unaligned_root_refused(self):
        for base,root,va in ((self.base+1,self.base,self.va),(self.base,self.base+8,self.va),(self.base,self.base,1 << 36),(self.base,self.base,True)):
            with self.subTest(base=base,root=root,va=va),self.assertRaises(ValueError):walk_tables(self.data,base,root,va)

    def test_truncated_table_image_refused(self):
        with self.assertRaises(ValueError):walk_tables(self.data[:4096],self.base,self.base,self.va)


class AttributeTests(unittest.TestCase):
    def test_noncacheable_and_cacheable_are_selected_by_mair_byte(self):
        nc=leaf_attributes(0x41000003|0x700,3)
        wb=leaf_attributes(0x41000003|0x704,3)
        self.assertEqual(nc['memory'],'normal_noncacheable');self.assertEqual(wb['memory'],'normal_write_back')

    def test_bad_level_type_descriptor_or_alignment_refused(self):
        for word,level in ((3,True),(3,1),(3,2),(1,3),(0x1001,2),(True,3),(-1,3),(1 << 64,3),(0x1000000747,3)):
            with self.subTest(word=word,level=level),self.assertRaises(ValueError):leaf_attributes(word,level)

    def test_unknown_mair_attribute_refused(self):
        with self.assertRaisesRegex(ValueError,'MAIR'):leaf_attributes(0x41000707,3,0)


class BindingTests(unittest.TestCase):
    def test_register_constants_and_root_bindings(self):
        r=register_bindings(fixture())
        self.assertEqual((r['root_relative'],r['l2_relative'],r['l3_relative']),('0x322000','0x323000','0x353000'))
        self.assertEqual((r['mair'],r['tcr'],r['t0sz'],r['tg0'],r['ips']),('0xff44','0x11b51c351c',28,0,1))
        self.assertFalse(r['active_registers_observed'])

    def test_root_source_register_or_displacement_mutation_refused(self):
        for pc,bit in ((0x18a1b4,1<<10),(0x18a228,1<<10),(0x18a1b4,1<<5),(0x18a1d0,1)):
            words=fixture();words[pc]^=bit
            with self.subTest(pc=pc,bit=bit),self.assertRaises(ValueError):register_bindings(words)

    def test_mapping_records_preserve_raw_end_and_physical_values(self):
        data=struct.pack('<5Q',0x1000,0x2001,0x3000,FLAGS,DELTA+40)+b'LK\0'
        r=records(data,0,1)[0]
        self.assertEqual((r['end_argument'],r['pa'],r['name']),('0x2001','0x3000','LK'))

    def test_truncated_bad_pointer_or_unterminated_name_refused(self):
        for data in (bytes(39),struct.pack('<5Q',0,0,0,FLAGS,0),struct.pack('<5Q',0,0,0,FLAGS,DELTA+40)+b'x'*65):
            with self.subTest(length=len(data)),self.assertRaises(ValueError):records(data,0,1)

    def test_mapping_record_bounds_and_types_refused(self):
        for offset,count in ((1,1),(0,0),(0,17),(-8,1),(True,1),(0,1.0)):
            with self.subTest(offset=offset,count=count),self.assertRaises(ValueError):records(bytes(80),offset,count)


class RefusalTests(unittest.TestCase):
    def test_wrong_size_or_hash_refused_before_gnu(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.bin'
            for data in (b'bad',bytes(IMAGES['sboot'][0])):
                p.write_bytes(data)
                with self.subTest(size=len(data)),patch('inspect_lk_pool_mmu.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError,'unsupported image'):inspect(p)
                    gnu.assert_not_called()

    def test_cli_refusal_has_no_partial_report(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.bin';p.write_bytes(b'bad')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('inspect_lk_pool_mmu.py')),str(p)],capture_output=True,text=True,check=False)
            self.assertEqual((r.returncode,r.stdout),(2,''));self.assertIn('unsupported image',r.stderr)


if __name__=='__main__':unittest.main()
