#!/usr/bin/env python3
"""Exercise exact materialization and refusal-before-write under ASan/UBSan."""
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('fixtures',ROOT/'scripts/test_payload.py')
test=importlib.util.module_from_spec(spec);spec.loader.exec_module(test)

def main():
    with tempfile.TemporaryDirectory() as directory:
        td=Path(directory);exe=td/'stage'
        subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined','shim/tests/payload_stage_probe.c',
                        'shim/payload_stage.c','shim/payload.c','r8/r10_payload/fdt.c','-o',str(exe)],
                        cwd=ROOT,check=True)
        dtb=test.fdt.encode(test.fdt.fixture());elf=test.elf_fixture()
        blob=test.pack.build(elf,dtb);source=td/'payload';fw=td/'firmware';out=td/'loaded'
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0');count=0
        def run(data=blob,firmware=dtb,mode=0,expected=1):
            nonlocal count
            source.write_bytes(data);fw.write_bytes(firmware)
            p=subprocess.run([str(exe),str(source),str(fw),str(mode),str(out)],
                             env=env,capture_output=True,text=True)
            assert p.returncode==expected,(p.returncode,p.stdout,p.stderr)
            count+=1
        run(expected=0)
        # Independent expected image, including non-word-sized file/BSS tails.
        expected=bytearray(0x5000);expected[:7]=b'CODE123'
        expected[0x1000:0x1003]=b'XYZ';expected[0x4000:0x4000+len(dtb)]=dtb
        assert out.read_bytes()==expected
        for mode in range(1,12):run(mode=mode)
        run(data=b'S21R')
        different=bytearray(dtb);struct.pack_into('>I',different,24,17)
        run(firmware=different)
        blocked=test.fdt.encode(test.fdt.fixture(),[(0x80080000,4096)])
        run(data=test.pack.build(elf,blocked),firmware=blocked)
        no_ram=test.fdt.fixture();no_ram[2]=[n for n in no_ram[2] if not n[0].startswith('memory@')]
        no_ram=test.fdt.encode(no_ram)
        run(data=test.pack.build(elf,no_ram),firmware=no_ram)
        dynamic=test.fdt.fixture();dynamic[2][1][2].append(test.fdt.node('dynamic',{'size':test.fdt.u32(4096)}))
        dynamic=test.fdt.encode(dynamic)
        run(data=test.pack.build(elf,dynamic),firmware=dynamic)
        print(f'PAYLOAD STAGE PASS: {count} cases; exact bytes, guards and no writes on rejection')
if __name__=='__main__':main()
