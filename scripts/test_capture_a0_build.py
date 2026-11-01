#!/usr/bin/env python3
"""Synthetic controls for build evidence; no Samsung package/toolchain required."""
import gzip
import hashlib
import io
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from capture_a0_build import (CRITICAL, archive_tree, directory_tree, tree_identity,
    blob, profile, partial_versions, vdso, patch_tui)
from check_capture_a0_build_profile import inspect, run


def config(values):
    return ''.join(f'# {k} is not set\n' if v == 'n' else f'{k}={v}\n' for k,v in values.items())


class BuildChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def archive(self, rows, mtime=0):
        raw=io.BytesIO()
        with tarfile.open(fileobj=raw,mode='w') as t:
            for name,data,kind in rows:
                m=tarfile.TarInfo(name);m.mode=0o755 if kind=='x' else 0o644
                if kind=='link':m.type=tarfile.SYMTYPE;m.linkname=data.decode()
                elif kind=='dir':m.type=tarfile.DIRTYPE
                elif kind=='hard':m.type=tarfile.LNKTYPE;m.linkname=data.decode()
                else:m.size=len(data)
                t.addfile(m,io.BytesIO(data) if m.isfile() else None)
        p=self.root/f'archive-{mtime}.gz';p.write_bytes(gzip.compress(raw.getvalue(),mtime=mtime));return p

    def test_tree_matches_independent_git(self):
        d=self.root/'tree';d.mkdir();(d/'a.c').write_bytes(b'one')
        (d/'a').mkdir();(d/'a'/'run').write_bytes(b'two');(d/'a'/'run').chmod(0o755)
        (d/'link').symlink_to('a.c')
        subprocess.run(['git','init','-q',str(d)],check=True)
        subprocess.run(['git','-C',str(d),'add','.'],check=True)
        expected=subprocess.check_output(['git','-C',str(d),'write-tree'],text=True).strip()
        identity=directory_tree(d);self.assertEqual(identity['tree'],expected)
        self.assertEqual(identity['members'],3)
        t=self.archive([('a.c',b'one','file'),('a',b'','dir'),('a/run',b'two','x'),('link',b'a.c','link')])
        self.assertEqual(archive_tree(t),identity)

    def test_transport_metadata_not_content_identity(self):
        rows=[('file',b'unchanged','file')]
        a=self.archive(rows,0);b=self.archive(rows,42)
        self.assertNotEqual(a.read_bytes(),b.read_bytes());self.assertEqual(archive_tree(a),archive_tree(b))

    def test_modes_content_links_and_extra_file_change_identity(self):
        p=self.root/'tool';p.write_bytes(b'a');first=directory_tree(self.root)
        p.chmod(0o755);self.assertNotEqual(first,directory_tree(self.root));p.chmod(0o644)
        p.write_bytes(b'b');self.assertNotEqual(first,directory_tree(self.root));p.unlink()
        p.symlink_to('a');self.assertNotEqual(first,directory_tree(self.root));p.unlink();p.write_bytes(b'a')
        (self.root/'extra').write_bytes(b'');self.assertNotEqual(first,directory_tree(self.root))

    def test_unsafe_archive_names(self):
        for name in ('../escape','/absolute','a/../b','a//b'):
            with self.subTest(name=name),self.assertRaises(ValueError):archive_tree(self.archive([(name,b'x','file')]))

    def test_duplicate_and_file_directory_collisions(self):
        for rows in ([('a',b'x','file'),('a',b'x','file')],
                     [('a',b'x','file'),('a/b',b'y','file')],
                     [('a/b',b'x','file'),('a',b'y','file')],
                     [('a',b'x','link'),('a/b',b'y','file')]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):archive_tree(self.archive(rows))

    def test_hardlink_refused(self):
        with self.assertRaises(ValueError):archive_tree(self.archive([('a',b'b','hard')]))

    def test_truncated_blob_and_tar(self):
        with self.assertRaises(ValueError):blob(io.BytesIO(b'1'),2)
        p=self.archive([('a',os.urandom(4096),'file')]);p.write_bytes(p.read_bytes()[:100])
        with self.assertRaises((EOFError,tarfile.TarError,ValueError)):archive_tree(p)

    def test_special_directory_member_refused(self):
        os.mkfifo(self.root/'fifo')
        with self.assertRaises(ValueError):directory_tree(self.root)

    def test_profile_pass_does_not_claim_abi(self):
        text=config(CRITICAL);r=profile(text,text)
        self.assertTrue(r['critical_profile_preserved']);self.assertTrue(r['source_defconfig_equal'])
        self.assertFalse(r['module_abi_established'])

    def test_each_critical_setting_is_required(self):
        for key in CRITICAL:
            values=dict(CRITICAL);values.pop(key)
            with self.subTest(key=key):self.assertIn(key,profile(config(CRITICAL),config(values))['critical_mismatches'])

    def test_permissive_cfi_and_wrong_compiler_refused(self):
        for key,value in [('CONFIG_CFI_PERMISSIVE','y'),('CONFIG_CLANG_VERSION','140000')]:
            values=dict(CRITICAL);values[key]=value
            self.assertFalse(profile(config(CRITICAL),config(values))['critical_profile_preserved'])

    def test_unrecognized_source_config_remains_visible(self):
        r=profile(config(CRITICAL)+'CONFIG_SEC_AUTO_INPUT=m\n',config(CRITICAL))
        self.assertTrue(r['critical_profile_preserved']);self.assertFalse(r['source_defconfig_equal'])
        self.assertEqual(r['config_differences'][0]['key'],'CONFIG_SEC_AUTO_INPUT')

    def test_duplicate_config_refused(self):
        with self.assertRaises(ValueError):profile('', 'CONFIG_LTO=y\nCONFIG_LTO=n\n')

    def test_partial_crc_matches_and_mismatches(self):
        stock={'module_layout':{'crcs':['0x1e5b7ab7']}}
        r=partial_versions(b'__crc_module_layout = 0x1e5b7ab7;\n',stock)
        self.assertTrue(r['compared']['module_layout']['matches_stock'])
        self.assertFalse(r['module_abi_established']);self.assertFalse(r['full_module_symvers'])
        self.assertFalse(partial_versions(b'__crc_module_layout = 0x1;\n',stock)['compared']['module_layout']['matches_stock'])
        self.assertEqual(partial_versions(b'__crc_other = 0x1;\n',stock)['compared'],{})

    def test_invalid_partial_crc(self):
        for data in (b'',b'x = 1;',b'__crc_x = 0x123456789;',b'__crc_x = 0x1;\n__crc_x = 0x1;'):
            with self.subTest(data=data),self.assertRaises(ValueError):partial_versions(data,{})

    def test_vdso_headers_only(self):
        for klass,machine in ((1,40),(2,183)):
            data=bytearray(64);data[:7]=b'\x7fELF'+bytes([klass,1,1]);struct.pack_into('<HHI',data,16,3,machine,1)
            r=vdso(data,klass,machine);self.assertTrue(r['elf_header_only']);self.assertFalse(r['runtime_execution_tested'])
            with self.assertRaises(ValueError):vdso(data,klass,999)
            with self.assertRaises(ValueError):vdso(data[:40],klass,machine)

    def test_patch_refuses_unpinned_input(self):
        with self.assertRaises(ValueError):patch_tui(b'ccflags-y += -Idrivers/video/fbdev/exynos/dpu30\n')

    def test_unverified_source_never_executes(self):
        source=self.root/'source.gz';source.write_bytes(b'wrong')
        with patch('check_capture_a0_build_profile.run') as execute:
            with self.assertRaises(ValueError):inspect(source,self.root,self.root,self.root/'out')
            execute.assert_not_called();self.assertFalse((self.root/'out').exists())

    def test_native_run_records_exit_and_timeout(self):
        env={'PATH':os.defpath};log=self.root/'log'
        self.assertEqual(run([sys.executable,'-c','raise SystemExit(7)'],env,log)['returncode'],7)
        r=run([sys.executable,'-c','import time;time.sleep(30)'],env,log,timeout=.1)
        self.assertTrue(r['timed_out']);self.assertNotEqual(r['returncode'],0)


if __name__=='__main__':unittest.main()
