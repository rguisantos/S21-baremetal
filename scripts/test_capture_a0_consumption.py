#!/usr/bin/env python3
"""Native descriptor binding, pre-consumption refusal and container-coordinate controls."""
import gzip
from copy import deepcopy
from contextlib import ExitStack
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from capture_a0_formats import digest
from capture_a0_inputs import HashingWriter, read_checked, read_sealed, sealed_input
from capture_a0_package_plan import payload_geometry, validate_consumption
import capture_a0_sizes as sizes
from check_capture_a0_sizes import extract_selected
from test_capture_a0_modules import archive,entry


class ConsumptionTests(unittest.TestCase):
    def test_native_consumer_reads_verified_bytes_after_original_path_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'input';p.write_bytes(b'verified');pin=dict(bytes=8,sha256=digest(b'verified'))
            data=read_checked(p,pin)
            with sealed_input(data,pin) as (fd,path):
                p.write_bytes(b'modified')
                self.assertEqual(subprocess.check_output(['cat',path],pass_fds=(fd,)),b'verified')

    def test_native_input_cannot_be_written_grown_or_truncated(self):
        with sealed_input(b'ab',dict(bytes=2,sha256=digest(b'ab'))) as (fd,path):
            for action in (lambda:os.pwrite(fd,b'X',0),lambda:os.ftruncate(fd,1),lambda:os.ftruncate(fd,3)):
                with self.assertRaises(OSError):action()

    def test_descriptor_closed_on_consumer_exception(self):
        with self.assertRaises(RuntimeError):
            with sealed_input(b'a',dict(bytes=1,sha256=digest(b'a'))) as (fd,path):raise RuntimeError('consumer')
        with self.assertRaises(OSError):os.fstat(fd)

    def test_wrong_pin_refused_before_creating_native_input(self):
        with patch('capture_a0_inputs.os.memfd_create') as create,self.assertRaises(ValueError):
            with sealed_input(b'a',dict(bytes=1,sha256='0'*64)):pass
        create.assert_not_called()

    def test_generated_output_short_write_refused(self):
        class Short:
            def write(self,data):return len(data)-1
        with self.assertRaises(ValueError):HashingWriter(Short()).write(b'ab')

    def test_gzip_header_mutation_refused_even_if_decoded_data_stays_equal(self):
        raw=archive(entry('a',b'payload'));original=sizes.read_checked
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'out.gz'
            def changed(path,pin):
                if path==target:
                    data=bytearray(path.read_bytes());data[4]^=1;path.write_bytes(data)
                    self.assertEqual(gzip.decompress(bytes(data)),raw)
                return original(path,pin)
            with patch.object(sizes,'read_checked',changed),self.assertRaises(ValueError):sizes.ramdisk(raw,{},target)

    def test_invalid_replacement_not_emitted_before_verification(self):
        raw=archive(entry('a',b'old'))
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'input';p.write_bytes(b'wrong');out=Path(temp)/'out.gz'
            with self.assertRaises(ValueError):sizes.ramdisk(raw,{'a':dict(path=p,bytes=5,sha256=digest(b'right'))},out)
            self.assertEqual(gzip.decompress(out.read_bytes()),b'')

    def test_archive_parser_uses_checked_snapshot_after_path_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'input.gz'
            with tarfile.open(p,'w:gz') as tar:
                for name,data in [('vmlinux',b'v'),('drivers/a.ko',b'a')]:
                    m=tarfile.TarInfo(name);m.size=len(data);tar.addfile(m,io.BytesIO(data))
            raw=p.read_bytes();checked=read_checked(p,dict(bytes=len(raw),sha256=digest(raw)));p.write_bytes(b'changed')
            out=root/'out';out.mkdir()
            extract_selected(checked,[dict(name='a',source='drivers/a.ko',bytes=1,sha256=digest(b'a'))],out,
                dict(bytes=1,sha256=digest(b'v')))
            self.assertEqual((out/'a.ko').read_bytes(),b'a')

    def test_extraction_snapshots_survive_later_working_copy_truncation(self):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);source=io.BytesIO()
            with tarfile.open(fileobj=source,mode='w:gz') as tar:
                for name,data in [('vmlinux',b'kernel'),('drivers/a.ko',b'complete module')]:
                    m=tarfile.TarInfo(name);m.size=len(data);tar.addfile(m,io.BytesIO(data))
            rows=[dict(name='a',source='drivers/a.ko',bytes=15,sha256=digest(b'complete module'))]
            snapshots={};extract_selected(source.getvalue(),rows,root,dict(bytes=6,sha256=digest(b'kernel')),stack,snapshots)
            (root/'a.ko').write_bytes(b'cut');(root/'vmlinux').write_bytes(b'cut')
            self.assertEqual(read_sealed(snapshots['drivers/a.ko'][0],rows[0]),b'complete module')
            self.assertEqual(subprocess.check_output(['cat',snapshots['vmlinux'][1]],pass_fds=(snapshots['vmlinux'][0],)),b'kernel')

    def test_ramdisk_uses_sealed_payload_instead_of_mutated_working_path(self):
        raw=archive(entry('a',b'old'));data=b'verified replacement';pin=dict(bytes=len(data),sha256=digest(data))
        with tempfile.TemporaryDirectory() as temp,sealed_input(data,pin) as (fd,path):
            out=Path(temp)/'out.gz';sizes.ramdisk(raw,{'a':dict(fd=fd,**pin)},out)
            rows,_=sizes.records(gzip.decompress(out.read_bytes()));self.assertEqual(rows[0]['data'],data)

    def test_unsealed_descriptor_refused_as_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'input';p.write_bytes(b'a')
            with p.open('rb') as file,self.assertRaises((OSError,ValueError)):read_sealed(file.fileno(),dict(bytes=1,sha256=digest(b'a')))


class GeometryTests(unittest.TestCase):
    def fixture(self):
        return dict(kind='boot_v3',page_size=4096,bytes=32768,body_end=16384,parts=[
            dict(name='header',start=0,end=1580,bytes=1580),dict(name='kernel',start=4096,bytes=4097),
            dict(name='ramdisk',start=12288,bytes=4096)])

    def test_one_byte_shrink_crosses_a_page_boundary(self):
        r=payload_geometry(self.fixture(),{'kernel':4096})
        self.assertEqual(r['payloads'][1]['coordinate_delta'],-4096)
        self.assertEqual(r['body_end_delta'],-4096)
        self.assertFalse(r['opaque_signature_and_vbmeta_placement_defined'])

    def test_body_exceeding_stock_file_does_not_infer_partition_capacity(self):
        r=payload_geometry(self.fixture(),{'ramdisk':40000})
        self.assertFalse(r['payload_body_within_stock_file']);self.assertFalse(r['physical_partition_capacity_established'])

    def test_bad_payload_kind_size_or_alignment_refused(self):
        for bad in ({'kernel':True},{'kernel':0},{'unknown':1}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):payload_geometry(self.fixture(),bad)
        f=self.fixture();f['page_size']=8192
        with self.assertRaises(ValueError):payload_geometry(f,{})


class EvidenceTests(unittest.TestCase):
    def fixture(self):
        old=dict(image=dict(sha256='image',comparison={'stock_bytes':2}),modules=[{'name':'a','sha256':'module'}],
            profiles={m:dict(gzip_bytes=2,gzip_sha256='gzip',cpio_bytes=3,cpio_sha256='cpio') for m in ('as_built','strip_debug')})
        new=deepcopy(old);new.update(selected_copy_readbacks_verified=275,consumption=dict(native_inputs_verified=275,
            snapshots_sealed_during_extraction=True,working_copy_paths_reconsumed=False,
            archive_source_and_stock_same_checked_buffers=True,native_objcopy_and_strip_inputs_sealed=True,
            ramdisk_replacements_checked_before_emit=True,gzip_replay_same_checked_buffer=True))
        return old,new

    def test_matching_artifact_hashes_do_not_replace_consumer_binding(self):
        old,new=self.fixture();new['consumption']['native_objcopy_and_strip_inputs_sealed']=False
        with self.assertRaises(ValueError):validate_consumption(new,old)

    def test_changed_module_or_cpio_refused_despite_other_matching_artifacts(self):
        for where in ('module','cpio'):
            old,new=self.fixture()
            if where=='module':new['modules'][0]['sha256']='changed'
            else:new['profiles']['strip_debug']['cpio_sha256']='changed'
            with self.subTest(where=where),self.assertRaises(ValueError):validate_consumption(new,old)


if __name__ == '__main__':unittest.main()
