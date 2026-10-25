import unittest
from inspect_newtime_smc_binding_hzc2 import sfr_write_candidate


class SFRConventionTests(unittest.TestCase):
    def test_known_identifiers(self):
        self.assertEqual(sfr_write_candidate(0x468d0100),0x1a340400)
        self.assertEqual(sfr_write_candidate(0x468d012d),0x1a3404b4)

    def test_boundary_and_round_trip(self):
        for address in (0,4,0x1a340404,0xfffffffc):
            self.assertEqual(sfr_write_candidate(0x40000000 | (address>>2)),address)

    def test_reject_other_classes_and_non_u32(self):
        for value in (0,0x80000000,0xc68d0100,-1,0x1468d0100,True,1.0,'0x468d0100'):
            with self.subTest(value=value),self.assertRaises(ValueError):sfr_write_candidate(value)


if __name__=='__main__':unittest.main()
