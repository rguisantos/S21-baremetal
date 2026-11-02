#!/usr/bin/env python3
"""CRC sampling controls without a private kernel, native build or toolchain."""
import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import capture_a0_crc_trace as m
from check_capture_a0_build_profile import inspect

CRC=b'__crc_nf_register_net_hooks = 0xca246fbf;\n'


def wait_for(predicate):
    deadline=time.monotonic()+3
    while not predicate():
        if time.monotonic()>=deadline:raise AssertionError('observer condition not reached')
        time.sleep(.01)


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'objects';self.out.mkdir()
        self.p=self.out/m.PATHS[0];self.p.parent.mkdir(parents=True)
        self.log=self.root/'trace.jsonl'

    def test_assignments_keep_conflicting_values(self):
        data=CRC+b'__crc_nf_register_net_hooks = 0x1;\n'+CRC
        self.assertEqual(m.assignments(data),{'nf_register_net_hooks':['0x00000001','0xca246fbf']})

    def test_module_symvers_zero_is_an_observation(self):
        data=b'0x00000000\tnf_register_net_hooks\tvmlinux\tEXPORT_SYMBOL\t\n'
        self.assertEqual(m.assignments(data),{'nf_register_net_hooks':['0x00000000']})
        self.assertEqual(m.assignments(b'__crc_other = 0x123;\n'),{})

    def test_snapshot_missing_empty_and_regular(self):
        self.assertEqual(m.snapshot(self.p),{'state':'missing'})
        self.p.write_bytes(b'');self.assertEqual(m.snapshot(self.p)['bytes'],0)
        self.p.write_bytes(CRC);s=m.snapshot(self.p)
        self.assertEqual(s['sha256'],hashlib.sha256(CRC).hexdigest())
        self.assertEqual(s['assignments'],{'nf_register_net_hooks':['0xca246fbf']})

    def test_symbolic_link_never_reads_target(self):
        target=self.root/'outside';target.write_bytes(CRC);self.p.symlink_to(target)
        self.assertEqual(m.snapshot(self.p),{'state':'non_regular'})
        self.assertEqual(target.read_bytes(),CRC)

    def test_fifo_never_blocks(self):
        os.mkfifo(self.p);self.assertEqual(m.snapshot(self.p),{'state':'non_regular'})

    def test_oversized_file_is_bounded(self):
        with self.p.open('wb') as f:f.truncate(m.MAX_BYTES+1)
        self.assertEqual(m.snapshot(self.p)['state'],'oversized')

    def test_trace_observes_create_empty_remove_and_recreate(self):
        with m.VersionTrace(self.out,self.log,interval=.01) as t:
            self.p.write_bytes(CRC)
            wait_for(lambda:any(e.get('sha256')==hashlib.sha256(CRC).hexdigest() for e in t.events))
            self.p.write_bytes(b'')
            wait_for(lambda:any(e['path']==m.PATHS[0] and e.get('bytes')==0 for e in t.events))
            self.p.unlink()
            wait_for(lambda:t.last[m.PATHS[0]]['state']=='missing')
            self.p.write_bytes(CRC.replace(b'ca246fbf',b'12345678'))
            wait_for(lambda:t.last[m.PATHS[0]].get('assignments')=={'nf_register_net_hooks':['0x12345678']})
        s=t.summary()
        self.assertFalse(s['event_limit_reached']);self.assertIsNone(s['observer_error'])
        self.assertFalse(s['source_modified_by_observer']);self.assertFalse(s['module_abi_established'])
        self.assertTrue(s['transitions_between_samples_may_be_missed'])
        self.assertEqual(self.p.read_bytes(),CRC.replace(b'ca246fbf',b'12345678'))
        self.assertEqual(s['log_sha256'],hashlib.sha256(self.log.read_bytes()).hexdigest())

    def test_limit_cannot_masquerade_as_complete_history(self):
        with m.VersionTrace(self.out,self.log,limit=1) as t:pass
        s=t.summary();self.assertTrue(s['event_limit_reached']);self.assertEqual(len(s['events']),1)
        self.assertEqual(set(s['final']),set(m.PATHS))

    def test_log_cannot_modify_object_tree_or_existing_file(self):
        with self.assertRaises(ValueError):m.VersionTrace(self.out,self.p)
        self.log.write_bytes(b'preserved')
        with self.assertRaises(FileExistsError):
            with m.VersionTrace(self.out,self.log):pass
        self.assertEqual(self.log.read_bytes(),b'preserved')

    def test_trace_error_is_explicit(self):
        with m.VersionTrace(self.out,self.log,interval=.01) as t:
            with patch.object(m,'snapshot',side_effect=RuntimeError('fixture')):
                wait_for(lambda:t.failure is not None)
        self.assertEqual(t.summary()['observer_error'],'RuntimeError')

    def test_summary_requires_stopped_trace(self):
        t=m.VersionTrace(self.out,self.log)
        with self.assertRaises(ValueError):t.summary()
        with t:
            with self.assertRaises(ValueError):t.summary()
        with self.assertRaises(ValueError):
            with t:pass

    def test_trace_without_compile_refused_before_inputs(self):
        with patch('check_capture_a0_build_profile.verify_file') as verify:
            with self.assertRaises(ValueError):inspect(self.root/'absent',self.root,self.root,self.root/'work',False,True)
            verify.assert_not_called()


if __name__=='__main__':unittest.main()
