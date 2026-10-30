import json
from pathlib import Path
import unittest
from inspect_newtime_dmc_init_order_hzc2 import EDGES,precedes
from test_newtime_dmc_method12 import RawThumb

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/newtime-dmc-init-order-hzc2.json').read_text())
WORDS={int(x['pc'],16):int(x['word'],16) for x in REPORT['a64_witnesses']}


def sign(v,bits):return v-(1<<bits) if v&(1<<(bits-1)) else v


def a64_poll(start,stop,samples,budget=100):
    """Small raw-word evaluator, no peripheral execution or fabricated reads."""
    r=[None]*31;r[20]=0x15900108;r[21]=0x15900108
    pc=start;values=iter(samples);reads=[];stores=[];z=None
    def get(n,bits):
        if n==31:return 0
        if r[n] is None:raise ValueError('undefined register')
        return r[n]&((1<<bits)-1)
    for _ in range(budget):
        if pc==stop:return dict(pc=pc,registers=r,reads=reads,stores=stores)
        w=WORDS[pc];d=w&31;n=(w>>5)&31;bits=64 if w>>31 else 32;mask=(1<<bits)-1;q=pc+4
        if w&0x7f800000 in (0x52800000,0x72800000):
            shift=((w>>21)&3)*16;v=((w>>5)&65535)<<shift
            if w&0x7f800000==0x72800000:v=(get(d,bits)&~(65535<<shift))|v
            r[d]=v&mask
        elif w&0xffc00000==0xb9400000:
            a=get(n,64)+((w>>10)&4095)*4
            if a not in (0x15900108,0x1590010c):raise ValueError('unexpected address')
            r[d]=next(values)&0xffffffff;reads.append((pc,a,r[d]))
        elif w&0xffc00000==0xb9000000:
            a=get(n,64)+((w>>10)&4095)*4;stores.append((pc,a,get(d,32)))
        elif w&0x7f000000==0x34000000:
            if get(d,32)==0:q=pc+4*sign((w>>5)&0x7ffff,19)
        elif w&0xffe0fc1f==0x6b00001f:z=get(n,32)==get((w>>16)&31,32)
        elif w&0xff00001f==0x54000001:
            if z is None:raise ValueError('undefined NZCV')
            if not z:q=pc+4*sign((w>>5)&0x7ffff,19)
        else:raise ValueError(f'unsupported word {pc:#x}')
        pc=q
    raise ValueError('host budget exhausted')


def core_poll(samples,budget=100):
    m=RawThumb(REPORT);m.r[2]=0xa5900108;values=iter(samples);old=m.word
    def word(a,value=None):
        if value is None and a==0xa5900108:return next(values)
        return old(a,value)
    m.word=word;m.run(0x56ef6,{0x56efc},budget=budget)
    return m


class DmcInitOrderTests(unittest.TestCase):
    def test_ap108_poll_waits_for_nonzero(self):
        result=a64_poll(0x179e4,0x179f4,[0,0,0x38e00])
        self.assertEqual([v for p,a,v in result['reads']],[0,0,0x38e00])
        self.assertEqual(result['registers'][21],0x15900108)

    def test_ap10c_poll_compares_exact_magic(self):
        result=a64_poll(0x17ebc,0x17ed8,[0,0xabcd1234,0x1234abcd])
        self.assertEqual(result['registers'][0],0x1234abcd)
        self.assertEqual(result['registers'][2],0x1590010c)
        self.assertEqual(len(result['reads']),3)

    def test_core108_poll_waits_for_zero(self):
        m=core_poll([0x38e00,0x38e00,0]);self.assertEqual(m.r[3],0)
        with self.assertRaises(StopIteration):core_poll([0x38e00])

    def test_waits_have_only_host_budget(self):
        with self.assertRaisesRegex(ValueError,'host budget'):a64_poll(0x179e4,0x179f4,[0]*100,budget=20)
        with self.assertRaisesRegex(ValueError,'host slice budget'):core_poll([0x38e00]*100,budget=20)

    def test_publish108_uses_38e00_and_readable_alias_address(self):
        m=RawThumb(REPORT);m.run(0x56eee,{0x56ef6})
        self.assertEqual([(pc,a,v) for pc,a,v in m.stores],[(0x56ef2,0xa5900108,0x38e00)])

    def test_ready_magic_is_the_literal_published_before_init7_return(self):
        m=RawThumb(REPORT);m.run(0x56e6a,{0x56e70})
        self.assertEqual(m.stores,[(0x56e6e,0xa590010c,0x1234abcd)])

    def test_core_roots_follow_ack_exit(self):
        m=RawThumb(REPORT);m.run(0x56efc,{0x56f0c})
        self.assertEqual([(a,v) for pc,a,v in m.stores],[(0x2fbf4,0x38e00),(0x2fd98,0x3a600)])

    def test_selected_ap_ack_before_late_entry(self):
        self.assertTrue(precedes('ack108','late_entry'))
        self.assertTrue(precedes('ack108','late_masks'))
        self.assertEqual(a64_poll(0x17a50,0x17a54,[])['stores'],[(0x17a50,0x15900108,0)])
        self.assertEqual(WORDS[0x17a5c],0xd65f03c0)

    def test_init9_and_late_masks_are_unordered_in_delimited_model(self):
        self.assertFalse(precedes('init9','late_masks'))
        self.assertFalse(precedes('late_masks','init9'))
        self.assertTrue(precedes('ready10c','init9'));self.assertTrue(precedes('ready10c','late_masks'))

    def test_abstract_orders_satisfy_edges_and_reverse_the_unordered_pair(self):
        orders=REPORT['abstract_orders'];positions=[]
        for order in orders:
            self.assertEqual(len(order),len(set(order)))
            for a,b in EDGES:self.assertLess(order.index(a),order.index(b))
            positions.append(order.index('init9')<order.index('late_masks'))
        self.assertEqual(positions,[True,False])
        self.assertFalse(REPORT['abstract_orders_are_observed_executions'])

    def test_framework_walk_calls_init7_before_init9_under_preserved_manager(self):
        m=RawThumb(REPORT);m.r[6]=0x8000;m.r[7]=0x9000;m.r[13]=0x10000
        for a,v in ((0x8000,0x7150),(0x8014,13),(0x8010,0),(0x8050,0x39800),(0x9020,0xdead0001),(0x9024,0xdead0003)):
            m.word(a,v)
        for i in range(13):
            d=0x7150+48*i;m.word(d+32,1 if i in (7,9) else 0)
            m.word(d+4,{7:0x29601,9:0x31e01}.get(i,0));m.word(d+36,0x100)
        seen=[]
        def hook(sim,pc,to):
            if pc==0x38e90:seen.append((sim.r[0],to))
            elif pc not in (0x38e86,0x38ea0,0x38ea6):raise ValueError(hex(pc))
            for r in (0,1,2,3,12):sim.r[r]=0xcccccccc
        m.run(0x38e6a,{0x38ec0},hook)
        self.assertEqual(seen,[(0x72a0,0x29600),(0x7300,0x31e00)])

    def test_init9_selected_prefix_installs_method_table(self):
        m=RawThumb(REPORT);m.r[0]=0x7300;m.r[13]=0x10000
        m.run(0x5f600,{0x5f618})
        self.assertEqual(m.word(0x730c),0x37c40)
        self.assertEqual(m.word(0x384d4),0x7300)

    def test_no_mask_readiness_or_race_is_claimed(self):
        self.assertFalse(REPORT['distinction']['initial_ack_certifies_later_mask_publication'])
        self.assertIn('race on physical hardware',REPORT['not_proven'])
        self.assertFalse(REPORT['firmware_executed']);self.assertFalse(REPORT['slot47_resolved'])

if __name__=='__main__':unittest.main()
