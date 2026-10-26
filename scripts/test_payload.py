#!/usr/bin/env python3
"""Independent ELF fixture + sanitizer tests of the actual C container consumer."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

pack = module(ROOT/'tools/mkpayload.py', 'mkpayload')
fdt = module(ROOT/'scripts/test_fdt.py', 'fixtures')
inspect_proton = module(ROOT/'scripts/inspect_proton.py', 'inspect_proton')


def elf_fixture():
    data = bytearray(0x180)
    ident = b'\x7fELF\x02\x01\x01' + b'\0'*9
    struct.pack_into('<16sHHIQQQIHHHHHH', data, 0, ident, 2, 183, 1,
                     0x80080000, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    struct.pack_into('<II6Q', data, 64, 1, 5, 0x100, 0x80080000, 0x80080000, 7, 7, 1)
    struct.pack_into('<II6Q', data, 120, 1, 6, 0x120, 0x80081000, 0x80081000, 3, 8195, 1)
    data[0x100:0x107] = b'CODE123'
    data[0x120:0x123] = b'XYZ'
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, default=ROOT/'r8/build/r10_payload.elf',
                        help='required production R10 ELF (build it before testing)')
    actual = parser.parse_args().elf.resolve()
    if not actual.is_file():
        parser.error(f'required R10 ELF is missing: {actual}; '
                     'run python3 scripts/validate_baseline.py or build it and pass --elf')
    dtb = fdt.encode(fdt.fixture())
    elf = elf_fixture()
    blob = pack.build(elf, dtb, 'console=test')
    # Decode wire bytes independently of the producer's Struct objects.
    assert blob[:8] == b'S21R10  ' and struct.unpack_from('<II', blob, 8) == (1, 2)
    va, entry, doff, dsize, end, pa, mem = struct.unpack_from('<7Q', blob, 16)
    assert (va, entry, end, pa) == (0x80080000, 0x80080000, 0x80084000, 0x80080000)
    assert mem == 0x5000 and blob[72:85] == b'console=test\0'
    assert blob[doff:doff+dsize] == dtb
    a, n, off, size = struct.unpack_from('<4Q', blob, 680)
    assert (a, n, size) == (va, 7, 7) and blob[off:off+size] == b'CODE123'
    a, n, off, size = struct.unpack_from('<4Q', blob, 712)
    assert (a, n, size) == (va+4096, 8195, 3) and blob[off:off+size] == b'XYZ'
    count = 1
    def rejected(data=elf, tree=dtb, **kwargs):
        nonlocal count
        try: pack.build(data, tree, **kwargs)
        except ValueError: count += 1
        else: raise AssertionError('producer accepted invalid input')
    rejected(phys_base=0x90080000)
    rejected(mem_size=0x80000000)
    rejected(mem_size=4096)
    rejected(cmdline='a'*608)
    rejected(cmdline='a\0b')
    rejected(tree=dtb[:39])
    rejected(tree=dtb+b'\0')
    bad=bytearray(dtb); struct.pack_into('>I',bad,4,len(dtb)+1); rejected(tree=bad)
    for off, fmt, value in [(18,'H',62),(16,'H',3),(32,'Q',len(elf)),
                            (24,'Q',0x80081000),(68,'I',7),(80,'Q',0xfffffffffffffff0),
                            (96,'Q',9999),(104,'Q',1),(112,'Q',3),
                            (136,'Q',0x80080000),(144,'Q',0x80082000)]:
        bad=bytearray(elf); struct.pack_into('<'+fmt,bad,off,value); rejected(data=bad)
    for data in [b'',elf[:63],elf[:150]]: rejected(data=data)
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); probe=td/'probe'; wire=td/'payload'
        subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined',str(ROOT/'shim/tests/payload_probe.c'),
                        str(ROOT/'shim/payload.c'),str(ROOT/'r8/r10_payload/fdt.c'),
                        '-o',str(probe)],check=True)
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
        def consume(data, valid=False, source='0x47000000'):
            nonlocal count
            wire.write_bytes(data)
            r=subprocess.run([str(probe),str(wire),source],env=env,capture_output=True,text=True)
            assert r.returncode == (0 if valid else 1),(r.returncode,r.stdout,r.stderr)
            count+=1
            return json.loads(r.stdout) if valid else None
        assert consume(blob,True)['memory_size']==0x5000
        consume(blob,source='0x80080000')
        consume(blob,source='0xfffffffffffffff0')
        for n in [0,7,16,679,700,len(blob)-1]: consume(blob[:n])
        for off,fmt,value in [(0,'Q',0),(8,'I',2),(12,'I',0),(12,'I',33),
                              (16,'Q',0x80080001),(24,'Q',0x80082000),(32,'Q',8),
                              (32,'Q',len(blob)+8),(40,'Q',0xffffffffffffffff),
                              (48,'Q',0x80081000),(48,'Q',0x17000),(56,'Q',0x90080000),(64,'Q',4096),
                              (64,'Q',0x80000000),(680,'Q',0xfffffffffffffff0),
                              (688,'Q',0xffffffffffffffff),(696,'Q',0),
                              (704,'Q',8),(712,'Q',0x80080000),
                              (728,'Q',struct.unpack_from('<Q',blob,696)[0])]:
            bad=bytearray(blob); struct.pack_into('<'+fmt,bad,off,value); consume(bad)
        bad=bytearray(blob);bad[72:680]=b'a'*608;consume(bad)
        bad=bytearray(blob);bad[doff:doff+4]=b'BAD!';consume(bad)
        # Exclusive CLI: validation failures do not replace an existing artifact.
        inp=td/'input.elf';tree=td/'tree.dtb';out=td/'out';inp.write_bytes(elf);tree.write_bytes(dtb)
        command=['python3',str(ROOT/'tools/mkpayload.py'),str(inp),'--dtb',str(tree),'-o',str(out)]
        subprocess.run(command,check=True,capture_output=True)
        prior=out.read_bytes(); assert prior==pack.build(elf,dtb)
        r=subprocess.run(command,capture_output=True);assert r.returncode==2 and out.read_bytes()==prior;count+=1
        # Reproduce the Linux + EFI-stub dual header with an independent fixture.
        image=bytearray(512);image[:2]=b'MZ';image[56:60]=b'ARMd'
        struct.pack_into('<QQQ',image,8,0x80000,0x400000,10)
        struct.pack_into('<I',image,60,64);image[64:68]=b'PE\0\0'
        struct.pack_into('<H',image,68,0xaa64);struct.pack_into('<H',image,156,10)
        banner=b'Linux version 5.4.302-ProtonPlus-test\0';image[256:256+len(banner)]=banner
        table=struct.pack('>8I',0xd7b7ab1e,64+len(dtb),32,32,1,32,2048,0)
        table+=struct.pack('>8I',len(dtb),64,0,0,0,0,0,0)+dtb
        vendor=bytearray(6144+len(table));vendor[:8]=b'VNDRBOOT'
        struct.pack_into('<5I',vendor,8,3,2048,0x10008000,0x11000000,4)
        struct.pack_into('<IIQ',vendor,2096,2112,len(table),0x11f00000)
        vendor[6144:]=table
        archive=td/'proton.zip'
        def make_archive(image_data=image,vendor_data=vendor):
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('Image',image_data);z.writestr('vendor_boot.img',vendor_data)
                z.writestr('anykernel.sh','not executed')
        make_archive();info=inspect_proton.inspect(archive)
        assert info['Image']['pe']=={'machine':'0xaa64','subsystem':10}
        assert info['Image']['linux_version']=='5.4.302-ProtonPlus-test'
        assert info['vendor_boot']['trees'][0]['memory_nodes']==['/memory@80000000','/memory@880000000']
        count+=1
        for bad_image,bad_vendor in [(image[:63],vendor),(image,vendor[:-1]),
                                      (image,bytes(8)+vendor[8:])]:
            make_archive(bad_image,bad_vendor)
            try: inspect_proton.inspect(archive)
            except ValueError: count+=1
            else: raise AssertionError('invalid kernel/vendor fixture accepted')
        actual_blob=pack.build(actual.read_bytes(),dtb)
        info=consume(actual_blob,True)
        symbols=subprocess.check_output(['readelf','-sW',str(actual)],text=True)
        line=next(line for line in symbols.splitlines() if line.endswith(' __payload_end'))
        assert int(info['kernel_end'],16)==int(line.split()[1],16)
        print('R10 ELF extent PASS: BSS and all stacks included')
    print(f'PAYLOAD PASS: {count} cases; C consumer with ASan/UBSan')

if __name__=='__main__':main()
