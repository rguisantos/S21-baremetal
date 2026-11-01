#!/usr/bin/env python3
"""Malformed container/module controls and candidate CRC comparison fixtures."""
import gzip
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch

import capture_a0_modules as m
import check_capture_a0_modules as audit
from capture_a0_formats import align
from test_capture_a0 import vendor, signed_container


def entry(name, data=b'', mode=stat.S_IFREG|0o644, links=1):
    name = name.encode()+b'\0'
    fields = [0, mode, 0, 0, links, 0, len(data), 0, 0, 0, 0, len(name), 0]
    header = b'070701'+b''.join(f'{n:08x}'.encode() for n in fields)+name
    return header+b'\0'*(align(len(header),4)-len(header))+data+b'\0'*(align(len(data),4)-len(data))


def archive(*entries):
    return b''.join(entries)+entry('TRAILER!!!')


def elf(versions=None, modinfo=None):
    versions = versions if versions is not None else [('module_layout', 0x12345678), ('service', 0x87654321)]
    raw = b''.join(struct.pack('<Q',crc)+name.encode().ljust(56,b'\0') for name,crc in versions)
    info = modinfo if modinfo is not None else b'name=fixture\0vermagic=fixture SMP modversions aarch64\0depends=\0'
    names = b'\0.shstrtab\0.modinfo\0__versions\0'
    payloads = [('.shstrtab', 3, names), ('.modinfo',1,info), ('__versions',1,raw)]
    data = bytearray(64); rows=[bytes(64)]
    for name,kind,payload in payloads:
        rows.append(struct.pack('<IIQQQQIIQQ',names.index(name.encode()),kind,0,0,len(data),len(payload),0,0,1,0))
        data.extend(payload)
    shoff=len(data);data.extend(b''.join(rows))
    data[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI',data,16,1,183,1)
    struct.pack_into('<Q',data,40,shoff)
    struct.pack_into('<6H',data,52,64,0,0,64,4,1)
    return bytes(data)


def image(load=b'fixture.ko\n', dep=b'/lib/modules/fixture.ko:\n'):
    raw=archive(entry('lib/modules/fixture.ko',elf()),entry('lib/modules/modules.load',load),
                entry('lib/modules/modules.dep',dep))
    compressed=gzip.compress(raw,mtime=0);body=bytearray(vendor())
    struct.pack_into('<I',body,24,len(compressed));body[4096:4096+len(compressed)]=compressed
    return signed_container(bytes(body))


class ArchiveTests(unittest.TestCase):
    def test_regular_archive_and_gzip(self):
        raw=archive(entry('lib/a',b'payload'))
        self.assertEqual(m.cpio(m.gunzip(gzip.compress(raw)))['lib/a']['data'],b'payload')

    def test_unsafe_or_duplicate_names(self):
        for name in ('../escape','/absolute','a/../b','a//b','./a'):
            with self.subTest(name=name),self.assertRaises(ValueError):m.cpio(archive(entry(name)))
        with self.assertRaises(ValueError):m.cpio(archive(entry('a'),entry('a')))

    def test_regular_hardlink_refused(self):
        with self.assertRaises(ValueError):m.cpio(archive(entry('a',links=2)))

    def test_symlink_is_not_followed(self):
        result=m.cpio(archive(entry('a',b'/outside',stat.S_IFLNK|0o777)))
        self.assertEqual(result['a']['kind'],stat.S_IFLNK)

    def test_truncated_missing_trailer_and_appended_archive(self):
        for raw in (entry('a'),archive(entry('a'))[:-1],archive(entry('a'))+archive(entry('b'))):
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):m.cpio(raw)

    def test_bad_name_and_hex(self):
        raw=bytearray(archive(entry('a')));raw[111]=1
        with self.assertRaises(ValueError):m.cpio(bytes(raw))
        raw[6]=ord('z')
        with self.assertRaises(ValueError):m.cpio(bytes(raw))

    def test_concatenated_and_truncated_gzip(self):
        raw=gzip.compress(b'a')
        for bad in (raw+raw,raw[:-1]):
            with self.assertRaises(ValueError):m.gunzip(bad)

    def test_decompression_budget(self):
        with patch.object(m,'MAX_RAMDISK',100),self.assertRaises(ValueError):m.gunzip(gzip.compress(b'a'*101))


class ElfTests(unittest.TestCase):
    def test_fixture_identity_and_crc(self):
        info,versions=m.module(elf())
        self.assertEqual(info['version_count'],2)
        self.assertEqual(versions['module_layout'],'0x12345678')

    def test_wrong_class_endian_machine_or_kind(self):
        for offset,value in ((4,1),(5,2),(16,2),(18,62)):
            data=bytearray(elf());data[offset]=value
            with self.subTest(offset=offset),self.assertRaises(ValueError):m.module(bytes(data))

    def test_section_bounds(self):
        data=bytearray(elf());shoff=struct.unpack_from('<Q',data,40)[0]
        struct.pack_into('<Q',data,shoff+3*64+32,len(data)+1)
        with self.assertRaises(ValueError):m.module(bytes(data))

    def test_duplicate_section_name(self):
        data=bytearray(elf());shoff=struct.unpack_from('<Q',data,40)[0]
        data[shoff+3*64:shoff+3*64+4]=data[shoff+2*64:shoff+2*64+4]
        with self.assertRaises(ValueError):m.module(bytes(data))

    def test_missing_layout_duplicate_crc_high_bits_and_long_name(self):
        for rows in ([('service',1)],[('module_layout',1)]*2,[('module_layout',1<<32)],[('a'*56,1)]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):m.module(elf(rows))

    def test_incomplete_version_record(self):
        data=bytearray(elf());shoff=struct.unpack_from('<Q',data,40)[0]
        struct.pack_into('<Q',data,shoff+3*64+32,127)
        with self.assertRaises(ValueError):m.module(bytes(data))

    def test_ambiguous_or_missing_modinfo(self):
        for info in (b'name=x\0', b'name=x\0name=y\0vermagic=v\0depends=\0'):
            with self.assertRaises(ValueError):m.module(elf(modinfo=info))


class ComparisonTests(unittest.TestCase):
    def setUp(self):self.required=m.requirements({'a':{'service':'0x12345678'}})

    def test_matching_crc_does_not_approve_abi(self):
        result=m.compare_symvers(self.required,'0x12345678 service vmlinux EXPORT_SYMBOL\n')
        self.assertTrue(result['crc_coverage_passed']);self.assertFalse(result['module_abi_established'])

    def test_changed_crc_and_missing_symbol_fail(self):
        for text in ('0x12345679 service vmlinux EXPORT_SYMBOL',''):
            self.assertFalse(m.compare_symvers(self.required,text)['crc_coverage_passed'])

    def test_stock_conflict_not_overwritten(self):
        r=m.requirements({'a':{'service':'0x12345678'},'b':{'service':'0x12345679'}})
        self.assertEqual(len(r['service']['crcs']),2)
        self.assertFalse(m.compare_symvers(r,'0x12345678 service vmlinux EXPORT_SYMBOL')['crc_coverage_passed'])

    def test_duplicate_or_malformed_symvers(self):
        row='0x12345678 service vmlinux EXPORT_SYMBOL'
        for text in (row+'\n'+row,'123 service vmlinux EXPORT_SYMBOL',row+' ns extra'):
            with self.assertRaises(ValueError):m.compare_symvers(self.required,text)

    def test_namespace_column_accepted_without_claim(self):
        self.assertTrue(m.compare_symvers(self.required,'0x12345678 service vmlinux EXPORT_SYMBOL_GPL NS')['crc_coverage_passed'])

    def test_empty_requirements_do_not_pass(self):
        self.assertFalse(m.compare_symvers({},'')['crc_coverage_passed'])


class IntegrationTests(unittest.TestCase):
    def test_inventory_is_offline_not_candidate_approval(self):
        r=audit.inventory(image())
        self.assertEqual(r['module_count'],1);self.assertEqual(r['unique_versioned_symbols'],2)
        self.assertFalse(r['candidate_comparison']['supplied']);self.assertFalse(r['a0_complete'])
        self.assertEqual(r['modules_load']['missing_files'],[])

    def test_duplicate_load_refused_missing_load_reported(self):
        with self.assertRaises(ValueError):audit.inventory(image(load=b'fixture.ko\nfixture.ko\n'))
        r=audit.inventory(image(load=b'missing.ko\n'))
        self.assertEqual(r['modules_load']['missing_files'],['lib/modules/missing.ko'])

    def test_missing_dependency_refused(self):
        with self.assertRaises(ValueError):audit.inventory(image(dep=b'/lib/modules/fixture.ko: /lib/modules/missing.ko\n'))

    def test_unpinned_input_refused_before_source_read(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(audit,'source_members') as read:
            p=Path(tmp)/'bad';p.write_bytes(b'bad')
            with self.assertRaises(ValueError):audit.inspect(p,p)
            read.assert_not_called()


if __name__ == '__main__':unittest.main()
