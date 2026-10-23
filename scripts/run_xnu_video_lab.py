#!/usr/bin/env python3
"""Capture graphics boot_args at XNU arm_init and verify UEFI framebuffer ownership."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.xnu import efi_lab as efi, efi_memory as memory, boot_contract as c, fdt_adapter as adapter
from scripts import run_xnu_lab as lab
from scripts.run_xnu_adapter_lab import run_case as headless_case
from scripts.capture_xnu_contract import Reader, ARM_INIT
from scripts.check_xnu_ramfb import QMP


def run_case(args,work,name,loader,kernel,ramdisk,tree):
    work.mkdir();(work/'esp/EFI/BOOT').mkdir(parents=True)
    shutil.copyfile(loader,work/'esp/EFI/BOOT/BOOTAA64.EFI');shutil.copyfile(args.efi_vars,work/'vars.fd')
    payload=efi.pack(kernel,ramdisk,c.encode_tree(tree));(work/'payload.bin').write_bytes(payload)
    cmd=lab.tool_commands(args.tools)['qemu']+['-L',str(args.out/'roms'),'-M','virt,gic-version=3',
        '-cpu','cortex-a76','-smp','1','-m','6G','-accel','tcg,tb-size=128',
        '-drive',f'if=pflash,format=raw,readonly=on,file={args.efi_code}',
        '-drive',f'if=pflash,format=raw,file={work/"vars.fd"}',
        '-drive',f'file=fat:rw:{work/"esp"},format=raw,if=virtio',
        '-device',f'loader,file={work/"payload.bin"},addr=0xF0000000,force-raw=on',
        '-device','ramfb','-display','none','-serial',f'file:{work/"serial.log"}',
        '-monitor','none','-no-reboot','-nic','none']
    capture=None
    with (work/'stderr.log').open('wb') as err:
        if name=='positive':
            # Named pipes keep QMP separate from GDB stdio, without host sockets.
            paths=[work/'qmp.in',work/'qmp.out'];fds=[]
            try:
                for path in paths:os.mkfifo(path)
                for path in paths:fds.append(os.open(path,os.O_RDWR|os.O_NONBLOCK))
                inp=os.fdopen(fds[0],'wb',buffering=0);out=os.fdopen(fds[1],'rb',buffering=0)
                cmd+=['-chardev',f'pipe,id=qmp,path={work/"qmp"}','-mon','chardev=qmp,mode=control',
                      '-S','-gdb','stdio']
                (work/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
                process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err)
                try:
                    qmp=QMP(SimpleNamespace(stdin=inp,stdout=out))
                    reader=Reader(process,90)
                    adapter.require(reader.command(f'Z1,{ARM_INIT:x},4')=='OK','breakpoint failed')
                    reader.send('c');adapter.require(reader.packet().startswith('T05'),'unexpected stop')
                    regs=bytes.fromhex(reader.command('g'));x0,=struct.unpack_from('<Q',regs)
                    pc,pstate=struct.unpack_from('<QI',regs,256)
                    adapter.require(pc==ARM_INIT and (pstate&0xc)==4,'not arm_init EL1')
                    raw=reader.memory(x0,c.BOOT_SIZE);boot=c.BootArgs.decode(raw)
                    raw_tree=reader.memory(boot.tree_va,boot.tree_size);actual=c.decode_tree(raw_tree)
                    adapter.require(boot.encode()==raw and c.encode_tree(actual)==raw_tree,'ABI round-trip failed')
                    (work/'boot-args.bin').write_bytes(raw);(work/'apple-tree.bin').write_bytes(raw_tree)
                    qmp.command('screendump',filename=str(work/'arm-init.png'),format='png')
                    capture={'pc':hex(pc),'pstate':hex(pstate),'x0':hex(x0),'video':list(boot.video),
                             'boot_args_sha256':efi.sha(raw),'apple_tree_sha256':efi.sha(raw_tree),
                             'read_only_gdb':True,'screenshot_sha256':lab.sha256(work/'arm-init.png')}
                    adapter.require(reader.command(f'z1,{ARM_INIT:x},4')=='OK','remove breakpoint failed')
                    reader.send('c');returncode=process.wait(timeout=90)
                finally:
                    if process.poll() is None:process.kill();process.wait()
                    process.stdin.close();process.stdout.close()
            finally:
                for f in ('inp','out'):
                    if f in locals():locals()[f].close()
                for path in paths:
                    if path.exists():path.unlink()
        else:
            cmd+=['-S','-qmp','stdio']
            (work/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
            process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err)
            try:
                qmp=QMP(process);qmp.command('cont')
                returncode=process.wait(timeout=90)
            finally:
                if process.poll() is None:process.kill();process.wait()
                process.stdin.close();process.stdout.close()
    serial=(work/'serial.log').read_bytes();maps,claims=memory.parse_serial(serial)
    for stage,snapshot in maps.items():(work/f'efi-map-{stage}.bin').write_bytes(snapshot.raw)
    allocations=re.findall(rb'^S21 VIDEO ALLOCATION ([0-9a-f]{1,16}) ([0-9a-f]{1,16})\r?$',serial,re.M)
    adapter.require(len(allocations)==1,'missing/duplicate framebuffer allocation')
    frame_claim=dict(zip(('base','size'),(int(x,16) for x in allocations[0])))
    ownership=None
    if name=='positive':
        profile,ownership=memory.verify(maps,claims,boot,actual,boot.physical(x0,c.BOOT_SIZE).base,kernel,video_claim=frame_claim)
        from PIL import Image
        with Image.open(work/'arm-init.png') as image:dimensions=list(image.size)
        capture['profile']=profile;capture['qemu_dimensions']=dimensions
        checks=lab.assess_log(serial,returncode,False)
        checks.update(framebuffer_owned=ownership['verified'],mode_matches_qemu=dimensions==list(boot.video[3:5])==[1125,2436],
                      actual_esp_hash=lab.sha256(loader)==lab.sha256(work/'esp/EFI/BOOT/BOOTAA64.EFI'),
                      no_video_rejection=b'S21 VIDEO: REJECT' not in serial,
                      native_resources=b'S21 XNU ADAPTER: resources PASS' in serial,
                      native_layout=b'S21 XNU ADAPTER: layout PASS before jump' in serial,
                      native_video=b'S21 VIDEO: boot arguments PASS' in serial,
                      kernel_framebuffer=b'MiniIOMobileFramebuffer: display 1125x2436 on a panel of 1125x2436 (4500 bytes per row)' in serial)
    else:
        checks={'exit_zero':returncode==0,'rejected':b'S21 VIDEO: REJECT framebuffer stage 2' in serial,
                'no_copy':b'kernel loaded at pa' not in serial,'no_jump':b'jumping to ' not in serial,
                'no_darwin':b'Darwin Kernel Version' not in serial,'no_init':b'S21 XNU LAB:' not in serial}
        if name=='page-busy':checks['fault_api_succeeded']=b'S21 VIDEO TEST: page-busy status 0\r\n' in serial
    report={'case':name,'passed':all(checks.values()),'checks':checks,'command':cmd,'capture':capture,
            'framebuffer_allocation':frame_claim,'memory_audit':ownership,
            'maps':{memory.STAGES[i]:m.report() for i,m in maps.items()},
            'serial_sha256':efi.sha(serial),'loader_sha256':lab.sha256(loader),'payload_sha256':efi.sha(payload),
            'qemu_returncode':returncode,'hardware_ready':False,'iOS_GUI':False}
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(name+(': PASS' if report['passed'] else ': FAIL'),flush=True)
    return report


def run(args):
    previous=json.loads((args.lab_run/'report.json').read_text())
    adapter.require(previous.get('passed') and not previous.get('negative_fixture'),'positive baseline required')
    kernel_path=args.kernel_tree/'prebuilt/mach.development.bcm2837'
    ref=json.loads(lab.REFERENCE.read_text());expected=next(x['sha256'] for x in ref['kernel_prebuilt_integrity']['checks'] if x['path']=='prebuilt/mach.development.bcm2837')
    lab.verified(kernel_path,expected);lab.verified(args.lab_run/'root.apfs',previous['artifacts']['root.apfs']['sha256'])
    for name in ('code','vars'):lab.verified(getattr(args,'efi_'+name),lab.EFI_HASHES[name])
    args.out.mkdir(parents=True,exist_ok=False);(args.out/'build').mkdir()
    shutil.copytree(args.tools/'usr/share/qemu',args.out/'roms')
    shutil.copyfile(args.tools/'usr/share/seabios/vgabios-ramfb.bin',args.out/'roms/vgabios-ramfb.bin')
    built=efi.build(args.kernel_tree,args.llvm_root,args.out/'build')
    resource=adapter.extract(efi.qemu_fdt(),adapter.build_probe(args.out));tree=efi.fragment(resource)
    kernel=kernel_path.read_bytes();ramdisk=(args.lab_run/'root.apfs').read_bytes()
    cases={};fault_builds={}
    if args.case=='positive':
        cases['positive']=run_case(args,args.out/'positive','positive',args.out/'build/loader.efi',kernel,ramdisk,tree)
    elif args.case=='headless':
        cases['headless']=headless_case(args.out/'headless','positive',args.out/'build/loader.efi',kernel,ramdisk,tree,resource,
            args.tools,args.efi_code,args.efi_vars,90)
    else:
        fault=('stride','input-overlap','page-busy').index(args.case)+1
        out=args.out/('build-'+args.case);out.mkdir()
        fault_builds[args.case]=efi.build(args.kernel_tree,args.llvm_root,out,video_test=fault)
        cases[args.case]=run_case(args,args.out/args.case,args.case,out/'loader.efi',kernel,ramdisk,tree)
    sources=('lab/xnu/efi_lab.py','lab/xnu/ramfb.py','lab/xnu/efi_memory_loader.inc','lab/xnu/efi_memory.c','lab/xnu/efi_memory.h',
             'lab/xnu/efi_memory.py','lab/xnu/boot_contract.py','lab/xnu/video.py','lab/xnu/efi_video.c','lab/xnu/efi_video.h',
             'scripts/run_xnu_video_lab.py','scripts/check_xnu_ramfb.py','scripts/capture_xnu_contract.py','scripts/test_xnu_video.py')
    report={'date':'2026-10-23','scope':'one-CPU QEMU graphics boot contract; XNU prebuilt, own init; UEFI resident',
            'passed':all(v['passed'] for v in cases.values()),'build':built,'fault_builds':fault_builds,'cases':cases,
            'kernel_sha256':efi.sha(kernel),'ramdisk_sha256':efi.sha(ramdisk),'own_sources_sha256':{p:lab.sha256(ROOT/p) for p in sources},
            'iOS_GUI_tested':False,'Samsung_tested':False}
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('kernel-tree','llvm-root','lab-run','efi-code','efi-vars','out'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--case',choices=('positive','headless','stride','input-overlap','page-busy'),required=True)
    parser.add_argument('--tools',type=Path,default=ROOT/'tools/root');args=parser.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):
            value=value.resolve()
            if ',' in str(value):parser.error('comma in QEMU path')
            setattr(args,key,value)
    try:sys.exit(run(args))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:print('Video lab error: '+str(exc),file=sys.stderr);sys.exit(2)
