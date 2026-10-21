#!/usr/bin/env python3
"""Generate independent DTSpec fixtures; exercise the production C parser.
--write-qemu PATH writes only the integration DTB. --inspect PATH... also
checks real DTBs, with no claim that they are a complete live boot contract.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent

def u32(*values):
    return struct.pack('>'+'I'*len(values), *values)

def u64(*values):
    return struct.pack('>'+'Q'*len(values), *values)

def text(value):
    return value.encode()+b'\0'

def node(name, props=None, children=None):
    return [name, dict(props or {}), list(children or [])]

def encode(tree, reservations=()):
    strings = bytearray()
    names = {}
    def emit(n):
        name, props, children = n
        out = bytearray(u32(1)+text(name))
        out += b'\0'*(-len(out)%4)
        for key, value in props.items():
            if key not in names:
                names[key] = len(strings)
                strings.extend(text(key))
            out.extend(u32(3, len(value), names[key])+value)
            out.extend(b'\0'*(-len(out)%4))
        for child in children:
            out.extend(emit(child))
        out.extend(u32(2))
        return out
    structure = emit(tree)+u32(9)
    reserve = b''.join(u64(a,s) for a,s in reservations)+u64(0,0)
    so = 40+len(reserve)
    ss = so+len(structure)
    header = u32(0xd00dfeed,ss+len(strings),so,ss,40,17,16,0,len(strings),len(structure))
    return header+reserve+structure+strings

def fixture(qemu=False, cells=2):
    ac=cells
    sc=1
    def reg(address,size):
        return (u64(address) if ac==2 else u32(address))+u32(size)
    ram=0x40000000 if qemu else 0x80000000
    dist,rd=(0x08000000,0x080a0000) if qemu else (0x10200000,0x10240000)
    reserved=[] if qemu else [node('firmware@90000000',{'reg':reg(0x90000000,0x100000)})]
    props={'#address-cells':u32(ac),'#size-cells':u32(sc),'interrupt-parent':u32(1)}
    cpus=[node('cpu@0',{'device_type':text('cpu'),'reg':u64(0)})]
    if not qemu: cpus.append(node('cpu@100',{'device_type':text('cpu'),'reg':u64(0x100)}))
    children=[
        node('memory@%x'%ram,{'device_type':text('memory'),'reg':reg(ram,0x08000000 if qemu else 0x40000000)}),
        node('reserved-memory',{'#address-cells':u32(ac),'#size-cells':u32(sc),'ranges':b''},reserved),
        node('cpus',{'#address-cells':u32(2),'#size-cells':u32(0)},cpus),
        node('gic@%x'%dist,{'compatible':text('arm,gic-v3'),'reg':reg(dist,0x10000)+reg(rd,0x20000 if qemu else 0x200000),'phandle':u32(1),'#interrupt-cells':u32(3),'interrupt-controller':b''}),
        node('timer',{'compatible':text('arm,armv8-timer'),'interrupts':u32(1,13,4,1,14,4,1,11,4,1,10,4),'clock-frequency':u32(26000000)}),
    ]
    if not qemu:
        children.append(node('chosen',{'linux,initrd-start':u32(0x84000000),'linux,initrd-end':u32(0x84200000)}))
        if ac==2:
            children.append(node('memory@880000000',{'device_type':text('memory'),'reg':reg(0x880000000,0x20000000)}))
    return node('',props,children)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-qemu',type=Path)
    parser.add_argument('--inspect',type=Path,nargs='*',default=[])
    args=parser.parse_args()
    if args.write_qemu:
        args.write_qemu.parent.mkdir(parents=True,exist_ok=True)
        args.write_qemu.write_bytes(encode(fixture(True),[(0x47f00000,4096)]))
        return
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); probe=td/'probe'
        subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined',str(ROOT/'r8/tests/fdt_probe.c'),
                        str(ROOT/'r8/r10_payload/fdt.c'),'-o',str(probe)],check=True)
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
        count=0
        def inspect(data, boot_args=()):
            path=td/'fixture.dtb';path.write_bytes(data)
            run=subprocess.run([str(probe),str(path),*map(str,boot_args)],env=env,
                               text=True,capture_output=True,check=True)
            return json.loads(run.stdout)
        def check(data, parse=0, boot=None, boot_args=()):
            nonlocal count
            result=inspect(data,boot_args)
            assert result['parse']==parse, result
            if boot is not None: assert result['boot']==boot,result
            count+=1
            return result
        tree=fixture();good=encode(tree,[(0x91000000,0x100000)])
        result=check(good,boot=0)
        assert result['ram'][1][0]=='0x880000000' and result['cpus']==['0x0','0x100']
        assert result['reserved_count']==2 and result['timer_irq']==30
        check(encode(fixture(cells=1)),boot=0)
        check(good,boot=0,boot_args=('0x880010000','0x880020000','0x81f00000','0x100'))
        check(good,boot=-6,boot_args=('0x90000000','0x90010000','0x81f00000',0))
        check(good,boot=-6,boot_args=('0x91000000','0x91010000','0x81f00000',0))
        check(good,boot=-6,boot_args=('0x84000000','0x84010000','0x81f00000',0))
        check(good,boot=-6,boot_args=('0x80080000','0x800c0000','0x80090000',0))
        check(good,boot=-6,boot_args=('0xc0000000','0xc0010000','0x81f00000',0))
        check(good,boot=-1,boot_args=('0xfffffffffffffff0','0xffffffffffffffff','0xfffffffffffffff0',0))
        check(good,boot=-7,boot_args=('0x80080000','0x800c0000','0x81f00000','0x200'))
        t=copy.deepcopy(tree); t[2][0][1]['status']=text('disabled');t[2].pop()
        check(encode(t),boot=-4)
        t=copy.deepcopy(tree);t[2][1][2].append(node('dynamic',{'size':u32(0x10000)}))
        check(encode(t),boot=-5)
        t=copy.deepcopy(tree);t[2][1][2].append(node('group',{'#address-cells':u32(2),'#size-cells':u32(1)},[node('nested',{'reg':u64(0x92000000)+u32(0x10000)})]))
        check(encode(t),boot=-5)
        t=copy.deepcopy(tree);t[2][0][1]['reg']=u64(0xfffffffffffffff0)+u32(0x100)
        check(encode(t),parse=-1)
        t=copy.deepcopy(tree);t[2].append(copy.deepcopy(t[2][0]))
        check(encode(t),parse=-1)
        t=copy.deepcopy(tree);t[2][0][1]['reg']=u32(0x80000000)
        check(encode(t),parse=-1)
        t=copy.deepcopy(tree);t[2][3][1]['reg']=u64(0x80000000)+u32(0x10000)+u64(0x10240000)+u32(0x200000)
        check(encode(t),boot=-6)
        t=copy.deepcopy(tree);t[2][3][1]['#redistributor-regions']=u32(2)
        check(encode(t),parse=-3)
        t=copy.deepcopy(tree);t[2][4][1]['interrupt-parent']=u32(2)
        check(encode(t),boot=-7)
        t=copy.deepcopy(tree);t[2][2][2].append(node('cpu@dup',{'device_type':text('cpu'),'reg':u64(0x100)}))
        check(encode(t),parse=-1)
        t=copy.deepcopy(tree);t[2][0][1]['#address-cells']=u32(5)
        check(encode(t),parse=-3)
        t=copy.deepcopy(tree);t[2][3][1]['#interrupt-cells']=u32(4)
        check(encode(t),parse=-3)
        t=copy.deepcopy(tree);del t[2][3][1]['interrupt-controller']
        check(encode(t),parse=-3)
        t=copy.deepcopy(tree);t[2][4][1]['interrupts']=u32(1,13,4,1,14,1)
        check(encode(t),parse=-3)
        t=copy.deepcopy(tree);t[2][4][1]['interrupts']=u32(1,13,8,1,14,0xf08)
        check(encode(t),boot=0)
        t=copy.deepcopy(tree);t[2][0][1]['reg']=u64(0x80000000,0x40000000);t[1]['#size-cells']=u32(2)
        # Make every root register tuple use two size cells as well.
        t[2][3][1]['reg']=u64(0x10200000,0x10000,0x10240000,0x200000)
        t[2][-1][1]['reg']=u64(0x880000000,0x20000000)
        check(encode(t),boot=0)
        # Structural corruption, not just wrong hardware values.
        for data in [b'',good[:39],good[:-1]]: check(data,parse=-1)
        for off,val in [(0,0),(8,41),(12,len(good)+4),(16,41),(32,0xffffffff),(36,0xfffffffc)]:
            data=bytearray(good);struct.pack_into('>I',data,off,val);check(data,parse=-1)
        data=bytearray(good);struct.pack_into('>I',data,20,16);check(data,parse=-3)
        data=bytearray(good);so=struct.unpack_from('>I',data,8)[0];struct.pack_into('>I',data,so,8);check(data,parse=-1)
        data=bytearray(good);struct.pack_into('>I',data,len(data)-struct.unpack_from('>I',data,32)[0]-4,4);check(data,parse=-1)
        # First property is #address-cells, verify unterminated name and bad offset.
        for off,val in [(so+12,0xffffffff)]:
            data=bytearray(good);struct.pack_into('>I',data,off,val);check(data,parse=-1)
        deep=node('n')
        for _ in range(33):deep=node('n',children=[deep])
        check(encode(node('',children=[deep])),parse=-2)
        t=fixture();t[2]=[node('memory@%x'%(0x10000000+i*0x100000),{'device_type':text('memory'),'reg':u64(0x10000000+i*0x100000)+u32(0x100000)}) for i in range(65)]
        check(encode(t),parse=-2)
        check(encode(tree,[(0xfffffffffffffff0,0x100)]),parse=-1)
        # NUL-less compatible list must not escape its property bounds.
        t=copy.deepcopy(tree);t[2][3][1]['compatible']=b'arm,gic-v3';check(encode(t),parse=-1)
        print(f'FDT MODEL PASS: {count} cases with ASan/UBSan')
        for path in args.inspect:
            run=subprocess.run([str(probe),str(path.resolve())],env=env,text=True,capture_output=True,check=True)
            print(str(path)+': '+run.stdout.strip())

if __name__=='__main__':
    main()
