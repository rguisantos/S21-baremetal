#!/usr/bin/env python3
"""Controls for stage coverage, pinned patching and intermediate retention."""
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_a0_module_stages as s
from capture_a0_formats import digest
from capture_a0_module_policy import Elf
from check_capture_a0_build_profile import run, inspect as full_inspect
from check_capture_a0_module_stages import inspect
from test_capture_a0_module_policy import fixture
from test_capture_a0_stack_versions import generated


class ModuleStageTests(unittest.TestCase):
    def test_prelink_without_versions_is_explicitly_distinct_from_final_module(self):
        data,_,_=fixture();data=data.replace(b'__versions\0',b'_xversions\0')
        self.assertEqual(s.imports(data),{'service':'strong'})
        with self.assertRaises(ValueError):Elf(data)

    def test_added_import_after_modpost_creates_a_version_gap(self):
        pre,_,_=fixture()
        final,_,_=fixture(imports=(('service',1),('late',1)))
        r=s.analyze(pre,generated([('module_layout','0x11'),('service','0x22')]),final,
                    {n:dict(crc=v) for n,v in [('module_layout','0x00000011'),('service','0x00000022'),('late','0x00000033')]})
        self.assertEqual(r['imports_added_after_modpost'],['late'])
        self.assertEqual(r['final_imports_without_versions'],['late'])
        self.assertFalse(r['strict_final_crc_coverage'])

    def test_matching_prelink_imports_produce_complete_final_coverage(self):
        data,_,_=fixture();r=s.analyze(data,generated([('module_layout','0x11'),('service','0x22')]),data,
            {'module_layout':dict(crc='0x00000011'),'service':dict(crc='0x00000022')})
        self.assertTrue(r['strict_final_crc_coverage']);self.assertFalse(r['module_abi_established'])

    def test_unexpected_record_and_modified_version_payload_refused(self):
        data,_,_=fixture();providers={'module_layout':dict(crc='0x00000011'),'service':dict(crc='0x00000022')}
        for rows in ([('module_layout','0x11')],[('module_layout','0x11'),('service','0x23')]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):s.analyze(data,generated(rows),data,providers)

    def test_missing_provider_refused_and_crc_difference_kept_explicit(self):
        data,_,_=fixture();g=generated([('module_layout','0x11'),('service','0x22')])
        with self.assertRaisesRegex(ValueError,'provider'):s.analyze(data,g,data,{})
        r=s.analyze(data,g,data,{'module_layout':dict(crc='0x00000011'),'service':dict(crc='0x00000023')})
        self.assertEqual(r['crc_mismatches'],['service']);self.assertFalse(r['strict_final_crc_coverage'])

    def test_patch_changes_only_prelink_module_flags(self):
        original=b'prefix\n\t$(LD) $(ld_flags) -r -o $(@) tail\nsuffix\n'
        with patch.object(s,'MODPOST_SHA',digest(original)):
            changed=s.patch_modpost(original)
        self.assertEqual(changed.replace(b' $(KBUILD_LDFLAGS_MODULE)',b''),original)

    def test_patch_refuses_wrong_hash_or_duplicate_command(self):
        with self.assertRaises(ValueError):s.patch_modpost(b'wrong')
        original=b'$(LD) $(ld_flags) -r -o $(@)\n'*2
        with patch.object(s,'MODPOST_SHA',digest(original)),self.assertRaises(ValueError):s.patch_modpost(original)

    def test_snapshot_keeps_bytes_and_missing_states(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'obj';p=root/s.FILES[0];p.parent.mkdir(parents=True);p.write_bytes(b'bitcode')
            dest=Path(d)/'capture';r=s.snapshot(root,dest)
            self.assertEqual((dest/s.FILES[0]).read_bytes(),b'bitcode')
            self.assertEqual(r[s.FILES[0]]['sha256'],digest(b'bitcode'))
            self.assertEqual(r[s.FILES[1]],dict(state='missing'))

    def test_snapshot_refuses_links_fifo_and_oversize(self):
        for kind in ('link','fifo','large'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d)/'obj';p=root/s.FILES[0];p.parent.mkdir(parents=True)
                if kind=='link':p.symlink_to(Path(d)/'outside')
                elif kind=='fifo':os.mkfifo(p)
                else:p.write_bytes(b'xx')
                with patch.object(s,'MAX_COPY',1),self.assertRaises(ValueError):s.snapshot(root,Path(d)/'capture')

    def test_snapshot_refuses_replacement_after_open(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'obj';p=root/s.FILES[0];p.parent.mkdir(parents=True);p.write_bytes(b'x')
            with patch.object(s,'identity',side_effect=[1,2]),self.assertRaises(ValueError):s.snapshot(root,Path(d)/'capture')

    def test_existing_snapshot_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'keep';p.write_text('kept')
            with self.assertRaises(ValueError):s.snapshot(root,root)
            self.assertEqual(p.read_text(),'kept')

    def test_link_commands_keep_resolved_flags_and_normalize_work_path(self):
        with tempfile.TemporaryDirectory() as d:
            work=Path(d);evidence=work/'evidence'
            for label in ('original','aligned'):
                for phase,suffix in (('pre','.lto.o'),('final','.ko')):
                    p=evidence/(label+'-'+phase)/('drivers/mfd/.s2mpb02_mfd'+suffix+'.cmd')
                    p.parent.mkdir(parents=True);p.write_text('cmd_target := ld.lld -r -mllvm -import-instr-limit=5 -o '+str(work/'out')+'\n')
            rows=s.link_commands(evidence,work)
            self.assertTrue(all('-import-instr-limit=5' in c and str(work) not in c and '<WORK>' in c for c in rows.values()))

    def test_native_runner_honors_working_directory(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);r=run([sys.executable,'-c','from pathlib import Path; print(Path.cwd())'],
                          dict(os.environ),p/'run.log',timeout=5,cwd=p)
            self.assertEqual(r['returncode'],0);self.assertEqual((p/'run.log').read_text().strip(),str(p))

    def test_existing_work_directory_refused_before_build(self):
        with tempfile.TemporaryDirectory() as d,patch('check_capture_a0_module_stages.run') as native:
            p=Path(d)
            with self.assertRaisesRegex(ValueError,'must be new'):inspect(p,p,p,p,p)
            native.assert_not_called()

    def test_full_runner_alignment_requires_compile_before_reading_inputs(self):
        p=Path('/nonexistent')
        with self.assertRaisesRegex(ValueError,'requires full compilation'):
            full_inspect(p,p,p,p,align_module_prelink=True)

    def test_full_runner_cli_alignment_requires_compile(self):
        script=Path(__file__).with_name('check_capture_a0_build_profile.py')
        args=[sys.executable,str(script),'--align-module-prelink']
        for n in ('source','toolchains','host-root','work-dir'):args+=['--'+n,'/nonexistent']
        r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(r.returncode,2)
        self.assertIn(b'--align-module-prelink requires --compile',r.stderr)


if __name__=='__main__':unittest.main()
