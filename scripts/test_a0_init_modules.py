#!/usr/bin/env python3
"""Bounds, binding refusals and immutable native-reader input controls."""
import fcntl
import lzma
import os
import struct
import unittest
from unittest.mock import patch

import inspect_a0_init_modules as audit


def elf():
    names=b'\0.shstrtab\0.text\0.gnu_debugdata\0'
    start=0x257000;length=0x32c824-start
    text=bytearray(length)
    for pc,target in audit.CALLS.items():
        word=0x94000000|(((target-pc)//4)&0x3ffffff)
        struct.pack_into('<I',text,pc-start,word)
    for pc,word in audit.WORDS.items():struct.pack_into('<I',text,pc-start,word)
    raw=bytearray(0x57000);raw[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI',raw,16,2,183,1)
    for at,value in audit.STRINGS.items():raw[at:at+len(value)+1]=value+b'\0'
    raw[0x400:0x400+len(names)]=names
    raw.extend(text);debug_at=len(raw);debug=lzma.compress(b'synthetic symbols');raw.extend(debug)
    rows=[bytes(64)]
    for name,kind,address,offset,size in [('.shstrtab',3,0,0x400,len(names)),
            ('.text',1,start,0x57000,length),('.gnu_debugdata',1,0,debug_at,len(debug))]:
        rows.append(struct.pack('<IIQQQQIIQQ',names.index(name.encode()),kind,0,address,offset,size,0,0,1,0))
    at=len(raw);raw.extend(b''.join(rows));struct.pack_into('<Q',raw,40,at)
    struct.pack_into('<HHH',raw,58,64,4,1)
    return bytes(raw)


class InitModulesTests(unittest.TestCase):
    def test_forward_and_backward_calls(self):
        self.assertEqual(audit.branch(0x94000001,0x100),0x104)
        self.assertEqual(audit.branch(0x97ffffff,0x100),0xfc)

    def test_non_call_refused(self):
        with self.assertRaises(ValueError):audit.branch(0x14000001,0x100)

    def test_section_uses_virtual_and_file_coordinates(self):
        address,offset,data=audit.section(elf(),'.text')
        self.assertEqual((address,offset),(0x257000,0x57000))
        self.assertEqual(struct.unpack_from('<I',data,0x2f659c-address)[0],0x52802220)

    def test_corrupt_elf_tables_and_missing_section_refused(self):
        raw=elf()
        for data in (raw[:60],b'BAD!'+raw[4:],raw[:-1]):
            with self.subTest(size=len(data)),self.assertRaises(ValueError):audit.section(data,'.text')
        with self.assertRaises(ValueError):audit.section(raw,'.missing')

    def test_debug_single_stream_and_budget(self):
        good=lzma.compress(b'symbols')
        self.assertEqual(audit.mini_debug(good),b'symbols')
        for bad in (good[:-1],good+good,lzma.compress(b'x'*(4*1024*1024+1))):
            with self.subTest(size=len(bad)),self.assertRaises((ValueError,lzma.LZMAError)):audit.mini_debug(bad)

    def test_wrong_init_identity_refused_before_native_reader(self):
        with patch.object(audit.subprocess,'check_output') as native,self.assertRaises(ValueError):audit.inspect_init(b'wrong')
        native.assert_not_called()

    def native(self,raw,mutate_symbols=False):
        def call(command,pass_fds,**kwargs):
            fd=pass_fds[0]
            self.assertEqual(fcntl.fcntl(fd,getattr(fcntl,'F_GET_SEALS',1034))&15,15)
            with self.assertRaises(OSError):os.pwrite(fd,b'x',0)
            if command[0]=='nm':
                self.assertEqual(os.pread(fd,100,0),b'synthetic symbols')
                return '\n'.join(f'{pc if not mutate_symbols else pc+4:016x} T {name}' for pc,name in audit.FUNCTIONS.items())
            self.assertEqual(os.pread(fd,len(raw)+1,0),raw)
            lines=[]
            for pc in audit.CALLS.keys()|audit.WORDS.keys():
                word=struct.unpack_from('<I',raw,0x57000+pc-0x257000)[0]
                lines.append(f'{pc:x}: {word:08x} synthetic-decoding')
            return '\n'.join(lines)
        return call

    def test_native_readers_receive_same_sealed_buffers(self):
        raw=elf()
        with patch.object(audit,'INIT_PIN',audit.pin(raw)),patch.object(audit.subprocess,'check_output',side_effect=self.native(raw)):
            r=audit.inspect_init(raw)
        self.assertEqual(len(r['calls']),11)
        self.assertFalse(r['init_executed']);self.assertFalse(r['exact_runtime_order_established'])

    def test_symbol_address_mismatch_refused(self):
        raw=elf()
        with patch.object(audit,'INIT_PIN',audit.pin(raw)),patch.object(audit.subprocess,'check_output',side_effect=self.native(raw,True)),self.assertRaisesRegex(ValueError,'symbol binding'):
            audit.inspect_init(raw)

    def test_changed_direct_call_refused(self):
        raw=bytearray(elf());struct.pack_into('<I',raw,0x57000+0x2f50dc-0x257000,0x94000000);raw=bytes(raw)
        with patch.object(audit,'INIT_PIN',audit.pin(raw)),patch.object(audit.subprocess,'check_output',side_effect=self.native(raw)),self.assertRaisesRegex(ValueError,'call target'):
            audit.inspect_init(raw)


if __name__=='__main__':unittest.main()
