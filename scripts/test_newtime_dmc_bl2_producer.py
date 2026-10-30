import hashlib
import json
from pathlib import Path
import random
import struct
import unittest
from inspect_newtime_dmc_bl2_producer_hzc2 import AP_RECORD,AP_SRAM,CORE_RECORD,U32,header_values
from test_newtime_dmc_method12 import RawThumb

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/newtime-dmc-bl2-producer-hzc2.json').read_text())
WORDS={int(x['pc'],16):int(x['word'],16) for x in REPORT['a64_witnesses']}
S=0x0211b688


class A64Slice:
    """Decoder of only the integer words used by the selected two BL2 slices."""
    def __init__(self):self.x=[None]*31;self.mem={};self.stores=[]
    def put(self,a,v,width):
        for i in range(width):self.mem[(a+i)&((1<<64)-1)]=(v>>(8*i))&255
    def get(self,a,width):return sum(self.mem[(a+i)&((1<<64)-1)]<<(8*i) for i in range(width))
    def reg(self,i,bits):
        if i==31:return 0
        if self.x[i] is None:raise ValueError('undefined register')
        return self.x[i]&((1<<bits)-1)
    def run(self,lo,hi):
        for pc in range(lo,hi,4):
            w=WORDS[pc];d=w&31;n=(w>>5)&31;bits=64 if w>>31 else 32;mask=(1<<bits)-1
            wide=w&0x7f800000
            if wide in (0x52800000,0x72800000):
                shift=((w>>21)&3)*16;v=((w>>5)&65535)<<shift
                if wide==0x72800000:v=(self.reg(d,bits)&~(65535<<shift))|v
                self.x[d]=v&mask
            elif w&0xfffffc00==0x93407c00:
                v=self.reg(n,32);self.x[d]=(v-(1<<32) if v&(1<<31) else v)&((1<<64)-1)
            elif w&0xffe0fc00==0x0b000000:
                self.x[d]=(self.reg(n,32)+self.reg((w>>16)&31,32))&U32
            elif w&0xffc00000 in (0xb9400000,0xf9400000,0xb9000000,0xf9000000):
                width=8 if w>>30==3 else 4;a=(self.reg(n,64)+((w>>10)&4095)*width)&((1<<64)-1)
                if w&(1<<22):self.x[d]=self.get(a,width)
                else:
                    v=self.reg(d,width*8);self.put(a,v,width);self.stores.append((pc,a,width,v))
            else:raise ValueError(f'unsupported word {pc:#x} {w:#x}')


def bridge(off12,off14,m8,m9):
    a=A64Slice();a.x[0]=AP_RECORD;a.x[19]=S;a.x[9]=0x10000000
    for p,v in ((AP_RECORD+0x264,off12),(AP_RECORD+0x274,0x1800),(AP_RECORD+0x284,off14)):a.put(p,v,4)
    a.run(0x2d720,0x2d768)
    payload=a.get(S+616,8);a.put(payload+60,m8,4);a.put(payload+88,m9,4)
    # An opaque call occurs in the actual function between these slices.
    # Clobber volatile registers, retain globals and callee-saved x19 for this fixture.
    for i in range(19):a.x[i]=0xcccccccccccccccc
    a.run(0x2d814,0x2d854)
    return a


class Bl2DmcProducerTests(unittest.TestCase):
    def test_selected_stores_have_exact_addresses_widths_values(self):
        a=bridge(0x1000,0x2000,0x1ff0,0x1fff)
        self.assertEqual(a.stores[-3:],[(0x2d82c,AP_RECORD+0x64,4,CORE_RECORD+0x2000),
            (0x2d840,AP_RECORD+0x60,4,0x1ff0),(0x2d850,AP_RECORD+0x68,4,0x1fff)])

    def test_u32_conversion_over_random_offsets_and_sxtw(self):
        rng=random.Random(2100)
        for off in [0,0x7df8ca00,0x7fffffff,0xffffffff]+[rng.getrandbits(32) for _ in range(80)]:
            a=bridge(0x1000,off,17,23)
            expected=header_values(off,17,23)
            self.assertEqual({p:a.get(p,4) for p in expected},expected)
            low=(AP_RECORD+off)&U32
            self.assertEqual(a.get(S+744,8),(low-(1<<32) if low&(1<<31) else low)&((1<<64)-1))

    def test_masks_are_reloaded_from_published_state_pointer(self):
        a=A64Slice();a.x[19]=S;a.put(S+744,AP_RECORD+0x2000,8)
        a.put(S+616,0x30000000,8);a.put(0x30000000+60,0x77,4);a.put(0x30000000+88,0x88,4)
        a.run(0x2d814,0x2d854)
        self.assertEqual((a.get(AP_RECORD+0x60,4),a.get(AP_RECORD+0x68,4)),(0x77,0x88))

    def test_missing_payload_fails_instead_of_inventing_masks(self):
        a=A64Slice();a.x[19]=S;a.put(S+744,AP_RECORD,8);a.put(S+616,0x30000000,8)
        with self.assertRaises(KeyError):a.run(0x2d814,0x2d854)

    def test_unsupported_word_and_undefined_register_fail_closed(self):
        a=A64Slice()
        with self.assertRaises(ValueError):a.run(0x2d814,0x2d818)
        old=WORDS[0x2d814]
        try:
            WORDS[0x2d814]=0
            with self.assertRaises(ValueError):a.run(0x2d814,0x2d818)
        finally:WORDS[0x2d814]=old

    def test_source_table_words_and_fingerprints(self):
        for t in REPORT['survey']['source_tables']:
            raw=struct.pack('<'+'I'*len(t['cells_u32']),*t['cells_u32'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),t['sha256'])
        sources={t['key']:t for t in REPORT['survey']['source_tables']}
        self.assertEqual([(sources[k]['cells_u32'][15],sources[k]['cells_u32'][22]) for k in ('0x81','0x82','0x83')],[(0x1ff0,0x1fff),(0x1fc0,0),(0,0)])

    def test_survey_counts_are_conditional_constructions(self):
        s=REPORT['survey'];self.assertEqual(s['counts'],dict(complete=8512,missing_key=2752))
        self.assertEqual(sum(g['multiplicity'] for g in s['grouped_cases']),8512)
        self.assertEqual(len(s['grouped_cases']),34)
        self.assertFalse(s['physical_probabilities']);self.assertFalse(s['observed_device_values'])
        self.assertEqual([(p['key'],p['cases']) for p in s['mask_profiles']],[('0x81',4096),('0x82',4352),('0x83',64)])

    def test_every_exported_group_passes_raw_bl2_store_slices(self):
        for g in REPORT['survey']['grouped_cases']:
            off=int(g['payload_offset'],16);m8=int(g['mask8'],16);m9=int(g['mask9'],16)
            a=bridge(0x1000,off,m8,m9)
            self.assertEqual(a.get(AP_RECORD+0x64,4),int(g['core_base'],16))
            self.assertEqual((a.get(AP_RECORD+0x60,4),a.get(AP_RECORD+0x68,4)),(m8,m9))

    def test_emitted_masks_restrict_levels_in_raw_thumb_helpers(self):
        for key,m8,m9,valid8,valid9 in [('0x81',0x1ff0,0x1fff,list(range(4,13)),list(range(13))),
            ('0x82',0x1fc0,0,list(range(6,13)),[]),('0x83',0,0,[],[])]:
            a=bridge(0x1000,0x2000,m8,m9)
            for pc,delta,expected in ((0x64620,0x60,valid8),(0x6463c,0x68,valid9)):
                accepted=[]
                for value in range(32):
                    m=RawThumb(REPORT);m.r[0]=value;m.word(CORE_RECORD+delta,a.get(AP_RECORD+delta,4));m.run(pc,set())
                    if m.r[0]!=U32:accepted.append(m.r[0])
                self.assertEqual(accepted,expected,key)

    def test_loader_and_fallback_agree_with_same_descriptor14(self):
        for off in (0x1bd8,0x2114,0xffffffff):
            a=bridge(0x1000,off,1,1);fallback=a.get(AP_RECORD+0x64,4)
            m=RawThumb(REPORT);m.r[3]=0x381c8;m.r[12]=0x23c;m.word(0x3a884,off)
            m.run(0x648b0,{0x648c0});self.assertEqual(m.word(0x38404),fallback)

    def test_mutated_descriptor14_breaks_the_agreement(self):
        a=bridge(0x1000,0x1000,1,1)
        m=RawThumb(REPORT);m.r[3]=0x381c8;m.r[12]=0x23c;m.word(0x3a884,0x2000)
        m.run(0x648b0,{0x648c0})
        self.assertNotEqual(m.word(0x38404),a.get(AP_RECORD+0x64,4))

    def test_h_and_g2_read_actual_exported_a1_cells(self):
        table=next(t for t in REPORT['survey']['source_tables'] if t['key']=='0xa1')['cells_u32']
        for g in REPORT['survey']['grouped_cases']:
            a=bridge(0x1000,int(g['payload_offset'],16),1,1);base=a.get(AP_RECORD+0x64,4)
            for pc,add,key in ((0x64658,18,'h_input0_12'),(0x6467c,31,'g2_input0_12')):
                got=[]
                for value in range(13):
                    m=RawThumb(REPORT);m.r[0]=value;m.word(0x38404,0);m.word(0x3a664,base)
                    for i,v in enumerate(table):m.word(base+4*i,v)
                    m.run(pc,set());got.append(m.r[0])
                self.assertEqual(got,REPORT['survey']['table_a1'][key])

    def test_general_inputs_are_not_a_table_bounds_proof(self):
        m=RawThumb(REPORT);m.r[0]=13;m.word(0x38404,0x40000)
        with self.assertRaises(KeyError):m.run(0x6467c,set())
        self.assertFalse(REPORT['firmware_executed']);self.assertFalse(REPORT['slot47_resolved'])

if __name__=='__main__':unittest.main()
