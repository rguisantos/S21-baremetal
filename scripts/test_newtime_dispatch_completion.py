import itertools
import json
from pathlib import Path
import random
import unittest
from inspect_newtime_dispatch_completion_hzc2 import next_index,U32
from test_newtime_dvfs_receiver import RawThumb

REPORT=Path(__file__).resolve().parent.parent/'docs/references/newtime-dispatch-completion-hzc2.json'

class DispatchCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=json.loads(REPORT.read_text())

    def run_index(self,old,count,result=0):
        m=RawThumb(self.report);m.r[9]=old;m.r[4]=0x1000;m.r[13]=0x8000;m.r[0]=result
        m.word(0x8000+4,result);m.word(0x8000+16,1)
        m.word(0x1008,0x2000);m.word(0x2000+72+52,count)
        m.word(0x2000+72+16,0x3000);m.word(0x3000,old)
        m.run(0x392e0,{0x39300})
        self.assertEqual(m.stores,[(0x392fe,0x3000,next_index(old,count))])
        self.assertEqual(m.word(0x8004),result)
        return m

    def test_valid_ring_indices_match_independent_modulo(self):
        for count in range(1,33):
            for old in range(count):
                m=self.run_index(old,count)
                self.assertEqual(m.word(0x3000),(old+1)%count)

    def test_result_does_not_change_selected_index_update(self):
        for result,old in itertools.product((0,1,10,65536,0x80000000,U32),range(3)):
            self.assertEqual(self.run_index(old,3,result).word(0x3000),(old+1)%3)

    def test_invalid_index_is_not_modulo_normalized(self):
        self.assertEqual(self.run_index(5,3).word(0x3000),6)
        self.assertNotEqual(next_index(5,3),(5+1)%3)

    def test_count_is_live_not_hardcoded_three(self):
        self.assertEqual(self.run_index(2,3).word(0x3000),0)
        self.assertEqual(self.run_index(2,4).word(0x3000),3)

    def test_u32_wrap_and_zero_count_are_arithmetic_not_validated_configuration(self):
        for count in (0,1,3,U32):self.assertEqual(self.run_index(U32,count).word(0x3000),0)
        self.assertEqual(self.run_index(0,0).word(0x3000),1)

    def test_256_random_raw_sequences_match_model(self):
        rng=random.Random(0x392fe)
        for _ in range(256):self.run_index(rng.getrandbits(32),rng.getrandbits(32),rng.getrandbits(32))

    def test_selected_empty_exit_overwrites_error_with_zero(self):
        for result in (0,65536,U32):
            m=RawThumb(self.report);m.r[0]=result;m.run(0x39312,{0x39314})
            self.assertEqual(m.r[0],0)

    def test_host_width_validation(self):
        for bad in (-1,True,1<<32):
            with self.assertRaises(ValueError):next_index(bad,3)

    def test_missing_memory_and_budget_refuse(self):
        with self.assertRaises(KeyError):RawThumb(self.report).run(0x392e0,{0x39300})
        with self.assertRaises(ValueError):RawThumb(self.report).run(0x392e0,{0x39300},budget=0)

if __name__=='__main__':unittest.main()
