import json
from pathlib import Path
import random
import unittest

from inspect_newtime_fast_apply_hzc2 import DOM
from test_newtime_dmc_method12 import RawThumb

ROOT = Path(__file__).resolve().parent.parent
REPORT = json.loads((ROOT/'docs/references/newtime-fast-apply-hzc2.json').read_text())
INDICES = list(range(1,8))+list(range(11,19))
SIGNAL = 0xa590010c


def entry(i):
    return (DOM+48*i)&0xffffffff


def header(i):
    return 0x38e00+52*i


def fixture(direct=True):
    m=RawThumb(REPORT);m.r[13]=0x20000;m.r[14]=0xdead0001
    for item in REPORT['initial_descriptors']:
        for j,value in enumerate(item['words']):
            m.word(entry(item['index'])+4*j,value)
    # Explicit post-handshake host fixtures. These are not observed RAM values.
    for i in range(19):
        m.word(entry(i)+12,header(i));m.word(entry(i)+32,(100+i)<<8 | i)
        m.word(header(i)+20,(1 if direct else 0)<<16)
        m.word(header(i)+24,0xa5000000+i);m.mem[header(i)+9]=0
    m.word(SIGNAL,0xabcd1234)
    return m


def opaque(result=0xffffffff,mutate=None):
    def call(m,pc,target):
        if mutate is not None:
            mutate(m,pc,target)
        m.r[0]=result
        for r in (1,2,3,12):
            m.r[r]=0xcccccccc
    return call


def dependencies(m,parent,ids):
    m.mem[header(parent)+9]=len(ids)
    for j,i in enumerate(ids):
        m.mem[header(parent)+36+j]=i


def nested(m,pc,target):
    """Interpret included callees with a real return LR; stop at explicit frontiers."""
    raw=m.code[pc]
    ret=pc+len(raw)
    m.r[14]=ret|1
    # BLX carries a core address; witnesses and evaluator use file PCs.
    if target==0x2c1ec:
        target=0x599ec
    if target in (0x5a938,0x5ba90,0x5baa4,0x59a8c,0x599ec):
        if m.run(target,set(),nested)!=ret:
            raise ValueError('wrong nested return')
    elif target in (0x5b790,0x59e34,0x5a004,0x5a2b8):
        opaque()(m,pc,target)
    else:
        raise ValueError(f'unexpected frontier {target:#x}')


class FastApplyTests(unittest.TestCase):
    def test_local_loop_visits_exactly_fifteen_domains(self):
        m=fixture();m.run(0x5a938,set(),opaque())
        self.assertEqual([args[0] for p,to,args in m.calls if p==0x5a972],
                         [entry(i) for i in INDICES])
        self.assertEqual([args[0] for p,to,args in m.calls if p==0x5a98c],INDICES)
        self.assertEqual(m.r[0],0);self.assertEqual(m.word(SIGNAL),0)

    def test_skip_and_terminal_descriptors_need_no_readable_headers(self):
        m=fixture()
        for i in (0,8,9,10):
            for at in range(entry(i)+12,entry(i)+16):
                m.mem.pop(at)
        m.run(0x5a938,set(),opaque())
        self.assertFalse(any(a==entry(19)+12 for p,a,n in m.reads))

    def test_halfword_selector_uses_both_bytes_and_no_adjacent_bytes(self):
        for selector in (0,1,0x100,0xffff):
            with self.subTest(selector=selector):
                m=fixture();m.word(header(1)+20,(selector<<16)|0xffff)
                m.run(0x5a938,set(),opaque())
                first=[(p,to) for p,to,args in m.calls if p in (0x5a972,0x5a97a)][0]
                self.assertEqual(first,(0x5a972,0x5ba90) if selector else (0x5a97a,0x5baa4))
                self.assertIn((0x5a95c,header(1)+22,2),m.reads)
        # The same real LDRH word also wraps its effective address at 32 bits.
        m=fixture();m.r[3]=0xfffffff0;m.mem[6]=0x23;m.mem[7]=0xf1
        m.run(0x5a95c,{0x5a95e})
        self.assertEqual(m.r[3],0xf123);self.assertEqual(m.reads[-1],(0x5a95c,6,2))

    def test_direct_values_are_high24_and_reloaded_after_opaque_call(self):
        m=fixture()
        def mutate(sim,pc,to):
            if pc==0x5a972:
                sim.word(sim.r[0]+32,0xfedcba98)
        m.run(0x5a938,set(),opaque(mutate=mutate))
        self.assertEqual([a[1] for p,to,a in m.calls if p==0x5a972],[100+i for i in INDICES])
        self.assertEqual([a[1] for p,to,a in m.calls if p==0x5a98c],[0xfedcba]*15)

    def test_later_descriptors_are_not_snapshotted_before_calls(self):
        m=fixture()
        def mutate(sim,pc,to):
            if pc==0x5a972 and sim.r[0]==entry(1):
                sim.word(header(2)+20,0)
        m.run(0x5a938,set(),opaque(mutate=mutate))
        self.assertEqual([a[0] for p,to,a in m.calls if p==0x5a97a],[entry(2)])

    def test_nonzero_child_returns_do_not_prevent_clear(self):
        for result in (0,1,10,0xffffffff,0x80000000):
            m=fixture();m.run(0x5a938,set(),opaque(result))
            self.assertEqual(m.word(SIGNAL),0);self.assertEqual(m.r[0],0)
            self.assertEqual(sum(p==0x5a972 for p,to,args in m.calls),15)

    def test_missing_header_fails_before_clear(self):
        m=fixture();del m.mem[header(1)+22]
        with self.assertRaises(KeyError):m.run(0x5a938,set(),opaque())
        self.assertEqual(m.word(SIGNAL),0xabcd1234)

    def test_nonreturning_frontier_does_not_reach_clear(self):
        m=fixture()
        def stopped(sim,pc,to):raise RuntimeError('opaque frontier did not return')
        with self.assertRaisesRegex(RuntimeError,'did not return'):
            m.run(0x5a938,set(),stopped)
        self.assertEqual(m.word(SIGNAL),0xabcd1234)

    def test_custom_wrapper_forwards_entry_and_full_value(self):
        m=fixture();m.r[0]=entry(0);m.r[1]=0xfedcba98
        m.run(0x5ba90,set(),opaque(0xfffffffe))
        self.assertEqual(m.calls[0][:2],(0x5ba96,0x2c1ec))
        self.assertEqual(m.calls[0][2][:2],(entry(0),0xfedcba98))
        self.assertEqual(m.r[0],0xfffffffe)

    def test_zero_callback_uses_fallback_mode2_and_returns_its_result(self):
        m=fixture();m.r[:2]=[entry(1),0x12345678]
        m.run(0x5ba90,set(),opaque(10))
        self.assertEqual(m.calls[0][:2],(0x5ba9c,0x5b790))
        self.assertEqual(m.calls[0][2][:3],(entry(1),0x12345678,2))
        self.assertEqual(m.r[0],10)

    def test_zero_dependencies_require_no_list_and_return_zero(self):
        m=fixture(False);m.r[0]=entry(1);m.run(0x5baa4,set(),opaque())
        self.assertEqual(m.calls,[]);self.assertEqual(m.r[0],0)

    def test_dependencies_keep_duplicates_and_do_not_filter_skipped_ids(self):
        m=fixture(False);ids=[0,8,9,10,0,18];dependencies(m,1,ids)
        m.r[0]=entry(1);m.run(0x5baa4,set(),opaque())
        self.assertEqual([a[0] for p,to,a in m.calls],[entry(i) for i in ids])
        self.assertEqual([a[1] for p,to,a in m.calls],[0xa5000000+i for i in ids])
        self.assertEqual(m.r[0],0)

    def test_dependency255_is_addressed_without_a_local_bounds_check(self):
        m=fixture(False);dependencies(m,1,[255])
        m.word(entry(255)+12,0x90000);m.word(0x90018,0xffffffff)
        m.r[0]=entry(1);m.run(0x5baa4,set(),opaque())
        self.assertEqual(m.calls[0][2][:2],(entry(255),0xffffffff))

    def test_dependency_count_is_captured_but_parent_header_is_reloaded(self):
        m=fixture(False);dependencies(m,1,[2,3]);new=0x90000
        m.mem[new+37]=4
        def mutate(sim,pc,to):
            if len(sim.calls)==1:
                sim.mem[header(1)+9]=0;sim.word(entry(1)+12,new)
        m.r[0]=entry(1);m.run(0x5baa4,set(),opaque(mutate=mutate))
        self.assertEqual([a[0] for p,to,a in m.calls],[entry(2),entry(4)])

    def test_random_dependency_lists_and_full_u32_values(self):
        rng=random.Random(521938)
        for _ in range(80):
            m=fixture(False);ids=[rng.randrange(19) for _ in range(rng.randrange(13))]
            values=[rng.randrange(1<<32) for _ in range(19)]
            for i,v in enumerate(values):m.word(header(i)+24,v)
            dependencies(m,1,ids);m.r[0]=entry(1);m.run(0x5baa4,set(),opaque())
            self.assertEqual([(a[0],a[1]) for p,to,a in m.calls],[(entry(i),values[i]) for i in ids])

    def test_current_notification_target_is_a_literal_bx_lr_leaf(self):
        m=fixture();regs=list(m.r);m.run(0x59a8c,set())
        self.assertEqual(m.r,regs);self.assertEqual(m.stores,[]);self.assertEqual(m.calls,[])

    def test_dependency_can_select_domain0_despite_outer_skip(self):
        m=fixture(False);dependencies(m,1,[0]);saved=list(m.r)
        m.run(0x56e98,set(),nested)
        self.assertTrue(any((p,to)==(0x5ba96,0x2c1ec) for p,to,a in m.calls))
        self.assertEqual(m.word(SIGNAL),0);self.assertEqual(m.r[0],0)
        self.assertEqual(m.r[4:12],saved[4:12]);self.assertEqual(m.r[13],saved[13])

    def test_domain0_callback_orders_calls_and_discards_returns(self):
        m=fixture();m.r[:2]=[entry(0),0x12345678]
        m.run(0x599ec,set(),opaque())
        self.assertEqual([to for p,to,a in m.calls],[0x59e34,0x5a004,0x5a2b8])
        self.assertEqual(m.calls[1][2][0],0xffffffff)
        self.assertEqual(m.calls[2][2][0],2);self.assertEqual(m.r[0],0)

    def test_method0_integrates_the_loop_but_initialization_magic_skips_it(self):
        for magic in (0x1234abcd,0xabcd1234):
            m=fixture(False);m.word(SIGNAL,magic);m.run(0x56e98,set(),nested)
            self.assertEqual(sum(p==0x5a97a for p,to,a in m.calls),15 if magic==0xabcd1234 else 0)
            self.assertEqual(m.word(SIGNAL),0 if magic==0xabcd1234 else magic)
            self.assertEqual(m.r[0],0)
            self.assertNotIn(0xa5900104,[a for p,a,n in m.reads])

    def test_literal_search_is_not_a_producer_claim(self):
        s=REPORT['magic_search'];self.assertEqual(s['occurrences'],['0x56eb0'])
        self.assertFalse(s['producer_resolved']);self.assertFalse(s['computed_or_external_producers_excluded'])
        self.assertFalse(REPORT['firmware_executed']);self.assertFalse(REPORT['slot47_resolved'])


if __name__=='__main__':unittest.main()
