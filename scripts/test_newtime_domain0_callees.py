import json
from pathlib import Path
import random
import unittest

from test_newtime_dmc_method12 import RawThumb, load as dmc_report

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/newtime-domain0-callees-hzc2.json').read_text())
DOM=0x2f44c;H=0x38e00;B=0x40000;U32=0xffffffff


def machine():
    m=RawThumb(REPORT);m.r[13]=0x20000;m.r[14]=0xdead0001
    old=dmc_report()
    for row in old['witnesses']:m.code.setdefault(int(row['pc'],16),bytes.fromhex(row['bytes']))
    for a,v in old['literals'].items():m.literals.setdefault(int(a,16),v)
    return m


def leaves(m,old=0x12345678):
    for item in ('first_leaf','second_leaf'):
        for a,expression in REPORT[item]['rmw']:m.word(int(a,16),old)


def selection(levels,value=500,width=8):
    m=machine();m.word(DOM+12,H);m.word(DOM+32,value<<8);m.word(0x2fbf4,B)
    for i in range(32):m.mem[H+i]=0
    m.mem[H+1]=len(levels);m.mem[H+2]=width;m.mem[H+8]=7
    m._store(H+18,0x300,half=True);m._store(H+20,0x100,half=True);m._store(H+22,0x200,half=True)
    m._store(B+0x300,0x400,half=True);m._store(B+0x302,0x500,half=True)
    for i,v in enumerate(levels):m.word(B+0x100+4*i,v)
    m.r[0]=2;m.stores=[]
    return m


def nested_lookup(m,pc,target):
    if (pc,target)!=(0x5a306,0x5acec):raise ValueError('unexpected lookup call')
    m.r[14]=(pc+4)|1
    if m.run(target,set())!=pc+4:raise ValueError('wrong lookup return')


def final_roots(m,byte=0xad,old=0x12345678):
    for a,v in ((0x383b0,0x90000),(0x37e0c,0xa0000),(0x37e1c,0xb0000),
                (0x37e08,0xc0000),(0x38268,0xd0000),(0xa0a94,old),(0xd0080,0x11223344)):
        m.word(a,v)
    m.mem[0x9001c]=byte


class Domain0CalleeTests(unittest.TestCase):
    def test_first_leaf_exact_stores_rmw_and_preserved_r0(self):
        m=machine();leaves(m);m.r[0]=0xabcdef01;m.run(0x59e34,set())
        self.assertEqual([(a,v) for p,a,v in m.stores],[(0xaa031800,2),(0xaa331830,4),
            (0xaa331034,2),(0xaa030600,0x12345678|16),(0xaa030840,0x12345678|1),(0xaa030844,0x12345678|1)])
        self.assertEqual(m.r[0],0xabcdef01);self.assertEqual(m.calls,[])

    def test_second_leaf_exact_constants_and_return_is_old_register(self):
        m=machine();leaves(m,0x87654321);m.run(0x5a004,set())
        self.assertEqual([(a,v) for p,a,v in m.stores[:5]],[(0xaa3318d4,1),(0xaa3310dc,1),
            (0xa0021804,2),(0xa0021000,0),(0xa0021800,7)])
        self.assertEqual(m.r[0],0x87654321);self.assertEqual(m.calls,[])
        self.assertEqual(m.word(0xa0020800),(0x87654321&0x0effffff)|0xf0000000)

    def test_leaf_rmw_masks_with_eighty_distinct_old_words(self):
        rng=random.Random(0x599ec)
        for _ in range(80):
            old=rng.randrange(1<<32);m=machine();leaves(m,old);m.run(0x5a004,set())
            self.assertEqual(m.word(0xa0020600),old|16)
            self.assertEqual(m.word(0xa0020850),old|1)
            self.assertEqual(m.word(0xa0020800),(old&0x0effffff)|0xf0000000)

    def test_unreadable_mmio_keeps_prior_stores_and_does_not_become_zero(self):
        m=machine()
        with self.assertRaises(KeyError):m.run(0x59e34,set())
        self.assertEqual([(a,v) for p,a,v in m.stores],[(0xaa031800,2),(0xaa331830,4),(0xaa331034,2)])

    def test_empty_lookup_becomes_index255_and_row255(self):
        m=selection([]);m.run(0x5a2b8,{0x5a320},nested_lookup)
        self.assertEqual(m.r[11],255);self.assertEqual(m.r[4],B+0x200+8*255)
        self.assertEqual(m.word(m.r[13]+20),U32)

    def test_real_lookup_selects_threshold_or_last_index(self):
        for value,want in ((1000,0),(999,1),(700,1),(699,2),(0,2)):
            m=selection([0xab0003e8,700,300],value);m.run(0x5a2b8,{0x5a320},nested_lookup)
            self.assertEqual(m.r[11],want);self.assertEqual(m.r[4],B+0x200+8*want)

    def test_random_lookup_results_reach_row_without_signed_error_guard(self):
        rng=random.Random(0x5a306)
        for _ in range(80):
            levels=[rng.randrange(1<<32) for _ in range(rng.randrange(12))];value=rng.randrange(1<<24)
            want=next((i for i,v in enumerate(levels) if (v&0xffffff)<=value),len(levels)-1)&255
            m=selection(levels,value);m.run(0x5a2b8,{0x5a320},nested_lookup)
            self.assertEqual(m.r[11],want);self.assertEqual(m.r[4],B+0x200+8*want)

    def test_missing_row255_fails_before_dmc17(self):
        m=selection([]);m.run(0x5a2b8,{0x5a320},nested_lookup)
        m.r[6]=m.r[1]
        with self.assertRaises(KeyError):m.run(0x5a328,{0x5a334})
        self.assertFalse(any(to==0x5822c for p,to,args in m.calls))

    def test_explicit_row255_bytes_can_feed_selected_early_stores(self):
        m=selection([]);m.run(0x5a2b8,{0x5a320},nested_lookup);row=m.r[4]
        m.mem[row+2]=0x81;m.mem[row+5]=0x42;m.run(0x5a328,{0x5a334})
        self.assertEqual(m.word(0x2fdd4),0x81);self.assertEqual(m.word(0x2fdd8),0x42)

    def test_callback_partial_effects_survive_failure_in_third_callee(self):
        m=selection([]);leaves(m)
        def hook(sim,pc,target):
            sim.r[14]=(pc+4)|1
            if target in (0x59e34,0x5a004):sim.run(target,set())
            elif target==0x5a2b8:
                sim.run(target,{0x5a320},nested_lookup)
                sim.run(0x5a328,{0x5a334})
            else:raise ValueError('unexpected callback target')
        with self.assertRaises(KeyError):m.run(0x599ec,set(),hook)
        self.assertEqual(m.word(0xaa031800),2);self.assertEqual(m.word(0xa0021800),7)
        self.assertFalse(any(p==0x5a43c for p,to,a in m.calls))

    def test_mode2_branch_passes_header_byte_and_truncated_index(self):
        m=machine();m.r[8]=2;m.r[5]=H;m.r[11]=255;m.mem[H+8]=0x81;m.word(0x2fdd0,0)
        m.run(0x5a3a4,{0x5a432})
        def hook(sim,pc,to):
            self.assertEqual((pc,to),(0x5a43c,0x5822c));sim.r[0]=0xffffffff
            for r in (1,2,3,12):sim.r[r]=0xcccccccc
        m.run(0x5a432,{0x5a462},hook)
        self.assertEqual(m.calls[0][2][:2],(0x81,255))

    def test_wrapper17_preserves_full_frame_words_and_its_return(self):
        m=machine();m.r[:2]=[0xfedcba98,0x800001ff];seen=[]
        def hook(sim,pc,to):
            self.assertEqual(to,0x58170)
            seen.append((sim.r[0],sim.word(sim.r[1]),sim.word(sim.r[1]+4),sim.r[2],sim.r[3]))
            sim.r[0]=10
        m.run(0x5822c,set(),hook)
        self.assertEqual(seen,[(9,0xfedcba98,0x800001ff,0,17)]);self.assertEqual(m.r[0],10)

    def test_method12_handler17_calls_loader_then_final_helper_and_returns_zero(self):
        m=machine();final_roots(m);m.r[:3]=[0x91000,0x91004,0x91008]
        for a,v in ((0x91000,0x92000),(0x91004,0),(0x91008,17),(0x92000,0x81),(0x92004,255),
                    (0x37cd0+4*17,0x322ad),(0x38038+96,0x36fad),(0x38038+192,0x37925)):m.word(a,v)
        seen=[]
        def hook(sim,pc,to):
            ret=pc+len(sim.code[pc]);sim.r[14]=ret|1
            mapping={0x322ac:0x5faac,0x60198:0x60198,0x37924:0x65124}
            if to in mapping:
                self.assertEqual(sim.run(mapping[to],set(),hook),ret)
            elif to==0x36fac:
                seen.append(tuple(sim.r[:2]));sim.r[0]=U32
                for r in (1,2,3,12):sim.r[r]=0xcccccccc
            else:raise ValueError(f'unexpected frontier {to:#x}')
        m.run(0x5f758,set(),hook)
        self.assertEqual(seen,[(0x81,255)]);self.assertEqual(m.word(0xb0a94),0x1234567d)
        self.assertEqual(m.word(0xc0504),0x11223344);self.assertEqual(m.r[0],0)

    def test_two_method_wrapper_reloads_second_pointer_after_first_call(self):
        m=machine();m.word(0x38038+96,0x36fad);m.word(0x38038+192,0x37925);seen=[]
        def hook(sim,pc,to):
            seen.append((pc,to))
            if pc==0x601a0:sim.word(0x38038+192,0x12345679)
            sim.r[0]=0xffffffff
            for r in (1,2,3,12):sim.r[r]=0xcccccccc
        m.run(0x60198,set(),hook)
        self.assertEqual(seen,[(0x601a0,0x36fac),(0x601a4,0x12345678)])

    def test_final_helper_uses_distinct_source_and_destination_roots(self):
        rng=random.Random(0x65124)
        for _ in range(80):
            byte=rng.randrange(256);old=rng.randrange(1<<32);m=machine();final_roots(m,byte,old)
            m.run(0x65124,set())
            self.assertEqual(m.word(0xb0a94),(old&0xfffffff0)|(byte&15))
            self.assertEqual(m.word(0xc0504),0x11223344);self.assertEqual(m.word(0xa0a94),old)
            self.assertEqual(m.r[0],0x38268)

    def test_first_store_alias_can_change_the_later_source_pointer(self):
        m=machine();final_roots(m,0,0x90100)
        m.word(0x37e1c,0x38268-0xa94);m.word(0x90180,0xaabbccdd)
        m.run(0x65124,set())
        self.assertEqual(m.word(0xc0504),0xaabbccdd)
        self.assertIn((0x6515a,0x90180,4),m.reads)

    def test_poll_requires_bit16_to_clear_and_has_only_host_budget(self):
        address=REPORT['literals']['0x5a554']
        for samples,done in (([1<<16,1<<16,0],True),([1<<16]*100,False)):
            m=machine();m.r[1]=address;m.r[2]=1<<16;values=iter(samples);old=m.word
            def word(a,value=None):
                if value is None and a==address:return next(values)
                return old(a,value)
            m.word=word
            if done:self.assertEqual(m.run(0x5a488,{0x5a48e}),0x5a48e)
            else:
                with self.assertRaisesRegex(ValueError,'host slice budget'):m.run(0x5a488,{0x5a48e},budget=40)

    def test_uxtb_preserves_flags_and_ldmia_wraps_writeback(self):
        m=machine();m.r[0]=U32;m.n,m.z,m.c,m.v=True,False,True,True
        m.run(0x5a30a,{0x5a30c});self.assertEqual(m.r[3],255)
        self.assertEqual((m.n,m.z,m.c,m.v),(True,False,True,True))
        m.r[1]=0xfffffffc;m.word(0xfffffffc,0x81234567);m.run(0x5ad0c,{0x5ad0e})
        self.assertEqual((m.r[1],m.r[3]),(0,0x81234567))
        m.r[3]=U32;m.r[6]=8;m.c=m.v=True;m.run(0x65142,{0x65144})
        self.assertEqual(m.r[3],0xfffffff7);self.assertTrue(m.c);self.assertTrue(m.v)

    def test_missing_final_root_is_not_assumed_zero(self):
        m=machine()
        with self.assertRaises(KeyError):m.run(0x65124,set())

    def test_report_keeps_loader_and_physical_effects_open(self):
        self.assertFalse(REPORT['dmc17']['full_loader_executed_in_host'])
        self.assertFalse(REPORT['selection']['error_guard_before_row_read'])
        self.assertFalse(REPORT['firmware_executed']);self.assertFalse(REPORT['slot47_resolved'])


if __name__=='__main__':unittest.main()
