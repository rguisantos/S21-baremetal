#!/usr/bin/env python3
"""Controls for completed-build provenance and all-module phase metadata."""
import copy
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import capture_a0_aligned_build as a
from capture_a0_build import CRITICAL
from capture_a0_formats import digest
from capture_a0_module_policy import Elf
from capture_a0_module_stages import imports
from test_capture_a0_module_policy import fixture, subject
from test_capture_a0_stack_versions import generated


CONFIG='\n'.join(k+'='+v for k,v in CRITICAL.items()).encode()+b'\n'


def report():
    return dict(stages=dict(full_build=dict(returncode=0,timed_out=False)),
        full_build_completed=True,build_result_state='finished',final_config_unchanged=True,
        module_prelink_patch=dict(before_sha256=a.MODPOST_SHA,after_sha256=digest(b'patched')),
        final_profile=dict(critical_profile_preserved=True,generated_config_sha256=digest(CONFIG)),
        candidate_comparison=dict(sha256=digest(b'exports')))


class AlignedBuildTests(unittest.TestCase):
    def validate(self,r=None,config=CONFIG,exports=b'exports',makefile=b'patched',reference=CONFIG):
        with patch.object(a,'ALIGNED_SHA',digest(b'patched')):
            return a.completed_build(r or report(),config,exports,makefile,reference)

    def test_completed_build_keeps_reference_config_distinct_from_source_defconfig(self):
        r=self.validate();self.assertTrue(r['reference_config_equal'])
        self.assertTrue(r['critical_profile_preserved']);self.assertNotIn('source_defconfig_equal',r)

    def test_incomplete_failed_or_timed_out_build_refused(self):
        cases=[]
        for key,value in [('full_build_completed',False),('build_result_state','running')]:
            r=report();r[key]=value;cases.append(r)
        for key,value in [('returncode',2),('timed_out',True)]:
            r=report();r['stages']['full_build'][key]=value;cases.append(r)
        for r in cases:
            with self.subTest(r=r),self.assertRaises(ValueError):self.validate(r)

    def test_patch_label_and_actual_makefile_both_must_match(self):
        with self.assertRaises(ValueError):self.validate(makefile=b'original')
        r=report();r['module_prelink_patch']['before_sha256']='0'*64
        with self.assertRaises(ValueError):self.validate(r)

    def test_reference_config_drift_and_false_critical_profile_refused(self):
        with self.assertRaises(ValueError):self.validate(reference=CONFIG+b'# other\n')
        cfg=CONFIG.replace(b'CONFIG_CFI_CLANG=y',b'CONFIG_CFI_CLANG=n');r=report()
        r['final_profile']['generated_config_sha256']=digest(cfg)
        with self.assertRaises(ValueError):self.validate(r,config=cfg,reference=cfg)

    def test_recorded_config_and_export_hashes_checked(self):
        with self.assertRaises(ValueError):self.validate(exports=b'changed')
        r=report();r['final_profile']['generated_config_sha256']='0'*64
        with self.assertRaises(ValueError):self.validate(r)

    def test_phase_late_import_is_reported_by_name(self):
        pre,_,_=fixture()
        final=dict(imports={'service':'strong','late':'strong'},versions={'module_layout':'0x00000011','service':'0x00000022'})
        r=a.phase_metadata(pre,generated([('module_layout','0x11'),('service','0x22')]),final)
        self.assertEqual(r['imports_added_after_modpost'],['late'])
        self.assertEqual(r['final_imports_without_version'],['late'])

    def test_unused_version_is_distinct_from_missing_final_version(self):
        pre,_,_=fixture();rows=[('module_layout','0x11'),('service','0x22'),('unused','0x33')]
        final=dict(imports={'service':'strong'},versions={'module_layout':'0x00000011','service':'0x00000022','unused':'0x00000033'})
        r=a.phase_metadata(pre,generated(rows),final)
        self.assertEqual(r['unused_version_records'],['unused']);self.assertFalse(r['final_imports_without_version'])

    def test_generated_source_must_match_final_payload(self):
        pre,_,_=fixture();final=dict(imports={'service':'strong'},versions={'module_layout':'0x00000011','service':'0x00000023'})
        with self.assertRaises(ValueError):a.phase_metadata(pre,generated([('module_layout','0x11'),('service','0x22')]),final)

    def test_metadata_changes_do_not_hide_added_removed_or_changed_crcs(self):
        old={'client':subject(versions={'module_layout':'0x00000011','removed':'0x00000022'})}
        new=copy.deepcopy(old);new['client']['versions']={'module_layout':'0x00000033','added':'0x00000044'}
        r=a.metadata_changes(old,new)['version_changes']['client']
        self.assertEqual(r['added'],{'added':'0x00000044'});self.assertEqual(r['removed'],{'removed':'0x00000022'})
        self.assertEqual(r['changed']['module_layout'],dict(before='0x00000011',after='0x00000033'))
        with self.assertRaises(ValueError):a.metadata_changes(old,{})

    def test_existing_output_refused_before_opening_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'keep';path.write_text('retained')
            args=[sys.executable,str(Path(__file__).with_name('check_capture_a0_aligned_build.py'))]
            for n in ('build-dir','vendor-boot','source','reference-artifacts'):args+=['--'+n,'/nonexistent']
            r=subprocess.run(args+['--output',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(r.returncode,1);self.assertIn(b'output must be new',r.stderr)
            self.assertEqual(path.read_text(),'retained')

    def test_split_lto_sections_use_a_larger_explicit_budget_than_final_modules(self):
        original,_,table=fixture();count=struct.unpack_from('<H',original,60)[0]
        rows=[list(struct.unpack_from('<IIQQQQIIQQ',original,table+64*i)) for i in range(count)]
        strings=bytearray(original[rows[1][4]:rows[1][4]+rows[1][5]])
        for i in range(5000):
            name=len(strings);strings.extend(('.split'+str(i)).encode()+b'\0')
            rows.append([name,1,0,0,64,0,0,0,1,0])
        data=bytearray(original[:table]);rows[1][4]=len(data);rows[1][5]=len(strings);data.extend(strings)
        newtable=len(data);data.extend(b''.join(struct.pack('<IIQQQQIIQQ',*row) for row in rows))
        struct.pack_into('<Q',data,40,newtable);struct.pack_into('<H',data,60,len(rows))
        self.assertEqual(imports(data),{'service':'strong'})
        with self.assertRaises(ValueError):Elf(data)

    def test_section_budget_cannot_be_unbounded(self):
        data,_,_=fixture()
        for limit in (0,16385,'unlimited'):
            with self.subTest(limit=limit),self.assertRaisesRegex(ValueError,'section count budget'):Elf(data,max_sections=limit)


if __name__=='__main__':unittest.main()
