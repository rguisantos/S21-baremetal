#!/usr/bin/env python3
"""Sizing, LMA mapping, metadata and bounded streaming controls without firmware."""
import gzip
import io
from pathlib import Path
import stat
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import capture_a0_sizes as sizes
import capture_a0_modules as normal
import check_capture_a0_sizes as audit
from capture_a0_formats import digest
from test_capture_a0_module_policy import fixture
from test_capture_a0_modules import archive, entry


def kernel_elf():
    data = bytearray(0x3000)
    image = bytearray(64); image[56:60] = b'ARM\x64'
    struct.pack_into('<3Q',image,8,0x80000,0x5000,10)
    data[0x1000:0x1040] = image; data[0x1040:0x1050] = b'N'*16
    data[0x2000:0x2010] = b'D'*16
    names = b'\0.shstrtab\0.text\0.data\0.bss\0.note\0'; data.extend(names)
    rows = [bytes(64)]
    for name,kind,flags,va,off,length in [('.shstrtab',3,0,0,0x3000,len(names)),
            ('.text',1,6,0x4000,0x1000,64),('.data',1,3,0x6000,0x2000,16),
            ('.bss',8,3,0x6010,0,128),('.note',7,2,0x4040,0x1040,16)]:
        rows.append(struct.pack('<IIQQQQIIQQ',names.index(name.encode()),kind,flags,va,off,length,0,0,8,0))
    shoff=len(data);data.extend(b''.join(rows));data[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI',data,16,3,183,1);struct.pack_into('<QQ',data,32,64,shoff)
    struct.pack_into('<6H',data,52,64,56,2,64,len(rows),1)
    struct.pack_into('<II6Q',data,64,1,5,0x1000,0x4000,0x8000,80,0x1000,0x1000)
    struct.pack_into('<II6Q',data,120,1,6,0x2000,0x6000,0x9000,16,144,0x1000)
    return bytes(data),shoff


class ImageTests(unittest.TestCase):
    def test_lma_and_gaps_not_virtual_address_or_whole_load_segment(self):
        data,_=kernel_elf();image,r=sizes.flat_image(data)
        self.assertEqual(len(image),0x1010);self.assertEqual(image[0x1000:],b'D'*16)
        self.assertEqual(image[64:0x1000],bytes(0x1000-64))
        self.assertEqual(r['base_lma'],'0x8000');self.assertEqual(r['file_backed_sections'],2)

    def test_bss_and_removed_note_not_emitted(self):
        data,_=kernel_elf();image,r=sizes.flat_image(data)
        self.assertEqual([s['name'] for s in r['sections']],['.text','.data'])
        self.assertGreater(r['header']['runtime_image_size'],len(image))

    def test_truncated_or_wrong_machine_elf_refused(self):
        data,_=kernel_elf()
        for candidate in (data[:-1],data[:18]+b'\x3e\x00'+data[20:]):
            with self.assertRaises(ValueError):sizes.flat_image(candidate)

    def test_missing_or_ambiguous_lma_refused(self):
        original,_=kernel_elf()
        for ambiguous in (False,True):
            data=bytearray(original)
            if ambiguous:struct.pack_into('<II6Q',data,120,1,6,0x1000,0x4000,0xa000,80,80,0x1000)
            else:struct.pack_into('<Q',data,64+8,0x1800)
            with self.subTest(ambiguous=ambiguous),self.assertRaises(ValueError):sizes.flat_image(data)

    def test_overlapping_allocated_sections_refused(self):
        data,shoff=kernel_elf();data=bytearray(data)
        struct.pack_into('<QQ',data,shoff+3*64+16,0x4000,0x1000)
        with self.assertRaises(ValueError):sizes.flat_image(data)

    def test_outside_file_section_refused(self):
        data,shoff=kernel_elf();data=bytearray(data)
        struct.pack_into('<Q',data,shoff+3*64+24,len(data))
        with self.assertRaises(ValueError):sizes.flat_image(data)

    def test_image_output_budget_checked_before_allocation(self):
        data,_=kernel_elf()
        with patch.object(sizes,'MAX_IMAGE',1024),self.assertRaises(ValueError):sizes.flat_image(data)

    def test_image_header_checks_runtime_extent(self):
        data,_=kernel_elf();image,_=sizes.flat_image(data);bad=bytearray(image)
        struct.pack_into('<Q',bad,16,len(image)-1)
        with self.assertRaises(ValueError):sizes.arm64_header(bad)


class SizeComparisonTests(unittest.TestCase):
    def test_smaller_is_not_an_exact_size_packer_input(self):
        r=sizes.comparison(100,99)
        self.assertTrue(r['not_larger_than_stock']);self.assertFalse(r['current_fixed_size_packer_accepts'])
        self.assertEqual(r['delta_bytes'],-1)

    def test_equal_and_larger_sizes_distinguished(self):
        self.assertTrue(sizes.comparison(100,100)['current_fixed_size_packer_accepts'])
        self.assertFalse(sizes.comparison(100,101)['not_larger_than_stock'])

    def test_invalid_sizes_rejected(self):
        for a,b in [(0,1),(1,-1),(True,1),(1,1.0)]:
            with self.subTest(a=a,b=b),self.assertRaises(ValueError):sizes.comparison(a,b)


class RamdiskTests(unittest.TestCase):
    def test_no_change_retains_original_cpio_bytes_including_padding(self):
        raw=archive(entry('a',b'data'))+bytes(52)
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'out.gz';r=sizes.ramdisk(raw,{},target)
            self.assertEqual(gzip.decompress(target.read_bytes()),raw)
            self.assertEqual(r['cpio_bytes'],len(raw));self.assertEqual(r['entries_verified'],1)

    def test_replacement_retains_metadata_order_and_untouched_entries(self):
        first=bytearray(entry('lib/modules/a.ko',b'old',mode=stat.S_IFREG|0o640))
        first[22:30]=b'00000064';first[30:38]=b'00000065';first[46:54]=b'12345678'
        raw=archive(bytes(first),entry('lib/modules/modules.load',b'a.ko\n'),entry('link',b'../target',stat.S_IFLNK|0o777))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'module';p.write_bytes(b'new longer payload')
            r=sizes.ramdisk(raw,{'lib/modules/a.ko':dict(path=p,bytes=p.stat().st_size,sha256=digest(p.read_bytes()))},root/'out.gz')
            result=gzip.decompress((root/'out.gz').read_bytes());old,_=sizes.records(raw);new,entries=sizes.records(result)
            self.assertEqual([x['name'] for x in old],[x['name'] for x in new])
            for a,b in zip(old,new):self.assertEqual(a['fields'][:6]+a['fields'][7:],b['fields'][:6]+b['fields'][7:])
            self.assertEqual(entries['lib/modules/modules.load']['data'],b'a.ko\n')
            self.assertEqual(entries['link']['data'],b'../target');self.assertEqual(r['modules_replaced'],1)
            self.assertEqual(len(result)%512,0)

    def test_large_output_uses_explicit_stream_limit_without_relaxing_normal_reader(self):
        raw=archive(entry('module',b'a'))
        with tempfile.TemporaryDirectory() as temp,patch.object(normal,'MAX_RAMDISK',1024):
            root=Path(temp);p=root/'m';p.write_bytes(b'X'*8192)
            r=sizes.ramdisk(raw,{'module':dict(path=p,bytes=8192,sha256=digest(p.read_bytes()))},root/'out.gz')
            self.assertGreater(r['cpio_bytes'],1024);self.assertTrue(r['stream_replay_verified'])
            with self.assertRaises(ValueError):normal.gunzip((root/'out.gz').read_bytes())

    def test_unknown_or_non_regular_replacement_refused(self):
        raw=archive(entry('dir',mode=stat.S_IFDIR|0o755))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'m';p.write_bytes(b'')
            for name in ('missing','dir'):
                with self.subTest(name=name),self.assertRaises(ValueError):
                    sizes.ramdisk(raw,{name:dict(path=p,bytes=0,sha256=digest(b''))},root/(name+'.gz'))

    def test_wrong_declared_size_or_hash_refused(self):
        raw=archive(entry('a',b'old'))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'m';p.write_bytes(b'new')
            for i,(size,sha) in enumerate([(4,digest(b'new')),(3,'0'*64)]):
                with self.subTest(size=size),self.assertRaises(ValueError):
                    sizes.ramdisk(raw,{'a':dict(path=p,bytes=size,sha256=sha)},root/(str(i)+'.gz'))

    def test_symlink_source_and_existing_output_refused(self):
        raw=archive(entry('a',b'x'))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'m';p.write_bytes(b'x');link=root/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):sizes.ramdisk(raw,{'a':dict(path=link,bytes=1,sha256=digest(b'x'))},root/'out.gz')
            with self.assertRaises(FileExistsError):sizes.ramdisk(raw,{},p)

    def test_explicit_output_budget_refused(self):
        raw=archive(entry('a',b'x'))
        with tempfile.TemporaryDirectory() as temp,patch.object(sizes,'MAX_CPIO',32),self.assertRaises(ValueError):
            sizes.ramdisk(raw,{},Path(temp)/'out.gz')


class StripTests(unittest.TestCase):
    def allocated_fixture(self):
        data,positions,shoff=fixture(debug=64);data=bytearray(data)
        struct.pack_into('<Q',data,shoff+11*64+8,6)
        return data,positions,shoff

    def test_non_allocated_debug_change_does_not_change_required_runtime_data(self):
        data,positions,_=self.allocated_fixture();other=bytearray(data);other[positions['.debug.fixture']]=1
        self.assertTrue(sizes.strip_equivalence(bytes(data),bytes(other))['metadata_preserved'])

    def test_changed_allocated_text_or_versions_refused(self):
        data,positions,_=self.allocated_fixture()
        for name in ('.text','__versions'):
            other=bytearray(data);other[positions[name]]^=1
            with self.subTest(name=name),self.assertRaises(ValueError):sizes.strip_equivalence(bytes(data),bytes(other))


class InputTests(unittest.TestCase):
    def test_module_copy_drift_refused_before_native_consumption(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'module.ko';p.write_bytes(b'original')
            pin=dict(bytes=8,sha256=digest(b'original'))
            self.assertEqual(audit.module_input(p,pin),b'original')
            for data in (b'orig',b'changed!'):
                p.write_bytes(data)
                with self.subTest(data=data),self.assertRaises(ValueError):audit.module_input(p,pin)

    def test_existing_output_refused_before_native_or_input_read(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(audit.subprocess,'run') as run:
            root=Path(temp)
            with self.assertRaises(ValueError):audit.inspect(root,root/'tar',root/'source',root,root)
            run.assert_not_called()

    def test_wrong_archive_prevents_native_and_output(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(audit.subprocess,'run') as run:
            root=Path(temp);tar=root/'archive';tar.write_bytes(b'bad')
            with self.assertRaises(ValueError):audit.inspect(root,tar,root/'source',root,root/'out')
            run.assert_not_called();self.assertFalse((root/'out').exists())

    def test_selected_archive_paths_types_hashes_and_presence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rows=[dict(name='fixture',source='drivers/a.ko',bytes=1,sha256=digest(b'a'))]
            for index,variant in enumerate(('good','unsafe','link','hash','missing','duplicate')):
                path=root/(variant+'.tar.gz');out=root/variant;out.mkdir()
                with tarfile.open(path,'w:gz') as tar:
                    for name,body in [('vmlinux',b'v')]+([] if variant=='missing' else [('drivers/a.ko',b'b' if variant=='hash' else b'a')]):
                        member=tarfile.TarInfo(name);member.size=len(body)
                        if variant=='link' and name.endswith('.ko'):member.type=tarfile.SYMTYPE;member.linkname='/tmp/a'
                        tar.addfile(member,None if member.issym() else io.BytesIO(body))
                    if variant in ('unsafe','duplicate'):
                        member=tarfile.TarInfo('../escape' if variant=='unsafe' else 'vmlinux');tar.addfile(member)
                if variant=='good':
                    audit.extract_selected(path,rows,out,dict(bytes=1,sha256=digest(b'v')))
                    self.assertEqual((out/'fixture.ko').read_bytes(),b'a')
                else:
                    with self.subTest(variant=variant),self.assertRaises(ValueError):
                        audit.extract_selected(path,rows,out,dict(bytes=1,sha256=digest(b'v')))


if __name__=='__main__':unittest.main()
