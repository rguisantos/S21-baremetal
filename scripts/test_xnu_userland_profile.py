#!/usr/bin/env python3
"""Profile parser, fixed cmdline and resource limits in the actual EFI C guard."""
import os
import copy
from types import SimpleNamespace
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.xnu import userland_profile as profile,resident,efi_lab as efi,boot_contract as c
from scripts.test_xnu_efi_resources import toy_kernel,resource_tree
from scripts.test_xnu_efi_memory import descriptor as memory_descriptor
from lab.xnu import fdt_adapter as adapter

PROBE=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "efi_resources.h"
int main(int argc,char **argv) {
 if (argc<3) return 2;
 if (!strcmp(argv[1],"tail")) {
  if(argc!=5)return 2;
  struct s21_profile p={1,1792773400};
  printf("%d\n",s21_profile_headroom(&p,strtoull(argv[2],0,0),strtoull(argv[3],0,0),strtoull(argv[4],0,0)));return 0;
 }
 FILE *f=fopen(argv[2],"rb");if(!f)return 2;unsigned char b[0x20000];size_t n=fread(b,1,sizeof(b),f);fclose(f);
 if(!strcmp(argv[1],"payload")){struct s21_payload p;printf("%d\n",s21_payload_decode(b,n,&p));return 0;}
 struct s21_profile p;int ok=s21_profile_decode(b,n,&p);if(!ok){puts("REJECT");return 0;}
 char text[96];if(!s21_profile_cmdline(&p,text,sizeof(text)))return 2;
 if(s21_profile_cmdline(&p,text,8))return 2;
 puts(text);return 0;
}
'''
class Profile(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name);(cls.work/'probe.c').write_text(PROBE);cls.probe=cls.work/'probe'
  subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'lab/xnu'),str(cls.work/'probe.c'),str(ROOT/'lab/xnu/efi_resources.c'),'-o',str(cls.probe)],check=True)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def check(self,mode,raw):
  p=self.work/'input';p.write_bytes(raw)
  return subprocess.check_output([str(self.probe),mode,str(p)],text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')).strip()
 def packed(self,**kwargs):
  return efi.pack(toy_kernel(),b'\0'*0x4000,c.encode_tree(resource_tree()),resident.encode(0x98000000),**kwargs)
 def test_c_and_python_command_match_at_epoch_edges(self):
  for epoch in (profile.FIRST_EPOCH,1792773400,profile.LAST_EPOCH-1):
   raw=profile.encode(epoch);self.assertEqual(profile.decode(raw)['cpus'],1);self.assertEqual(self.check('profile',raw),profile.cmdline(epoch))
 def test_every_truncated_prefix_rejected(self):
  raw=profile.encode(1792773400)
  for i in range(32):self.assertEqual(self.check('profile',raw[:i]),'REJECT')
 def test_unknown_version_id_flags_and_magic_rejected(self):
  raw=profile.encode(1792773400)
  for offset,value in ((0,0),(8,2),(12,2),(24,1)):
   bad=bytearray(raw);struct.pack_into('<I',bad,offset,value);self.assertEqual(self.check('profile',bad),'REJECT')
   with self.assertRaises(c.ContractError):profile.decode(bad)
 def test_epoch_invalid_and_suffix_rejected(self):
  for epoch in (0,profile.FIRST_EPOCH-1,profile.LAST_EPOCH,(1<<64)-1):
   bad=struct.pack('<8sIIQQ',profile.MAGIC,1,1,epoch,0);self.assertEqual(self.check('profile',bad),'REJECT')
  self.assertEqual(self.check('profile',profile.encode(1792773400)+b'\0'),'REJECT')
 def test_profile_payload_valid(self):self.assertEqual(self.check('payload',self.packed(profile=profile.encode(1792773400))),'1')
 def test_profile_requires_resident_and_large_image(self):
  for rd in (None,resident.encode(4<<20)):
   packed=efi.pack(toy_kernel(),b'\0'*0x4000,c.encode_tree(resource_tree()),rd,profile=profile.encode(1792773400));self.assertEqual(self.check('payload',packed),'0')
 def test_duplicate_profile_rejected(self):
  p=self.packed(profile=profile.encode(1792773400));p=p[:-24]+struct.pack('<16sII',b'labprofile',32,0)+profile.encode(1792773400)+b'\0'*24;p=p[:4]+struct.pack('<I',len(p)-8)+p[8:];self.assertEqual(self.check('payload',p),'0')
 def test_free_form_command_is_rejected(self):
  p=self.packed(profile=profile.encode(1792773400));bad=p.replace(profile.TAG,b'cpus=8'+b'\0'*(len(profile.TAG)-6));self.assertEqual(self.check('payload',bad),'0')
 def test_old_command_cannot_select_userland_profile(self):
  p=self.packed();entry=struct.pack('<16sII',b'labprofile',32,0)+profile.encode(1792773400);p=p[:-24]+entry+b'\0'*24;p=p[:4]+struct.pack('<I',len(p)-8)+p[8:];self.assertEqual(self.check('payload',p),'0')
 def test_minimum_tail_boundaries_and_overflow(self):
  env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
  for size,top,expected in ((0x80000000,0x140000000,1),(0x80000000,0x140000001,0),(0x80000000,0x180000001,0),((1<<64)-1,0x140000000,0)):
   self.assertEqual(int(subprocess.check_output([str(self.probe),'tail',str(0x100000000),str(size),str(top)],text=True,env=env)),expected)

 def test_read_only_snapshot_decoder_rejects_corrupt_metadata(self):
  block=65536+40;raw=bytearray(4*block);entry=memory_descriptor(0x40000000,0x200000,7)
  for stage in range(4):
   start=stage*block;raw[start:start+len(entry)]=entry;struct.pack_into('<4Q2I',raw,start+65536,len(entry),48,17,0,1,1)
  self.assertEqual(set(profile.snapshots(raw)),{0,1,2,3})
  with self.assertRaises(c.ContractError):profile.snapshots(raw[:-1])
  for offset,fmt,value in ((0,'Q',65584),(8,'Q',16),(24,'Q',1<<63),(32,'I',2),(36,'I',0)):
   bad=bytearray(raw);struct.pack_into('<'+fmt,bad,65536+offset,value)
   with self.assertRaises(c.ContractError):profile.snapshots(bad)
 def test_independent_profile_rejects_wrong_cmdline_cpu_disk_and_tail(self):
  epoch=1792773400;declared=profile.decode(profile.encode(epoch));small=4<<20
  args=SimpleNamespace(cmdline='debug=0x8 serial=3 rd=md0 '+profile.cmdline(epoch),phys_base=0xf4000000,mem_size=0x100000000,top=0x1b4000000)
  tree=adapter.node('device-tree',children=[adapter.node('cpus',children=[adapter.node('cpu0',{'reg':struct.pack('<I',0)})]),adapter.node('chosen',children=[adapter.node('memory-map',{'RAMDisk1':adapter.le64(0xf9000000,small)})])])
  self.assertTrue(profile.verify(args,tree,declared,small)['verified'])
  for field,value in (('cmdline',args.cmdline.replace('cpus=1','cpus=8')),('top',args.top+1)):
   bad=copy.copy(args);setattr(bad,field,value)
   with self.assertRaises(c.ContractError):profile.verify(bad,tree,declared,small)
  bad=copy.deepcopy(tree);bad.at('/cpus').children.append(adapter.node('cpu1',{'reg':struct.pack('<I',1)}))
  with self.assertRaises(c.ContractError):profile.verify(args,bad,declared,small)
  with self.assertRaises(c.ContractError):profile.verify(args,tree,declared,small+0x4000)

if __name__=='__main__':unittest.main()
