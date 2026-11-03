#!/usr/bin/env python3
"""Synthetic input-consumption, copy-limit and kallsyms refusal controls."""
import io
import json
import os
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from capture_a0_formats import align, digest
from capture_a0_inputs import checked_buffer, read_checked, select_members
import capture_a0_kallsyms as k
import check_capture_a0_handoff as h
from test_capture_a0_layout import image


def symbols_fixture(stock=False, extra=270, duplicate=False):
    init = 0x40000 if stock else 0x30000; before = init-(0xc000 if stock else 0x2000)
    notes = before-5*4096-128
    values = dict(_text=0, _stext=4096, _etext=65536, __start_rodata=65536,
        __end_rodata=notes & -4096, __start_notes=notes-48, __stop_notes=notes,
        idmap_pg_dir=before-5*4096, idmap_pg_end=before-2*4096,
        reserved_pg_dir=before-2*4096, swapper_pg_dir=before-4096,
        __init_begin=init, stext=init, __initdata_begin=init+65536,
        _edata=init+65536+1024, _end=init+65536+4096)
    rows = [(k.LINK_BASE+a,'T',n) for n,a in values.items()]
    rows += [(k.LINK_BASE+0x10000+i,'r','fixture_'+str(i)) for i in range(extra)]
    if duplicate: rows.append((k.LINK_BASE+values['_end'],'T','_end'))
    rows.sort(); count = len(rows)
    data = bytearray(image(code=init+65536-4096)); struct.pack_into('<I',data,4,0x14000000+(init-4)//4)
    struct.pack_into('<I',data,88+16,init+64)
    start = 0x12000; offsets = b''.join(struct.pack('<I',a-k.LINK_BASE) for a,t,n in rows)
    data[start:start+len(offsets)] = offsets; base_at = align(start+len(offsets),8)
    struct.pack_into('<QQ',data,base_at,k.LINK_BASE,count)
    cursor = base_at+16; names_at = cursor; marks = []
    for i,(a,t,n) in enumerate(rows):
        if i%256==0:marks.append(cursor-names_at)
        raw=(t+n).encode(); data[cursor:cursor+1+len(raw)] = bytes([len(raw)])+raw; cursor += len(raw)+1
    names_end = cursor; marker_at = align(cursor,8)
    data[marker_at:marker_at+4*len(marks)] = struct.pack('<'+str(len(marks))+'I',*marks)
    table = align(marker_at+4*len(marks),8); tokens=[]; indexes=[]; cursor=table
    for i in range(256):
        token=bytes([i]) if 32<=i<127 else b'';indexes.append(cursor-table)
        data[cursor:cursor+len(token)+1]=token+b'\0';cursor+=len(token)+1
    index=align(cursor,8);data[index:index+512]=struct.pack('<256H',*indexes)
    raw_map=''.join(f'{a:016x} {t} {n}\n' for a,t,n in rows).encode()
    return bytes(data),raw_map,dict(offsets=start,base=base_at,names=names_at,names_end=names_end,
        markers=marker_at,table=table,index=index,count=count)


class SymbolTests(unittest.TestCase):
    def test_all_names_markers_addresses_match_independent_map(self):
        data,reference,meta=symbols_fixture();rows,r=k.decode(data)
        self.assertEqual(r['symbol_count'],meta['count'])
        self.assertEqual(k.compare_map(rows,reference)['decoded_symbols_matched'],len(rows))
        self.assertTrue(r['all_markers_verified']);self.assertTrue(r['image_boundaries_verified'])

    def test_alignment_mechanism_does_not_claim_upstream_producer(self):
        a,_,_=symbols_fixture(stock=True);b,_,_=symbols_fixture();r=k.alignment_delta(a,b)
        self.assertEqual(r['pre_alignment_delta_bytes'],-24576)
        self.assertEqual(r['alignment_padding_delta_bytes'],-40960)
        self.assertEqual(r['init_boundary_delta_bytes'],-65536)
        self.assertFalse(r['source_producer_cause_identified']);self.assertFalse(r['stock_elf_section_table_available'])

    def test_corrupt_or_overlong_count_refused(self):
        data,_,m=symbols_fixture()
        for count in (0,k.MAX_SYMBOLS+1,0xffffffffffffffff):
            b=bytearray(data);struct.pack_into('<Q',b,m['base']+8,count)
            with self.subTest(count=count),self.assertRaises(ValueError):k.decode(bytes(b))

    def test_unsorted_or_outside_runtime_offsets_refused(self):
        data,_,m=symbols_fixture()
        for pos,value in [(m['offsets'],999999),(m['offsets']+(m['count']-1)*4,0xffffffff)]:
            b=bytearray(data);struct.pack_into('<I',b,pos,value)
            with self.subTest(pos=pos),self.assertRaises(ValueError):k.decode(bytes(b))

    def test_every_marker_is_verified(self):
        data,_,m=symbols_fixture();b=bytearray(data);b[m['markers']+4]^=1
        with self.assertRaises(ValueError):k.decode(bytes(b))

    def test_token_index_mismatch_refused(self):
        data,_,m=symbols_fixture();b=bytearray(data);b[m['index']+498]^=1
        with self.assertRaises(ValueError):k.decode(bytes(b))

    def test_ambiguous_token_tables_refused(self):
        data,_,m=symbols_fixture();extra=data[m['table']:m['index']+512]
        with self.assertRaises(ValueError):k.token_tables(data+bytes((-len(data))%8)+extra)

    def test_unsupported_name_type_and_zero_length_refused(self):
        data,_,m=symbols_fixture()
        for pos,value in [(m['names'],0),(m['names']+1,ord('?'))]:
            b=bytearray(data);b[pos]=value
            with self.subTest(pos=pos),self.assertRaises(ValueError):k.decode(bytes(b))

    def test_names_alignment_padding_must_be_zero(self):
        data,_,m=symbols_fixture(extra=271);self.assertLess(m['names_end'],m['markers'])
        b=bytearray(data);b[m['names_end']]=1
        with self.assertRaises(ValueError):k.decode(bytes(b))

    def test_duplicate_boundary_refused(self):
        data,_,_=symbols_fixture(duplicate=True)
        with self.assertRaises(ValueError):k.decode(data)

    def test_map_mismatch_is_not_accepted_as_independent_confirmation(self):
        data,reference,_=symbols_fixture();rows,_=k.decode(data)
        with self.assertRaises(ValueError):k.compare_map(rows,reference.replace(b'_end\n',b'wrong\n'))

    def test_nonzero_padding_refused_even_when_symbols_still_decode(self):
        a,_,_=symbols_fixture(stock=True);b,_,_=symbols_fixture();b=bytearray(b);b[0x2f000]=1
        with self.assertRaises(ValueError):k.alignment_delta(a,bytes(b))

    def test_wrong_image_boundaries_refused(self):
        data,_,_=symbols_fixture();b=bytearray(data);struct.pack_into('<I',b,4,0x14000000+(0x30004-4)//4)
        with self.assertRaises(ValueError):k.decode(bytes(b))


class InputTests(unittest.TestCase):
    def test_processed_buffer_survives_path_replacement_without_reopening(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'input';p.write_bytes(b'original');pin=dict(bytes=8,sha256=digest(b'original'))
            data=read_checked(p,pin);p.write_bytes(b'modified')
            self.assertEqual(data,b'original');self.assertIs(checked_buffer(data,pin),data)
            with self.assertRaises(ValueError):read_checked(p,pin)

    def test_hash_size_budget_and_mutable_input_refused(self):
        for data,pin in [(b'x',dict(bytes=2,sha256=digest(b'x'))),
                (b'x',dict(bytes=1,sha256='0'*64)),(bytearray(b'x'),dict(bytes=1,sha256=digest(b'x'))),
                (b'x',dict(bytes=True,sha256=digest(b'x')))]:
            with self.subTest(pin=pin),self.assertRaises(ValueError):checked_buffer(data,pin)

    def test_symlink_and_oversized_input_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'input';p.write_bytes(b'ab');link=Path(temp)/'link';link.symlink_to(p)
            with self.assertRaises(OSError):read_checked(link,dict(bytes=2,sha256=digest(b'ab')))
            with self.assertRaises(ValueError):read_checked(p,dict(bytes=1,sha256=digest(b'a')))

    def archive(self,variant='good'):
        out=io.BytesIO();pin=dict(bytes=3,sha256=digest(b'abc'))
        manifest=json.dumps(dict(schema='S21-CANDIDATE-ARTIFACTS-v1',files={'a':pin})).encode()
        if variant=='manifest':manifest=b'{"files":{},"files":{}}'
        with tarfile.open(fileobj=out,mode='w:gz') as tar:
            for name,data in [('a',b'xyz' if variant=='hash' else b'abc'),('manifest.json',manifest)]:
                m=tarfile.TarInfo(name);m.size=len(data);tar.addfile(m,io.BytesIO(data))
            if variant in ('duplicate','unsafe','link'):
                m=tarfile.TarInfo('a' if variant=='duplicate' else '../bad' if variant=='unsafe' else 'link')
                if variant=='link':m.type=tarfile.SYMTYPE;m.linkname='a'
                tar.addfile(m)
        return out.getvalue()

    def test_selected_members_checked_in_same_tar_buffer(self):
        selected,manifest=select_members(self.archive(),{'a'},manifest=True)
        self.assertEqual(selected,{'a':b'abc'});self.assertIsInstance(manifest,bytes)

    def test_member_hash_duplicate_json_path_and_type_refused(self):
        for v in ('hash','manifest','duplicate','unsafe','link'):
            with self.subTest(v=v),self.assertRaises(ValueError):select_members(self.archive(v),{'a'},manifest=True)

    def test_missing_selected_member_refused(self):
        with self.assertRaises(ValueError):select_members(self.archive(),{'absent'},manifest=True)

    def test_source_metadata_skipped_without_following_selected_links(self):
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w:gz') as tar:
            m=tarfile.TarInfo('directory');m.type=tarfile.DIRTYPE;tar.addfile(m)
            m=tarfile.TarInfo('a');m.type=tarfile.SYMTYPE;m.linkname='/outside';tar.addfile(m)
        self.assertEqual(select_members(out.getvalue(),set(),source_tree=True)[0],{})
        with self.assertRaises(ValueError):select_members(out.getvalue(),{'a'},source_tree=True)
        with self.assertRaises(ValueError):select_members(out.getvalue(),set())


class SearchTests(unittest.TestCase):
    def test_arithmetic_spellings_found_without_executing_code(self):
        raw=b'a=1024**2 * 25\nb=25 << 20\nc=0x1900000\nd=25_000_000\n'
        self.assertEqual(h.boundary_hits(raw,python=True),[1,2,3])

    def test_unrelated_hex_prefix_and_dangerous_expression_not_evaluated(self):
        self.assertEqual(h.boundary_hits(b'a=0x190000000\nb=__import__("os").system("bad")\n',python=True),[])

    def test_expression_computation_is_bounded(self):
        for expr in ('2**999999999','1<<99999999','2**32**32','True*26214400'):
            self.assertIsNone(h.integer_expression(h.ast.parse(expr,mode='eval').body))


class NativeCopyTests(unittest.TestCase):
    def test_controlled_rlimit_is_explicit_failure_and_full_copies_exceed_boundary(self):
        data=bytes(range(256))*((h.CUT+4096)//256)
        with tempfile.TemporaryDirectory() as temp:
            r=h.copy_probes(data,Path(temp))
        full,limited=r['native_trials'];self.assertEqual(full['returncode'],0)
        self.assertTrue(full['exceeds_25mib']);self.assertEqual(full['sha256'],digest(data))
        self.assertNotEqual(limited['returncode'],0);self.assertEqual(limited['bytes'],h.CUT)
        self.assertEqual(limited['sha256'],digest(data[:h.CUT]));self.assertIn('File too large',limited['diagnostic'])
        self.assertFalse(r['historical_writer_identified']);self.assertTrue(r['injected_limit_is_not_a_reproduction_of_the_historical_process'])


if __name__ == '__main__': unittest.main()
