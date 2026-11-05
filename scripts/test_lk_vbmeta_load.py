#!/usr/bin/env python3
"""Synthetic callback bindings, fallback predicate and sealed GNU input tests."""
import fcntl
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import inspect_lk_vbmeta_load as audit


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.words={
            0x180de8:0xb0005c21,0x180df0:0x91240021,
            0x180dec:0x90000003,0x180dfc:0x91112063,
            0x180e28:0xf0ffffe4,0x180e48:0x9132e084,
            0x180e10:0xa9018823,0x180e60:0xf9002c24,
            0x1225f4:0xf9400f26,0x122610:0xd63f00c0,
            0x1227b4:0xf9400f26,0x1227cc:0xd63f00c0,
            0x1806b4:0x97fffd81,
            0xfbc58:0xf0000c80,0xfbc64:0x913e0000,
            0x1246f8:0xb0000847,0x1246fc:0x911f80fc,
            0x123034:0xf0000793,0x123060:0x9127c273}

    def changed(self,pc,word):
        words=dict(self.words);words[pc]=word;return words

    def test_callbacks_names_and_suffix_bound(self):
        r=audit.resolve_bindings(self.words)
        self.assertEqual((r['read_slot'],r['read_target']),(24,'0x180448'))
        self.assertEqual((r['size_slot'],r['size_target']),(88,'0x17fcb8'))
        self.assertEqual(r['initial_root_name_offset'],'0x22d7e0')
        self.assertEqual(r['fallback_name_offset'],'0x2169f0')
        self.assertEqual(r['selected_caller_suffix_offset'],'0x28ef80')
        self.assertFalse(r['runtime_binding_and_preservation_established'])

    def test_wrong_read_store_slot_or_register_refused(self):
        for word in (0xa9018824,0xa9028823):
            with self.subTest(word=word),self.assertRaises(ValueError):
                audit.resolve_bindings(self.changed(0x180e10,word))

    def test_wrong_read_target_refused(self):
        with self.assertRaisesRegex(ValueError,'read callback store'):
            audit.resolve_bindings(self.changed(0x180dfc,0x91116063))

    def test_both_consumers_must_use_the_installed_slot(self):
        for pc in (0x1225f4,0x1227b4):
            with self.subTest(pc=pc),self.assertRaisesRegex(ValueError,'consumer'):
                audit.resolve_bindings(self.changed(pc,0xf9401326))

    def test_both_indirect_calls_must_use_the_loaded_register(self):
        for pc in (0x122610,0x1227cc):
            with self.subTest(pc=pc),self.assertRaisesRegex(ValueError,'consumer'):
                audit.resolve_bindings(self.changed(pc,0xd63f00a0))

    def test_size_callback_slot_refused_if_changed(self):
        with self.assertRaisesRegex(ValueError,'size binding'):
            audit.resolve_bindings(self.changed(0x180e60,0xf9003024))

    def test_direct_size_call_must_match_installer(self):
        with self.assertRaisesRegex(ValueError,'size binding'):
            audit.resolve_bindings(self.changed(0x1806b4,0x97fffd82))

    def test_store_decoder_rejects_load_wrong_width_and_indexed(self):
        self.assertEqual(audit.store_x(0xf9002c24),(4,1,88))
        for word in (0xf9402c24,0xb9002c24,0xf8008c24):
            with self.subTest(word=word),self.assertRaises(ValueError):audit.store_x(word)

    def test_different_add_destination_is_decoded_explicitly(self):
        self.assertEqual(audit.address_to(self.words,0x1246f8,0x1246fc,7,28),0x22d7e0)

    def test_wrong_source_or_destination_in_name_binding_refused(self):
        for word in (0x911f80fd,0x911f811c,0x111f80fc):
            with self.subTest(word=word),self.assertRaises(ValueError):
                audit.resolve_bindings(self.changed(0x1246fc,word))

    def test_wrong_root_or_fallback_literal_refused(self):
        for pc,word in ((0x1246fc,0x911f90fc),(0x123060,0x9127d273)):
            with self.subTest(pc=pc),self.assertRaises(ValueError):
                audit.resolve_bindings(self.changed(pc,word))


class PredicateTests(unittest.TestCase):
    def test_missing_root_with_normal_flags_selects_fallback(self):
        for flags in (0,1,2,3):self.assertTrue(audit.fallback_model(3,0,flags))

    def test_IO_OOM_and_other_statuses_do_not_select_fallback(self):
        for status in (0,1,2,4,5,6,7,8,0xffffffff):
            with self.subTest(status=status):self.assertFalse(audit.fallback_model(status,0,0))

    def test_non_root_or_nonzero_chain_location_cannot_select_fallback(self):
        for prefix,chain in ((1,0),(-1,0),(0xffffffff,0),(0,1),(0,6)):
            with self.subTest(prefix=prefix,chain=chain):self.assertFalse(audit.fallback_model(3,prefix,0,chain))

    def test_flag_bit2_disables_fallback(self):
        for flags in (4,5,6,7,0xffffffff):self.assertFalse(audit.fallback_model(3,0,flags))

    def test_model_refuses_non_integral_and_out_of_width_inputs(self):
        for args in ((True,0,0),(3,0,-1),(2**32,0,0),(3,-2**31-1,0),(3,0,0,-1)):
            with self.subTest(args=args),self.assertRaises(ValueError):audit.fallback_model(*args)

    def test_ASCII_uppercase_preserves_explicit_names_without_redirect(self):
        for name in (b'vbmeta',b'vbmeta_samsung',b'vbmeta_system',b'boot',b'vbmeta_a'):
            self.assertEqual(audit.ascii_upper(name),name.upper())

    def test_non_ASCII_bytes_and_punctuation_are_preserved(self):
        self.assertEqual(audit.ascii_upper(b'azAZ_09-\x80\xff'),b'AZAZ_09-\x80\xff')

    def test_name_model_rejects_NUL_type_and_analyzer_over_budget(self):
        for data in (b'a\0b',bytearray(b'a'),b'a'*129):
            with self.subTest(data_type=type(data)),self.assertRaises(ValueError):audit.ascii_upper(data)


class InputTests(unittest.TestCase):
    def test_unidentified_firmware_rejected_before_native_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bad.bin'
            for b in (b'bad',bytes(audit.IMAGES['sboot'][0])):
                path.write_bytes(b)
                with patch.object(audit.subprocess,'check_output') as native:
                    with self.assertRaises(ValueError):audit.inspect(path)
                    native.assert_not_called()

    def test_GNU_receives_sealed_snapshot_of_the_same_buffer(self):
        data=bytes.fromhex('1f2003d5');seen=[]
        def native(command,**kwargs):
            fd,=kwargs['pass_fds'];self.assertEqual(command[-1],'/proc/self/fd/'+str(fd))
            self.assertEqual(os.pread(fd,len(data),0),data)
            self.assertEqual(fcntl.fcntl(fd,1034)&15,15)
            with self.assertRaises(OSError):os.pwrite(fd,b'X',0)
            seen.append(fd);return '0: d503201f nop\n'
        with patch.object(audit.subprocess,'check_output',side_effect=native):
            lines=audit.disassemble(data,{'synthetic':(0,4)})
        self.assertEqual(lines[0],(0xd503201f,'nop',''));self.assertEqual(len(seen),1)

    def test_bad_GNU_block_bounds_refused_before_launch(self):
        for blocks in ({},{'a':(1,4)},{'a':(0,8)},{'a':(-4,0)}):
            with self.subTest(blocks=blocks),patch.object(audit.subprocess,'check_output') as native:
                with self.assertRaises(ValueError):audit.disassemble(b'1234',blocks)
                native.assert_not_called()

    def test_duplicate_GNU_PC_refused(self):
        with patch.object(audit.subprocess,'check_output',return_value='0: d503201f nop\n'):
            with self.assertRaisesRegex(ValueError,'duplicate GNU PC'):
                audit.disassemble(bytes.fromhex('1f2003d5'),{'a':(0,4),'b':(0,4)})

    def test_CLI_refusal_has_no_report(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bad.bin';path.write_bytes(b'bad');out=Path(temp)/'report.json'
            r=subprocess.run([sys.executable,str(Path(audit.__file__)),str(path),'--output',str(out)],
                capture_output=True,text=True)
            self.assertEqual(r.returncode,2);self.assertEqual(r.stdout,'');self.assertFalse(out.exists())

    def test_CLI_native_timeout_is_a_refusal(self):
        with patch.object(sys,'argv',['inspect','unused']),redirect_stderr(io.StringIO()),\
                patch.object(audit,'inspect',side_effect=subprocess.TimeoutExpired('GNU',30)):
            with self.assertRaises(SystemExit) as result:audit.main()
        self.assertEqual(result.exception.code,2)


if __name__=='__main__':unittest.main()
