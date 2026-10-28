"""Snapshot confinement and refusal of invalid/non-comparable NEWTIME captures."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from compare_newtime_gate import compare
from trace_newtime_columns_qemu import OBSERVATIONS, observe_stop, write_observations

ROOT = Path(__file__).resolve().parent.parent


class GateObservationTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT/'docs/references/newtime-gate-observation'
        self.left,self.right = [json.loads((directory/f'line{row}__none.json').read_text()) for row in (10,15)]

    def test_refuted_zero_prediction_is_reported(self):
        result = compare(self.left,self.right)
        for placement in result['placements']:
            self.assertTrue(placement['comparable'])
            self.assertTrue(placement['primary_fields_unchanged_from_entry'])
            self.assertTrue(placement['primary_fields_identical_between_rows'])
            self.assertFalse(placement['predictions']['scratch_zero'])

    def test_different_stop_prevents_field_comparison(self):
        self.right['cases'][0]['observation']['reason']='instruction_limit'
        result=compare(self.left,self.right)['placements'][0]
        self.assertFalse(result['comparable'])
        self.assertFalse(result['field_comparison_performed'])
        self.assertNotIn('predictions',result)

    def test_different_return_prevents_field_comparison(self):
        self.right['cases'][0]['observation']['entry_lr']='0x40016000'
        self.assertFalse(compare(self.left,self.right)['placements'][0]['comparable'])

    def test_bad_primary_bytes_rejected(self):
        self.left['cases'][0]['observation']['fields']['scratch_31f30']['hex']='00'
        with self.assertRaisesRegex(ValueError,'snapshot bytes'):
            compare(self.left,self.right)

    def test_wrong_relocation_rejected(self):
        self.left['cases'][0]['observation']['fields']['ptr_31c30']['address']='0x31c30'
        with self.assertRaisesRegex(ValueError,'address or width'):
            compare(self.left,self.right)

    def test_unavailable_primary_is_not_equal_data(self):
        field=self.left['cases'][0]['observation']['fields']['ptr_31c30']
        del field['hex'];field['error']='unavailable'
        with self.assertRaisesRegex(ValueError,'primary observation'):
            compare(self.left,self.right)

    def test_wrong_firmware_rejected(self):
        self.left['sboot_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'firmware identity'):
            compare(self.left,self.right)

    def test_duplicate_placement_rejected(self):
        self.left['cases'][1]=copy.deepcopy(self.left['cases'][0])
        with self.assertRaisesRegex(ValueError,'placement'):
            compare(self.left,self.right)

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'line15__none.json';p.write_text('preserve')
            with self.assertRaisesRegex(ValueError,'overwrite'):
                write_observations(self.left,directory)
            self.assertEqual(p.read_text(),'preserve')
            self.assertFalse((Path(directory)/'line10__none.json').exists())

    def test_snapshot_never_steps_or_reads_ap_literal(self):
        class RemoteFixture:
            def __init__(self):self.reads=[];self.commands=[]
            def command(self,command):
                self.commands.append(command)
                regs=[0]*33;regs[32]=0x40019774
                return struct.pack('<33Q',*regs).hex()
            def read(self,address,size):self.reads.append(address);return b'\xff'*size
        remote=RemoteFixture()
        result=observe_stop(remote,0x40000000,[(0x40030000,0x40032000,True)],
            0x40015000,0x40015000,dict(reason='before_access_outside_lab_ram',
                pc='0x19774',address='0x158609bc'))
        self.assertEqual(remote.commands,['g'])
        self.assertNotIn(0x0207365c,remote.reads)
        self.assertEqual(len(remote.reads),len(OBSERVATIONS)-1)
        self.assertEqual(result['fields']['result_col1_0207365c']['error'],'not_in_lab_regions')


if __name__=='__main__':unittest.main()
