import itertools
import json
from pathlib import Path
import random
import struct
import unittest

from inspect_newtime_fvp_effective_hzc2 import (
    arbitrate, returned_cache, STATE, CAP_ENABLE, RAW_MAX, DIRECTION, POLICY_ENABLE, U32,
)

REPORT=Path(__file__).resolve().parent.parent/'docs/references/newtime-fvp-effective-hzc2.json'


def raw_path(code,args,policy=0,budget=200):
    """Independent, bounded raw Thumb word interpreter; no GNU text semantics.

    Only the selected pre-relay arithmetic path; uninitialized memory, missing
    code and unsupported encodings fail. It neither executes Samsung firmware
    nor models logging/relay calls. Host budget is not a firmware timeout.
    """
    request,b,c,old,cap,enabled,direction=args
    regs=[0xa5a50000+i for i in range(16)];regs[8]=0;regs[13]=0x10000000
    memory={STATE:old,STATE+4:0xdeadbeef,STATE+8:b,STATE+12:c,STATE+16:cap,
            CAP_ENABLE:enabled,RAW_MAX:0xcafe,DIRECTION:direction,POLICY_ENABLE:policy,
            regs[13]+20:request,regs[13]+24:6}
    stores=[];visited=[];flags=dict(n=False,z=False,c=False,v=False)

    def nz(value):flags.update(n=bool(value>>31),z=value==0)
    def arithmetic(a,b,subtract=False):
        full=a-b if subtract else a+b;result=full&U32
        nz(result);flags['c']=a>=b if subtract else full>U32
        flags['v']=bool(((a^b) if subtract else ~(a^b)) & (a^result) & (1<<31))
        return result
    def branch(cond):
        n,z,c,v=(flags[k] for k in ('n','z','c','v'))
        return (z,not z,c,not c,n,not n,v,not v,c and not z,not c or z,
                n==v,n!=v,not z and n==v,z or n!=v)[cond]
    def load(address):return memory[address&U32]
    def store(address,value,pc):
        address&=U32;memory[address]=value&U32;stores.append((pc,address,value&U32))
    def signed(value,bits):return value-(1<<bits) if value&(1<<(bits-1)) else value

    pc=0x3f6a4
    for _ in range(budget):
        if pc==0x3f2cc:
            return dict(memory=memory,stores=stores,visited=visited,relay_domain=regs[0])
        visited.append(pc);raw=code[pc];h=struct.unpack_from('<H',raw)[0];next_pc=pc+len(raw)
        if len(raw)==4:
            # MOVW/T AArch32 T3, immediate i:imm4:imm3:imm8.
            hi=struct.unpack_from('<H',raw,2)[0]
            if h&0xfbf0 not in (0xf240,0xf2c0) or hi&0x8000:
                raise ValueError(f'unsupported wide word at {pc:#x}')
            rd=(hi>>8)&15
            imm=((h&15)<<12)|(((h>>10)&1)<<11)|(((hi>>12)&7)<<8)|(hi&255)
            regs[rd]=(regs[rd]&65535)|(imm<<16) if h&0x80 else imm
        elif h&0xf800==0x2000:
            rd=(h>>8)&7;regs[rd]=h&255;nz(regs[rd])
        elif h&0xf800==0x2800:
            arithmetic(regs[(h>>8)&7],h&255,True)
        elif h&0xf800 in (0x3000,0x3800):
            rd=(h>>8)&7;regs[rd]=arithmetic(regs[rd],h&255,bool(h&0x800))
        elif h&0xf800==0x0000:
            rd=h&7;rm=(h>>3)&7;shift=(h>>6)&31
            regs[rd]=(regs[rm]<<shift)&U32;nz(regs[rd])
        elif h&0xf800==0x1800:
            rd=h&7;rn=(h>>3)&7;operand=(h>>6)&7
            rhs=operand if h&0x400 else regs[operand]
            regs[rd]=arithmetic(regs[rn],rhs,bool(h&0x200))
        elif h&0xfc00==0x4400:
            rd=(h&7)|((h>>4)&8);rm=(h>>3)&15;op=(h>>8)&3
            if op==0:regs[rd]=(regs[rd]+regs[rm])&U32
            elif op==2:regs[rd]=regs[rm]
            elif op==1:arithmetic(regs[rd],regs[rm],True)
            else:raise ValueError('unmodeled high-register branch')
        elif h&0xfc00==0x4000:
            rd=h&7;rm=(h>>3)&7;op=(h>>6)&15
            if op==10:arithmetic(regs[rd],regs[rm],True)
            elif op==13:regs[rd]=(regs[rd]*regs[rm])&U32;nz(regs[rd])
            else:raise ValueError(f'unsupported low-register ALU {op}')
        elif h&0xf000==0x6000:
            rt=h&7;rn=(h>>3)&7;address=(regs[rn]+((h>>6)&31)*4)&U32
            if h&0x800:regs[rt]=load(address)
            else:store(address,regs[rt],pc)
        elif h&0xfe00 in (0x5000,0x5800):
            rt=h&7;rn=(h>>3)&7;rm=(h>>6)&7;address=(regs[rn]+regs[rm])&U32
            if h&0x800:regs[rt]=load(address)
            else:store(address,regs[rt],pc)
        elif h&0xf000==0x9000:
            rt=(h>>8)&7;address=(regs[13]+(h&255)*4)&U32
            if h&0x800:regs[rt]=load(address)
            else:store(address,regs[rt],pc)
        elif h&0xf500==0xb100:
            if (regs[h&7]!=0)==bool(h&0x800):
                next_pc=pc+4+((h>>9)&1)*64+((h>>3)&31)*2
        elif h&0xf000==0xd000 and (h>>8)&15<14:
            if branch((h>>8)&15):next_pc=pc+4+2*signed(h&255,8)
        elif h&0xf800==0xe000:
            next_pc=pc+4+2*signed(h&2047,11)
        else:raise ValueError(f'unsupported Thumb word {h:#x} at {pc:#x}')
        pc=next_pc
    raise ValueError('host path budget exhausted')


class FormulaTests(unittest.TestCase):
    def test_selected_request_with_other_votes_zero(self):
        self.assertEqual(arbitrate(3172000,0,0,0,U32,1,9)['effective'],3172000)

    def test_both_competing_fields_participate(self):
        self.assertEqual(arbitrate(100,200,300,0,U32,1,0)['effective'],300)

    def test_unsigned_not_signed_max(self):
        self.assertEqual(arbitrate(1,0x80000000,U32,0,U32,1,0)['effective'],U32)

    def test_cap_is_conditional_on_nonzero_enable(self):
        self.assertEqual(arbitrate(300,0,0,0,100,0,0)['effective'],300)
        self.assertEqual(arbitrate(300,0,0,0,100,0x80000000,0)['effective'],100)

    def test_enabled_zero_cap_is_a_real_zero_result(self):
        self.assertEqual(arbitrate(300,0,0,0,0,1,0)['effective'],0)

    def test_mirror_is_uncapped_candidate(self):
        p=arbitrate(300,0,0,200,100,1,9)
        self.assertEqual((p['raw_max_cell'],p['effective']),(300,100))

    def test_direction_is_computed_before_cap_even_if_final_value_falls(self):
        p=arbitrate(300,0,0,200,100,1,9)
        self.assertEqual(p['direction_after'],0)

    def test_equal_uncapped_candidate_does_not_update_direction(self):
        p=arbitrate(300,0,0,300,100,1,9)
        self.assertEqual(p['direction_after'],9)
        self.assertFalse(p['direction_written'])
        self.assertEqual(p['effective'],100)

    def test_equal_final_value_still_selects_helper(self):
        p=arbitrate(200,0,0,100,100,1,9)
        self.assertEqual(p['effective'],100)
        self.assertTrue(p['helper_call_selected'])

    def test_direction_fall_and_zero_candidate(self):
        self.assertEqual(arbitrate(0,0,0,100,0,0,9)['direction_after'],1)

    def test_unknown_direction_is_preserved_on_equal_candidate(self):
        self.assertEqual(arbitrate(0,0,0,0,U32,1,U32)['direction_after'],U32)

    def test_host_fixture_refuses_wrong_widths_and_bool(self):
        for bad in (-1,True,1<<32):
            with self.assertRaises(ValueError):arbitrate(bad,0,0,0,0,0,0)


class ReturnTests(unittest.TestCase):
    def test_initial_domain0_index5_cache_slot(self):
        self.assertEqual(returned_cache(5,0,123),dict(core=0x12714,value=123))

    def test_nonzero_full_result_skips_cache(self):
        for result in (1,0x10000,0x80000000,U32):self.assertIsNone(returned_cache(5,result,123))

    def test_negative_signed_index_skips_cache(self):
        self.assertIsNone(returned_cache(U32,0,123))

    def test_reloaded_frame_value_can_differ_from_pre_call_effective(self):
        self.assertEqual(returned_cache(5,0,456)['value'],456)

    def test_cache_address_arithmetic_is_W32(self):
        self.assertEqual(returned_cache(0x40000000,0,0)['core'],0x12700)


class RawWordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads(REPORT.read_text())
        cls.code={int(row['pc'],16):bytes.fromhex(row['bytes']) for row in cls.report['witnesses']}

    def check_path(self,args,policy=0):
        run=raw_path(self.code,args,policy)
        expected=arbitrate(*args);m=run['memory']
        self.assertEqual((m[STATE+4],m[STATE],m[RAW_MAX],m[DIRECTION]),
                         (args[0],expected['effective'],expected['uncapped'],expected['direction_after']))
        self.assertEqual(run['relay_domain'],0)
        self.assertNotIn(0x3f298,run['visited'])  # command6 skips the R0==1 auxiliary arm
        return run

    def test_all4096_boundary_combinations_against_raw_Thumb_words(self):
        values=(0,1,0x80000000,U32)
        for r,b,c,old,cap in itertools.product(values,repeat=5):
            for enable,policy in itertools.product((0,1),repeat=2):
                self.check_path((r,b,c,old,cap,enable,9),policy)

    def test512_deterministic_random_cases_against_raw_words(self):
        rng=random.Random(0x3f6a4)
        for _ in range(512):self.check_path(tuple(rng.getrandbits(32) for _ in range(7)),1)

    def test_cap_store_occurs_after_direction_store(self):
        run=self.check_path((300,0,0,200,100,1,9))
        stores=run['stores'];direction=next(i for i,x in enumerate(stores) if x[1]==DIRECTION)
        cap=next(i for i,x in enumerate(stores) if x[0]==0x3f53a)
        self.assertLess(direction,cap)

    def test_unchanged_candidate_still_takes_cap_store_and_helper(self):
        run=self.check_path((300,0,0,300,100,1,9))
        self.assertIn(0x3f53a,run['visited'])
        self.assertFalse(any(address==DIRECTION for _,address,_ in run['stores']))

    def test_unchanged_and_uncapped_still_reaches_relay_call_site(self):
        self.check_path((300,0,0,300,U32,1,9),1)

    def test_competing8_above_request_still_skips_auxiliary_lookup_for_command6(self):
        run=self.check_path((100,300,0,0,U32,1,9),1)
        self.assertIn(0x3f28c,run['visited'])
        self.assertEqual(run['relay_domain'],0)

    def test_all_zero_mirror_is_written_by_clear_only(self):
        run=self.check_path((0,0,0,0,0,0,9))
        self.assertEqual([x[0] for x in run['stores'] if x[1]==RAW_MAX],[0x3f4be])

    def test_unsupported_raw_instruction_is_not_treated_as_noop(self):
        code=dict(self.code);code[0x3f6a4]=bytes.fromhex('00de')
        with self.assertRaises(ValueError):raw_path(code,(0,0,0,0,0,0,0))

    def test_host_budget_is_explicit_not_firmware_timeout(self):
        with self.assertRaises(ValueError):raw_path(self.code,(0,0,0,0,0,0,0),budget=1)

    def test_initial_file_and_initializer_are_separate_evidence(self):
        self.assertEqual(self.report['fields']['initial_file_words'],[0,0,0,0,0])
        self.assertEqual(self.report['fields']['initial_cap_enable'],1)
        self.assertFalse(self.report['fields']['file_initial_is_runtime_observation'])

    def test_no_runtime_success_or_slot47_resolution_claimed(self):
        self.assertFalse(self.report['firmware_executed'])
        self.assertFalse(self.report['physical_device_tested'])
        self.assertFalse(self.report['slot47_caller_resolved'])
        self.assertFalse(self.report['relay']['rollback_in_selected_error_path'])


if __name__=='__main__':unittest.main()
