#!/usr/bin/env python3
"""Trace accounting and source-adapter controls, with no remote dependencies."""
import unittest
from unittest.mock import patch

import replay_a0_modprobe as replay


class ReplayTests(unittest.TestCase):
    def test_counts_new_modules_but_not_existing_attempts(self):
        r=replay.parse_trace('ATTEMPT driver success\nATTEMPT driver existing\nRESULT success 1\n')
        self.assertEqual(r['count'],1);self.assertEqual(len(r['attempts']),2)

    def test_failure_is_not_counted_as_loaded(self):
        r=replay.parse_trace('ATTEMPT driver failure\nRESULT failure 0\n')
        self.assertFalse(r['success']);self.assertEqual(r['count'],0)

    def test_bad_count_missing_or_duplicate_result_refused(self):
        for text in ('RESULT success 1\n','ATTEMPT driver success\n',
                     'RESULT success 0\nRESULT success 0\n','garbage\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):replay.parse_trace(text)

    def test_attempt_after_final_result_refused(self):
        with self.assertRaises(ValueError):
            replay.parse_trace('RESULT failure 0\nATTEMPT driver failure\n')

    def test_literals_cannot_inject_cpp_or_lose_nuls(self):
        self.assertEqual(replay.literal(b'"\\\0\n'),'std::string("\\x22\\x5c\\x00\\x0a",4)')

    def test_literal_input_budget(self):
        with self.assertRaises(ValueError):replay.literal(b'x'*(1024*1024+1))

    def test_adapter_removes_only_include_and_pragma_lines(self):
        body=b'#include <x>\n#pragma once\nbool resolve() { return true; }\n'
        self.assertEqual(replay.strip_includes(body),'bool resolve() { return true; }')

    def test_source_identity_checked_before_translation(self):
        with self.assertRaisesRegex(ValueError,'identity'):
            replay.translation_unit({'libmodprobe.cpp':b'changed','modprobe.h':b'changed'}, {})

    def test_translation_preserves_resolver_body_and_embeds_control_bytes(self):
        from capture_a0_formats import digest
        sources={'libmodprobe.cpp':b'#include <x>\nbool resolve() { return false; }',
                 'modprobe.h':b'#pragma once\nclass Fixture {};'}
        pins={n:dict(bytes=len(b),sha256=digest(b)) for n,b in sources.items()}
        with patch.object(replay,'SOURCE_PINS',pins):
            unit=replay.translation_unit(sources,{'modules.load':b'driver.ko\n'}).decode()
        self.assertIn('bool resolve() { return false; }',unit)
        self.assertNotIn('#include <x>',unit)
        self.assertIn('controls["/lib/modules/modules.load"]',unit)
        self.assertNotIn('finit_module',unit)


if __name__=='__main__':unittest.main()
