#!/usr/bin/env python3
"""Natural geometry boundaries and real RSA, independent of private firmware."""
import struct
import unittest
from unittest.mock import Mock

import capture_a0_natural as pack
from capture_a0_container import describe, signature_valid
from capture_a0_formats import layout
from test_capture_a0 import boot, vendor


class NaturalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_capture_a0_container
        cls.crypto=test_capture_a0_container.ContainerTests
        cls.crypto.setUpClass();cls.addClassCleanup(cls.crypto.doClassCleanups)
        body=bytearray(5*4096)
        body[:1580]=boot()[:1580]
        struct.pack_into('<II',body,8,8193,113)
        body[4096:4096+8193]=b'K'*8193;body[16384:16497]=b'R'*113
        cls.original=cls.crypto.fixture(bytes(body),'boot')
        body=bytearray(5*4096);body[:2112]=vendor()[:2112]
        struct.pack_into('<I',body,24,8193)
        body[4096:12289]=b'R'*8193;body[16384:16424]=b'D'*40
        cls.vendor=cls.crypto.fixture(bytes(body),'vendor_boot')

    def signed(self,original=None,replacements=None):
        return pack.seal_lab(self.original if original is None else original,
            {'kernel':b'N'*4097} if replacements is None else replacements,
            self.crypto.public[1],self.crypto.sign)

    def row(self,data,name):return next(r for r in layout(data)['parts'] if r['name']==name)

    def test_empty_reconstruction_is_exact_for_both_formats(self):
        for original in (self.original,self.vendor):
            self.assertEqual(pack.stage(original,{}),original)

    def test_identical_explicit_payload_is_exact(self):
        self.assertEqual(pack.stage(self.original,{'kernel':b'K'*8193}),self.original)

    def test_zero_length_original_ramdisk_remains_absent(self):
        original=self.crypto.original
        self.assertEqual(pack.stage(original,{}),original)

    def test_kernel_shrink_updates_header_and_keeps_natural_length(self):
        out=self.signed();row=self.row(out,'kernel')
        self.assertEqual(row['bytes'],4097);self.assertEqual(out[row['start']:row['end']],b'N'*4097)
        self.assertEqual(struct.unpack_from('<I',out,8)[0],4097)

    def test_kernel_shrink_moves_ramdisk_and_opaque_by_one_page(self):
        out=self.signed()
        self.assertEqual(self.row(out,'ramdisk')['start'],self.row(self.original,'ramdisk')['start']-4096)
        self.assertEqual(layout(out)['body_end'],layout(self.original)['body_end']-4096)

    def test_total_length_and_footer_eof_are_fixed(self):
        out=self.signed();self.assertEqual(len(out),len(self.original));self.assertEqual(out[-64:-60],b'AVBf')

    def test_footer_and_descriptor_follow_new_extent(self):
        a,b=describe(self.original),describe(self.signed())
        self.assertEqual(b['extent'],a['extent']-4096)
        self.assertEqual(b['inventory']['avb']['offset'],a['inventory']['avb']['offset']-4096)
        self.assertEqual(b['inventory']['avb']['hash_descriptors'][0]['image_size'],b['extent'])

    def test_vendor_shrink_moves_dtb_without_changing_it(self):
        out=self.signed(self.vendor,{'ramdisk':b'N'*4097})
        row=self.row(out,'dtb');self.assertEqual(row['start'],self.row(self.vendor,'dtb')['start']-4096)
        self.assertEqual(out[row['start']:row['end']],b'D'*40)

    def test_vendor_rounding_uses_pages_not_raw_size_difference(self):
        out=self.signed(self.vendor,{'ramdisk':b'N'*4096})
        self.assertEqual(self.row(out,'dtb')['start'],self.row(self.vendor,'dtb')['start']-8192)
        self.assertEqual(8193-4096,4097)

    def test_shrink_inside_page_changes_length_without_moving_next_payload(self):
        out=self.signed(replacements={'kernel':b'N'*8192})
        self.assertEqual(self.row(out,'ramdisk')['start'],self.row(self.original,'ramdisk')['start']-4096)
        out=self.signed(replacements={'kernel':b'N'*8194})
        self.assertEqual(self.row(out,'ramdisk')['start'],self.row(self.original,'ramdisk')['start'])

    def test_opaque_full_gap_and_signed_subextent_are_retained(self):
        r=pack.evidence(self.original,self.signed())
        self.assertTrue(r['opaque_bytes_preserved']);self.assertTrue(r['vbmeta_header_preserved'])
        self.assertEqual(r['signed_extension_bytes'],describe(self.original)['extent']-layout(self.original)['body_end'])

    def test_only_length_fields_change_in_android_header(self):
        for original,replacements,offset in [(self.original,{'kernel':b'N'*4097},8),(self.vendor,{'ramdisk':b'N'*4097},24)]:
            out=self.signed(original,replacements);end=self.row(original,'header')['end']
            a,b=bytearray(original[:end]),bytearray(out[:end]);a[offset:offset+4]=b[offset:offset+4]
            self.assertEqual(a,b)

    def test_hash_only_cannot_reuse_stock_signature(self):
        out=pack.rehash(pack.stage(self.original,{'kernel':b'N'*4097}));p=describe(out)
        self.assertTrue(p['inventory']['avb']['all_hashes_match']);self.assertFalse(signature_valid(p))

    def test_lab_authentication_is_valid_and_deterministic(self):
        out=self.signed();self.assertEqual(out,self.signed())
        self.assertTrue(signature_valid(describe(out)));self.assertTrue(layout(out)['avb']['all_hashes_match'])

    def test_payload_tamper_after_signing_is_detected(self):
        out=bytearray(self.signed());out[4096]^=1
        self.assertFalse(layout(bytes(out))['avb']['all_hashes_match'])

    def test_signed_opaque_tamper_is_detected(self):
        out=bytearray(self.signed());out[layout(bytes(out))['body_end']]^=1
        self.assertFalse(layout(bytes(out))['avb']['all_hashes_match'])

    def test_unsigned_opaque_padding_is_not_promoted_to_avb_coverage(self):
        out=bytearray(self.signed());p=describe(bytes(out));out[p['extent']+1]^=1
        r=pack.evidence(self.original,bytes(out))
        self.assertTrue(r['hash_descriptors_match']);self.assertFalse(r['opaque_bytes_preserved'])

    def test_footer_offset_overlapping_body_is_refused(self):
        out=bytearray(self.signed());struct.pack_into('>Q',out,len(out)-64+20,4096)
        with self.assertRaises(ValueError):describe(bytes(out))

    def test_growth_exceeding_fixed_output_bound_is_refused(self):
        with self.assertRaises(ValueError):pack.stage(self.original,{'kernel':b'X'*len(self.original)})

    def test_empty_or_mutable_replacement_is_refused(self):
        for data in (b'',bytearray(b'X'),None):
            with self.subTest(data=type(data)),self.assertRaises(ValueError):pack.stage(self.original,{'kernel':data})

    def test_metadata_replacement_is_refused(self):
        for name in ('header','opaque_extension','vbmeta','avb_footer','unknown'):
            with self.subTest(name=name),self.assertRaises(ValueError):pack.stage(self.original,{name:b'X'})

    def test_wrong_template_hash_prevents_signing(self):
        original=bytearray(self.original);original[4096]^=1;sign=Mock()
        with self.assertRaises(ValueError):pack.seal_lab(bytes(original),{},self.crypto.public[1],sign)
        sign.assert_not_called()

    def test_nonzero_unsigned_tail_is_refused_instead_of_silently_dropped(self):
        original=bytearray(self.original);original[-65]=1
        with self.assertRaises(ValueError):pack.stage(bytes(original),{})

    def test_original_lab_key_is_refused(self):
        with self.assertRaises(ValueError):pack.seal_lab(self.original,{},self.crypto.public[0],self.crypto.sign)

    def test_wrong_signer_key_is_refused(self):
        with self.assertRaises(ValueError):pack.seal_lab(self.original,{},self.crypto.public[1],lambda data:self.crypto.sign(data,0))

    def test_short_signature_is_refused(self):
        with self.assertRaises(ValueError):pack.seal_lab(self.original,{},self.crypto.public[1],lambda data:b'X'*511)

    def test_unsupported_header_version_is_refused(self):
        original=bytearray(self.original);struct.pack_into('<I',original,40,4)
        with self.assertRaises(ValueError):pack.stage(bytes(original),{})

    def test_report_keeps_parent_runtime_and_acceptance_unproved(self):
        r=pack.evidence(self.original,self.signed())
        self.assertEqual(r['parent_vbmeta_status'],'not_supplied_not_assumed_unaffected')
        for name in ('parent_vbmeta_updated','physical_partition_capacity_established','samsung_signerver03_validated',
                'samsung_acceptance_established','module_abi_established','a0_complete','a1_started','physical_action'):
            self.assertFalse(r[name])


if __name__=='__main__':unittest.main()
