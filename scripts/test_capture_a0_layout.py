#!/usr/bin/env python3
"""Readback faults, prefix evidence and ARM64/PE geometry without firmware."""
import io
import json
import os
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import capture_a0_copy as copier
from capture_a0_formats import digest
from capture_a0_layout import explain_delta, pe_layout, prefix_evidence
from check_capture_a0_layout import archive_inventory
from test_capture_a0_module_policy import fixture


def image(code=8192,data_file=1024,data_virtual=4096):
    headers=4096;runtime=headers+code+data_virtual;data=bytearray(headers+code+data_file)
    data[:2]=b'MZ';primary=headers+code-512;struct.pack_into('<I',data,4,0x14000000+((primary-4)//4))
    struct.pack_into('<3Q',data,8,0x80000,runtime,10);data[56:60]=b'ARM\x64';struct.pack_into('<I',data,60,64)
    data[64:68]=b'PE\0\0';struct.pack_into('<HH',data,68,0xaa64,2);struct.pack_into('<H',data,84,160)
    opt=88;struct.pack_into('<H',data,opt,0x20b);struct.pack_into('<5I',data,opt+4,code,data_virtual,0,primary+64,headers)
    struct.pack_into('<II',data,opt+32,4096,512);struct.pack_into('<II',data,opt+56,runtime,headers)
    struct.pack_into('<8s4I',data,248,b'.text',code,headers,code,headers)
    struct.pack_into('<8s4I',data,288,b'.data',data_virtual,headers+code,data_file,headers+code)
    return bytes(data)


class CopyTests(unittest.TestCase):
    def test_destination_is_read_back_with_identity_and_hash(self):
        data=b'reproducible bytes';pin=dict(bytes=len(data),sha256=digest(data))
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'copy';r=copier.copy_checked(io.BytesIO(data),p,pin)
            self.assertEqual(p.read_bytes(),data);self.assertEqual(r['source_sha256'],r['destination_sha256'])
            self.assertTrue(r['destination_readback_verified']);self.assertEqual(r['destination']['bytes'],len(data))

    def test_truncated_or_overlong_or_wrong_hash_source_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            for i,data in enumerate((b'ab',b'abcdef',b'xxxx')):
                with self.subTest(data=data),self.assertRaises(ValueError):
                    copier.copy_checked(io.BytesIO(data),Path(temp)/str(i),dict(bytes=4,sha256=digest(b'abcd')))

    def test_destination_truncated_at_flush_is_refused(self):
        def truncate(fd):os.ftruncate(fd,2)
        with tempfile.TemporaryDirectory() as temp,patch.object(copier.os,'fsync',truncate),self.assertRaises(ValueError):
            copier.copy_checked(io.BytesIO(b'abcd'),Path(temp)/'copy',dict(bytes=4,sha256=digest(b'abcd')))

    def test_same_size_destination_corruption_at_flush_is_refused(self):
        def corrupt(fd):os.pwrite(fd,b'X',0)
        with tempfile.TemporaryDirectory() as temp,patch.object(copier.os,'fsync',corrupt),self.assertRaises(ValueError):
            copier.copy_checked(io.BytesIO(b'abcd'),Path(temp)/'copy',dict(bytes=4,sha256=digest(b'abcd')))

    def test_source_digest_is_not_a_substitute_for_destination_digest(self):
        data=b'original';seen=[]
        def change(fd):seen.append(data);os.pwrite(fd,b'changed!',0)
        with tempfile.TemporaryDirectory() as temp,patch.object(copier.os,'fsync',change):
            with self.assertRaisesRegex(ValueError,'destination SHA'):
                copier.copy_checked(io.BytesIO(data),Path(temp)/'copy',dict(bytes=len(data),sha256=digest(data)))
        self.assertEqual(seen,[data])

    def test_existing_target_and_symlink_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'old';p.write_bytes(b'keep');link=Path(temp)/'link';link.symlink_to(p)
            for target in (p,link):
                with self.assertRaises(FileExistsError):copier.copy_checked(io.BytesIO(b'new'),target,dict(bytes=3,sha256=digest(b'new')))
            self.assertEqual(p.read_bytes(),b'keep')

    def test_copy_budget_and_pin_types_refused_before_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'out'
            for size in (-1,True,copier.MAX_COPY+1):
                with self.subTest(size=size),self.assertRaises(ValueError):copier.copy_checked(io.BytesIO(b''),p,dict(bytes=size,sha256=digest(b'')))
            self.assertFalse(p.exists())


class LayoutTests(unittest.TestCase):
    def test_file_and_runtime_deltas_are_separately_accounted(self):
        r=explain_delta(image(code=12288),image())
        self.assertEqual(r['file_delta_bytes'],-4096);self.assertEqual(r['runtime_delta_bytes'],-4096)
        self.assertEqual(r['section_deltas']['.data']['virtual_bytes'],0)
        self.assertEqual(r['section_deltas']['.data']['file_bytes'],0)
        self.assertEqual(r['section_deltas']['.data']['rva'],-4096)
        self.assertFalse(r['producer_build_cause_identified']);self.assertFalse(r['padding_validated'])

    def test_header_declared_virtual_tail_is_not_file_length(self):
        r=pe_layout(image())
        self.assertEqual(r['virtual_tail_without_file_bytes'],3072)
        self.assertEqual(r['pe_runtime_bytes'],r['linux_header']['runtime_image_size'])

    def test_primary_and_efi_entry_movements_match_fixture_layout(self):
        r=explain_delta(image(code=12288),image())
        self.assertEqual(r['primary_branch_target_delta'],-4096)
        self.assertEqual(r['efi_entry_rva_delta'],-4096)

    def test_overlay_is_reported_and_not_silently_treated_as_source_layout(self):
        padded=image()+bytes(512)
        self.assertEqual(pe_layout(padded)['unmapped_file_tail_bytes'],512)
        with self.assertRaises(ValueError):explain_delta(image(code=12288),padded)

    def test_linux_and_pe_runtime_mismatch_refused(self):
        data=bytearray(image());struct.pack_into('<I',data,88+56,17000)
        with self.assertRaises(ValueError):pe_layout(data)

    def test_wrong_machine_count_optional_magic_or_branch_refused(self):
        for offset,fmt,value in [(68,'H',0x8664),(70,'H',3),(88,'H',0x10b),(4,'I',0x94000000)]:
            data=bytearray(image());struct.pack_into('<'+fmt,data,offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):pe_layout(data)

    def test_invalid_section_bounds_or_overlapping_geometry_refused(self):
        for offset,value in [(288+20,999999),(288+12,4096),(248+16,1)]:
            data=bytearray(image());struct.pack_into('<I',data,offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):pe_layout(data)

    def test_wrong_pe_pointer_and_duplicate_names_refused(self):
        for pointer in (0,0xffffffff):
            data=bytearray(image());struct.pack_into('<I',data,60,pointer)
            with self.assertRaises(ValueError):pe_layout(data)
        data=bytearray(image());data[288:296]=b'.text\0\0\0'
        with self.assertRaises(ValueError):pe_layout(data)


class PrefixTests(unittest.TestCase):
    def test_prefix_hash_and_missing_section_table_are_evidence_not_attribution(self):
        data,_,shoff=fixture(debug=4096);cut=shoff-16
        r=prefix_evidence(data,cut,digest(data[:cut]))
        self.assertTrue(r['recorded_hash_matches_prefix']);self.assertFalse(r['section_table_fits_prefix'])
        self.assertEqual(r['absent_tail_bytes'],len(data)-cut);self.assertFalse(r['historical_mutator_identified'])

    def test_nonmatching_recorded_hash_stays_nonmatching(self):
        data,_,shoff=fixture(debug=4096)
        self.assertFalse(prefix_evidence(data,shoff-16,'0'*64)['recorded_hash_matches_prefix'])

    def test_invalid_full_module_and_prefix_bound_refused(self):
        data,_,shoff=fixture(debug=4096)
        for full,length in [(data,63),(data,len(data)),(data[:-1],shoff-16)]:
            with self.subTest(length=length),self.assertRaises(ValueError):prefix_evidence(full,length,'0'*64)


class ArchiveTests(unittest.TestCase):
    def make(self,root,variant='good'):
        path=root/(variant+'.tar.gz');rows={'a':dict(bytes=3,sha256=digest(b'abc'))}
        manifest=dict(schema='S21-CANDIDATE-ARTIFACTS-v1',files=rows)
        if variant=='hash':rows['a']['sha256']='0'*64
        raw=json.dumps(manifest).encode()
        if variant=='duplicate-json':raw=b'{"schema":"S21-CANDIDATE-ARTIFACTS-v1","files":{},"files":{}}'
        with tarfile.open(path,'w:gz') as tar:
            for name,data in [('a',b'abc'),('manifest.json',raw)]:
                m=tarfile.TarInfo(name);m.size=len(data);tar.addfile(m,io.BytesIO(data))
            if variant in ('duplicate','unsafe','extra','link'):
                m=tarfile.TarInfo({'duplicate':'a','unsafe':'../bad','extra':'unlisted','link':'link'}[variant])
                if variant=='link':m.type=tarfile.SYMTYPE;m.linkname='a'
                tar.addfile(m)
        return path,dict(bytes=path.stat().st_size,sha256=digest(path.read_bytes()),files_verified=1)

    def test_whole_archive_and_all_manifest_payloads_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            p,pin=self.make(Path(temp));r=archive_inventory(p,pin)
            self.assertEqual(r['payloads_verified'],1);self.assertEqual(r['failures'],0)

    def test_wrong_archive_pin_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p,pin=self.make(Path(temp));pin['sha256']='0'*64
            with self.assertRaises(ValueError):archive_inventory(p,pin)

    def test_manifest_member_and_path_faults_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            for variant in ('hash','duplicate-json','duplicate','unsafe','extra','link'):
                p,pin=self.make(Path(temp),variant)
                with self.subTest(variant=variant),self.assertRaises(ValueError):archive_inventory(p,pin)


if __name__=='__main__':unittest.main()
