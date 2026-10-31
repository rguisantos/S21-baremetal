#!/usr/bin/env python3
"""Test narrow SRAM declaration grammar, host ABI and source-hash refusals."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import inspect_flop_acpm_reference as ref

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/flop-acpm-reference.json').read_text())


class GrammarTests(unittest.TestCase):
    def test_fixed_width_fields_and_comments(self):
        self.assertEqual(ref.struct_fields('struct sample {u32 id; /* comment */ u8 flag;};','sample'),[('u32','id'),('u8','flag')])

    def test_kernel_conditional_selects_u32_not_host_pointer(self):
        text='''struct sample {
#if !(defined(CONFIG_EXYNOS_ACPM) || defined(CONFIG_EXYNOS_ACPM_MODULE))
void *address;
#else
u32 address;
#endif
u8 enabled;
};'''
        self.assertEqual(ref.struct_fields(text,'sample'),[('u32','address'),('u8','enabled')])

    def test_unknown_preprocessor_pointer_array_or_function_refused(self):
        for body in ('#include "other.h"\nu32 x;','void *x;','u32 x[4];','u32 (*fn)(void);','#define N 1\nu32 x;'):
            with self.subTest(body=body),self.assertRaises(ValueError):ref.struct_fields('struct sample {'+body+'};','sample')

    def test_missing_duplicate_struct_or_field_refused(self):
        for text in ('struct sample {};','struct sample {u32 x;u32 x;};','struct sample {u32 x;};struct sample {u32 y;};','struct other {u32 x;};'):
            with self.subTest(text=text),self.assertRaises(ValueError):ref.struct_fields(text,'sample')

    def test_invalid_name_is_not_interpolated_into_regex_or_c(self):
        with self.assertRaises(ValueError):ref.struct_fields('','sample; int main(void)')


class ProbeTests(unittest.TestCase):
    def test_probe_measures_padding_and_nested_struct_offset(self):
        r=ref.host_layout([('timer_desc',[('u32','period'),('u32','count')]),
            ('sample',[('u8','flag'),('struct timer_desc','timer'),('u32','end')])])
        self.assertEqual(r,{'timer_desc.bytes':8,'timer_desc.period':0,'timer_desc.count':4,
            'sample.bytes':16,'sample.flag':0,'sample.timer':4,'sample.end':12})

    def test_probe_refuses_unsafe_grammar_before_compiler(self):
        with patch('inspect_flop_acpm_reference.subprocess.run') as cc:
            with self.assertRaises(ValueError):ref.host_layout([('sample',[('u32','x;}; int main(void){return 0;}')])])
            cc.assert_not_called()

    def test_missing_compiler_is_an_error(self):
        with self.assertRaises(OSError):ref.host_layout([('sample',[('u32','x')])],cc='/not-an-installed-compiler')


class SourceTests(unittest.TestCase):
    def make_sources(self,path):
        rows=[]
        for i,name in enumerate(sorted(ref.FILES)):
            p=path/name;p.parent.mkdir(parents=True,exist_ok=True);data=('fixture'+str(i)).encode();p.write_bytes(data)
            rows.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),blob_sha1=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()))
        manifest=path/'manifest.json';manifest.write_text(json.dumps(dict(repository='FlopKernel-Series/flop_exynos2100_kernel',commit=ref.COMMIT,files=rows)))
        return manifest,rows

    def test_exact_size_sha256_and_git_blob_checked(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,rows=self.make_sources(root)
            with patch.object(ref,'MANIFEST',manifest):
                texts,_=ref.verify_sources(root);self.assertEqual(len(texts),8)
                (root/rows[0]['path']).write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'source bytes differ'):ref.verify_sources(root)

    def test_manifest_revision_and_duplicate_paths_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);manifest,rows=self.make_sources(root);m=json.loads(manifest.read_text())
            for changed in (dict(m,commit='wrong'),dict(m,files=rows+[rows[0]])):
                manifest.write_text(json.dumps(changed))
                with patch.object(ref,'MANIFEST',manifest),self.assertRaisesRegex(ValueError,'manifest'):ref.verify_sources(root)

    def test_bad_firmware_refused_before_source_or_compiler(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.bin';p.write_bytes(b'bad')
            with patch.object(ref,'verify_sources') as sources,patch.object(ref,'host_layout') as cc:
                with self.assertRaisesRegex(ValueError,'unsupported image'):ref.inspect(d,p)
                sources.assert_not_called();cc.assert_not_called()

    def test_bad_source_refused_before_compiler(self):
        with patch.object(ref,'read_exact',return_value=b''),patch.object(ref,'verify_sources',side_effect=ValueError('bad source')),patch.object(ref,'host_layout') as cc:
            with self.assertRaisesRegex(ValueError,'bad source'):ref.inspect('unused','unused')
            cc.assert_not_called()


class PublishedReferenceTests(unittest.TestCase):
    def test_stride_and_channel_offsets_match_binary_reference(self):
        r=REPORT['layout'];self.assertEqual((r['plugin.bytes'],r['ipc_channel.bytes']),(48,72))
        self.assertEqual(REPORT['channel3']['offsets'],dict(rx_base=24,tx_base=48,q_len=52,q_elem_size=56,mbox_addr=64))
        self.assertEqual(REPORT['mailbox_constants'],dict(INTGR0=8,INTSR1=40,INTCR1=32))

    def test_orientation_and_namespace_have_explicit_limits(self):
        self.assertTrue(all(REPORT['kernel_buffer_orientation'].values()))
        self.assertTrue(REPORT['ect']['namespace_agrees'])
        self.assertFalse(REPORT['ect']['same_runtime_parser_or_data_version_proven'])
        self.assertFalse(REPORT['channel3']['physical_alias_verified'])
        self.assertFalse(REPORT['kernel_or_firmware_executed'])
        self.assertEqual(REPORT['source_files'],8)


if __name__=='__main__':unittest.main()
