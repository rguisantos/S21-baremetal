#!/usr/bin/env python3
"""One-CPU strict EFI consumer: resident md0, deliberately invalid small md1."""
import argparse
import copy
import json
import re
from pathlib import Path
import shutil
import struct
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.xnu import efi_lab as efi, efi_memory as memory, resident, boot_contract as c, fdt_adapter as adapter
from scripts import run_xnu_lab as lab
from scripts.capture_xnu_contract import Reader,ARM_INIT
from scripts.check_xnu_ramfb import QMP


def run(args):
    previous=json.loads((args.lab_run/'report.json').read_text())
    adapter.require(previous.get('passed') and not previous.get('negative_fixture'),'positive baseline required')
    kernel_path=args.kernel_tree/'prebuilt/mach.development.bcm2837'
    ref=json.loads(lab.REFERENCE.read_text())
    expected=next(x['sha256'] for x in ref['kernel_prebuilt_integrity']['checks'] if x['path']=='prebuilt/mach.development.bcm2837')
    lab.verified(kernel_path,expected);lab.verified(args.lab_run/'root.apfs',previous['artifacts']['root.apfs']['sha256'])
    for name in ('code','vars'):lab.verified(getattr(args,'efi_'+name),lab.EFI_HASHES[name])
    work=args.out;work.mkdir(parents=True,exist_ok=False);(work/'build').mkdir();(work/'esp/EFI/BOOT').mkdir(parents=True)
    shutil.copytree(args.tools/'usr/share/qemu',work/'roms')
    shutil.copyfile(args.tools/'usr/share/seabios/vgabios-ramfb.bin',work/'roms/vgabios-ramfb.bin')
    built=efi.build(args.kernel_tree,args.llvm_root,work/'build',resident_test=int(args.case=='page-busy'))
    shutil.copyfile(work/'build/loader.efi',work/'esp/EFI/BOOT/BOOTAA64.EFI');shutil.copyfile(args.efi_vars,work/'vars.fd')
    kernel=kernel_path.read_bytes();image=bytearray((args.lab_run/'root.apfs').read_bytes())
    if args.case=='header':image[32]^=1
    (work/'resident.apfs').write_bytes(image)
    desc=resident.encode(len(image))
    if args.case=='input-overlap':desc=desc[:16]+struct.pack('<Q',0xf0000000)+desc[24:]
    if args.case=='oversize':desc=desc[:24]+struct.pack('<Q',resident.LIMIT+4096)
    resource=adapter.extract(efi.qemu_fdt(),adapter.build_probe(work));tree=efi.fragment(resource)
    small=b'\0'*0x4000 # Not APFS. Passing the root test cannot come from this disk.
    payload=efi.pack(kernel,small,c.encode_tree(tree),desc);(work/'payload.bin').write_bytes(payload)
    command=lab.tool_commands(args.tools)['qemu']+['-L',str(work/'roms'),'-M','virt,gic-version=3',
        '-cpu','cortex-a76','-smp','1','-m','6G','-accel','tcg,tb-size=128',
        '-drive',f'if=pflash,format=raw,readonly=on,file={args.efi_code}',
        '-drive',f'if=pflash,format=raw,file={work/"vars.fd"}',
        '-drive',f'file=fat:rw:{work/"esp"},format=raw,if=virtio',
        '-device',f'loader,file={work/"payload.bin"},addr=0xf0000000,force-raw=on',
        '-device',f'loader,file={work/"resident.apfs"},addr=0xfc000000,force-raw=on',
        '-display','none','-serial',f'file:{work/"serial.log"}','-monitor','none','-no-reboot','-nic','none','-S']
    if args.graphics:command+=['-device','ramfb']
    capture=None;ownership=None
    with (work/'stderr.log').open('wb') as err:
        command+=['-gdb','stdio'] if args.case=='positive' else ['-qmp','stdio']
        (work/'command.json').write_text(json.dumps(command,indent=2)+'\n')
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err)
        try:
            if args.case=='positive':
                reader=Reader(process,90);adapter.require(reader.command(f'Z1,{ARM_INIT:x},4')=='OK','breakpoint failed')
                reader.send('c');adapter.require(reader.packet().startswith('T05'),'unexpected stop')
                regs=bytes.fromhex(reader.command('g'));x0,=struct.unpack_from('<Q',regs);pc,pstate=struct.unpack_from('<QI',regs,256)
                adapter.require(pc==ARM_INIT and pstate&12==4,'not arm_init EL1')
                raw=reader.memory(x0,c.BOOT_SIZE);args_boot=c.BootArgs.decode(raw);raw_tree=reader.memory(args_boot.tree_va,args_boot.tree_size);actual=c.decode_tree(raw_tree)
                adapter.require(args_boot.encode()==raw and c.encode_tree(actual)==raw_tree,'ABI mismatch')
                root_va=resident.BASE-args_boot.phys_base+args_boot.virt_base
                header=reader.memory(root_va,4096);resident.verify_header(header,len(image));adapter.require(header==image[:4096],'resident header differs at arm_init')
                for name,data in [('boot-args.bin',raw),('apple-tree.bin',raw_tree),('resident-header.bin',header)]: (work/name).write_bytes(data)
                capture={'pc':hex(pc),'pstate':hex(pstate),'x0':hex(x0),'boot_args_sha256':efi.sha(raw),'tree_sha256':efi.sha(raw_tree),'resident_header_sha256':efi.sha(header),'read_only_gdb':True}
                adapter.require(reader.command(f'z1,{ARM_INIT:x},4')=='OK','remove breakpoint failed');reader.send('c')
            else:QMP(process).command('cont')
            returncode=process.wait(timeout=90)
        finally:
            if process.poll() is None:process.kill();process.wait()
            process.stdin.close();process.stdout.close()
    serial=(work/'serial.log').read_bytes();snapshots,claims=memory.parse_serial(serial)
    for stage,snapshot in snapshots.items():(work/f'efi-map-{stage}.bin').write_bytes(snapshot.raw)
    if args.case=='positive':
        claim=resident.parse_serial(serial);adapter.require(claim==resident.decode(desc),'emitted declaration differs from payload')
        frame=None
        if args.graphics:
            allocations=re.findall(rb'^S21 VIDEO ALLOCATION ([0-9a-f]+) ([0-9a-f]+)\r?$',serial,re.M)
            phases=re.findall(rb'^S21 VIDEO ACQUIRED AFTER ([01])\r?$',serial,re.M)
            adapter.require(len(allocations)==len(phases)==1,'framebuffer allocation record missing')
            frame=dict(zip(('base','size'),(int(x,16) for x in allocations[0])));frame['after_stage']=int(phases[0])
        profile,ownership=memory.verify(snapshots,claims,args_boot,actual,args_boot.physical(x0,c.BOOT_SIZE).base,kernel,resident_claim=claim,video_claim=frame)
        capture['profile']=profile
        controls={}
        swapped=copy.deepcopy(actual);props=swapped.at('/chosen/memory-map').properties
        props['RAMDisk'],props['RAMDisk1']=props['RAMDisk1'],props['RAMDisk']
        for label,changed_tree,changed_claim in (
            ('missing_declaration',actual,None),
            ('wrong_root_role',swapped,claim),
            ('wrong_declared_size',actual,dict(claim,size=claim['size']+4096))):
            try:memory.verify(snapshots,claims,args_boot,changed_tree,args_boot.physical(x0,c.BOOT_SIZE).base,kernel,resident_claim=changed_claim,video_claim=frame)
            except c.ContractError:controls[label]=True
            else:controls[label]=False
        checks=lab.assess_log(serial,returncode,False)
        checks.update(controls)
        checks.update(resident_owned=ownership['verified'],actual_header_at_arm_init=True,
            invalid_small_ramdisk=small[:4]==b'\0'*4 and b'NXSB' not in small,
            resident_is_md0=profile['placements']['RAMDisk'][0]=='0xfc000000',
            embedded_is_md1=profile['placements']['RAMDisk1'][1]=='0x4000',
            native_before_copy=b'S21 RESIDENT: ownership/header PASS stage 2' in serial,
            native_handoff=b'S21 RESIDENT: ownership/header PASS stage 3' in serial,
            no_resident_rejection=b'S21 RESIDENT: REJECT' not in serial,
            actual_esp_hash=lab.sha256(work/'build/loader.efi')==lab.sha256(work/'esp/EFI/BOOT/BOOTAA64.EFI'))
    else:
        marker={'header':b'S21 RESIDENT: REJECT APFS header','page-busy':b'S21 RESIDENT: REJECT ownership stage 2',
                'input-overlap':b'S21 XNU ADAPTER: REJECT payload','oversize':b'S21 XNU ADAPTER: REJECT payload'}[args.case]
        checks={'exit_zero':returncode==0,'specific_rejection':marker in serial,'no_copy':b'kernel loaded at pa' not in serial,
                'no_jump':b'jumping to ' not in serial,'no_darwin':b'Darwin Kernel Version' not in serial,'no_init':b'S21 XNU LAB:' not in serial}
        if args.case=='page-busy':checks['fault_api_succeeded']=b'S21 RESIDENT TEST: page-busy status 0\r\n' in serial
    if args.case=='positive' and args.graphics:
        checks['framebuffer_with_resident']=b'MiniIOMobileFramebuffer: display 1125x2436 on a panel of 1125x2436 (4500 bytes per row)' in serial
    sources=('lab/xnu/efi_lab.py','lab/xnu/efi_resources.c','lab/xnu/efi_resources.h','lab/xnu/efi_memory_loader.inc','lab/xnu/efi_memory.py','lab/xnu/resident.py','lab/xnu/video.py','scripts/run_xnu_resident_lab.py','scripts/test_xnu_resident.py')
    report={'date':'2026-10-23','case':args.case,'passed':all(checks.values()),'checks':checks,'build':built,'command':command,
            'capture':capture,'memory_audit':ownership,'maps':{memory.STAGES[i]:m.report() for i,m in snapshots.items()},
            'resident_bytes':len(image),'resident_sha256':efi.sha(image),'resident_descriptor_hex':desc.hex(),
            'small_disk_sha256':efi.sha(small),'payload_sha256':efi.sha(payload),'serial_sha256':efi.sha(serial),
            'qemu_returncode':returncode,'own_sources_sha256':{p:lab.sha256(ROOT/p) for p in sources},
            'graphics':args.graphics,'scope':'One-CPU QEMU strict EFI resident md0, own init; not full iOS GUI or Samsung',
            'Samsung_tested':False,'iOS_GUI_tested':False}
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(args.case+(': PASS' if report['passed'] else ': FAIL'),flush=True)
    return 0 if report['passed'] else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('kernel-tree','llvm-root','lab-run','efi-code','efi-vars','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--case',choices=('positive','header','page-busy','input-overlap','oversize'),required=True)
    p.add_argument('--graphics',action='store_true')
    p.add_argument('--tools',type=Path,default=ROOT/'tools/root');args=p.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):
            value=value.resolve()
            if ',' in str(value):p.error('comma in QEMU path')
            setattr(args,key,value)
    try:sys.exit(run(args))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:print('Resident lab error: '+str(exc),file=sys.stderr);sys.exit(2)
