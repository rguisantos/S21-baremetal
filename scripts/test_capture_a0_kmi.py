#!/usr/bin/env python3
"""Bounds, input provenance and injection refusals for the offline KMI audit."""
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import check_capture_a0_kmi as audit


class Archive:
    def __init__(self, rows): self.rows = rows
    def __iter__(self): return iter(info for info, data in self.rows)
    def extractfile(self, info):
        return io.BytesIO(next(data for member, data in self.rows if member is info))


def member(name, data=b'', kind=tarfile.REGTYPE, size=None):
    info = tarfile.TarInfo(name)
    info.type = kind
    info.size = len(data) if size is None else size
    return info, data


class PathAndListTests(unittest.TestCase):
    def test_public_relative_paths(self):
        self.assertEqual(audit.list_paths('"android/list abi_greylist"'), ['android/list', 'abi_greylist'])

    def test_duplicate_list(self):
        with self.assertRaises(ValueError): audit.list_paths('"a a"')

    def test_traversal_or_absolute(self):
        for name in ('../private', 'a/../b', '/private'):
            with self.subTest(name=name), self.assertRaises(ValueError): audit.list_paths(json.dumps(name))

    def test_noncanonical_paths(self):
        for name in ('a//b', './a', 'a/', '.'):
            with self.subTest(name=name), self.assertRaises(ValueError): audit.list_paths(json.dumps(name))

    def test_shell_characters(self):
        for name in ('$(id)', 'a;id', '`id`', 'a\\b'):
            with self.subTest(name=name), self.assertRaises(ValueError): audit.list_paths(json.dumps(name))

    def test_not_a_string(self):
        for value in ('true', '[]', 'null'):
            with self.subTest(value=value), self.assertRaises(ValueError): audit.list_paths(value)

    def test_empty_or_oversize_list(self):
        for value in ('', ' '.join('list'+str(n) for n in range(65))):
            with self.subTest(value=value), self.assertRaises(ValueError): audit.list_paths(json.dumps(value))

    def test_grouped_list_comments_and_duplicates(self):
        self.assertEqual(audit.symbols(b'[abi_symbol_list]\n alpha # public\nalpha\n_beta2\n', True), {'alpha', '_beta2'})

    def test_raw_list_rejects_section(self):
        with self.assertRaises(ValueError): audit.symbols(b'[abi_symbol_list]\nalpha\n')

    def test_list_is_data_not_shell(self):
        for data in (b'alpha;id', b'alpha beta', b'$(id)', b'\x00', b'[other_section]'):
            with self.subTest(data=data), self.assertRaises(ValueError): audit.symbols(data, True)


class CensusTests(unittest.TestCase):
    def test_identifier_boundaries_and_config_prefix(self):
        data = b'ADDITIONAL_KMI_SYMBOL_LISTS\nKMI_SYMBOL_LISTS\nCONFIG_KMI_SYMBOL_LISTS\nKMI_SYMBOL_LIST_STRICT_MODE\n'
        found, census = audit.scan_stream(Archive([member('one', data)]), {'one'})
        self.assertEqual(found['one'], data)
        self.assertEqual(census['identifier_hits']['KMI_SYMBOL_LISTS'], [{'file':'one','line':2}, {'file':'one','line':3}])

    def test_unselected_regular_files_are_still_scanned(self):
        _, census = audit.scan_stream(Archive([member('other', b'CONFIG_UNUSED_KSYMS_WHITELIST=y')]), set())
        self.assertEqual(census['regular_members'], 1)
        self.assertEqual(len(census['identifier_hits']['UNUSED_KSYMS_WHITELIST']), 1)
        self.assertEqual(census['skipped_regular_members'], 0)

    def test_duplicate_normalized_path(self):
        with self.assertRaises(ValueError):
            audit.scan_stream(Archive([member('./one'), member('one')]), {'one'})

    def test_symlink_is_reported_and_never_followed(self):
        info, data = member('selected', kind=tarfile.SYMTYPE)
        info.linkname = '../../private'
        found, census = audit.scan_stream(Archive([(info, data)]), {'selected'})
        self.assertEqual(found, {})
        self.assertEqual(census['wanted_nonregular'], {'selected':'../../private'})

    def test_device_member_refused(self):
        with self.assertRaises(ValueError):
            audit.scan_stream(Archive([member('device', kind=tarfile.CHRTYPE)]), set())

    def test_oversize_member_is_not_silently_skipped(self):
        with self.assertRaises(ValueError):
            audit.scan_stream(Archive([member('large', size=32*1024*1024+1)]), set())

    def test_short_member_refused(self):
        with self.assertRaises(ValueError):
            audit.scan_stream(Archive([member('short', b'x', size=2)]), set())

    def test_negative_member_size_refused(self):
        with self.assertRaises(ValueError):
            audit.scan_stream(Archive([member('negative', size=-1)]), set())

    def test_identifier_hit_budget(self):
        with self.assertRaises(ValueError):
            audit.scan_stream(Archive([member('many', b'KMI_SYMBOL_LISTS\n'*1001)]), set())


class ExecutionRefusals(unittest.TestCase):
    def test_archive_hash_checked_before_tar_parser(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit.tarfile, 'open') as parse:
            path = Path(temp) / 'bad.tar.gz'; path.write_bytes(b'bad')
            with self.assertRaises(ValueError): audit.read_archive(path, set())
            parse.assert_not_called()

    def test_config_hash_checked_before_archive_or_output(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, 'read_archive') as read:
            root = Path(temp); config = root/'config'; config.write_bytes(b'bad')
            with self.assertRaises(ValueError): audit.inspect(root/'archive', config, root/'out')
            read.assert_not_called(); self.assertFalse((root/'out').exists())

    def test_scratch_path_shell_injection_refused(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit.subprocess, 'run') as run:
            root = Path(temp)/'bad$(id)'
            with self.assertRaises(ValueError): audit.probe_case(root, Path('/source'), 'cc', 'nm')
            run.assert_not_called(); self.assertFalse(root.exists())

    def test_metadata_shell_injection_refused(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit.subprocess, 'run') as run:
            root = Path(temp)/'case'
            with self.assertRaises(ValueError): audit.probe_case(root, Path('/source'), 'cc', 'nm', metadata='$(id)')
            run.assert_not_called(); self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
