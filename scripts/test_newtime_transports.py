import unittest
from inspect_newtime_transports_hzc2 import project_cell


class FieldTransportTests(unittest.TestCase):
    def test_whole_cell_at_last_valid_offset(self):
        self.assertEqual(project_cell(100,116,1000,108),1008)

    def test_partial_overlap_is_not_whole_transport(self):
        self.assertIsNone(project_cell(100,116,1000,109))
        self.assertIsNone(project_cell(100,116,1000,99))

    def test_half_open_end_and_disjoint(self):
        self.assertIsNone(project_cell(100,116,1000,116))
        self.assertIsNone(project_cell(100,116,1000,0))

    def test_invalid_and_wrapping_intervals(self):
        for args in ((100,100,0,100),(100,116,0,108,0),(0,16,(1<<64)-8,0),
                     (0,16,0,(1<<64)-4),(True,16,0,0)):
            with self.subTest(args=args),self.assertRaises(ValueError):project_cell(*args)


if __name__=='__main__':unittest.main()
