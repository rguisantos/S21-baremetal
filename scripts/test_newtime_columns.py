"""Preflight address boundaries, decoder refusal and the later bit scan's edges."""
import unittest

from inspect_newtime_columns_hzc2 import column1_result
from trace_newtime_columns_qemu import access_allowed, memory_access


class ColumnTests(unittest.TestCase):
    def setUp(self):
        self.regs = [0]*33
        self.regs[0]=0x1000;self.regs[1]=0xfffffffe;self.regs[2]=3;self.regs[31]=0x8000

    def test_unsigned_ldr_address_and_memory_width(self):
        self.assertEqual(memory_access('ldrsw','x3, [x0, #12]',self.regs),
            dict(address=0x100c,size=4,operation='read'))

    def test_byte_register_offset_has_byte_width(self):
        self.assertEqual(memory_access('ldrb','w4, [x0, x2]',self.regs)['address'],0x1003)
        self.assertEqual(memory_access('ldrb','w4, [x0, x2]',self.regs)['size'],1)

    def test_scaled_register_offset(self):
        self.assertEqual(memory_access('ldr','w4, [x0, x2, lsl #2]',self.regs)['address'],0x100c)

    def test_signed_and_unsigned_w_extension_are_distinct(self):
        self.assertEqual(memory_access('ldr','x4, [x0, w1, sxtw #3]',self.regs)['address'],0xff0)
        self.assertEqual(memory_access('ldr','x4, [x0, w1, uxtw #3]',self.regs)['address'],0x800000ff0)

    def test_pair_preindex_uses_updated_address_and_full_span(self):
        self.assertEqual(memory_access('stp','x29, x30, [sp, #-288]!',self.regs),
            dict(address=0x7ee0,size=16,operation='write'))

    def test_postindex_uses_original_base(self):
        self.assertEqual(memory_access('ldp','x0, x1, [sp], #32',self.regs)['address'],0x8000)

    def test_unscaled_negative_offset(self):
        self.assertEqual(memory_access('ldur','w3, [x0, #-28]',self.regs)['address'],0xfe4)

    def test_unsupported_memory_and_literal_fail_closed(self):
        for op,args in [('ldxr','x1, [x0]'),('cas','x1, x2, [x0]'),('ldr','q0, [x0]'),
                ('ldr','x0, 0x40000000'),('prfm','pldl1keep, [x0]'),('ldr','x0, [x1, x2, ror #1]')]:
            with self.assertRaises(ValueError):memory_access(op,args,self.regs)

    def test_nonmemory_arithmetic_has_no_memory_access(self):
        self.assertIsNone(memory_access('add','x0, x1, #16',self.regs))

    def test_boundary_rejects_partial_overlap_and_readonly_write(self):
        regions=[(0x1000,0x1010,False),(0x2000,0x2010,True)]
        self.assertTrue(access_allowed(dict(address=0x1008,size=8,operation='read'),regions))
        self.assertFalse(access_allowed(dict(address=0x100c,size=8,operation='read'),regions))
        self.assertFalse(access_allowed(dict(address=0x1000,size=4,operation='write'),regions))
        self.assertTrue(access_allowed(dict(address=0x2000,size=16,operation='write'),regions))
        self.assertFalse(access_allowed(dict(address=0x158609bc,size=4,operation='read'),regions))

    def test_key_payloads_compute_distinct_state(self):
        self.assertEqual(column1_result(0),0)
        self.assertEqual(column1_result(0x100001),28)

    def test_bit_scan_requires_enable_and_excludes_bit31(self):
        self.assertEqual(column1_result(1<<4),0)
        self.assertEqual(column1_result((1<<4)|1),12)
        self.assertEqual(column1_result((1<<30)|1),38)
        self.assertEqual(column1_result((1<<31)|1),0)
        self.assertEqual(column1_result((1<<20)|(1<<4)|1),12)

    def test_bit_scan_requires_unsigned_w_input(self):
        for value in (True,-1,1<<32,'1'):
            with self.assertRaises(ValueError):column1_result(value)


if __name__=='__main__':unittest.main()
