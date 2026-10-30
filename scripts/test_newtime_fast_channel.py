import json
from pathlib import Path
import unittest

from test_newtime_dmc_method12 import RawThumb

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/newtime-fast-channel-hzc2.json').read_text())


def machine():
    m=RawThumb(REPORT);m.r[13]=0x20000;m.r[14]=0xdead0001
    for a,v in REPORT['anchors'].items():
        address=int(a,16)
        if 0x38000<=address<0x3d000:core=address-0x34000
        else:core=address-0x2d800
        m.word(core,v)
    for i,v in enumerate(REPORT['channel']['file_words']):m.word(0x7498+4*i,v)
    for i,v in enumerate(REPORT['route']['plugin_map_words']):m.word(0x799c+4*i,v)
    return m


def callback(magic,argument=0xbad00000,helper_result=0xffffffff):
    m=machine();m.r[0]=argument;m.word(0xa590010c,magic)
    def hook(sim,pc,to):
        if (pc,to)!=(0x56ea4,0x5a938):raise ValueError('unexpected callback callee')
        sim.r[0]=helper_result
    m.run(0x56e98,set(),hook)
    return m


def decoder(m,mask=8):
    m.r[:4]=[128,0x8000,mask,0x10008];m.word(0x8008,0x73c0)
    for i in range(15):m.word(0x7ef0+4*i,0x12345678+i)
    m.run(0x39c34,set())
    return m


def fast_prefix(magic,packet_word0=0x13572468):
    m=machine();m.r[4]=0x8000;m.r[6]=0x7960;m.r[7]=0x7d20
    m.r[8]=128;m.r[2]=8;m.r[13]=0x10000
    for a,v in ((0x8000,0x7150),(0x8008,0x73c0),(0x8010,0),(0x80a8,0),
                (0x72a0,7),(0x72ac,0x2e828),(0x7d48,0xdead0003),
                (0xa5900100,packet_word0),(0xa590010c,magic)):
        m.word(a,v)
    def nested(sim,pc,to):
        child=machine();child.mem=sim.mem;child.r[:4]=sim.r[:4]
        if pc==0x3938e:
            if to!=0x5c34:raise ValueError('wrong decoder')
            for i in range(15):child.word(0x7ef0+4*i,10+i)
            child.run(0x39c34,set())
        elif pc==0x39416:
            if to!=0x29698:raise ValueError('wrong callback')
            def opaque(inner,p,target):
                if (p,target)!=(0x56ea4,0x5a938):raise ValueError('unexpected helper')
                inner.r[0]=0xdeadbeef
            child.run(0x56e98,set(),opaque)
        elif pc==0x393da:
            if to!=0x38684:raise ValueError('wrong logger')
            for r in (0,1,2,3,12):sim.r[r]=0xcccccccc
            return
        elif pc==0x393e0:
            child.r[0]=100
        else:raise ValueError(f'unexpected hook {pc:#x}')
        sim.r[0]=child.r[0]
        for r in (1,2,3,12):sim.r[r]=0xcccccccc
        sim.reads+=child.reads;sim.calls+=child.calls;sim.stores+=child.stores
    m.run(0x39386,{0x3941a,0x39464},nested)
    return m


class FastChannelTests(unittest.TestCase):
    def test_file_channel3_is_direct_and_uses_two_mmio_buffers(self):
        c=REPORT['channel'];self.assertEqual((c['index'],c['type'],c['request'],c['response']),(3,2,'0xa5900100','0xa5900108'))
        self.assertEqual((c['count'],c['packet_stride']),(1,16))

    def test_allocator_preserves_nonzero_direct_channel_pointers(self):
        m=machine();m.r[0]=0x8000;m.word(0x8048,0x8800)
        # Start at the real per-entry loop; stop after its advance.
        m.r[3]=0x7498;m.r[4]=0x7800;m.r[2]=0x8800;m.r[13]=0x20000
        before=dict(m.mem);m.run(0x39902,{0x39958})
        self.assertEqual(m.r[3],0x74e0);self.assertEqual(m.mem,before)

    def test_single_bit8_decoder_returns_channel3_and_plugin7(self):
        m=decoder(machine());self.assertEqual(m.r[0],7);self.assertEqual(m.word(0x10008),3)
        self.assertEqual(m.word(0x7efc),0x12345678+3+2)

    def test_simultaneous_events_are_not_assumed_equal_to_single_bit8(self):
        m=machine();m.r[:4]=[128,0x8000,10,0x10008];m.word(0x8008,0x73c0)
        for i in range(15):m.word(0x7ef0+4*i,100+i)
        m.word(0x7ef4,1);m.word(0x73c0+72+60,1)
        m.run(0x39c34,set())
        self.assertEqual(m.word(0x10008),1);self.assertEqual(m.r[0],2)

    def test_method0_skips_for_the_initialization_magic(self):
        m=callback(0x1234abcd);self.assertEqual(m.calls,[]);self.assertEqual(m.r[0],0)

    def test_method0_calls_only_for_its_distinct_exact_magic(self):
        for value in (0,0xffffffff,0x1234abcd,0xabcd1235,0xabcd1234):
            with self.subTest(value=value):
                m=callback(value);self.assertEqual(bool(m.calls),value==0xabcd1234)
                self.assertEqual(m.r[0],0)

    def test_method0_never_dereferences_its_argument_in_local_body(self):
        for pointer in (0,0xa5900100,0x3a660,0xffffffff):
            m=callback(0x1234abcd,pointer)
            self.assertEqual([a for p,a,n in m.reads if p==0x56e9c],[0xa590010c])
            self.assertFalse(any(a in (0xa5900100,0xa5900104,0x3a660,0x3a664,0x3a668) for p,a,n in m.reads))

    def test_zero_return_does_not_encode_helper_return_or_invocation(self):
        for result in (0,10,0xffffffff,0x80000000):
            self.assertEqual(callback(0xabcd1234,helper_result=result).r[0],0)

    def test_fast_dispatch_passes_address_of_request_pointer(self):
        m=fast_prefix(0x1234abcd)
        call=[c for c in m.calls if c[0]==0x39416][0]
        self.assertEqual(call[1],0x29698);self.assertEqual(call[2][1],3)
        self.assertEqual(m.word(call[2][0]),0xa5900100);self.assertEqual(m.r[8],0)

    def test_fast_prefix_does_not_require_a_mapped_word_at104(self):
        m=fast_prefix(0x1234abcd)
        self.assertNotIn(0xa5900104,m.mem)
        self.assertIn((0x393aa,0xa5900100,4),m.reads)
        self.assertNotIn(0xa5900104,[a for p,a,n in m.reads])

    def test_packet_header_variations_do_not_replace_the_local_magic_gate(self):
        for header in (0,0xffffffff,0x1234abcd,0xabcd1234):
            m=fast_prefix(0x1234abcd,header)
            self.assertFalse(any(p==0x56ea4 for p,to,args in m.calls))

    def test_fast_callback_match_selects_helper_but_not_a_physical_result(self):
        m=fast_prefix(0xabcd1234)
        self.assertTrue(any((p,to)==(0x56ea4,0x5a938) for p,to,args in m.calls))
        self.assertEqual(m.r[8],0)

    def test_missing_magic_memory_fails_instead_of_becoming_zero(self):
        m=machine();m.r[0]=0
        with self.assertRaises(KeyError):m.run(0x56e98,set())

    def test_no_repoll_in_callback(self):
        m=callback(0x1234abcd)
        self.assertEqual(sum(p==0x56e9c for p,a,n in m.reads),1)

    def test_selected_tail_clears10c_after_opaque_body(self):
        m=machine();m.word(0xa590010c,0xabcd1234);m.run(0x5a994,{0x5a99c})
        self.assertEqual(m.word(0xa590010c),0)
        self.assertEqual(m.stores,[(0x5a998,0xa590010c,0)])

    def test_direct_response_allocator_does_not_read_queue_indices(self):
        m=machine();m.r[0]=3;m.word(0x8008,0x73c0)
        m.run(0x386bc,set());self.assertEqual(m.r[0],0xa5900108)
        self.assertFalse(any(a in (0,0xa5900104) for p,a,n in m.reads))

    def test_report_preserves_open_frontiers(self):
        self.assertFalse(REPORT['firmware_executed']);self.assertFalse(REPORT['slot47_resolved'])
        self.assertIn('all readers of104',REPORT['not_proven'])
        self.assertFalse(REPORT['callback']['poll'])
        self.assertTrue(REPORT['callback']['magic_values_differ'])


if __name__=='__main__':unittest.main()
