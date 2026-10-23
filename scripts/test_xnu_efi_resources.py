#!/usr/bin/env python3
"""Exercise the same freestanding C guards used by the rebuilt EFI consumer."""
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
from lab.xnu import boot_contract as c
from lab.xnu import efi_lab as efi
from lab.xnu import fdt_adapter as a

PROBE=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "efi_resources.h"
int main(int argc,char **argv) {
    if (argc<3) return 2;
    if (!strcmp(argv[1],"layout")) {
        if (argc!=12) return 2;
        uint64_t v[10]; for (int i=0;i<10;++i) v[i]=strtoull(argv[i+2],0,0);
        printf("{\"accepted\":%d}\n",s21_layout_check(v[0],v[1],v[2],v[3],v[4],v[5],v[6],v[7],v[8],v[9]));return 0;
    }
    FILE *f=fopen(argv[2],"rb");if (!f) return 2;
    unsigned char *p=malloc(S21_PAYLOAD_LIMIT+1U);if (!p) return 2;
    size_t n=fread(p,1,S21_PAYLOAD_LIMIT+1U,f);int bad=ferror(f);fclose(f);
    if (bad || n>S21_PAYLOAD_LIMIT) { free(p); return 2; }
    if (!strcmp(argv[1],"payload")) {
        struct s21_payload out;printf("{\"accepted\":%d}\n",s21_payload_decode(p,(uint32_t)n,&out));
    } else {
        struct s21_resources r={0};int decoded=s21_resources_decode(p,(uint32_t)n,&r),unexpected=0;
        if (!strcmp(argv[1],"prefix"))
            for (uint32_t i=0;i<n;++i) unexpected+=s21_resources_decode(p,i,&r)!=0;
        uint64_t frequency=argc>3?strtoull(argv[3],0,0):62500000;
        uint64_t mpidr=argc>4?strtoull(argv[4],0,0):0;
        printf("{\"decoded\":%d,\"accepted\":%d,\"unexpected_prefixes\":%d,\"redist_size\":%llu}\n",
               decoded,decoded?s21_resources_qemu(&r,frequency,mpidr):0,unexpected,(unsigned long long)r.redist_size);
    }
    free(p);return 0;
}
'''


def resource_tree():
    tree=a.node("device-tree",children=[a.node("chosen",{"psci-method":b"hvc\0"}),
        a.node("cpus",children=[a.node("cpu0",{"device_type":b"cpu\0","reg":struct.pack("<I",0),
                                              "timebase-frequency":a.le64(62500000)})]),
        a.node("arm-io",{"ranges":a.le64(0,0x08000000,0x01001000)},[
            a.node("gic",{"device_type":b"interrupt-controller\0","compatible":b"arm,gic-v3\0",
                          "reg":a.le64(0,0x10000,0xa0000,0x100000)}),
            a.node("uart0",{"device_type":b"uart\0","compatible":b"arm,pl011\0",
                            "reg":a.le64(0x1000000,0x1000)})])])
    return tree


def toy_kernel():
    va=0xfffffff007004000
    segment=struct.pack("<II16s4Q4I",0x19,72,b"__TEXT",va,0x4000,0,0x4000,5,5,0,0)
    state=[0]*34;state[32]=va+0x400
    thread=struct.pack("<4I34Q",5,288,6,68,*state)
    return (struct.pack("<8I",0xfeedfacf,0x100000c,0,2,2,360,0,0)+segment+thread).ljust(0x4000,b"\0")


class Guards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="efi-guards-");cls.work=Path(cls.temp.name)
        (cls.work/"probe.c").write_text(PROBE)
        cls.probe=cls.work/"probe"
        subprocess.run(["cc","-std=c11","-O1","-g","-Wall","-Wextra","-Werror",
            "-fsanitize=address,undefined","-I",str(ROOT/"lab/xnu"),str(cls.work/"probe.c"),
            str(ROOT/"lab/xnu/efi_resources.c"),"-o",str(cls.probe)],check=True)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def check(self,data,mode="resource",*args):
        path=self.work/"input.bin";path.write_bytes(data)
        env=dict(os.environ,ASAN_OPTIONS="detect_leaks=0",UBSAN_OPTIONS="halt_on_error=1")
        return json.loads(subprocess.check_output([str(self.probe),mode,str(path),*map(str,args)],env=env,text=True,timeout=10))

    def test_valid_resource(self):
        result=self.check(c.encode_tree(resource_tree()))
        self.assertEqual((result['decoded'],result['accepted'],result['redist_size']),(1,1,0x100000))

    def test_every_truncated_prefix_rejected(self):
        self.assertEqual(self.check(c.encode_tree(resource_tree()),"prefix")['unexpected_prefixes'],0)

    def test_invalid_counts_names_padding_and_suffix(self):
        raw=c.encode_tree(resource_tree())
        count=bytearray(raw);struct.pack_into('<I',count,0,0xffffffff)
        name=bytearray(raw);name[8:40]=b'x'*32
        padding=bytearray(raw);padding[raw.index(b'cpu0\0')+5]=1
        for data in (bytes(count),bytes(name),bytes(padding),raw+b'\0'*4):
            with self.subTest(size=len(data)):self.assertEqual(self.check(data)['decoded'],0)

    def test_declared_frequency_is_compared_to_register_value(self):
        raw=c.encode_tree(resource_tree())
        self.assertEqual(self.check(raw,'resource',62500001,0)['accepted'],0)

    def test_boot_mpidr_is_compared(self):
        self.assertEqual(self.check(c.encode_tree(resource_tree()),'resource',62500000,0x100)['accepted'],0)

    def test_incompatible_resource_values_are_rejected(self):
        for path,key,value in [('/chosen','psci-method',b'smc\0'),
            ('/arm-io/gic','reg',a.le64(0,0x10000,0xb0000,0x100000)),
            ('/arm-io/uart0','reg',a.le64(0x1001000,0x1000))]:
            tree=resource_tree();tree.at(path).properties[key]=value
            with self.subTest(path=path):self.assertEqual(self.check(c.encode_tree(tree))['accepted'],0)

    def test_unknown_properties_not_silently_ignored(self):
        tree=resource_tree();tree.at('/chosen').properties['unknown']=b'x'
        self.assertEqual(self.check(c.encode_tree(tree))['decoded'],0)

    def test_samsung_fragment_not_accepted_as_qemu(self):
        m=json.loads((ROOT/'docs/references/xnu-fdt-adapter-20261022.json').read_text())
        raw=bytes.fromhex(''.join(m['resource_fragment_hex_32_bytes_per_line']))
        self.assertEqual(self.check(raw)['accepted'],0)

    def payload(self,kernel=None):return efi.pack(toy_kernel() if kernel is None else kernel,b'fixture disk',c.encode_tree(resource_tree()))

    def test_valid_payload(self): self.assertEqual(self.check(self.payload(),'payload')['accepted'],1)

    def test_truncated_payload_and_header_overflow(self):
        raw=self.payload();overflow=bytearray(raw);struct.pack_into('<I',overflow,4,0xffffffff)
        for data in (raw[:7],raw[:-1],bytes(overflow)):
            with self.subTest(size=len(data)):self.assertEqual(self.check(data,'payload')['accepted'],0)

    def test_duplicate_or_unknown_entry(self):
        raw=self.payload();at=8+24+0x4000
        for name in ('kernel','unknown'):
            data=bytearray(raw);data[at:at+16]=name.encode().ljust(16,b'\0')
            self.assertEqual(self.check(data,'payload')['accepted'],0)

    def test_macho_command_and_file_bounds(self):
        for offset,fmt,value in ((36,'I',0),(32+48,'Q',0x100000),(32+72+272,'Q',0)):
            kernel=bytearray(toy_kernel());struct.pack_into('<'+fmt,kernel,offset,value)
            with self.subTest(offset=offset):self.assertEqual(self.check(self.payload(bytes(kernel)),'payload')['accepted'],0)

    def test_cmdline_cannot_enable_phone_paths(self):
        command=b'cpus=1 loader_return_after=30'
        raw=self.payload().replace(command,b'ufs_native=1'.ljust(len(command),b' '))
        self.assertEqual(self.check(raw,'payload')['accepted'],0)

    def layout(self,values):
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
        return json.loads(subprocess.check_output([str(self.probe),'layout',*map(str,values)],env=env,text=True))['accepted']

    def good_layout(self): return [0x40000000,0x10000000,0x43004000,0x43008000,0x43008000,0x4000,0x4300c000,0x4000,0x43010000,0x43014000]

    def test_adjacent_layout_accepted(self):self.assertEqual(self.layout(self.good_layout()),1)

    def test_layout_overlap_alignment_and_end(self):
        for index,value in ((4,0x43004000),(6,0x43008000),(8,0x4300c000),(9,0x43010001),(9,0x43000000)):
            values=self.good_layout();values[index]=value
            with self.subTest(index=index):self.assertEqual(self.layout(values),0)

    def test_layout_overflow_and_payload_reservation(self):
        for base,size in ((0xffffffffff000000,0x2000000),(0xf0000000,0x10000000)):
            values=self.good_layout();values[:2]=[base,size]
            if base==0xf0000000:
                for index in (2,3,4,6,8,9):values[index]+=base-0x40000000
            self.assertEqual(self.layout(values),0)


if __name__=='__main__':unittest.main(verbosity=1)
