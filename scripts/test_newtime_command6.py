import json
from pathlib import Path
import unittest

from inspect_newtime_command6_hzc2 import (
    allocate_channels, core_file, fvp_packet, response_projection, service_allowed, thumb_lsl,
)
from inspect_newtime_method56_hzc2 import reply_matches, request_words


class MappingTests(unittest.TestCase):
    def test_two_copies_have_distinct_deltas(self):
        self.assertEqual(core_file(0x7408),0x3b408)
        self.assertEqual(core_file(0x1196c),0x3f16c)
        self.assertEqual(core_file(0x2e36c),0x5bb6c)

    def test_gaps_are_not_mapped_by_global_delta(self):
        for core in (0,0x9000,0xf7ff,0x39800):
            with self.assertRaises(ValueError): core_file(core)

    def test_negative_or_bool_addresses_are_rejected(self):
        for core in (-1,True,1<<32):
            with self.assertRaises(ValueError): core_file(core)


class ChannelTests(unittest.TestCase):
    def test_two_initial_rows_link_to_BL2_channel1(self):
        rows=[dict(tx=0,rx=0,count=n,stride=16) for n in (15,3)]
        plan=allocate_channels(0x8800,rows);c=plan['rows'][1]
        self.assertEqual((c['tx'],c['rx'],c['count'],c['stride']),(0x8a50,0x8a10,3,16))
        self.assertEqual((c['tx']+0x2039000,c['rx']+0x2039000),(0x2041a50,0x2041a10))

    def test_sender_indices_are_counterpart_pointers(self):
        c=allocate_channels(0x8a00,[dict(tx=0,rx=0,count=3,stride=16)])['rows'][0]
        self.assertEqual(c['tx_write'],c['tx']-4)
        self.assertEqual(c['rx_read'],c['rx']-8)
        self.assertEqual(c['tx_read'],c['tx']-8)
        self.assertEqual(c['rx_write'],c['rx']-4)

    def test_preexisting_TX_skips_allocator_and_does_not_advance(self):
        p=allocate_channels(0x8800,[dict(tx=0x1000,rx=0,count=3,stride=16)])
        self.assertFalse(p['rows'][0]['allocated'])
        self.assertEqual(p['next'],0x8800)

    def test_preexisting_RX_skips_even_with_zero_TX(self):
        p=allocate_channels(0x8800,[dict(tx=0,rx=0x1000,count=3,stride=16)])
        self.assertFalse(p['rows'][0]['allocated'])

    def test_zero_count_not_a_host_invented_firmware_error(self):
        c=allocate_channels(0x1000,[dict(tx=0,rx=0,count=0,stride=16)])
        self.assertEqual(c['next'],0x1020)

    def test_host_budget_does_not_claim_more_channel_paths(self):
        with self.assertRaises(ValueError): allocate_channels(0,[])
        with self.assertRaises(ValueError): allocate_channels(0,[{}]*16)


class PacketAndPermissionTests(unittest.TestCase):
    def test_BL2_packet_selects_third_word_command6_not_word0(self):
        p=fvp_packet(request_words(0xab3066a0),1)
        self.assertEqual((p['domain'],p['header'],p['value'],p['command']),(0,0,3172000,6))
        self.assertTrue(p['generic_switch'])

    def test_fourth_word_does_not_select_command(self):
        p=fvp_packet([0,1234,0,6],1)
        self.assertEqual(p['command'],0)

    def test_channel15_has_an_explicit_separate_path(self):
        p=fvp_packet([0,1234,6,6],15)
        self.assertTrue(p['channel15_special'])
        self.assertFalse(p['generic_switch'])

    def test_command7_does_not_index_seven_entry_switch(self):
        self.assertFalse(fvp_packet([0,0,7,0],1)['generic_switch'])

    def test_header_and_domain_are_separate_halves(self):
        p=fvp_packet([0x12340002,0,6,6],1)
        self.assertEqual((p['header'],p['domain']),(0x12340000,2))

    def test_initial_DVFS_mask_allows_FVP_plugin2(self):
        self.assertTrue(service_allowed(13,1,0x2e36d,0xb34,2))

    def test_guards_are_not_assumed_satisfied_by_mask_alone(self):
        for args in ((7,1,1,0xb34,2),(13,0,1,0xb34,2),(13,1,0,0xb34,2),(13,1,1,0xb30,2)):
            self.assertFalse(service_allowed(*args))

    def test_Thumb_LSL_register_does_not_use_A64_five_bit_mask(self):
        self.assertEqual(thumb_lsl(1,31),0x80000000)
        self.assertEqual(thumb_lsl(1,32),0)
        self.assertEqual(thumb_lsl(1,256),1)
        self.assertEqual(thumb_lsl(1,257),2)

    def test_permission_caller32_does_not_alias_caller0(self):
        self.assertFalse(service_allowed(13,1,1,1,32))


class ReplyProjectionTests(unittest.TestCase):
    def test_nonzero_internal_low16_is_removed_before_BL2_match(self):
        p=response_projection(0,10)
        self.assertEqual(p['constructed'],10)
        self.assertEqual(p['published'],0)
        self.assertTrue(reply_matches(1,p['published']))

    def test_all_low16_results_share_the_same_published_word(self):
        self.assertEqual({response_projection(0,i)['published'] for i in range(65536)},{0})

    def test_high_request_header_is_preserved(self):
        p=response_projection(0x56781234,0xffff)
        self.assertEqual(p['constructed'],0x5678ffff)
        self.assertEqual(p['published'],0x56780000)

    def test_word_match_alone_does_not_release_zero_status_poll(self):
        p=response_projection(0,0xffffffff)
        self.assertFalse(reply_matches(0,p['published']))
        self.assertTrue(reply_matches(1,p['published']))

    def test_internally_different_results_do_not_prove_success(self):
        values=[response_projection(0,v) for v in (0,1,10,0xffff,0x10000,0xffffffff)]
        self.assertGreater(len({v['constructed'] for v in values}),1)
        self.assertEqual({v['published'] for v in values},{0})


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=json.loads((Path(__file__).resolve().parent.parent/'docs/references/newtime-command6-hzc2.json').read_text())

    def test_route_and_plugin_initializers_agree(self):
        self.assertEqual(self.r['route']['plugin_names']['2'],'fvp')
        self.assertEqual(self.r['route']['plugin_names']['7'],'plugin_DVFS_0_0_0.fw')
        self.assertEqual(self.r['route']['receive_file'],'0x3f16c')
        self.assertEqual(self.r['command']['entry6_file'],'0x3f38c')

    def test_remaining_frontier_is_a_concrete_DVFS_target(self):
        self.assertEqual(self.r['service']['target_file'],'0x5bb6c')
        self.assertEqual(self.r['service']['next_target_file'],'0x59be4')
        self.assertFalse(self.r['physical_device_tested'])
        self.assertFalse(self.r['firmware_executed'])
        self.assertFalse(self.r['reply']['has_success_inference'])


if __name__=='__main__': unittest.main()
