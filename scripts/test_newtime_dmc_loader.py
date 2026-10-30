import json
from pathlib import Path
import unittest

from test_newtime_dmc_method12 import RawThumb

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/newtime-dmc-loader-hzc2.json').read_text())
B=0x3a600;S=0x381c8;D=0x3a7a0;U32=0xffffffff
OFF=[0x1000+0x100*i for i in range(16)]


def signed(x):return x-(1<<32) if x&(1<<31) else x


def shape(first,k,mask):
    alt=signed(k)>5 and bool((mask&65535)>>(k&255)&1)
    j=(k-6 if alt else k)&U32;t=int(alt)
    return alt,j,{0xa4:(B+OFF[1+t]+64*j)&U32,0xa8:(B+OFF[9+t]+8*j)&U32,
        0xa0:(B+OFF[3+t]+4*7*j)&U32,0x1ec:(B+OFF[5+t]+4*11*j)&U32,
        0x1e8:(B+OFF[5+t]+4*11*first)&U32,8:(B+OFF[7+t]+4*8*j)&U32}


def fixture(first=3,k=7,mask=0,size=0x1000,control1=0,control2=0):
    m=RawThumb(REPORT);m.r[13]=0x20000;m.r[14]=0xdead0001;m.r[:2]=[first,k]
    for i in range(16):
        for off in range(0,16,4):m.word(D+16*i+off,0)
        m.word(D+16*i+4,OFF[i]);m.word(D+16*i+8,0x10+i)
    m.word(D+3*16+8,7);m.word(D+5*16+8,11);m.word(D+7*16+8,8)
    m.mem[D+3*16+12]=0xa3;m.mem[D+11*16+12]=0xb3
    for a,v in ((B,0x12345670),(B+4,0x76543210),(B+16,size),(S+0x9c,0x90000),
        (0xa58609bc,mask),(0xa58609a8,control1),(0xa58609ac,control2),
        (0x37fb4+16,0x369a5),(0x37fb4+40,0x369d1),
        (0x38038+96,0x36fad),(0x38038+192,0x37925),
        (0x37e0c,0xa0000),(0x37e1c,0xb0000),(0x37e08,0xc0000),(0xa0a94,0x12345678)):
        m.word(a,v)
    _,_,pointers=shape(first,k,mask)
    for p in {pointers[0x1e8],pointers[0x1ec]}:
        for i in range(32):m.mem[(p+i)&U32]=0
    m.mem[(pointers[0x1e8]+28)&U32]=0xad
    m.word((pointers[0xa0]+128)&U32,0x11223344)
    m.services=[];return m


def nested(m,pc,to):
    ret=pc+len(m.code[pc]);m.r[14]=ret|1
    mapping={0x60c6c:0x60c6c,0x64a64:0x64a64,0x36fac:0x647ac,0x37924:0x65124}
    if to in mapping:
        if m.run(mapping[to],set(),nested)!=ret:raise ValueError('wrong nested return')
    elif to in (0x369a4,0x369d0):
        m.services.append((pc,to,tuple(m.r[:2])))
        m.r[0]=0xffffffff
        for r in (1,2,3,12):m.r[r]=0xcccccccc
    else:raise ValueError(f'unexpected frontier {to:#x}')


def run(m):m.run(0x647ac,set(),nested);return m


class DmcLoaderTests(unittest.TestCase):
    def test_size_comparison_calls_noop_and_does_not_abort(self):
        for size in (0x23ff,0x2400,0x80000000,0xffffffff):
            m=run(fixture(size=size))
            expected=signed((B+size)&U32)>0x3c9ff
            self.assertEqual(any(pc==0x647c4 for pc,to,a in m.calls),expected)
            self.assertEqual(m.word(S+0x23c),B+OFF[14]);self.assertEqual(m.r[0],0)

    def test_upper_flag_excludes_bit31_and_uses_low8_shift(self):
        for k,mask,want in ((0,0x10000,1),(0,0x80000000,0),(14,0x40000000,1),
                            (15,0x80000000,0),(255,U32,0),(256,0x10000,1)):
            m=run(fixture(k=k,mask=mask))
            self.assertEqual(m.mem[S+0x229],want);self.assertEqual(m.word(0x3a658),want)

    def test_all_byte_indices_use_alternate_only_for6_through15(self):
        for k in range(256):
            m=run(fixture(k=k,mask=0xffff))
            self.assertEqual(m.word(0x3a654),int(6<=k<=15))
            self.assertEqual(m.word(S+0xa4),shape(3,k,0xffff)[2][0xa4])

    def test_pointer_publications_match_both_descriptor_groups(self):
        for k,mask in ((7,0),(7,1<<7),(15,1<<15),(0x80000006,U32)):
            m=run(fixture(k=k,mask=mask))
            for offset,value in shape(3,k,mask)[2].items():
                self.assertEqual(m.word(S+offset),value,(k,hex(offset)))

    def test_index255_uses_regular_group_without_a_local_bounds_guard(self):
        m=run(fixture(first=0x81,k=255,mask=U32))
        self.assertEqual(m.word(0x3a654),0)
        self.assertEqual(m.word(S+0x1ec),B+OFF[5]+4*11*255)
        self.assertEqual(m.word(S+0x1e8),B+OFF[5]+4*11*0x81)

    def test_first_argument_and_adjusted_second_select_distinct_rows(self):
        m=run(fixture(first=3,k=7,mask=1<<7))
        self.assertEqual(m.word(S+0x1ec),B+OFF[6]+44)
        self.assertEqual(m.word(S+0x1e8),B+OFF[6]+132)

    def test_common_cache_header_and_indirect_publications(self):
        m=run(fixture())
        for offset,index in ((0x10,11),(0x1e4,12),(0x23c,14),(0x204,15),(0xac,0)):
            self.assertEqual(m.word(S+offset),B+OFF[index])
        self.assertEqual(m.word(0x90024),B+OFF[13])
        self.assertEqual((m.word(S+0x240),m.word(S+0x244)),(0x12345670,0x76543210))
        self.assertEqual((m.mem[S+0x208],m.mem[S+12],m.mem[S+0x209]),(0xa3,0xb3,7))

    def test_alias_to_stride_changes_a_later_published_pointer(self):
        m=fixture(k=2);m.word(S+0x9c,D+3*16+8-36);run(m)
        self.assertEqual(m.word(D+3*16+8),B+OFF[13])
        self.assertEqual(m.word(S+0xa0),(B+OFF[3]+4*(B+OFF[13])*2)&U32)

    def test_two_method_wrapper_executes_loader_tail_and_second_method(self):
        m=fixture(first=3,k=7,mask=1<<7);saved=list(m.r)
        m.run(0x60198,set(),nested)
        self.assertEqual(m.word(0xb0a94),0x1234567d)
        self.assertEqual(m.word(0xc0504),0x11223344)
        self.assertEqual(m.r[4:8],saved[4:8]);self.assertEqual(m.r[13],saved[13])
        self.assertEqual(m.r[0],S+0xa0)

    def test_zero_control_words_do_not_call_indirect_services(self):
        m=run(fixture());self.assertEqual(m.services,[]);self.assertEqual(m.r[0],0)

    def test_tail_bit24_zero_nibble_sets_descriptor_byte11(self):
        m=run(fixture(control1=1<<24));p=m.word(S+0x1ec)
        self.assertEqual(m.mem[p+11],32)

    def test_tail_bit24_nonzero_nibble_updates_both_groups_in_byte18(self):
        m=run(fixture(control1=(1<<24)|3));p=m.word(S+0x1ec)
        self.assertEqual(m.mem[p+18],27)

    def test_tail_bit25_updates_overlapping_byte_and_halfword_fields(self):
        m=run(fixture(control1=(1<<25)|(5<<4)));p=m.word(S+0x1ec)
        self.assertEqual(m._load(p+12,half=True),0x0b6d)

    def test_tail_bit26_updates_word_and_byte26_fields(self):
        m=run(fixture(control1=(1<<26)|(3<<8)));p=m.word(S+0x1ec)
        self.assertEqual(m.word(p+12),0x1b000);self.assertEqual(m.mem[p+26],27)

    def test_tail_resamples_control_for_distinct_field_updates(self):
        m=fixture();m.run(0x647ac,{0x6494c},nested);old=m.word
        samples={0x64a68:1<<24,0x64a6e:1,0x64a8a:5,0x64a9a:2}
        def word(a,value=None):
            if value is None and a==0xa58609a8:return samples.get(m.pc,0)
            return old(a,value)
        m.word=word;m.r[14]=0xdead0001;m.run(0x64a64,set(),nested)
        p=m.word(S+0x1ec);self.assertEqual(m.mem[p+18],21)

    def test_service_failures_are_not_aggregated_in_tail_or_loader_return(self):
        m=run(fixture(control2=0x1f000321))
        reads=[a[0] for pc,to,a in m.services if to==0x369a4]
        self.assertEqual(reads,[11,11,41,18,17,3])
        self.assertEqual(m.r[0],0)
        self.assertTrue(all(a[1]<=255 for pc,to,a in m.services if to==0x369d0))

    def test_publications_precede_tail_and_are_not_rolled_back_if_it_stops(self):
        m=fixture();seen=[]
        def hook(sim,pc,to):
            if to==0x64a64:
                seen.append(sim.word(S+0x23c));raise RuntimeError('tail did not return')
            nested(sim,pc,to)
        with self.assertRaisesRegex(RuntimeError,'did not return'):m.run(0x647ac,set(),hook)
        self.assertEqual(seen,[B+OFF[14]]);self.assertEqual(m.word(S+0x1ec),B+OFF[5]+44*7)

    def test_asr_raw_word_counts_carry_sign_and_preserves_overflow(self):
        for value in (0,0x7fffffff,0x80000001,U32):
            for count in (0,1,15,31,32,33,255,256):
                m=RawThumb(REPORT);m.r[2]=value;m.r[4]=count;m.c=m.v=True
                m.run(0x647fa,{0x647fc});n=count&255
                self.assertEqual(m.r[2],(signed(value)>>min(n,32))&U32)
                carry=True if n==0 else bool(value&(1<<31) if n>=32 else value&(1<<(n-1)))
                self.assertEqual(m.c,carry);self.assertTrue(m.v)

    def test_uxth_and_strh_preserve_flags_and_wrap_addresses(self):
        m=RawThumb(REPORT);m.r[2]=0xabcdef12;m.n=m.c=m.v=True;m.z=False
        m.run(0x6481e,{0x64820});self.assertEqual(m.r[2],0xef12)
        self.assertEqual((m.n,m.z,m.c,m.v),(True,False,True,True))
        m.r[4]=0xfffffff6;m.r[3]=0xaabb1234;m.mem[1]=0x88;m.mem[4]=0x99
        m.run(0x64b00,{0x64b02})
        self.assertEqual([m.mem[i] for i in range(1,5)],[0x88,0x34,0x12,0x99])

    def test_missing_mask_memory_fails_after_prior_stores(self):
        m=fixture()
        for a in range(0xa58609bc,0xa58609c0):del m.mem[a]
        with self.assertRaises(KeyError):run(m)
        self.assertEqual(m.mem[S+0x208],0xa3)
        self.assertFalse(any(pc==0x648be for pc,a,v in m.stores))
