import itertools
import json
from pathlib import Path
import random
import struct
import unittest
from inspect_newtime_dmc_config_hzc2 import BASE,DIRECTORY,CACHE,U32,target,packet_fields
from test_newtime_dmc_method12 import RawThumb

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/newtime-dmc-config-hzc2.json').read_text())


def machine():return RawThumb(REPORT)


def writer(offset,stride,column,row,mode,value,descriptor=0,budget=3000):
    m=machine();m.r[0:4]=[descriptor,column,row,mode];m.r[13]=0x10000
    m.word(0x10000,value);d=(DIRECTORY+16*descriptor)&U32
    m.word(d+4,offset);m.word(d+8,stride)
    m.run(0x64c68,set(),budget=budget)
    return m


class DmcConfigTests(unittest.TestCase):
    def test_single_row_addresses_match_actual_words(self):
        for offset,stride,col,row in itertools.product((0,0x1000),(1,13),(0,3),(0,12,255)):
            m=writer(offset,stride,col,row,0,0x1234)
            stores=[(a,v) for pc,a,v in m.stores if pc==0x64c94]
            self.assertEqual(stores,[(target(offset,stride,col,row),0x1234)])
            self.assertEqual(m.r[0],0x1234);self.assertEqual(m.r[13],0x10000)

    def test_mode1_writes_thirteen_inclusive_rows(self):
        m=writer(0x1000,11,3,255,1,0xabcd)
        self.assertEqual([(a,v) for pc,a,v in m.stores if pc==0x64c94],
                         [(target(0x1000,11,3,i),0xabcd) for i in range(13)])

    def test_other_modes_do_not_mean_all_rows(self):
        for mode in (0,2,255,U32):
            m=writer(0x1000,3,2,5,mode,17)
            self.assertEqual(len([pc for pc,a,v in m.stores if pc==0x64c94]),1)

    def test_byte_fields_extracted_by_handler(self):
        p=struct.pack('<IIII',20|(0x1234<<16),0x07060504,0xdeadbeef,0)
        self.assertEqual(packet_fields(p),dict(command=20,descriptor=7,column=6,row=5,mode=4,value=0xdeadbeef))
        m=machine();m.r[1]=0x20000;m.r[13]=0x10000
        for i,b in enumerate(p):m.mem[0x20000+i]=b
        args=[]
        def hook(sim,pc,to):
            self.assertEqual(to,0x60148)
            args.append(tuple(sim.r[:4])+(sim.word(sim.r[13]),));sim.r[0]=0x77
        m.run(0x5fd38,{0x5fd74},hook)
        self.assertEqual(args,[(7,6,5,4,0xdeadbeef)])
        self.assertEqual(m.word(0x2000c),0x77)

    def test_normal_method0_command20_dispatch(self):
        m=machine();m.r[0]=0x1000;m.r[1]=1;m.r[13]=0x10000
        m.word(0x1000,0x2000);m.word(0x2000,0x12340014)
        m.word(0x37d3c,0);m.word(0x37cd0+20*4,0x32539)
        seen=[]
        def hook(sim,pc,to):seen.append((pc,to,sim.r[0],sim.r[1]));sim.r[0]=0x1234
        m.run(0x5ff14,{0x5ff98},hook)
        self.assertEqual(seen,[(0x5ff4a,0x32538,0,0x2000)])
        self.assertEqual(m.word(m.r[7]+44),0x1234)

    def test_busy_gate_bypasses_command_dispatch(self):
        m=machine();m.r[0]=0x1000;m.r[13]=0x10000
        m.word(0x1000,0x2000);m.word(0x2000,20);m.word(0x37d3c,1)
        m.run(0x5ff14,{0x5ff54})
        self.assertEqual(m.calls,[])

    def test_handler_wrapper_writer_chain_with_opaque_finalize(self):
        m=machine();m.r[1]=0x20000;m.r[13]=0x10000
        packet=struct.pack('<IIII',20,0x02030400,0xcafe1234,0)
        for i,b in enumerate(packet):m.mem[0x20000+i]=b
        # Descriptor 2, column3, row4, mode0; the receive path remains a fixture.
        d=DIRECTORY+2*16;m.word(d+4,0x1000);m.word(d+8,13)
        m.word(0x38038+104,0x37469);calls=[]
        def hook(sim,pc,to):
            calls.append((pc,to))
            if to==0x60148:sim.run(0x60148,set(),hook)
            elif to==0x37468:sim.run(0x64c68,set(),hook)
            elif to==0x5f8dc:
                for r in (0,1,2,3,12):sim.r[r]=0xcccccccc
            else:raise ValueError(hex(to))
        m.run(0x5fd38,set(),hook)
        self.assertEqual([(a,v) for pc,a,v in m.stores if pc==0x64c94],[(target(0x1000,13,3,4),0xcafe1234)])
        self.assertEqual(m.word(0x2000c),0xcafe1234)
        self.assertEqual(m.r[0],0);self.assertEqual(m.r[13],0x10000)
        self.assertEqual([pc for pc,to in calls],[0x5fd6a,0x60152,0x5fd74])

    def test_conditional_aliases_to_masks_and_base(self):
        for off in (0x60,0x64,0x68):
            m=writer(off,13,0,0,0,0x55aa)
            self.assertEqual([(a,v) for pc,a,v in m.stores if pc==0x64c94],[(BASE+off,0x55aa)])
        # These are explicit synthetic descriptor values, not captured firmware RAM.

    def test_stride_is_reloaded_after_aliasing_store(self):
        m=writer(DIRECTORY+8-BASE,3,0,0,1,0)
        addresses=[a for pc,a,v in m.stores if pc==0x64c94]
        self.assertEqual(addresses,[DIRECTORY+8]*13)

    def test_base_offset_is_captured_once(self):
        m=writer(DIRECTORY+4-BASE,16,0,0,1,0)
        self.assertEqual([a for pc,a,v in m.stores if pc==0x64c94],
                         [DIRECTORY+4+64*i for i in range(13)])

    def test_u32_arithmetic_randomized(self):
        rng=random.Random(2100)
        for _ in range(80):
            off=rng.getrandbits(32);stride=rng.getrandbits(32);col=rng.randrange(256);row=rng.randrange(256)
            a=target(off,stride,col,row)
            if a in range(DIRECTORY,DIRECTORY+16):continue
            m=writer(off,stride,col,row,0,0x1111)
            self.assertEqual([a for pc,a,v in m.stores if pc==0x64c94],[a])

    def test_missing_directory_and_target_fail_closed(self):
        m=machine();m.r[0:4]=[0,0,0,0];m.r[13]=0x10000;m.word(0x10000,17)
        with self.assertRaises(KeyError):m.run(0x64c68,set())
        with self.assertRaises(ValueError):target(-1,1,0,0)
        with self.assertRaises(ValueError):packet_fields(b'')

    def test_direct_helper_signed_wrap_can_exhaust_host_budget(self):
        with self.assertRaisesRegex(ValueError,'host slice budget'):
            writer(0x1000,0,0,0x7fffffff,0,1,budget=200)
        # Packet-supplied row is u8; this checks the helper, not packet reachability.

    def test_cache_header_fallback_only_when_zero(self):
        for pc,delta in ((0x64658,18),(0x6467c,31)):
            m=machine();m.r[0]=2;m.word(CACHE,0);m.word(0x3a664,0x40000)
            m.word(0x40000+8*(2+delta)+4,0xbeef)
            m.run(pc,set())
            self.assertEqual(m.r[0],0xbeef);self.assertEqual(m.word(CACHE),0x40000)
            self.assertTrue(any(a==0x3a664 for pc,a,w in m.reads))

    def test_loader_cache_bypasses_header_and_is_shared_by_h_g2(self):
        m=machine();m.r[3]=0x381c8;m.r[12]=0x23c
        m.word(0x3a884,0x2000)
        m.run(0x648b0,{0x648c0})
        self.assertEqual(m.word(CACHE),BASE+0x2000)
        for pc,delta,result in ((0x64658,18,42),(0x6467c,31,99)):
            m.r[0]=2;m.word(BASE+0x2000+8*(2+delta)+4,result)
            m.run(pc,set());self.assertEqual(m.r[0],result)
        self.assertFalse(any(a==0x3a664 for pc,a,w in m.reads))

    def test_missing_cache_fallback_does_not_invent_a_pointer(self):
        m=machine();m.r[0]=0;m.word(CACHE,0)
        with self.assertRaises(KeyError):m.run(0x64658,set())

if __name__=='__main__':unittest.main()
