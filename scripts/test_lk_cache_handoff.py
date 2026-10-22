"""Cache-gate contract and host boundaries; no firmware/cache fixture."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from check_lk_cache_handoff import U64, model, normalize, read_scenario
from emulate_lk_cache_handoff import emulate


def supplied(**changes):
    values = dict(current_el=1, sctlr_el1=0x1005, sctlr_el2=0x2205,
                  sctlr_el3=0x3305, daif=0, clidr_el1=0,
                  csselr_el1=3, ccsidr_by_level={}, kernel_offset=0x8000)
    values.update(changes)
    return values


class CacheGateTests(unittest.TestCase):
    def test_m_zero_c_one_is_not_disabled(self):
        r = model(supplied(sctlr_el1=0x1004))
        self.assertFalse(r['data_maintenance_taken'])
        self.assertEqual(r['sctlr_after_gate']['sctlr_el1'], '0x1004')
        self.assertEqual(r['csselr_after_gate'], '0x3')
        self.assertEqual(r['system_operation_trace'], [{'op': 'daifset_irq', 'value': '0x80'}])

    def test_only_active_el_is_changed_and_i_is_preserved(self):
        for el in (1, 2, 3):
            values = supplied(current_el=el)
            original = {f'sctlr_el{i}': values[f'sctlr_el{i}'] for i in (1, 2, 3)}
            r = model(values)
            for key, value in original.items():
                with self.subTest(el=el, key=key):
                    self.assertEqual(int(r['sctlr_after_gate'][key], 0),
                                     value & ~5 if key == f'sctlr_el{el}' else value)
            self.assertEqual(r['current_el_unchanged'], el)

    def test_no_cache_levels_still_resets_selector_and_has_completion_barriers(self):
        r = model(supplied())
        self.assertEqual(r['csselr_after_gate'], '0x0')
        self.assertEqual(r['dc_cisw_operands'], [])
        ops = r['system_operation_trace']
        self.assertEqual(sum(x['op'] == 'dsb_sy' for x in ops), 2)
        self.assertEqual(ops[-2:], [{'op': 'sctlr_el1_write', 'value': '0x1000'}, {'op': 'isb'}])

    def test_data_set_way_sequence_descends_sets_then_ways(self):
        r = model(supplied(clidr_el1=0x01000002,
                           ccsidr_by_level={'0': 2 | (1 << 3) | (1 << 13)}))
        self.assertEqual(r['dc_cisw_operands'], ['0x80000040', '0x40', '0x80000000', '0x0'])
        self.assertEqual(r['legacy_cache_levels'][0]['line_shift'], 6)

    def test_instruction_only_levels_are_skipped_and_direct_mapped_clz_zero_works(self):
        r = model(supplied(clidr_el1=0x02000021,
                           ccsidr_by_level={'1': 2 | (1 << 13)}))
        self.assertEqual(r['dc_cisw_operands'], ['0x42', '0x2'])
        self.assertEqual([x['level'] for x in r['legacy_cache_levels']], [1])
        self.assertEqual(r['legacy_cache_levels'][0]['way_count'], 1)

    def test_irq_is_masked_and_other_daif_bits_preserved(self):
        for daif in range(0, 0x400, 0x40):
            with self.subTest(daif=daif):
                r = model(supplied(daif=daif))
                self.assertEqual(int(r['daif_after_preserved_calls'], 0), daif | 0x80)

    def test_final_arguments_are_conditional_and_not_a_hardware_observation(self):
        r = model(supplied(kernel_offset=0x1f8000))
        self.assertEqual(r['conditional_final_arguments'],
                         dict(x0='0x8b080000', x1='0x0', x2='0x0', x3='0x0',
                              x4='0x80278000', x5='0x1f8000',
                              target='0x80278000', link_register='0xfbe18'))
        for name in ('runtime_observed', 'cache_contents_simulated', 'translation_simulated',
                     'physical_coherency_verified', 'final_hardware_state_verified'):
            self.assertFalse(r[name], name)

    def test_model_rejects_unresolved_or_excessive_cache_walks(self):
        for values in (supplied(clidr_el1=0x01000002),
                       supplied(clidr_el1=0x01000005),
                       supplied(clidr_el1=0x01000004, ccsidr_by_level={'0': 0xfffffff8})):
            with self.subTest(values=values), self.assertRaises(ValueError):
                model(values)
        # M=0 does not read CLIDR/CCSIDR, even when those supplied fields
        # could not support a bounded legacy walk.
        self.assertFalse(model(supplied(sctlr_el1=4, clidr_el1=0x01000005))['data_maintenance_taken'])

    def test_other_sctlr_bits_survive_the_mc_clear(self):
        r = model(supplied(sctlr_el1=U64))
        self.assertEqual(int(r['sctlr_after_gate']['sctlr_el1'], 0), 0xfffffffffffffffa)


class InputBoundaryTests(unittest.TestCase):
    def test_all_fields_and_canonical_cache_level_keys_are_required(self):
        bad = [{}, [], None, dict(supplied(), extra=0), supplied(current_el=0),
               supplied(current_el=4), supplied(daif=1), supplied(kernel_offset=1),
               supplied(kernel_offset=0x200000), supplied(sctlr_el1=-1),
               supplied(sctlr_el1=True), supplied(sctlr_el1=U64+1),
               supplied(ccsidr_by_level={'01': 0}), supplied(ccsidr_by_level={7: 0}),
               supplied(ccsidr_by_level=[])]
        missing = supplied()
        del missing['sctlr_el3']
        bad.append(missing)
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize(value)

    def test_json_literals_duplicates_and_nesting(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'scenario.json'
            values = {k: (hex(v) if isinstance(v, int) else v) for k, v in supplied().items()}
            p.write_text(json.dumps(values))
            self.assertEqual(read_scenario(p), supplied())
            for text in (json.dumps(values)[:-1]+',"current_el":2}',
                         '['*2000+'0'+']'*2000, ' '*8193):
                p.write_text(text)
                with self.subTest(text=text[:40]), self.assertRaises(ValueError):
                    read_scenario(p)

    def test_scenario_read_is_bounded_before_json_parsing(self):
        stream = MagicMock()
        stream.__enter__.return_value = stream
        stream.read.return_value = b' '*8193
        with patch('builtins.open', return_value=stream), self.assertRaises(ValueError):
            read_scenario('untrusted')
        stream.read.assert_called_once_with(8193)

    def test_wrong_firmware_cli_produces_no_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'sboot.bin'
            p.write_bytes(b'not HZC2')
            script = Path(__file__).with_name('check_lk_cache_handoff.py')
            result = subprocess.run([sys.executable, str(script), str(p)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'')
        self.assertIn(b'unsupported image', result.stderr)

    def test_emulation_rejects_wrong_image_before_optional_dependency(self):
        with self.assertRaisesRegex(ValueError, 'exact HZC2'):
            emulate(b'not HZC2', supplied())


if __name__ == '__main__':
    unittest.main()
