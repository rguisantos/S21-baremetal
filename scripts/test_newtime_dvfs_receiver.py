import itertools
import json
from pathlib import Path
import struct
import unittest

from inspect_newtime_dvfs_receiver_hzc2 import (
    DOM,U32,broadcast_field,callback,init_first29,lookup,minlock_position,pack,regime,rmw,
)
from inspect_newtime_command6_hzc2 import response_projection
from inspect_newtime_fvp_effective_hzc2 import arbitrate

REPORT=Path(__file__).resolve().parent.parent/'docs/references/newtime-dvfs-receiver-hzc2.json'


class RawThumb:
    """Independent raw-word evaluator for short callback/init/selector slices.

    Calls are explicit opaque hooks, not emulated peripheral/plugin effects.
    Missing memory, unsupported words and the host budget fail closed.
    """
    def __init__(self,report):
        self.code={int(r['pc'],16):bytes.fromhex(r['bytes']) for r in report['witnesses']}
        self.literals={int(k,16):v for k,v in report['literals'].items()}
        self.r=[0xa5a50000+i for i in range(16)];self.mem={};self.pc=0
        self.n=self.z=self.c=self.v=False;self.visited=[];self.calls=[];self.stores=[]

    def word(self,address,value=None):
        address&=U32
        if value is None:return sum(self.mem[(address+i)&U32]<<(8*i) for i in range(4))
        for i in range(4):self.mem[(address+i)&U32]=(value>>(8*i))&255

    def nz(self,x):self.n,self.z=bool(x&(1<<31)),x==0

    def sub(self,a,b,borrow=0):
        x=(a-b-borrow)&U32;self.nz(x);self.c=a>=b+borrow
        self.v=bool((a^b)&(a^x)&(1<<31));return x

    def cond(self,c):
        n,z,k,v=self.n,self.z,self.c,self.v
        return (z,not z,k,not k,n,not n,v,not v,k and not z,not k or z,
                n==v,n!=v,not z and n==v,z or n!=v)[c]

    @staticmethod
    def signed(x,bits):return x-(1<<bits) if x&(1<<(bits-1)) else x

    def run(self,start,stops,hook=None,budget=3000):
        self.pc=start
        for _ in range(budget):
            p=self.pc
            if p in stops:return p
            self.visited.append(p);raw=self.code[p];h=struct.unpack_from('<H',raw)[0];q=p+len(raw)
            if len(raw)==4:
                b=struct.unpack_from('<H',raw,2)[0]
                if h&0xf800==0xf000 and b&0xd000==0xd000:
                    sign=(h>>10)&1
                    imm=sign<<24|(1^((b>>13)&1)^sign)<<23|(1^((b>>11)&1)^sign)<<22|(h&1023)<<12|(b&2047)<<1
                    target=p+4+self.signed(imm,25);self.calls.append((p,target,tuple(self.r[:3])))
                    if hook is None:raise ValueError('opaque call needs explicit hook')
                    hook(self,p,target)
                else:raise ValueError(f'unsupported wide word {p:#x}')
            elif h&0xf800==0x2000:
                d=(h>>8)&7;self.r[d]=h&255;self.nz(self.r[d])
            elif h&0xf800==0x2800:self.sub(self.r[(h>>8)&7],h&255)
            elif h&0xf800 in (0x3000,0x3800):
                d=(h>>8)&7
                if h&0x800:self.r[d]=self.sub(self.r[d],h&255)
                else:self.r[d]=(self.r[d]+(h&255))&U32;self.nz(self.r[d])
            elif h&0xf800 in (0,0x0800):
                d=h&7;s=(h>>3)&7;bits=(h>>6)&31
                self.r[d]=(self.r[s]<<bits)&U32 if not h&0x800 else self.r[s]>>(bits or 32)
                self.nz(self.r[d])
            elif h&0xf800==0x1800:
                d=h&7;a=self.r[(h>>3)&7];b=(h>>6)&7;b=b if h&0x400 else self.r[b]
                self.r[d]=self.sub(a,b) if h&0x200 else (a+b)&U32;self.nz(self.r[d])
            elif h&0xfc00==0x4400:
                d=(h&7)|((h>>4)&8);s=(h>>3)&15;op=(h>>8)&3
                if op==0:self.r[d]=(self.r[d]+self.r[s])&U32
                elif op==1:self.sub(self.r[d],self.r[s])
                elif op==2:self.r[d]=self.r[s]
                else:
                    target=self.r[s]&~1
                    self.calls.append((p,target,tuple(self.r[:3])))
                    if hook is None:raise ValueError('opaque indirect call needs hook')
                    hook(self,p,target)
            elif h&0xfc00==0x4000:
                d=h&7;s=(h>>3)&7;op=(h>>6)&15
                if op==0:self.r[d]&=self.r[s];self.nz(self.r[d])
                elif op==2:
                    shift=self.r[s]&255
                    self.r[d]=(self.r[d]<<shift)&U32 if shift<32 else 0;self.nz(self.r[d])
                elif op==6:self.r[d]=self.sub(self.r[d],self.r[s],int(not self.c))
                elif op==9:self.r[d]=self.sub(0,self.r[s])
                elif op==10:self.sub(self.r[d],self.r[s])
                elif op==12:self.r[d]|=self.r[s];self.nz(self.r[d])
                elif op==15:self.r[d]=U32^self.r[s];self.nz(self.r[d])
                else:raise ValueError(f'unsupported ALU {op}')
            elif h&0xf800==0x4800:
                self.r[(h>>8)&7]=self.literals[((p+4)&~3)+(h&255)*4]
            elif h&0xe000==0x6000:
                d=h&7;a=self.r[(h>>3)&7];byte=bool(h&0x1000)
                a=(a+((h>>6)&31)*(1 if byte else 4))&U32
                if h&0x800:self.r[d]=self.mem[a] if byte else self.word(a)
                else:
                    if byte:self.mem[a]=self.r[d]&255
                    else:self.word(a,self.r[d])
                    self.stores.append((p,a,self.r[d]&(255 if byte else U32)))
            elif h&0xf800==0x9800:self.r[(h>>8)&7]=self.word(self.r[13]+(h&255)*4)
            elif h&0xf500==0xb100:
                if (self.r[h&7]!=0)==bool(h&0x800):q=p+4+((h>>9)&1)*64+((h>>3)&31)*2
            elif h&0xf000==0xd000 and (h>>8)&15<14:
                if self.cond((h>>8)&15):q=p+4+2*self.signed(h&255,8)
            elif h&0xf800==0xe000:q=p+4+2*self.signed(h&2047,11)
            else:raise ValueError(f'unsupported word {h:#x} at {p:#x}')
            self.pc=q
        raise ValueError('host slice budget exhausted')


class ModelTests(unittest.TestCase):
    def test_first_failure_does_not_select_an_abort(self):
        r=callback(300,200,100,first_result=U32,final_result=0)
        self.assertEqual(r['calls'],[(300,200),(200,100)])
        self.assertEqual(r['return_value'],0)

    def test_boundary_is_reloaded_not_assumed_preserved(self):
        self.assertEqual(callback(300,200,100,b_after_first=250)['calls'],[(300,200),(250,100)])

    def test_strict_boundary_and_both_directions(self):
        self.assertEqual(len(callback(100,200,300)['calls']),2)
        for a,b,v in [(100,100,300),(100,300,300),(100,400,300)]:
            self.assertEqual(callback(a,b,v)['calls'],[(a,v)])

    def test_unsigned_callback_values(self):
        self.assertEqual(len(callback(0,0x80000000,U32)['calls']),2)

    def test_lookup_low24_and_full_input(self):
        self.assertEqual(lookup(500,[0xff0003e8,0x800001f4]),1)
        self.assertEqual(lookup(0x10000000,[1000,500]),0)

    def test_lookup_empty_and_lower_clamp(self):
        self.assertEqual(lookup(1,[]),-1)
        self.assertEqual(lookup(1,[1000,500]),1)

    def test_from_above_threshold_does_not_reject(self):
        self.assertFalse(regime(2000,500,1000,0)['threshold_is_rejection'])
        self.assertEqual(regime(2000,500,1000,0)['selector'],1)

    def test_target_above_threshold_selects2_or3(self):
        self.assertEqual(regime(500,2000,1000,0)['selector'],2)
        self.assertEqual(regime(500,2000,1000,1<<31)['selector'],3)

    def test_pack_preserves_low8_and_truncates_target(self):
        self.assertEqual(pack(0x123456ab,0x12345678),0x345678ab)

    def test_init_advances_source52_and_domain48(self):
        rows=init_first29(0x38e00,list(range(29)),[0xab]*29)
        self.assertEqual(rows[1],dict(sub=0x38e34,packed=0x1ab))
        self.assertEqual(rows[28]['sub'],0x38e00+28*52)

    def test_file_zero_does_not_force_host_live_current_to_zero(self):
        self.assertEqual(init_first29(0x38e00,[3172000]*29,[0]*29)[0]['packed']>>8,3172000)

    def test_rmw_same_write_different_poll_gate(self):
        a=rmw(0,0x10000001,1<<31);b=rmw(0,0x50000001,1<<31)
        self.assertEqual(a['written'],b['written'])
        self.assertFalse(a['poll_entered']);self.assertTrue(b['poll_entered'])

    def test_rmw_status31_gate_and_status29_exit(self):
        self.assertFalse(rmw(U32,2,0)['poll_entered'])
        self.assertTrue(rmw(U32,2,1<<31)['poll_entered'])
        self.assertEqual(rmw(U32,2,0)['written'],0xcffffffe)

    def test_actual_reply_projection_removes_internal10(self):
        self.assertEqual(response_projection(0,10)['constructed'],10)
        self.assertEqual(response_projection(0,10)['published'],0)

    def test_final_broadcast_f1_mask_also_clears_bit24(self):
        self.assertEqual(broadcast_field(U32,0xf1,0xf0),0xfeffffff)

    def test_FVP_effective_value_is_the_receiver_input(self):
        e=arbitrate(3172000,0,0,0,2730000,1,0)['effective']
        self.assertEqual(e,2730000)
        self.assertEqual(callback(1000000,2288000,e)['calls'],[(1000000,2288000),(2288000,2730000)])

    def test_invalid_host_widths_are_refused(self):
        for v in (-1,True,1<<32):
            with self.assertRaises(ValueError):pack(0,v)


class RawSliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=json.loads(REPORT.read_text())

    def callback_run(self,a,b,value,first,final,after=None):
        m=RawThumb(self.report);m.r[4]=value;m.r[5]=DOM
        m.word(DOM+32,pack(0,a));m.word(0x2f248,b)
        def hook(cpu,pc,target):
            self.assertEqual(target,0x5944c)
            if pc==0x59906:
                cpu.r[0]=first
                if after is not None:cpu.word(0x2f248,after)
            else:self.assertEqual(pc,0x59916);cpu.r[0]=final
            for reg in (1,2,3,12):cpu.r[reg]=0xaabbccdd
        m.run(0x598e2,{0x5991a},hook)
        self.assertEqual(m.r[0],final)
        return m

    def test216_raw_callback_combinations(self):
        for a,b,v in itertools.product(range(6),repeat=3):
            m=self.callback_run(a,b,v,U32,0)
            self.assertEqual([row[2][:2] for row in m.calls],callback(a,b,v,U32,0)['calls'])

    def test_raw_callback_failure_is_overwritten_by_final_success(self):
        m=self.callback_run(300,200,100,U32,0)
        self.assertEqual([x[0] for x in m.calls],[0x59906,0x59916])

    def test_raw_callback_second_failure_is_returned(self):
        self.callback_run(100,200,300,0,U32)

    def test_raw_callback_reads_modified_boundary_after_first_call(self):
        m=self.callback_run(300,200,100,U32,0,250)
        self.assertEqual(m.calls[-1][2][:2],(250,100))

    def test_raw29_row_init_uses_live_words_and_advancing_source(self):
        m=RawThumb(self.report);m.r[4]=0x38e00
        values=[(i+1)*421000 for i in range(29)];old=[0xa5]*29
        for i,v in enumerate(values):
            m.word(0x38e00+i*52+24,v)
            for off,val in [(0,0),(4,0),(32,old[i])]:m.word(DOM+i*48+off,val)
        m.run(0x56f0c,{0x56f4a})
        expected=init_first29(0x38e00,values,old)
        for i,e in enumerate(expected):
            self.assertEqual(m.word(DOM+i*48+12),e['sub'])
            self.assertEqual(m.word(DOM+i*48+32),e['packed'])

    def test_raw_threshold_branches_route_without_error_exit(self):
        for a,v,status in itertools.product((500,2000),(500,2000),(0,1<<31)):
            m=RawThumb(self.report);m.r[13]=0x10000000;m.r[4]=v
            m.word(m.r[13]+52,a);m.word(0x2f230,1000);m.word(0xac00010c,status)
            stop=m.run(0x5960e,{0x5961e,0x596b4})
            if a<=1000 and v<=1000:self.assertEqual(stop,0x5961e)
            else:
                self.assertEqual(stop,0x596b4)
                self.assertEqual(m.r[7],regime(a,v,1000,status)['selector'])

    def test_raw_handler_post_minlock_does_not_replace_dispatch_result(self):
        for cur,v,result in [(300,100,U32),(100,300,0),(100,100,123)]:
            m=RawThumb(self.report);m.r[0]=0;m.r[1]=v
            m.word(DOM+32,pack(0,cur));m.word(DOM+40,0x2c0dd)
            def hook(cpu,pc,target):
                cpu.r[0]=result if pc==0x59c18 else 0x12345678
                for r in (1,2,3,12):cpu.r[r]=0xaabbccdd
            m.run(0x59bea,{0x59c54},hook)
            self.assertEqual(m.r[0],result)
            minlock=[p for p,t,args in m.calls if t==0x59a90]
            self.assertEqual(minlock,[0x59c02 if minlock_position(cur,v)=='pre' else 0x59c4e])

    def test_raw_broadcast_excludes_upper_bound_and_clears_bit24(self):
        m=RawThumb(self.report);m.r[0]=24;m.r[1]=0xf1;m.r[2]=0xf0
        addresses=list(range(0xac000800,0xac400800,0x100000))
        for address in addresses:m.word(address,U32)
        m.run(0x587a6,{0x587c8})
        self.assertEqual([a for p,a,v in m.stores],addresses)
        self.assertEqual(len(m.stores),4)
        self.assertEqual({m.word(a) for a in addresses},{0xfeffffff})

    def test_raw_interpreter_refuses_missing_memory_and_unknown_opcode(self):
        m=RawThumb(self.report)
        with self.assertRaises(KeyError):m.run(0x598e2,{0x5991a})
        m=RawThumb(self.report);m.code[0x598e2]=bytes.fromhex('00de')
        with self.assertRaises(ValueError):m.run(0x598e2,{0x5991a})

    def test_host_budget_is_not_a_firmware_timeout(self):
        with self.assertRaises(ValueError):RawThumb(self.report).run(0x598e2,{0x5991a},budget=0)

    def test_report_does_not_claim_hardware_or_slot47_resolution(self):
        self.assertFalse(self.report['firmware_executed'])
        self.assertFalse(self.report['slot47_resolved'])
        self.assertFalse(self.report['init']['file_current0_is_runtime_observation'])
        self.assertFalse(self.report['transition']['threshold_rejects'])


if __name__=='__main__':unittest.main()
