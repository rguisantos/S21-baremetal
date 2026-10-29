from pathlib import Path
import unittest

from inspect_newtime_ect_gate_hzc2 import finalize, gate, nibble, signature

TABLE=bytes([0x20,0x14,0,0x40,0,0,0,0,0,0,0x40])


class NibbleTests(unittest.TestCase):
    def test_direct_path_examples(self):
        self.assertEqual(nibble(0x00040004),4)
        self.assertEqual(nibble(0x00500005),5)

    def test_selector_8_wraps_to_itself(self):
        self.assertEqual(nibble(8),8)
        self.assertEqual(nibble(0xffffffff00000008),8)

    def test_independent_nibble_list_covers_exactly226_reachable_pairs(self):
        pairs=set()
        for selector in range(16):
            for value in range(16):
                index=selector%8
                if index==0 and value!=selector:continue
                digits=[0]*8;digits[0]=selector;digits[index]=value
                w=sum(d<<(4*i) for i,d in enumerate(digits))
                self.assertEqual(nibble(w),digits[index])
                pairs.add((selector,value))
        self.assertEqual(len(pairs),226)

    def test_high_half_is_ignored_before_the_gate_test(self):
        self.assertEqual(nibble(0xffffffff00040004),4)

    def test_fixture_rejects_wrong_widths_and_bool(self):
        for v in (-1,True,1<<64):
            with self.assertRaises(ValueError):nibble(v)


class SignatureTests(unittest.TestCase):
    def test_preserved_source_makes_PARA007_the_selected_signature(self):
        self.assertEqual(signature(b'PARA007n',b'PARA007x'),0)

    def test_last_three_bytes_are_read_from_current_ECT(self):
        self.assertEqual(signature(b'PARAabc?',b'PARAabc!'),0)
        self.assertNotEqual(signature(b'PARAabc?',b'PARA007!'),0)

    def test_source_prefix_is_not_checked_by_this_helper(self):
        self.assertEqual(signature(b'XXXXabc?',b'PARAabc!'),0)
        # The later parser independently validates its own PARA prefix.

    def test_SRAM_prefix_must_still_match_the_constant(self):
        self.assertNotEqual(signature(b'PARA007n',b'XXXX007n'),0)

    def test_short_host_buffers_are_refused(self):
        with self.assertRaises(ValueError):signature(b'PARA00',b'PARA007')


class GateTests(unittest.TestCase):
    def test_direct_nibble_does_not_read_gate_MMIO_or_call244(self):
        p=gate(0x40004,1,0xffffffffffffffff,1)
        self.assertTrue(p['parser_edge']);self.assertFalse(p['gate_MMIO_read'])
        self.assertEqual(p['SMC244_calls'],[])

    def test_clear_bit_with_mismatch_ignores_nonzero_returns(self):
        p=gate(0,0,1,0xffffffffffffffff,sram=b'XXXX007')
        self.assertTrue(p['parser_edge'])
        self.assertEqual([c['X2'] for c in p['SMC244_calls']],[0,1])
        self.assertIsNone(p['direct_MMIO_store'])

    def test_clear_bit_match_rereads_MMIO_before_RMW(self):
        p=gate(0,0,1,2,rmw_sample=0x80)
        self.assertTrue(p['parser_edge'])
        self.assertEqual(p['direct_MMIO_store'],0x81)
        self.assertEqual([c['X2'] for c in p['SMC244_calls']],[0,2])

    def test_set_bit_first_X64_result_nonzero_skips_second_call(self):
        p=gate(0,1,1<<32,0)
        self.assertTrue(p['return_without_parser'])
        self.assertEqual(len(p['SMC244_calls']),1)
        self.assertEqual(p['direct_state_stores'],[])

    def test_set_bit_second_X64_result_nonzero_skips_parser(self):
        p=gate(0,1,0,1<<63)
        self.assertTrue(p['return_without_parser'])
        self.assertEqual(len(p['SMC244_calls']),2)

    def test_set_bit_both_zero_publishes_two_cells(self):
        p=gate(0,1,0,0)
        self.assertTrue(p['parser_edge'])
        self.assertEqual(p['direct_state_stores'],['0x31c08','0x31c10'])

    def test_initial_call233_is_not_hidden_in_zero_call244_count(self):
        p=gate(0x40004,1,0,0)
        self.assertEqual(p['initial_SMC']['command'],-233)
        self.assertEqual(p['initial_SMC']['result_register'],'X2')
        self.assertEqual(p['initial_SMC']['X3'],'inherited')

    def test_no_local_store_is_not_monitor_memory_preservation(self):
        p=gate(0,1,1,0)
        self.assertFalse(p['opaque_SMC_memory_effects_excluded'])


class FinalizeTests(unittest.TestCase):
    def test_finalize_resamples_233_and_can_select_another_mode(self):
        self.assertTrue(gate(0x40004,0,0,0)['parser_edge'])
        self.assertEqual(finalize(0x21,0,0,TABLE)['mode'],0x14)

    def test_W32_zero_allows_clear_even_with_upper_return_bits(self):
        p=finalize(0,1<<32,1<<63,TABLE)
        self.assertTrue(p['clears_entire_gate_MMIO_word'])
        self.assertEqual(p['terminal'],'return')
        self.assertTrue(gate(0,1,1<<32,0)['return_without_parser'])

    def test_first_spin_happens_before_clear(self):
        p=finalize(0,1,0,TABLE)
        self.assertFalse(p['clears_entire_gate_MMIO_word'])
        self.assertEqual(p['terminal'],'spin_1cb5c')

    def test_second_spin_happens_after_whole_word_clear(self):
        p=finalize(0,0,1,TABLE)
        self.assertTrue(p['clears_entire_gate_MMIO_word'])
        self.assertEqual(p['terminal'],'spin_1cb70')

    def test_mode64_skips237_but_still_writes_metadata_prefix_before230(self):
        p=finalize(0x40004,1,0,TABLE)
        self.assertFalse(p['SMC237_called'])
        self.assertEqual(p['metadata_u32_stores'],{0:0xe8000000,4:0x280000,8:0x2024c00,12:0})

    def test_mode20_does_not_claim_tail_word24_was_written(self):
        p=finalize(0x21,0,0,TABLE)
        self.assertEqual(p['metadata_u32_stores'][16],0x1400)
        self.assertNotIn(24,p['metadata_u32_stores'])


if __name__=='__main__':unittest.main()
