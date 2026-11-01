#!/usr/bin/env python3
"""Synthetic controls: unchanged payloads do not imply a valid no-change repack."""
import copy
import gzip
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import capture_a0_formats as fmt
import check_capture_a0 as a0


def boot():
    data = bytearray(8192)
    struct.pack_into('<8s4I', data, 0, b'ANDROID!', 64, 0, 0, 1580)
    struct.pack_into('<I', data, 40, 3)
    data[4096:4160] = b'K'*64
    return bytes(data)


def vendor():
    data = bytearray(12288)
    struct.pack_into('<8s5I', data, 0, b'VNDRBOOT', 3, 4096, 0, 0, 16)
    struct.pack_into('<II', data, 2096, 2112, 40)
    data[4096:4112] = b'R'*16
    data[8192:8232] = b'D'*40
    return bytes(data)


def dt_table():
    data = bytearray(104)
    struct.pack_into('>8I', data, 0, 0xd7b7ab1e, 104, 32, 32, 1, 32, 4096, 0)
    struct.pack_into('>8I', data, 32, 40, 64, 0, 0, 0, 0, 0, 0)
    struct.pack_into('>II', data, 64, 0xd00dfeed, 40)
    return bytes(data)


def signed_container(body=None):
    """Hash descriptor fixture only; deliberately no signature/key trust."""
    prefix = (boot() if body is None else body) + b'SAMSUNG-OPAQUE!'
    offset = fmt.align(len(prefix), 4096)
    name, salt = b'boot', b'salt'
    import hashlib
    wanted = hashlib.sha256(salt+prefix).digest()
    size = fmt.align(132+len(name)+len(salt)+len(wanted), 8)
    desc = bytearray(size)
    struct.pack_into('>3Q', desc, 0, 2, size-16, len(prefix))
    desc[24:30] = b'sha256'
    struct.pack_into('>4I', desc, 56, len(name), len(salt), len(wanted), 0)
    desc[132:132+len(name+salt+wanted)] = name+salt+wanted
    meta = bytearray(256+size)
    meta[:4] = b'AVB0'
    struct.pack_into('>QQ', meta, 12, 0, size)
    struct.pack_into('>QQ', meta, 96, 0, size)
    meta[256:] = desc
    data = bytearray(offset+len(meta)+128)
    data[:len(prefix)] = prefix
    data[offset:offset+len(meta)] = meta
    struct.pack_into('>4sIIQQQ', data, len(data)-64, b'AVBf', 1, 0,
                     len(prefix), offset, len(meta))
    return bytes(data)


class LayoutTests(unittest.TestCase):
    def test_boot_layout_covers_every_byte(self):
        result = fmt.layout(boot())
        self.assertEqual(sum(p['bytes'] for p in result['parts']), len(boot()))
        self.assertEqual(result['kind'], 'boot_v3')

    def test_vendor_payload_locations(self):
        parts = {p['name']:p for p in fmt.layout(vendor())['parts']}
        self.assertEqual(parts['ramdisk']['start'], 4096)
        self.assertEqual(parts['dtb']['start'], 8192)

    def test_dt_table(self):
        result = fmt.layout(dt_table())
        self.assertEqual(result['parts'][-1]['name'], 'dtb_0')
        self.assertFalse(result['dtb_contents_interpreted'])

    def test_unknown_magic(self):
        with self.assertRaises(ValueError):fmt.layout(b'x'*8192)

    def test_header_version(self):
        data = bytearray(boot());struct.pack_into('<I',data,40,4)
        with self.assertRaises(ValueError):fmt.layout(bytes(data))

    def test_truncated_payload(self):
        with self.assertRaises(ValueError):fmt.layout(boot()[:4100])

    def test_reserved_header(self):
        data = bytearray(boot());data[24]=1
        with self.assertRaises(ValueError):fmt.layout(bytes(data))

    def test_vendor_invalid_page(self):
        data = bytearray(vendor());struct.pack_into('<I',data,12,3000)
        with self.assertRaises(ValueError):fmt.layout(bytes(data))

    def test_dt_entry_bounds(self):
        data = bytearray(dt_table());struct.pack_into('>I',data,36,32)
        with self.assertRaises(ValueError):fmt.layout(bytes(data))

    def test_dt_fdt_length(self):
        data = bytearray(dt_table());struct.pack_into('>I',data,68,41)
        with self.assertRaises(ValueError):fmt.layout(bytes(data))


class IntegrityTests(unittest.TestCase):
    def test_original_hash_matches_without_signature_claim(self):
        result = fmt.avb(signed_container())
        self.assertTrue(result['all_hashes_match'])
        self.assertFalse(result['signature_verified'])
        self.assertFalse(result['trusted_key_established'])

    def test_opaque_change_invalidates_hash_despite_unchanged_payloads(self):
        before = signed_container();after = bytearray(before);after[8192] ^= 1
        result = fmt.compare(before, bytes(after))
        self.assertTrue(result['header_and_payloads_identical'])
        self.assertTrue(result['vbmeta_blob_identical'])
        self.assertFalse(result['avb_after']['all_hashes_match'])
        self.assertFalse(result['no_change_gate_passed'])

    def test_footer_change_is_a_failure_even_if_digest_still_matches(self):
        before = signed_container();after = bytearray(before)
        struct.pack_into('>Q',after,len(after)-64+12,8192)
        result = fmt.compare(before,bytes(after))
        self.assertTrue(result['avb_after']['hash_descriptors'][0]['matches'])
        self.assertFalse(result['avb_after']['all_hashes_match'])
        self.assertFalse(result['no_change_gate_passed'])

    def test_vbmeta_truncation_refused(self):
        data=bytearray(signed_container());struct.pack_into('>Q',data,len(data)-64+28,2**32)
        with self.assertRaises(ValueError):fmt.avb(bytes(data))

    def test_descriptor_extent_refused(self):
        data=bytearray(signed_container());off=fmt.avb(bytes(data))['offset']
        struct.pack_into('>Q',data,off+256+8,2**32)
        with self.assertRaises(ValueError):fmt.avb(bytes(data))

    def test_unknown_hash_algorithm_refused(self):
        data=bytearray(signed_container());off=fmt.avb(bytes(data))['offset']
        data[off+256+24:off+256+30]=b'md5xxx'
        with self.assertRaises(ValueError):fmt.avb(bytes(data))

    def test_identical_image_passes_no_change_only(self):
        data=signed_container();result=fmt.compare(data,data)
        self.assertTrue(result['no_change_gate_passed'])
        self.assertFalse(result['signature_or_boot_acceptance_established'])

    def test_difference_report_is_bounded(self):
        before=signed_container();after=bytearray(before)
        for i in range(8300,8500,2):after[i]^=1
        result=fmt.compare(before,bytes(after))
        self.assertEqual(result['different_range_count'],100)
        self.assertEqual(result['different_bytes_in_common_extent'],100)
        self.assertEqual(len(result['first_ranges']),32)

    def test_lossless_reassembly_preserves_tail(self):
        data=signed_container();parts=fmt.layout(data)['parts']
        self.assertEqual(fmt.reassemble(parts,[data[p['start']:p['end']] for p in parts],len(data)),data)

    def test_reassembly_refuses_modified_piece(self):
        data=signed_container();parts=fmt.layout(data)['parts']
        pieces=[data[p['start']:p['end']] for p in parts];pieces[-1]=b'X'*len(pieces[-1])
        with self.assertRaises(ValueError):fmt.reassemble(parts,pieces,len(data))

    def test_reassembly_refuses_gap_and_duplicate(self):
        data=boot();parts=fmt.layout(data)['parts'];pieces=[data[p['start']:p['end']] for p in parts]
        for key,value in (('start',99),('name',parts[0]['name'])):
            altered=copy.deepcopy(parts);altered[1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):fmt.reassemble(altered,pieces,len(data))


class SourceAndExecutionTests(unittest.TestCase):
    def source_fixture(self):
        config=b'CONFIG_EFI=y\n'
        return {'Makefile':b'VERSION = 5\nPATCHLEVEL = 4\nSUBLEVEL = 242\n',
            'arch/arm64/configs/exynos2100-p3sxxx_defconfig':config,
            'arch/arm64/kernel/head.S':b'ENTRY(stext)\nbl\tpreserve_boot_args\nbl\tel2_setup // EL change\nENDPROC(stext)\nbl\tel2_setup\n'},b'IKCFG_ST'+gzip.compress(config)+b'IKCFG_ED'

    def test_entry_evidence_scoped_to_primary_source_not_final_elf(self):
        members,kernel=self.source_fixture();result=a0.source_report(members,kernel)
        self.assertEqual(result['entry_source_lines']['bl\tel2_setup'],3)
        self.assertFalse(result['final_elf_checked'])
        self.assertFalse(result['module_abi_established'])
        self.assertEqual(result['config_differences'],[])

    def test_entry_missing_or_reordered_refused(self):
        members,kernel=self.source_fixture()
        for head in (b'ENTRY(stext)\nENDPROC(stext)',b'ENTRY(stext)\nbl\tel2_setup\nbl\tpreserve_boot_args\nENDPROC(stext)'):
            members['arch/arm64/kernel/head.S']=head
            with self.subTest(head=head),self.assertRaises(ValueError):a0.source_report(members,kernel)

    def test_config_not_set_and_duplicate(self):
        self.assertEqual(fmt.config_values('# CONFIG_FOO is not set'),{'CONFIG_FOO':'n'})
        with self.assertRaises(ValueError):fmt.config_values('CONFIG_FOO=y\nCONFIG_FOO=n')

    def test_config_diff_does_not_leak_host_path(self):
        result=fmt.config_diff('CONFIG_PATH="relative"\n','CONFIG_PATH="/private/build/host"\nCONFIG_KMI=y\n')
        self.assertEqual([r['key'] for r in result],['CONFIG_KMI','CONFIG_PATH'])
        self.assertNotIn('/private',json.dumps(result))

    def test_ikconfig_exact_extent(self):
        config=b'CONFIG_FOO=y\n';image=b'ARM64'+b'IKCFG_ST'+gzip.compress(config)+b'IKCFG_ED'
        self.assertEqual(fmt.ikconfig(image),config)
        with self.assertRaises(ValueError):fmt.ikconfig(image+b'IKCFG_ST')

    def test_ikconfig_truncated_or_bomb(self):
        for raw in (gzip.compress(b'X')[:-2],gzip.compress(b'X'*(1024*1024+1))):
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):fmt.ikconfig(b'IKCFG_ST'+raw+b'IKCFG_ED')

    def test_source_duplicate_or_link_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'source.tar.gz'
            for link in (False,True):
                with tarfile.open(path,'w:gz') as archive:
                    for _ in range(1 if link else 2):
                        member=tarfile.TarInfo('Makefile')
                        if link:member.type=tarfile.SYMTYPE;member.linkname='/private'
                        else:member.size=1
                        archive.addfile(member,None if link else io.BytesIO(b'x'))
                with self.assertRaises(ValueError):a0.source_members(path,{'Makefile'})

    def test_source_missing_member_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'source.tar.gz'
            with tarfile.open(path,'w:gz'):pass
            with self.assertRaises(ValueError):a0.source_members(path,{'Makefile'})

    def test_wrong_input_prevents_native_execution_and_output_creation(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(a0,'run_tool') as tool:
            root=Path(temp);(root/'boot.img.lz4').write_bytes(b'bad')
            pins={'stock_lz4':{'boot.img.lz4':{'bytes':3,'sha256':'0'*64}}}
            with self.assertRaises(ValueError):a0.analyse(root,root/'source',root/'apk',root/'out',pins)
            tool.assert_not_called();self.assertFalse((root/'out').exists())

    def test_wrong_apk_prevents_archive_read_and_native_execution(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(a0,'source_members') as read,patch.object(a0,'run_tool') as tool:
            root=Path(temp)
            for name in ('boot.img.lz4','source','apk'):(root/name).write_bytes(b'123')
            good={'bytes':3,'sha256':fmt.digest(b'123')}
            pins={'stock_lz4':{'boot.img.lz4':good},'samsung_source_archive':good,
                  'magisk':{'apk':{'bytes':3,'sha256':'0'*64}}}
            with self.assertRaises(ValueError):a0.analyse(root,root/'source',root/'apk',root/'out',pins)
            read.assert_not_called();tool.assert_not_called();self.assertFalse((root/'out').exists())

    def test_native_environment_and_vendor_success_code(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(a0.subprocess,'run') as run:
            run.return_value.returncode=3;run.return_value.stdout=b'vendor header\n'
            rc=a0.run_tool(Path('/verified/tool'),['unpack','-n','-h','vendor_boot.img'],Path(temp),(3,))
            self.assertEqual(rc,3)
            self.assertEqual(set(run.call_args.kwargs['env']),{'PATH','LC_ALL'})
            self.assertEqual(run.call_args.kwargs['env']['LC_ALL'],'C')
            with self.assertRaises(ValueError):a0.run_tool(Path('/verified/tool'),[],Path(temp),(0,))


if __name__ == '__main__':
    unittest.main()
