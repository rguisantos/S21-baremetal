import itertools
import json
from pathlib import Path
import struct
import unittest
from inspect_newtime_policy_writers_hzc2 import cap_store,enable_store
from inspect_newtime_fvp_effective_hzc2 import STATE,CAP_ENABLE,RAW_MAX,DIRECTION,U32
from test_newtime_fvp_effective import raw_path

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/newtime-policy-writers-hzc2.json').read_text())
CODE={int(x['pc'],16):bytes.fromhex(x['bytes']) for x in REPORT['witnesses']}
FVP=json.loads((ROOT/'docs/references/newtime-fvp-effective-hzc2.json').read_text())
FULL_CODE={int(x['pc'],16):bytes.fromhex(x['bytes']) for x in FVP['witnesses']}


def raw_setter(kind,value,domain=0,channel=1,budget=150):
    """Bounded decoder of actual Thumb words, explicit opaque API hooks."""
    r=[0xa5a50000+i for i in range(16)];r[6]=domain;r[7]=channel;r[8]=value;r[2]=2
    r[4]=0;r[13]=0x10000000
    mem={0x1220c:0x9000,0x9008:0x9100,0x910c:0xdead0001,0x9110:0xdead0003,
         r[13]+20:value,r[13]+12:0,STATE:300,STATE+16:1000,
         CAP_ENABLE:1,RAW_MAX:300,DIRECTION:0,0x12714:300}
    stores=[];calls=[];visited=[];z=False
    def write(a,v,pc):mem[a&U32]=v&U32;stores.append((pc,a&U32,v&U32))
    def load(a):return mem[a&U32]
    def opaque(pc,target):
        if pc in (0x3f5b0,0x3f1da):
            if target!=0xdead0000:raise ValueError('unexpected allocation target')
            if r[0]!=channel:raise ValueError('unexpected channel')
            write(r[1],0,pc);r[0]=0x9200
        elif pc==0x3f1f2:
            if target!=0xdead0002:raise ValueError('unexpected publisher')
            r[0]=0x7777
        elif pc==0x3f1fe:
            if target!=0x3f040:raise ValueError('unexpected logger')
            r[0]=0x8888
        else:raise ValueError(f'unmodeled call {pc:#x} -> {target:#x}')
        calls.append((pc,target))
        for i in (1,2,3,12):r[i]=0xcccccccc
    pc=0x3f32c if kind=='cap' else 0x3f348
    for _ in range(budget):
        if pc==0x3f204:return dict(memory=mem,stores=stores,calls=calls,result=r[0],visited=visited)
        visited.append(pc);raw=CODE[pc];h=struct.unpack_from('<H',raw)[0];q=pc+len(raw)
        if len(raw)==4:
            b=struct.unpack_from('<H',raw,2)[0]
            if h&0xfbf0 in (0xf240,0xf2c0):
                d=(b>>8)&15;imm=(h&15)<<12|((h>>10)&1)<<11|((b>>12)&7)<<8|(b&255)
                r[d]=(r[d]&65535)|(imm<<16) if h&0x80 else imm
            elif h&0xf800==0xf000 and b&0xd000==0xd000:
                s=(h>>10)&1;imm=s<<24|(1^((b>>13)&1)^s)<<23|(1^((b>>11)&1)^s)<<22|(h&1023)<<12|(b&2047)<<1
                if s:imm-=1<<25
                opaque(pc,pc+4+imm)
            else:raise ValueError('unsupported wide word')
        elif h&0xf800==0x2000:d=(h>>8)&7;r[d]=h&255;z=r[d]==0
        elif h&0xf800==0x2800:z=r[(h>>8)&7]==(h&255)
        elif h&0xf800==0:
            r[h&7]=(r[(h>>3)&7]<<((h>>6)&31))&U32;z=r[h&7]==0
        elif h&0xf800==0x1800:
            operand=(h>>6)&7;b=operand if h&0x400 else r[operand]
            r[h&7]=(r[(h>>3)&7]+(-b if h&0x200 else b))&U32;z=r[h&7]==0
        elif h&0xfc00==0x4400:
            d=(h&7)|((h>>4)&8);m=(h>>3)&15;op=(h>>8)&3
            if op==0:r[d]=(r[d]+r[m])&U32
            elif op==2:r[d]=r[m]
            elif op==3:opaque(pc,r[m]&~1)
            else:raise ValueError('unsupported high ALU')
        elif h&0xfc00==0x4000:
            d=h&7;m=(h>>3)&7;op=(h>>6)&15
            if op==13:r[d]=(r[d]*r[m])&U32
            elif op==12:r[d]|=r[m]
            else:raise ValueError('unsupported low ALU')
            z=r[d]==0
        elif h&0xf000==0x6000:
            d=h&7;a=r[(h>>3)&7]+((h>>6)&31)*4
            if h&0x800:r[d]=load(a)
            else:write(a,r[d],pc)
        elif h&0xf000==0x9000:
            d=(h>>8)&7;a=r[13]+(h&255)*4
            if h&0x800:r[d]=load(a)
            else:write(a,r[d],pc)
        elif h&0xf800==0xa800:r[(h>>8)&7]=(r[13]+(h&255)*4)&U32
        elif h&0xf000==0xd000:
            cond=(h>>8)&15
            if cond not in (0,1):raise ValueError('unsupported condition')
            if z==(cond==0):q=pc+4+2*((h&255)-256 if h&128 else h&255)
        elif h&0xf800==0xe000:q=pc+4+2*((h&2047)-2048 if h&1024 else h&2047)
        else:raise ValueError(f'unsupported word {pc:#x}')
        pc=q
    raise ValueError('host budget exhausted')


class PolicyWriterTests(unittest.TestCase):
    def test_cap_value_and_two_domains_from_raw_words(self):
        for domain,value in itertools.product((0,1),(0,1,100,U32)):
            r=raw_setter('cap',value,domain)
            self.assertEqual([(p,a,v) for p,a,v in r['stores'] if p==0x3f5aa],[(0x3f5aa,cap_store(domain,value)['core'],value)])
            self.assertEqual(r['result'],0)

    def test_enable_preserves_whole_word_and_only_later_zero_test(self):
        for value in (0,1,2,0x80000000,U32):
            r=raw_setter('enable',value)
            self.assertEqual(r['memory'][CAP_ENABLE],value)
            self.assertEqual(enable_store(value),dict(core=CAP_ENABLE,value=value))
            self.assertEqual(r['result'],0)

    def test_setters_do_not_directly_select_relay_or_update_effective_cache(self):
        for kind in ('cap','enable'):
            r=raw_setter(kind,0)
            self.assertEqual([p for p,t in r['calls']],[0x3f5b0 if kind=='cap' else 0x3f1da,0x3f1f2,0x3f1fe])
            for a,v in ((STATE,300),(RAW_MAX,300),(DIRECTION,0),(0x12714,300)):
                self.assertEqual(r['memory'][a],v)
                self.assertNotIn(a,[a for _,a,_ in r['stores']])

    def test_cap_store_precedes_response_allocation(self):
        r=raw_setter('cap',100);pcs=r['visited']
        self.assertLess(pcs.index(0x3f5aa),pcs.index(0x3f5b0))

    def test_lower_cap_only_changes_effective_on_subsequent_command6_fixture(self):
        s=raw_setter('cap',100)
        self.assertEqual(s['memory'][STATE],300)
        r=raw_path(FULL_CODE,(300,0,0,s['memory'][STATE],s['memory'][STATE+16],s['memory'][CAP_ENABLE],0))
        self.assertEqual(r['memory'][STATE],100)
        self.assertEqual(r['relay_domain'],0)

    def test_disabling_cap_keeps_current_until_subsequent_request(self):
        s=raw_setter('enable',0)
        self.assertEqual(s['memory'][STATE],300)
        r=raw_path(FULL_CODE,(500,0,0,s['memory'][STATE],100,s['memory'][CAP_ENABLE],0))
        self.assertEqual(r['memory'][STATE],500)

    def test_nonzero_enable_word_applies_cap_on_subsequent_request(self):
        for value in (2,0x80000000,U32):
            s=raw_setter('enable',value)
            r=raw_path(FULL_CODE,(500,0,0,300,100,s['memory'][CAP_ENABLE],0))
            self.assertEqual(r['memory'][STATE],100)

    def test_cap_channel_guard_skips_store_for_other_channel(self):
        r=raw_setter('cap',100,channel=2)
        self.assertNotIn(0x3f5aa,r['visited'])
        self.assertEqual(r['memory'][STATE+16],1000)
        self.assertEqual(r['result'],0)

    def test_enable_selected_arm_has_no_channel1_guard(self):
        r=raw_setter('enable',2,channel=2)
        self.assertEqual(r['memory'][CAP_ENABLE],2)
        self.assertEqual(r['result'],0)

    def test_host_input_widths_and_budget_fail_closed(self):
        for bad in (-1,True,1<<32):
            with self.assertRaises(ValueError):enable_store(bad)
        with self.assertRaises(ValueError):cap_store(65536,1)
        with self.assertRaises(ValueError):raw_setter('cap',1,budget=0)

if __name__=='__main__':unittest.main()
