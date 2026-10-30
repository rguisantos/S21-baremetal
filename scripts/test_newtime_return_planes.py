import json
from pathlib import Path
import struct
import unittest
from inspect_newtime_return_planes_hzc2 import outcome
from inspect_newtime_fvp_effective_hzc2 import STATE, DIRECTION, U32
from test_newtime_fvp_effective import raw_path

ROOT=Path(__file__).resolve().parent.parent
FVP=json.loads((ROOT/'docs/references/newtime-fvp-effective-hzc2.json').read_text())
CODE={int(x['pc'],16):bytes.fromhex(x['bytes']) for x in FVP['witnesses']}


def straight(pcs, registers):
    """Raw Thumb MOVW, LSLS/MOVS and AND/OR; missing/other words fail closed."""
    r=list(registers)
    for pc in pcs:
        raw=CODE[pc];h=struct.unpack_from('<H',raw)[0]
        if len(raw)==4:
            b=struct.unpack_from('<H',raw,2)[0]
            if h&0xfbf0!=0xf240 or b&0x8000:raise ValueError('unsupported wide word')
            r[(b>>8)&15]=((h&15)<<12)|(((h>>10)&1)<<11)|(((b>>12)&7)<<8)|(b&255)
        elif h&0xf800==0:
            r[h&7]=(r[(h>>3)&7]<<((h>>6)&31))&U32
        elif h&0xfc00==0x4000:
            d=h&7;s=(h>>3)&7;op=(h>>6)&15
            if op==0:r[d]&=r[s]
            elif op==12:r[d]|=r[s]
            else:raise ValueError('unsupported ALU')
        else:raise ValueError('unsupported instruction')
    return r


class ReturnPlanesTests(unittest.TestCase):
    def test_raw_caller_keeps_full_result_and_separate_low_half(self):
        for value in (0,1,10,65535,65536,0x80000000,U32):
            r=[0]*16;r[0]=value;r[4]=0x12340000
            r=straight((0x3f2d0,0x3f2d4,0x3f2d6,0x3f2d8,0x3f1de),r)
            self.assertEqual(r[5],value)
            self.assertEqual(r[4],0x12340000|(value&65535))
            r[0]=0xdeadbeef  # opaque publication/log return must not replace carried R5
            self.assertEqual(straight((0x3f202,),r)[0],value)

    def test_raw_helper_restores_result_after_logging_clobbers_r0(self):
        r=[0]*16;r[0]=U32;r=straight((0x3f120,),r)
        r[0]=123;r=straight((0x3f160,0x3f144),r)
        self.assertEqual((r[0],r[1]),(U32,U32))

    def test_nonzero_high_half_skips_cache_even_when_constructed_word_zero(self):
        r=outcome(65536,300)
        self.assertIsNone(r['cache_write'])
        self.assertEqual((r['full_callback_return'],r['constructed_word'],r['published_word']),(65536,0,0))

    def test_zero_return_can_update_cache_with_mutated_argument(self):
        self.assertEqual(outcome(0,777)['cache_write'],dict(core=0x12714,value=777))
        self.assertFalse(outcome(0,777)['physical_success_established'])

    def test_signed_negative_index_skips_cache_on_zero_return(self):
        self.assertIsNone(outcome(0,777,index=U32)['cache_write'])

    def test_header_zero_is_a_separate_condition(self):
        self.assertFalse(outcome(10,300,header=0x10000)['bl2_exact_zero'])
        self.assertTrue(outcome(10,300)['bl2_exact_zero'])

    def test_repeated_request_after_failure_still_reaches_helper(self):
        first=raw_path(CODE,(300,0,0,200,U32,0,9))
        self.assertEqual(first['memory'][STATE],300)
        self.assertIsNone(outcome(U32,300)['cache_write'])
        # New explicit invocation, not an automatic retry; stable state between calls.
        second=raw_path(CODE,(300,0,0,first['memory'][STATE],U32,0,first['memory'][DIRECTION]))
        self.assertEqual(second['relay_domain'],0)
        self.assertEqual(second['memory'][STATE],300)
        self.assertNotIn(DIRECTION,[a for _,a,_ in second['stores']])

    def test_raw_decoder_rejects_unimplemented_instruction(self):
        with self.assertRaises(ValueError):straight((0x3f130,),[0]*16)

    def test_invalid_host_width_rejected(self):
        for x in (-1,True,1<<32):
            with self.assertRaises(ValueError):outcome(x,300)

if __name__=='__main__':unittest.main()
