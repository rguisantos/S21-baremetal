#!/usr/bin/env python3
"""Raw-word tests with an explicit external-agent clear during a memory read."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_el2_hzc2 import IMAGES
from inspect_newtime_dmc_magic_hzc2 import MAGIC,SIGNAL,LOCAL_SIGNAL,bindings,census,inspect
from test_newtime_dmc_method12 import RawThumb

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/newtime-dmc-magic-hzc2.json').read_text())
U64=(1 << 64)-1


def signed(v,bits):return v-(1 << bits) if v & (1 << (bits-1)) else v


class RawA64:
    """Only selected integer words. System instructions and unmodeled words fail."""
    def __init__(self):
        self.code={int(r['pc'],16):int(r['word'],16) for r in REPORT['a64_witnesses']}
        self.x=[0xa550000000000000+i for i in range(32)]
        self.mem={};self.pc=0;self.z=None;self.stores=[];self.reads=[];self.calls=[]
        for a,r in REPORT['a64_literals'].items():self.put(int(a,16),int(r['value'],16),r['bytes'],record=False)
    def get(self,a,n):return sum(self.mem[(a+i)&U64] << (8*i) for i in range(n))
    def put(self,a,v,n,*,record=True):
        for i in range(n):self.mem[(a+i)&U64]=(v >> (8*i)) & 255
        if record:self.stores.append((self.pc,a,n,v & ((1 << (n*8))-1)))
    def word(self,a,value=None):
        if value is None:
            v=self.get(a,4);self.reads.append((self.pc,a,4,v));return v
        self.put(a,value,4)
    def reg(self,n,bits=64,*,sp=False):
        if n==31 and not sp:return 0
        return self.x[n] & ((1 << bits)-1)
    def run(self,start,stops=(),hook=None,*,budget=128):
        if type(budget) is not int or budget<1:raise ValueError('positive host budget required')
        pc=start
        for _ in range(budget):
            self.pc=pc
            if pc in stops:return pc
            w=self.code[pc];d=w&31;n=(w >> 5)&31;bits=64 if w >> 31 else 32;mask=(1 << bits)-1;q=pc+4
            wide=w & 0x7f800000
            if wide in (0x12800000,0x52800000,0x72800000):
                sh=((w >> 21)&3)*16;v=((w >> 5)&65535) << sh
                if wide==0x12800000:v=~v
                elif wide==0x72800000:v=(self.reg(d,bits)&~(65535 << sh))|v
                if d!=31:self.x[d]=v & mask
            elif w & 0xffc00000 in (0xa9800000,0xa8c00000):
                imm=signed((w >> 15)&127,7)*8;base=self.reg(n,sp=True);r2=(w >> 10)&31
                load=w & 0xffc00000==0xa8c00000;a=base if load else (base+imm)&U64
                if load:self.x[d],self.x[r2]=self.get(a,8),self.get(a+8,8)
                else:self.put(a,self.reg(d),8);self.put(a+8,self.reg(r2),8)
                self.x[n]=(base+imm)&U64
            elif w & 0x7f000000 in (0x11000000,0x51000000):
                imm=((w >> 10)&4095) << (12 if w & (1 << 22) else 0)
                self.x[d]=(self.reg(n,bits,sp=True)+(-imm if w & (1 << 30) else imm)) & mask
            elif w & 0xffc00000 in (0xb9400000,0xb9000000,0xf9400000,0xf9000000):
                size=8 if w >> 30==3 else 4;a=(self.reg(n,sp=True)+((w >> 10)&4095)*size)&U64
                if w & (1 << 22):
                    value=self.word(a) if size==4 else self.get(a,8)
                    if d!=31:self.x[d]=value
                elif size==4:self.word(a,self.reg(d,32))
                else:self.put(a,self.reg(d),8)
            elif w & 0xff000000 in (0x18000000,0x58000000):
                a=pc+4*signed((w >> 5)&0x7ffff,19);self.x[d]=self.get(a,8 if w >> 30==1 else 4)
            elif w & 0xffe0fc1f==0x6b00001f:self.z=self.reg(n,32)==self.reg((w >> 16)&31,32)
            elif w==0x927cec1f:self.x[31]=self.reg(0)&~15
            elif w & 0xff000010==0x54000000:
                condition=w&15
                if condition not in (0,1) or self.z is None:raise ValueError('unsupported/undefined condition')
                if self.z != bool(condition):q=pc+4*signed((w >> 5)&0x7ffff,19)
            elif w & 0x7e000000==0x34000000:
                nz=bool(w & (1 << 24))
                if bool(self.reg(d,bits))==nz:q=pc+4*signed((w >> 5)&0x7ffff,19)
            elif w >> 26==37:
                target=pc+4*signed(w&0x3ffffff,26);self.calls.append((pc,target));self.x[30]=q
                if hook is None:raise ValueError('opaque call requires hook')
                hook(self,pc,target)
            elif w >> 26==5:q=pc+4*signed(w&0x3ffffff,26)
            elif w & 0xfffffc1f==0xd65f0000:
                q=self.reg((w >> 5)&31)
                if q not in self.code:return q
            else:raise ValueError(f'unsupported raw A64 word {w:#x} at {pc:#x}')
            pc=q
        raise ValueError('host slice budget exhausted')


def fixture(pmu=0x12345678):
    m=RawA64();m.x[31]=0x20000000;m.x[29]=0xabcdef00;m.x[30]=0xdead0000
    m.word(0x15863b50,pmu);m.stores.clear();return m


def clocks(m,pc,target):
    if (pc,target)!=(0x369bc,0x36934):raise ValueError('unexpected opaque clock call')
    m.clock_argument=m.x[0]
    for i in range(19):m.x[i]=0xcccccccccccccccc


def release_on_read(m,third_value=0):
    original=m.word;reads=[0]
    def timed_word(address,value=None):
        if value is None and address==SIGNAL:
            reads[0]+=1
            if reads[0]==3:original(address,third_value)
        return original(address,value)
    m.word=timed_word
    return reads


class PublisherTests(unittest.TestCase):
    def test_publication_and_doorbell_precede_poll(self):
        m=fixture();m.run(0x36974,{0x369b0})
        self.assertEqual([(p,a,n,v) for p,a,n,v in m.stores if a in (SIGNAL,0x15900008)],
            [(0x369a0,SIGNAL,4,MAGIC),(0x369ac,0x15900008,4,0x80000)])
        self.assertEqual(m.calls,[])

    def test_external_agent_clears_third_read_then_clock_call(self):
        m=fixture();reads=release_on_read(m)
        self.assertEqual(m.run(0x36974,hook=clocks),0xdead0000)
        self.assertEqual(reads[0],3);self.assertEqual(m.clock_argument,0x12345678)
        self.assertEqual([v for p,a,n,v in m.reads if a==SIGNAL],[MAGIC,MAGIC,0])
        self.assertEqual((m.x[31],m.x[29],m.x[30]),(0x20000000,0xabcdef00,0xdead0000))

    def test_bl_hook_cannot_release_poll_that_precedes_it(self):
        m=fixture();called=[]
        def late(*args):called.append(True);m.word(SIGNAL,0)
        with self.assertRaisesRegex(ValueError,'host slice budget'):m.run(0x36974,hook=late,budget=60)
        self.assertEqual(called,[]);self.assertEqual(m.word(SIGNAL),MAGIC)

    def test_any_nonzero_word_keeps_poll_busy(self):
        for value in (1,0x1234abcd,0xffffffff):
            m=fixture();release_on_read(m,value)
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'host slice budget'):m.run(0x36974,hook=clocks,budget=60)
            self.assertEqual(m.calls,[])

    def test_pmu_value_is_saved_before_external_change(self):
        m=fixture(0xfedcba98);m.run(0x36974,{0x369b0});m.word(0x15863b50,0);m.word(SIGNAL,0)
        m.run(0x369b0,hook=clocks);self.assertEqual(m.clock_argument,0xfedcba98)

    def test_low32_pmu_input(self):
        m=fixture(0x100000001);release_on_read(m);m.run(0x36974,hook=clocks)
        self.assertEqual(m.clock_argument,1)

    def test_clock_call_needs_explicit_external_result(self):
        m=fixture();release_on_read(m)
        with self.assertRaisesRegex(ValueError,'opaque call'):m.run(0x36974)

    def test_unmapped_pmu_is_not_invented(self):
        with self.assertRaises(KeyError):RawA64().run(0x36974)

    def test_privileged_and_unknown_words_are_not_silently_executed(self):
        for pc in (0x36008,0x36138):
            with self.subTest(pc=pc),self.assertRaisesRegex(ValueError,'unsupported'):RawA64().run(pc)

    def test_bad_host_budgets_refused(self):
        for budget in (0,-1,True,1.5):
            with self.subTest(budget=budget),self.assertRaises(ValueError):fixture().run(0x36974,budget=budget)


class EntryAndContinuationTests(unittest.TestCase):
    def test_pmu_stack_selection_and_alignment(self):
        for pmu,stack in ((0xbad,0x02039000),(0,0x0225a000),(0xffffffff,0x0225a000)):
            m=RawA64();m.word(0x15860804,pmu)
            m.run(0x36054,{0x36084},lambda *args:None)
            self.assertEqual(m.x[31],stack);self.assertEqual(m.calls,[(0x36080,0x360f8)])

    def test_service_minus232_arguments_stop_before_smc(self):
        m=RawA64();self.assertEqual(m.run(0x3624c,{0x36138}),0x36138)
        self.assertEqual(m.x[:4],[0xffffffffffffff18,0,0,0xbffff000])

    def test_region_and_privilege_claims_remain_separate(self):
        self.assertEqual(REPORT['stage']['candidate_container'],'BL2')
        self.assertFalse(REPORT['stage']['actual_el3_entry_established'])
        self.assertFalse(REPORT['continuation']['service_minus232_implementation_executed'])

    def test_no_global_uniqueness_or_live_hardware_claim(self):
        self.assertFalse(REPORT['publisher']['global_unique_writer_proven'])
        self.assertFalse(REPORT['census']['global_writer_uniqueness_proven'])
        self.assertFalse(REPORT['hardware_observed']);self.assertFalse(REPORT['slot47_resolved'])


class AcpmTests(unittest.TestCase):
    def test_magic_gate_takes_only_exact_value(self):
        for magic,expected in ((MAGIC,1),(0x1234abcd,0),(0,0)):
            t=RawThumb(REPORT);t.word(LOCAL_SIGNAL,magic)
            t.run(0x56e98,set(),lambda *args:None)
            self.assertEqual(len(t.calls),expected);self.assertEqual(t.r[0],0)

    def test_original_thumb_tail_clears_local_signal(self):
        t=RawThumb(REPORT);t.word(LOCAL_SIGNAL,MAGIC);t.r[13]=0x10000
        for i in range(6):t.word(0x10000+4*i,0xdead0001 if i==5 else i)
        t.run(0x5a994,set());self.assertEqual(t.word(LOCAL_SIGNAL),0)

    def test_cross_core_clear_is_an_explicit_alias_fixture(self):
        m=fixture();old=m.word;reads=[0];seen=[]
        def timed_word(a,value=None):
            if value is None and a==SIGNAL:
                reads[0]+=1
                if reads[0]==3:
                    t=RawThumb(REPORT);t.word(LOCAL_SIGNAL,old(SIGNAL))
                    t.run(0x56e98,set(),lambda sim,pc,to:seen.append(to))
                    t.r[13]=0x10000
                    for i in range(6):t.word(0x10000+4*i,0xdead0001 if i==5 else i)
                    t.run(0x5a994,set());old(SIGNAL,t.word(LOCAL_SIGNAL))
            return old(a,value)
        m.word=timed_word;m.run(0x36974,hook=clocks)
        self.assertEqual(seen,[0x5a938]);self.assertEqual(reads[0],3)
        self.assertTrue(REPORT['acpm']['ap_local_alias_assumed_for_cross_core_interpretation'])


class ExtractionTests(unittest.TestCase):
    def test_report_census_has_bounded_not_global_meaning(self):
        r=REPORT['census'];self.assertEqual(r['exact_le32_magic'],['0x56eb0'])
        self.assertEqual([v['pc'] for v in r['a64_aligned_movk_abcd']],['0x36988'])
        self.assertEqual(r['thumb_movw_1234'],[])

    def test_census_preserves_unaligned_literal_matches(self):
        r=census(b'x'+struct.pack('<I',MAGIC)+b'x'+struct.pack('<I',MAGIC))
        self.assertEqual(r['exact_le32_magic'],['0x1','0x6'])
        self.assertFalse(r['computed_copied_aliased_or_external_writers_excluded'])

    def test_argument_register_and_width_mutations_refused(self):
        original={int(v['pc'],16):int(v['word'],16) for v in REPORT['a64_witnesses']}
        for pc in (0x36978,0x3697c,0x36998,0x369a4,0x3698c,0x3625c):
            words=original.copy();words[pc]^=1
            with self.subTest(pc=pc),self.assertRaises(ValueError):bindings(words)

    def test_wrong_image_refused_before_gnu(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.bin'
            for data in (b'bad',bytes(IMAGES['sboot'][0])):
                p.write_bytes(data)
                with self.subTest(size=len(data)),patch('inspect_newtime_dmc_magic_hzc2.subprocess.check_output') as gnu:
                    with self.assertRaisesRegex(ValueError,'unsupported image'):inspect(p)
                    gnu.assert_not_called()

    def test_cli_failure_emits_no_partial_report(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.bin';p.write_bytes(b'bad')
            r=subprocess.run([sys.executable,str(ROOT/'scripts/inspect_newtime_dmc_magic_hzc2.py'),str(p)],capture_output=True,text=True,check=False)
            self.assertEqual((r.returncode,r.stdout),(2,''));self.assertIn('unsupported image',r.stderr)


if __name__=='__main__':unittest.main()
