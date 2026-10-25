"""Allowlist privacy, persistent/current sections and signature-field distinctions."""
import json
import unittest

from inspect_bugreport_dram import technical_fields
from inspect_dram_logging_hzc2 import OBSERVED, REFERENCE, fields


class BugreportTests(unittest.TestCase):
    def test_cmdline_emits_only_two_allowlisted_fields(self):
        result=technical_fields(['Linux version 5.4.242-30958140-abG998BXXSJHZC2 user@private-host\n',
            'Command line: serial=SECRET_SERIAL vbmeta=SECRET_DIGEST operator=SECRET_OPERATOR '
            'dram_info=01,08,00,12G log_buf_len=256K\n'])
        text=json.dumps(result)
        for secret in ('SECRET_SERIAL','SECRET_DIGEST','SECRET_OPERATOR','private-host','Command line'):
            self.assertNotIn(secret,text)
        self.assertIn('01,08,00,12G',text)

    def test_app_text_is_not_reclassified_as_a_bootloader_observation(self):
        result=technical_fields(['------ SYSTEM LOG (logcat) ------\n',
            'message: 0001000850500130 DRAM Manufacturer = Samsung DRAM Process ver = D1Z\n'])
        self.assertEqual(result['records'],[])

    def test_last_kmsg_captures_typed_labels_without_line_suffix(self):
        result=technical_fields(['------ LAST KMSG (/proc/last_kmsg) ------\n',
            '0001000850500130 SECRET_SERIAL\n','DRAM Manufacturer = Samsung SECRET_SERIAL\n',
            'DRAM Process ver = D1Z SECRET_SERIAL\n','DRAM Size = 12.000000GB SECRET_SERIAL\n'])
        self.assertEqual(len(result['records']),4)
        self.assertNotIn('SECRET_SERIAL',json.dumps(result))

    def test_recovery_kernel_stays_separate_from_current_header(self):
        result=technical_fields(['Linux version 5.4.242-30958140-abG998BXXSJHZC2\n',
            '------ PRINT RECOVERY LOG ------\n','Linux version 5.4.242-30958140-abG998BXXSJHZA6\n'])
        self.assertIn('kernel',result['records'][0]['fields'])
        self.assertIn('recovery_kernel',result['records'][1]['fields'])

    def test_kernel_statistics_stop_at_next_section(self):
        result=technical_fields(['------ KERNEL LOG (dmesg) ------\n','npu event\n',
            '------ OTHER LOG ------\n','DEVFREQ : dram: 1234\n'])
        self.assertEqual(result['kernel_log']['lines'],1)
        self.assertEqual(result['kernel_log']['npu_lines'],1)
        self.assertEqual(result['kernel_log']['devfreq_dram_lines'],0)

    def test_arbitrary_property_values_do_not_escape(self):
        result=technical_fields(['------ SYSTEM PROPERTIES ------\n','[ro.product.model]: [PRIVATE_ID]\n',
            '[ro.serialno]: [PRIVATE_ID]\n'])
        self.assertEqual(result['records'],[])

    def test_different_full_words_share_manufacturer_and_process(self):
        a,b=fields(REFERENCE),fields(OBSERVED)
        self.assertNotEqual(a['word'],b['word'])
        self.assertEqual((a['selected_manufacturer_label'],a['selected_process_label']),('Samsung','D1Z'))
        self.assertEqual((b['selected_manufacturer_label'],b['selected_process_label']),('Samsung','D1Z'))
        self.assertTrue(a['reference_driver_exact_match'])
        self.assertFalse(b['reference_driver_exact_match'])

    def test_mode_and_density_fields_are_distinct(self):
        a,b=fields(REFERENCE),fields(OBSERVED)
        self.assertEqual((a['mode'],a['first_density_index']),(1,6))
        self.assertEqual((b['mode'],b['first_density_index'],b['second_density_index']),(3,5,5))

    def test_word_types_are_strict_unsigned_u64(self):
        for value in (True,-1,1<<64,'1'):
            with self.assertRaises(ValueError):fields(value)


if __name__=='__main__':unittest.main()
