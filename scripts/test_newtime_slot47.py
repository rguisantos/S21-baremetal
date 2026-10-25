import unittest
from inspect_newtime_slot47_hzc2 import load_offsets


class LoadEncodingTests(unittest.TestCase):
    def test_unsigned_x_load_scales_by_eight(self):
        self.assertEqual(load_offsets(0xf940bc02),[376])
        self.assertEqual(load_offsets(0xf9400000),[0])

    def test_pair_second_word_and_signed_offset(self):
        self.assertEqual(load_offsets(0xa9400000|(46<<15)),[368,376])
        self.assertEqual(load_offsets(0xa9400000|(127<<15)),[-8,0])

    def test_other_width_store_and_writeback_excluded(self):
        for word in (0xb940bc02,0xf900bc02,0xa9c00000,0xa8c00000):
            with self.subTest(word=word):self.assertEqual(load_offsets(word),[])

    def test_reject_non_u32(self):
        for value in (-1,1<<32,True,'0xf9400000',1.0):
            with self.subTest(value=value),self.assertRaises(ValueError):load_offsets(value)


if __name__=='__main__':unittest.main()
