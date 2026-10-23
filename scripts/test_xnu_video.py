#!/usr/bin/env python3
"""Counterexamples for native and independent Python QEMU video guards."""
import ctypes
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.xnu import boot_contract as c, video, efi_memory as m
from scripts.test_xnu_efi_memory import descriptor
from scripts.test_xnu_contract import fixture

FIELDS=(0x80000000,1,4500,1125,2436,32)
SIZE=(4500*2436+4095)&~4095


class VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='s21-video-')
        out=Path(cls.temp.name)/'video.so'
        subprocess.run(['cc','-shared','-fPIC','-std=c11','-O2','-Wall','-Wextra','-Werror',
                        str(ROOT/'lab/xnu/efi_video.c'),'-o',str(out)],check=True)
        cls.lib=ctypes.CDLL(str(out));cls.native=cls.lib.s21_video_geometry
        cls.native.argtypes=[ctypes.c_uint64]*6+[ctypes.POINTER(ctypes.c_uint64)]
        cls.native.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def check(self,fields,expected):
        size=ctypes.c_uint64()
        self.assertEqual(bool(self.native(*fields,ctypes.byref(size))),expected)
        if expected:
            decoded=video.decode(fields);self.assertEqual(decoded.allocation.size,size.value)
        else:
            with self.assertRaises(c.ContractError):video.decode(fields)
    def test_geometry(self):self.check(FIELDS,True)
    def test_bad_geometry_and_modes(self):
        for index,bad in ((0,0),(0,0x80000001),(1,0),(1,2),(2,4496),(2,4504),
                          (3,800),(3,0),(4,600),(4,0),(5,24),(5,0)):
            with self.subTest(index=index,bad=bad):
                f=list(FIELDS);f[index]=bad;self.check(f,False)
    def test_extreme_fields_and_overflow(self):
        for i in range(6):
            f=list(FIELDS);f[i]=0xfffffffffffff000 if i==0 else (1<<64)-1
            self.check(f,False)
    def test_python_rejects_invalid_types(self):
        for v in (-1,True,1<<64):
            f=list(FIELDS);f[0]=v
            with self.assertRaises(c.ContractError):video.decode(f)
    def maps(self,tail=None):
        raw=descriptor(FIELDS[0],SIZE,2) if tail is None else tail
        return {i:m.Snapshot(raw,48,1) for i in range(4)}
    def verify(self,maps=None,claim=None,window=None,payload=None):
        return video.verify_maps(FIELDS,self.maps() if maps is None else maps,
            {'base':FIELDS[0],'size':SIZE} if claim is None else claim,
            c.Span(0x40000000,0x10000000) if window is None else window,
            c.Span(0xf0000000,0x4000000) if payload is None else payload)
    def test_owned_across_four_maps(self):self.assertEqual(self.verify().allocation.size,SIZE)
    def test_released_page_or_unsafe_attributes(self):
        for kind,attrs in ((7,8),(4,8),(2,0),(2,8|(1<<63)),(2,8|0x20000)):
            maps=self.maps();maps[3]=m.Snapshot(descriptor(FIELDS[0],4096,kind,attrs)+descriptor(FIELDS[0]+4096,SIZE-4096,2),48,1)
            with self.assertRaises(c.ContractError):self.verify(maps=maps)
    def test_page_rounding_tail_must_be_owned(self):
        maps=self.maps();maps[2]=m.Snapshot(descriptor(FIELDS[0],SIZE-4096,2)+descriptor(FIELDS[0]+SIZE-4096,4096,7),48,1)
        with self.assertRaises(c.ContractError):self.verify(maps=maps)
    def test_missing_stage_or_claim_mismatch(self):
        maps=self.maps();del maps[0]
        with self.assertRaises(c.ContractError):self.verify(maps=maps)
        for claim in ({'base':FIELDS[0]+4096,'size':SIZE},{'base':FIELDS[0],'size':SIZE-4096}):
            with self.assertRaises(c.ContractError):self.verify(claim=claim)
    def test_overlap_window_and_payload(self):
        for field in ('window','payload'):
            with self.assertRaises(c.ContractError):self.verify(**{field:c.Span(FIELDS[0]+4096,4096)})
    def contract(self,fields,decl=None,**extra):
        old,tree,kernel=fixture()
        args=c.BootArgs.decode(old.encode());tree=c.decode_tree(c.encode_tree(tree))
        args=replace(args,video=fields)
        return c.validate_profile(args,tree,0x43210000,kernel,ram=[c.Span(0x40000000,0x10000000)],
            reserved=[],protected=extra.get('protected',[]),complete=True,framebuffer=decl)
    def test_headless_default_remains_strict(self):
        self.assertTrue(self.contract((0,)*6)['profile_consistent'])
        with self.assertRaises(c.ContractError):self.contract(FIELDS)
        with self.assertRaises(c.ContractError):self.contract((0,)*6,c.Span(FIELDS[0],SIZE))
    def test_explicit_video_declaration(self):
        self.assertTrue(self.contract(FIELDS,c.Span(FIELDS[0],SIZE))['profile_consistent'])
        with self.assertRaises(c.ContractError):self.contract(FIELDS,c.Span(FIELDS[0],SIZE-4096))
    def test_declared_video_cannot_overlap_protected(self):
        with self.assertRaises(c.ContractError):
            self.contract(FIELDS,c.Span(FIELDS[0],SIZE),protected=[c.Span(FIELDS[0],4096)])

if __name__=='__main__':unittest.main()
