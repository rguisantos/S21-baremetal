#!/usr/bin/env python3
"""Dependency scheduling and refusal controls; no kernel modules are loaded."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_capture_a0_load_plan as checker
from check_capture_a0_load_plan import audit, inspect
from capture_a0_formats import digest


def fixture():
    return {'lib/modules/provider.ko':dict(name='provider-name', depends=[]),
            'lib/modules/client.ko':dict(name='client', depends=['provider_name'])}


LOAD = b'provider.ko\nclient.ko\n'
DEP = b'/lib/modules/provider.ko:\n/lib/modules/client.ko: /lib/modules/provider.ko\n'


class LoadPlanTests(unittest.TestCase):
    def test_stock_mode_reads_and_checks_synthetic_container_end_to_end(self):
        from test_capture_a0_modules import image
        from check_capture_a0_modules import inventory
        raw = image(); reference = inventory(raw)
        def pin(data): return dict(bytes=len(data), sha256=digest(data))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); vendor = root/'vendor.img'; vendor.write_bytes(raw)
            path = root/'inventory.json'; data = json.dumps(reference).encode(); path.write_bytes(data)
            (root/'capture-a0-pins-hzc2.json').write_text(json.dumps(
                dict(stock_raw={'vendor_boot.img':pin(raw)})))
            with patch.object(checker, 'INVENTORY', path), patch.object(checker, 'INVENTORY_PIN', pin(data)):
                r = inspect(vendor)
                self.assertTrue(r['result']['control_files_checks_passed'])
                self.assertTrue(r['result']['control_files_supplied'])
                vendor.write_bytes(raw[:-1])
                with self.assertRaisesRegex(ValueError, 'identity'): inspect(vendor)

    def test_dependency_precedes_client_with_normalized_name(self):
        r = audit(fixture())
        self.assertTrue(r['declared_graph_closed_and_acyclic'])
        self.assertEqual(r['proposed_dependency_first_order'],
                         ['lib/modules/provider.ko', 'lib/modules/client.ko'])
        self.assertIsNone(r['control_files_checks_passed'])

    def test_missing_dependency_prevents_order(self):
        m = fixture(); del m['lib/modules/provider.ko']
        r = audit(m)
        self.assertFalse(r['declared_graph_closed_and_acyclic'])
        self.assertIsNone(r['proposed_dependency_first_order'])

    def test_cycle_and_blocked_dependents_prevent_order(self):
        m = fixture(); m['lib/modules/provider.ko']['depends'] = ['client']
        r = audit(m)
        self.assertEqual(len(r['cycle_or_blocked_dependents']), 2)
        self.assertIsNone(r['proposed_dependency_first_order'])

    def test_normalized_identity_collision_refused(self):
        m = fixture(); m['lib/modules/other.ko'] = dict(name='provider_name', depends=[])
        with self.assertRaisesRegex(ValueError, 'ambiguous'): audit(m)

    def test_duplicate_normalized_dependency_refused(self):
        m = fixture(); m['lib/modules/client.ko']['depends'].append('provider-name')
        with self.assertRaisesRegex(ValueError, 'duplicate'): audit(m)

    def test_valid_control_files(self):
        r = audit(fixture(), LOAD, DEP)
        self.assertTrue(r['control_files_checks_passed'])
        self.assertTrue(r['literal_load_order_dependency_first'])
        self.assertFalse(r['runtime_loading_validated'])

    def test_reverse_literal_order_is_not_claimed_runtime_failure(self):
        r = audit(fixture(), b'client.ko\nprovider.ko\n', DEP)
        self.assertFalse(r['literal_load_order_dependency_first'])
        self.assertFalse(r['literal_order_is_runtime_failure'])
        self.assertTrue(r['control_files_checks_passed'])

    def test_missing_declared_dep_edge_fails_control_check(self):
        r = audit(fixture(), LOAD, b'/lib/modules/provider.ko:\n/lib/modules/client.ko:\n')
        self.assertFalse(r['control_files_checks_passed'])
        self.assertEqual(len(r['modules_dep_missing_declared_edges']), 1)

    def test_extra_dep_cycle_fails_even_when_modinfo_acyclic(self):
        dep = b'/lib/modules/provider.ko: /lib/modules/client.ko\n/lib/modules/client.ko: /lib/modules/provider.ko\n'
        self.assertFalse(audit(fixture(), LOAD, dep)['control_files_checks_passed'])

    def test_absent_dep_key_fails(self):
        self.assertFalse(audit(fixture(), LOAD, DEP.splitlines(keepends=True)[1])['control_files_checks_passed'])

    def test_missing_duplicate_or_unsafe_load_refused(self):
        for load in (b'', b'missing.ko\n', b'client.ko\nclient.ko\n', b'../client.ko\n'):
            with self.subTest(load=load), self.assertRaises(ValueError): audit(fixture(), load, DEP)

    def test_ambiguous_or_missing_dep_target_refused(self):
        for dep in (DEP+DEP, b'/lib/modules/client.ko: /lib/modules/missing.ko\n',
                    b'/lib/modules/client.ko: /lib/modules/provider.ko /lib/modules/provider.ko\n'):
            with self.subTest(dep=dep), self.assertRaises(ValueError): audit(fixture(), LOAD, dep)

    def test_control_files_must_be_paired(self):
        with self.assertRaises(ValueError): audit(fixture(), LOAD)

    def test_input_not_mutated(self):
        m = fixture(); before = deepcopy(m); audit(m, LOAD, DEP)
        self.assertEqual(m, before)

    def test_real_pinned_inventory_never_claims_control_file_validation(self):
        r = inspect()
        self.assertEqual(r['result']['module_count'], 274)
        self.assertTrue(r['result']['declared_graph_closed_and_acyclic'])
        self.assertFalse(r['result']['control_files_supplied'])
        self.assertIsNone(r['result']['control_files_checks_passed'])


if __name__ == '__main__': unittest.main()
