#!/usr/bin/env python3
"""Regressions for the readelf symbol reader used by both QEMU harnesses."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_payload_loader import symbols


ROWS = """
     0: 0000000000000000     0 NOTYPE  LOCAL  DEFAULT  UND
     7: 0000000040080080     0 NOTYPE  GLOBAL DEFAULT    1 diag_image
     8: 0000000040080200     0 NOTYPE  GLOBAL DEFAULT    1 diag_record
"""
EXPECTED = {'diag_image': 0x40080080, 'diag_record': 0x40080200}


class SymbolTests(unittest.TestCase):
    def test_english_header_and_unnamed_null_entry(self):
        listing = '   Num:    Value          Size Type    Bind   Vis      Ndx Name\n' + ROWS
        with patch('test_payload_loader.subprocess.check_output', return_value=listing):
            self.assertEqual(symbols(Path('sample.elf')), EXPECTED)

    def test_translated_header_reproducing_tamanho_failure(self):
        # Synthetic translated header with the exact failing token reported on Mint.
        listing = '   Num: Tamanho Valor Tipo Vinculo Visibilidade Indice Nome\n' + ROWS
        with patch('test_payload_loader.subprocess.check_output', return_value=listing):
            self.assertEqual(symbols(Path('sample.elf')), EXPECTED)

    def test_child_locale_is_c_without_changing_parent_environment(self):
        parent = {'LANG': 'pt_BR.UTF-8', 'LC_ALL': 'pt_BR.UTF-8', 'USE_SYSTEM_TOOLS': '1'}
        with patch.dict(os.environ, parent):
            before = dict(os.environ)
            with patch('test_payload_loader.subprocess.check_output', return_value=ROWS) as readelf:
                self.assertEqual(symbols(Path('sample.elf')), EXPECTED)
            self.assertEqual(readelf.call_args.args[0], ['readelf', '-sW', 'sample.elf'])
            self.assertEqual(readelf.call_args.kwargs['env'], dict(before, LC_ALL='C'))
            self.assertEqual(dict(os.environ), before)

    def test_bad_value_in_numbered_symbol_is_still_an_error(self):
        listing = '  7: not-hex 0 NOTYPE GLOBAL DEFAULT 1 diag_image\n'
        with patch('test_payload_loader.subprocess.check_output', return_value=listing):
            with self.assertRaises(ValueError):
                symbols(Path('sample.elf'))

    def test_real_readelf_on_fresh_elf(self):
        with tempfile.TemporaryDirectory(prefix='elf-symbols-') as directory:
            elf = Path(directory)/'fixture.o'
            # Assembler directives only: this fixture does not execute host code.
            source = '.text\n.global fixture_entry\nfixture_entry:\n.byte 0\n' \
                     '.global fixture_limit\n.set fixture_limit, 0x1234\n'
            subprocess.run(['cc', '-x', 'assembler', '-c', '-o', str(elf), '-'],
                           input=source, text=True, check=True)
            with patch.dict(os.environ, {'LANG': 'pt_BR.UTF-8', 'LC_ALL': 'pt_BR.UTF-8'}):
                table = symbols(elf)
            self.assertEqual(table['fixture_entry'], 0)
            self.assertEqual(table['fixture_limit'], 0x1234)


if __name__ == '__main__':
    unittest.main()
