#!/usr/bin/env python3
"""Run pinned iOS images through the guarded one-CPU EFI userland profile.

Captures the actual boot ABI and UEFI snapshots with read-only GDB/QMP.
Visual success is recorded separately after inspecting native PNGs.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.xnu import boot_contract as c,efi_lab as efi,efi_memory as memory,resident,userland_profile as profile
from lab.xnu import fdt_adapter as adapter
from scripts import run_xnu_lab as lab
from scripts.run_hackios_userland import Console,prepare_memory
from scripts.capture_xnu_contract import Reader,ARM_INIT
from scripts.check_hackios_userland import replacements


def inputs(args):
    source=json.loads((ROOT/'docs/references/hackios-userland-inputs-20261023.json').read_text())
    result={}
    for role,path in (('root',args.root_image),('system',args.system_image)):
        result[role]=lab.verified(path,source['images'][role]['sha256'])
        adapter.require(path.stat().st_size==source['images'][role]['bytes'],'image length differs')
    for name in ('code','vars'):result['efi_'+name]=lab.verified(getattr(args,'efi_'+name),lab.EFI_HASHES[name])
    ref=json.loads(lab.REFERENCE.read_text());expected=next(x['sha256'] for x in ref['kernel_prebuilt_integrity']['checks'] if x['path']=='prebuilt/mach.development.bcm2837')
    result['kernel']=lab.verified(args.kernel_tree/'prebuilt/mach.development.bcm2837',expected)
    git=['git','-C',str(args.kernel_tree)];adapter.require(subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip()==efi.REVISION,'kernel revision changed')
    adapter.require(not subprocess.check_output(git+['diff','--name-only']),'kernel tracked changes')
    ugit=['git','--git-dir='+str(args.kernel_tree/'.userland.git'),'--work-tree='+str(args.kernel_tree)]
    adapter.require(subprocess.check_output(ugit+['rev-parse','HEAD'],text=True).strip()=='906425b75e02b4f99eb5d7bb1ef7c9583472d772','userland revision changed')
    jobs=subprocess.check_output(ugit+['show','HEAD:userland/mkjobs.py']).decode();build=subprocess.check_output(ugit+['show','HEAD:userland/build.sh']).decode();jobs,build=replacements(jobs,build)
    adapter.require(set(subprocess.check_output(ugit+['diff','--name-only'],text=True).splitlines())=={'userland/mkjobs.py','userland/build.sh'},'unexpected userland diff')
    for path,text in (('userland/mkjobs.py',jobs),('userland/build.sh',build)):adapter.require((args.kernel_tree/path).read_bytes()==text.encode(),'audited patch mismatch')
    return result


def capture(console,reader,process,work,built,raw_profile,system_bytes,small_bytes,kernel):
    adapter.require(reader.command(f'Z1,{ARM_INIT:x},4')=='OK','breakpoint failed');reader.send('c')
    adapter.require(reader.packet().startswith('T05'),'unexpected kernel stop')
    regs=bytes.fromhex(reader.command('g'));x0,=struct.unpack_from('<Q',regs);pc,pstate=struct.unpack_from('<QI',regs,256)
    adapter.require(pc==ARM_INIT and pstate&12==4,'not arm_init EL1')
    ba=reader.memory(x0,c.BOOT_SIZE);boot=c.BootArgs.decode(ba);adt=reader.memory(boot.tree_va,boot.tree_size);tree=c.decode_tree(adt)
    adapter.require(boot.encode()==ba and c.encode_tree(tree)==adt,'ABI round-trip failed')
    serial=(work/'serial.log').read_bytes();addresses=re.findall(rb'CurrentEL=.*? image=([0-9a-f]+)\r?$',serial,re.M)
    adapter.require(len(addresses)==1,'loader address missing');actual=int(addresses[0],16);delta=actual-built['symbols']['__ImageBase']
    reads={}
    def physical(name,count):
        address=built['symbols'][name]+delta;target=work/(name+'.bin')
        console.qmp.command('pmemsave',val=address,size=count,filename=str(target));data=target.read_bytes()
        adapter.require(len(data)==count,'short physical capture');reads[name]={'physical':hex(address),'bytes':count,'sha256':efi.sha(data)};return data
    maps=profile.snapshots(physical('s21_maps',4*(memory.CAPACITY+40)))
    values={name:struct.unpack('<Q',physical(name,8))[0] for name in ('win_base','win_size','s21_payload_status','s21_payload_claim','s21_window_status','s21_window_claim','s21_frame_base','s21_frame_size','s21_frame_after_stage')}
    claims={'payload':{'base':memory.PAYLOAD.base,'size':memory.PAYLOAD.size,'status':values['s21_payload_status'],'returned':values['s21_payload_claim']},
            'window':{'base':values['win_base'],'size':values['win_size'],'status':values['s21_window_status'],'returned':values['s21_window_claim']}}
    claim=dict(zip(('base','size'),struct.unpack('<QQ',physical('s21_resident_cfg',16))))
    ident,epoch=struct.unpack('<I4xQ',physical('s21_profile_cfg',16));typed=profile.decode(raw_profile)
    adapter.require((ident,epoch)==(typed['id'],typed['epoch']) and claim==resident.decode(resident.encode(system_bytes)),'native descriptors differ from inputs')
    frame={'base':values['s21_frame_base'],'size':values['s21_frame_size'],'after_stage':values['s21_frame_after_stage']}
    checked,ownership=memory.verify(maps,claims,boot,tree,boot.physical(x0,c.BOOT_SIZE).base,kernel,resident_claim=claim,video_claim=frame)
    limits=profile.verify(boot,tree,typed,small_bytes)
    header=reader.memory(resident.BASE-boot.phys_base+boot.virt_base,4096);resident.verify_header(header,system_bytes)
    for name,data in (('boot-args.bin',ba),('apple-tree.bin',adt),('resident-header.bin',header)):(work/name).write_bytes(data)
    for stage,snapshot in maps.items():(work/f'efi-map-{stage}.bin').write_bytes(snapshot.raw)
    shot=console.capture('arm-init');adapter.require(shot['dimensions']==[1125,2436],'QEMU mode differs')
    result={'verified':True,'pc':hex(pc),'pstate':hex(pstate),'x0':hex(x0),'loader_actual_base':hex(actual),'loader_relocation':delta,'read_only_gdb_qmp':True,
            'boot_args_sha256':efi.sha(ba),'tree_sha256':efi.sha(adt),'header_sha256':efi.sha(header),'profile':checked,'userland_limits':limits,
            'memory_audit':ownership,'physical_reads':reads,'boot_args_cmdline':boot.cmdline}
    (work/'contract.json').write_text(json.dumps(result,indent=2)+'\n')
    adapter.require(reader.command(f'z1,{ARM_INIT:x},4')=='OK','remove breakpoint failed');reader.send('c')
    return result


def run(args):
    checked=inputs(args);work=args.out;work.mkdir(parents=True,exist_ok=False);(work/'build').mkdir();(work/'esp/EFI/BOOT').mkdir(parents=True)
    built=efi.build(args.kernel_tree,args.llvm_root,work/'build');shutil.copyfile(work/'build/loader.efi',work/'esp/EFI/BOOT/BOOTAA64.EFI');shutil.copyfile(args.efi_vars,work/'vars.fd')
    shutil.copytree(args.tools/'usr/share/qemu',work/'roms');shutil.copyfile(args.tools/'usr/share/seabios/vgabios-ramfb.bin',work/'roms/vgabios-ramfb.bin')
    epoch=int(time.time());raw_profile=profile.encode(epoch);desc=resident.encode(args.system_image.stat().st_size)
    gib=6 if args.case=='headroom' else 7
    resource=adapter.extract(efi.qemu_fdt(gib),adapter.build_probe(work));tree=efi.fragment(resource,ram_size=gib<<30)
    if args.case=='profile':raw_profile=raw_profile[:12]+struct.pack('<I',2)+raw_profile[16:]
    payload=efi.pack((args.kernel_tree/'prebuilt/mach.development.bcm2837').read_bytes(),args.root_image.read_bytes(),c.encode_tree(tree),desc,raw_profile)
    if args.case=='cmdline':payload=payload.replace(profile.TAG,b'cpus=8'+b'\0'*(len(profile.TAG)-6))
    (work/'payload.bin').write_bytes(payload)
    if args.case=='positive':resident_memory=prepare_memory(args.system_image,work/'ram.img')
    else:
        with (work/'ram.img').open('wb') as f:f.truncate(12<<30)
        resident_memory={'negative_case_unpopulated':True}
    command=lab.tool_commands(args.tools)['qemu']+['-L',str(work/'roms'),'-M','virt,gic-version=3','-cpu','cortex-a76','-smp','1','-m',f'{gib}G','-accel','tcg,tb-size=384',
        '-object',f'memory-backend-file,id=ram,size={gib<<30},mem-path={work/"ram.img"},share=off','-machine','memory-backend=ram',
        '-global','virtio-mmio.force-legacy=false','-drive',f'if=pflash,format=raw,readonly=on,file={args.efi_code}',
        '-drive',f'if=pflash,format=raw,file={work/"vars.fd"}','-drive',f'file=fat:rw:{work/"esp"},format=raw,if=virtio',
        '-device',f'loader,file={work/"payload.bin"},addr=0xf0000000,force-raw=on','-device','ramfb','-device','virtio-tablet-device','-device','virtio-keyboard-device',
        '-display','none','-serial',f'file:{work/"serial.log"}','-monitor','none','-no-reboot','-nic','none','-S']
    sources=('lab/xnu/efi_resources.c','lab/xnu/efi_resources.h','lab/xnu/efi_lab.py','lab/xnu/efi_memory_loader.inc','lab/xnu/userland_profile.py','lab/xnu/efi_memory.py','lab/xnu/resident.py','lab/xnu/video.py','scripts/run_guarded_userland.py','scripts/run_hackios_userland.py')
    report={'date':'2026-10-23','case':args.case,'inputs':checked,'build':built,'command':command,'resident_memory':resident_memory,
            'raw_profile_hex':raw_profile.hex(),'resident_descriptor_hex':desc.hex(),'payload_sha256':efi.sha(payload),
            'own_sources_sha256':{p:lab.sha256(ROOT/p) for p in sources},'strict_resource_consumer':True,'Samsung_tested':False,'UI_visually_verified':False,
            'contract':None,'actions':[],'captures':[],'error':None,'returncode':None,'stopped_by_control':False}
    (work/'inputs.json').write_text(json.dumps(report,indent=2)+'\n');start=time.monotonic();process=None;pipefiles=[];fds=[];console=None
    try:
        with (work/'stderr.log').open('wb') as err:
            if args.case=='positive':
                for suffix in ('in','out'):
                    path=work/('qmp.'+suffix);os.mkfifo(path);pipefiles.append(path);fds.append(os.open(path,os.O_RDWR|os.O_NONBLOCK))
                qin=os.fdopen(fds[0],'wb',buffering=0);qout=os.fdopen(fds[1],'rb',buffering=0)
                command+=['-chardev',f'pipe,id=qmp,path={work/"qmp"}','-mon','chardev=qmp,mode=control','-gdb','stdio']
            else:command+=['-qmp','stdio']
            (work/'command.json').write_text(json.dumps(command,indent=2)+'\n')
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err)
            console=Console(SimpleNamespace(stdin=qin,stdout=qout) if args.case=='positive' else process,work)
            if args.case!='positive':
                console.qmp.command('cont');report['returncode']=process.wait(timeout=120)
            else:
                reader=Reader(process,180);report['contract']=capture(console,reader,process,work,built,raw_profile,args.system_image.stat().st_size,args.root_image.stat().st_size,(args.kernel_tree/'prebuilt/mach.development.bcm2837').read_bytes())
                with args.system_image.open('rb') as f:adapter.require(efi.sha(f.read(4096))==report['contract']['header_sha256'],'physical header differs from actual system image')
                observation_deadline=time.monotonic()+profile.SECONDS+300
                report['observation_grace_seconds']=300
                report['observation_deadline_from']='arm_init_resume'
                next_capture=15;offset=0;seen=set()
                while process.poll() is None and time.monotonic()<observation_deadline:
                    elapsed=int(time.monotonic()-start)
                    if elapsed>=next_capture:console.capture(f'auto-{elapsed:04d}');next_capture=elapsed+15
                    with (work/'serial.log').open('rb') as f:f.seek(offset);chunk=f.read();offset+=len(chunk)
                    for marker in ('Darwin Kernel Version','launchd.ios','SpringBoard','backboardd','systemShellDidFinishLaunching'):
                        if marker.encode() in chunk:seen.add(marker)
                    control=work/'control.json'
                    if control.exists():
                        value=json.loads(control.read_text());control.unlink()
                        for action in value.get('actions',[]):console.action(action)
                        if value.get('stop'):report['stopped_by_control']=True;console.qmp.command('quit');break
                    report.update(elapsed_seconds=elapsed,markers_seen=sorted(seen),captures=console.captures,actions=console.events)
                    (work/'status.json').write_text(json.dumps(report,indent=2)+'\n');time.sleep(1)
                if process.poll() is None:
                    if not report['stopped_by_control']:report['observation_timeout']=True;console.qmp.command('quit')
                    process.wait(timeout=15)
                report['returncode']=process.returncode
    except Exception as exc:report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if process is not None:
            if process.poll() is None:process.kill();process.wait()
            process.stdin.close();process.stdout.close()
        for name in ('qin','qout'):
            if name in locals():locals()[name].close()
        for p in pipefiles:
            if p.exists():p.unlink()
    serial=(work/'serial.log').read_bytes() if (work/'serial.log').exists() else b''
    report.update(serial_sha256=efi.sha(serial),elapsed_seconds=round(time.monotonic()-start,2),captures=console.captures if console else [],actions=console.events if console else [])
    if args.case=='positive':
        report['completed_native_return']=False
        if report['error'] is None and report['returncode']==0 and report['contract'] and not report.get('observation_timeout'):
            try:
                adapter.require(b'--- loader_return_after expired ---' in serial and b'kernel returned: log at ' in serial and re.search(rb'^returned [0-9]+ 0\r?$',serial,re.M),'native budget return missing')
                emitted,claims=memory.parse_serial(serial);initial=profile.snapshots((work/'s21_maps.bin').read_bytes())
                adapter.require(set(emitted)==set(initial)=={0,1,2,3},'incomplete returned snapshots')
                for stage in range(4):
                    a,b=emitted[stage],initial[stage]
                    adapter.require((a.raw,a.stride,a.version,a.key)==(b.raw,b.stride,b.version,b.key),'returned snapshot differs from entry capture')
                adapter.require(claims==report['contract']['memory_audit']['claims'],'returned claims differ from entry capture')
                report['completed_native_return']=True
            except ValueError as exc:report['error']=type(exc).__name__+': '+str(exc)
        report['passed']=report['error'] is None and report['returncode']==0 and bool(report['contract']) and report['completed_native_return']
    else:
        marker=b'S21 USERLAND: REJECT headroom' if args.case=='headroom' else b'S21 XNU ADAPTER: REJECT payload'
        report['checks']={'exit_zero':report['returncode']==0,'specific_rejection':marker in serial,'no_copy':b'kernel loaded at pa' not in serial,'no_jump':b'jumping to ' not in serial,'no_darwin':b'Darwin Kernel Version' not in serial,'no_resident_read':b'S21 RESIDENT: ownership/header PASS' not in serial}
        report['passed']=not report['error'] and all(report['checks'].values())
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'case':args.case,'passed':report['passed'],'error':report['error'],'report':str(work/'report.json')}),flush=True)
    return 0 if report['passed'] else 2

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('kernel-tree','llvm-root','root-image','system-image','efi-code','efi-vars','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--case',choices=('positive','headroom','profile','cmdline'),default='positive');p.add_argument('--tools',type=Path,default=ROOT/'tools/root');args=p.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):
            value=value.resolve()
            if ',' in str(value):p.error('comma in QEMU path')
            setattr(args,key,value)
    try:sys.exit(run(args))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:print('Guarded userland error: '+str(exc),file=sys.stderr);sys.exit(2)
