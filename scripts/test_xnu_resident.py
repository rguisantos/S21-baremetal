#!/usr/bin/env python3
"""Native C boundary tests for the descriptor, payload and two-disk layout."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.xnu import efi_lab as efi, boot_contract as c
from scripts.test_xnu_efi_resources import toy_kernel,resource_tree

BASE=0xfc000000

def descriptor(base=BASE,size=0x400000,version=1,flags=0):
    return struct.pack('<8sIIQQ',b'S21RDSK\0',version,flags,base,size)

PROBE=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "efi_resources.h"
int main(int argc,char **argv) {
    if (argc<3) return 2;
    if (!strcmp(argv[1],"layout")) {
        if (argc!=14) return 2;
        uint64_t a[12];for (int i=0;i<12;i++) a[i]=strtoull(argv[i+2],0,0);
        struct s21_resident r={a[0],a[1]};
        printf("%d\n",s21_resident_layout(&r,a[2],a[3],a[4],a[5],a[6],a[7],a[8],a[9],a[10],a[11]));return 0;
    }
    FILE *f=fopen(argv[2],"rb");if (!f) return 2;
    unsigned char b[0x20000];size_t n=fread(b,1,sizeof(b),f);int bad=ferror(f);fclose(f);if(bad) return 2;
    int ok=0;
    if (!strcmp(argv[1],"descriptor")) { struct s21_resident r;ok=s21_resident_decode(b,n,&r); }
    else if (!strcmp(argv[1],"payload")) { struct s21_payload p;ok=s21_payload_decode(b,n,&p); }
    else if (!strcmp(argv[1],"header")) ok=s21_resident_apfs(b,n);
    else return 2;
    printf("%d\n",ok);return 0;
}
'''

class Resident(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        (cls.work/'probe.c').write_text(PROBE);cls.probe=cls.work/'probe'
        subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-I',str(ROOT/'lab/xnu'),str(cls.work/'probe.c'),str(ROOT/'lab/xnu/efi_resources.c'),'-o',str(cls.probe)],check=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def check(self,mode,data):
        path=self.work/'input';path.write_bytes(data)
        return int(subprocess.check_output([str(self.probe),mode,str(path)],env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'),text=True))
    def test_descriptor_and_every_truncated_prefix(self):
        d=descriptor();self.assertEqual(self.check('descriptor',d),1)
        for i in range(len(d)):self.assertEqual(self.check('descriptor',d[:i]),0)
    def test_version_magic_flags_and_suffix(self):
        for d in (descriptor(version=2),descriptor(flags=1),b'BADMAGIC'+descriptor()[8:],descriptor()+b'\0'):
            self.assertEqual(self.check('descriptor',d),0)
    def test_payload_overlap_and_noncanonical_base(self):
        for base in (0xf0000000,BASE+1,BASE+4096,0xfffffffffffff000):
            self.assertEqual(self.check('descriptor',descriptor(base=base)),0)
    def test_size_alignment_limit_and_overflow(self):
        for size in (0,1,4095,4097,0xc0001000,0xffffffffffffffff):
            self.assertEqual(self.check('descriptor',descriptor(size=size)),0)
        self.assertEqual(self.check('descriptor',descriptor(size=4096)),1)
        self.assertEqual(self.check('descriptor',descriptor(size=0xc0000000)),1)
    def test_payload_optional_descriptor_and_duplicate(self):
        packed=efi.pack(toy_kernel(),b'\0'*0x4000,c.encode_tree(resource_tree()),descriptor())
        self.assertEqual(self.check('payload',packed),1)
        duplicate=packed[:-24]+struct.pack('<16sII',b'resident',32,0)+descriptor()+b'\0'*24
        duplicate=duplicate[:4]+struct.pack('<I',len(duplicate)-8)+duplicate[8:]
        self.assertEqual(self.check('payload',duplicate),0)
    def test_legacy_rdres_string_is_not_accepted(self):
        p=efi.pack(toy_kernel(),b'\0'*0x4000,c.encode_tree(resource_tree()),descriptor())
        self.assertEqual(self.check('payload',p.replace(b'resident'+b'\0'*8,b'rdres'+b'\0'*11)),0)
    def test_apfs_header_requires_block_count_consistency(self):
        d=bytearray(4096);struct.pack_into('<IIQ',d,32,0x4253584e,4096,1)
        self.assertEqual(self.check('header',d),1)
        for offset,value in ((32,0),(36,16384),(40,2)):
            bad=bytearray(d);struct.pack_into('<I',bad,offset,value);self.assertEqual(self.check('header',bad),0)
    def layout(self,**kw):
        a=dict(resident=BASE,res_size=0x400000,base=0xf4000000,size=0x80000000,lo=0xf7004000,hi=0xf9000000,
               rd=0xf9000000,rn=0x4000,dt=0xfc400000,dn=0x10000,ba=0xfc410000,top=0xfc414000);a.update(kw)
        return int(subprocess.check_output([str(self.probe),'layout',*[str(x) for x in a.values()]],text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')))
    def test_valid_two_disk_layout(self):self.assertEqual(self.layout(),1)
    def test_resident_cannot_overlap_kernel_small_disk_tree_or_args(self):
        for changes in ({'hi':BASE+0x4000},{'rd':BASE},{'dt':BASE},{'ba':BASE}):
            self.assertEqual(self.layout(**changes),0)
    def test_resident_must_fit_window_static_mapping_and_offset(self):
        for changes in ({'base':0xf2000000},{'res_size':0x500000},{'size':0x8000000},{'top':0xfc400000}):
            self.assertEqual(self.layout(**changes),0)

if __name__=='__main__':unittest.main()
