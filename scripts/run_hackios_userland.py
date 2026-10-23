#!/usr/bin/env python3
"""QEMU reference userland run; upstream resident-image ABI, ramfb-fixed EFI.

This is separate from the strict S21 resource consumer. No network, sound,
phone or host disks are exposed. Prepared iOS images stay outside Git.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_xnu_lab as lab
from scripts.check_xnu_ramfb import QMP

class Console:
    def __init__(self,process,path):
        self.qmp=QMP(process);self.path=path;self.events=[];self.captures=[]
    def event(self,*events):self.qmp.command('input-send-event',events=list(events))
    def pointer(self,x,y,down=None):
        if not 0<=x<=1 or not 0<=y<=1:raise ValueError('pointer outside normalized screen')
        events=[{'type':'abs','data':{'axis':'x','value':round(x*32767)}},
                {'type':'abs','data':{'axis':'y','value':round(y*32767)}}]
        if down is not None:events.append({'type':'btn','data':{'button':'left','down':down}})
        self.event(*events)
    def action(self,a):
        self.events.append({'host_epoch':time.time(),'action':a});kind=a['type']
        if kind=='tap':
            x,y=a['x'],a['y'];self.pointer(x,y);self.pointer(x,y,True);time.sleep(.08);self.pointer(x,y,False)
        elif kind=='swipe':
            x0,y0,x1,y1=(a[k] for k in ('x0','y0','x1','y1'));ms=a.get('ms',400)
            if not 100<=ms<=3000:raise ValueError('swipe duration')
            self.pointer(x0,y0);self.pointer(x0,y0,True);steps=max(2,ms//16)
            for i in range(1,steps+1):
                time.sleep(ms/1000/steps);self.pointer(x0+(x1-x0)*i/steps,y0+(y1-y0)*i/steps)
            self.pointer(x1,y1,False)
        elif kind=='key':
            code={'home':'h','lock':'l','volup':'up','voldown':'down'}[a['name']]
            for down in (True,False):
                self.event({'type':'key','data':{'key':{'type':'qcode','data':code},'down':down}});time.sleep(.08)
        elif kind=='capture':self.capture(a['name'])
        elif kind=='wait':
            seconds=a.get('seconds',1)
            if not 0<=seconds<=30:raise ValueError('wait must be <=30 seconds')
            time.sleep(seconds)
        else:raise ValueError('unknown action')
    def capture(self,name):
        from PIL import Image,ImageStat
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',name):raise ValueError('unsafe capture label')
        target=self.path/(name+'.png')
        if target.exists():raise ValueError('capture already exists')
        self.qmp.command('screendump',filename=str(target),format='png')
        with Image.open(target) as img:
            shot={'path':str(target),'dimensions':list(img.size),'mean_rgb':ImageStat.Stat(img.convert('RGB')).mean,
                  'sha256':lab.sha256(target),'host_epoch':time.time()}
        self.captures.append(shot);return shot

def prepare_memory(source,path):
    offset=0xfc000000-0x40000000
    with source.open('rb') as src,path.open('wb') as dst:
        dst.truncate(12<<30);done=0;total=source.stat().st_size
        while done<total:
            n=os.copy_file_range(src.fileno(),dst.fileno(),min(total-done,32<<20),done,offset+done)
            if n<=0:raise ValueError('short resident image copy')
            done+=n
    return {'guest_base':'0xfc000000','file_offset':hex(offset),'bytes':total,'file_size':12<<30,'guest_mapping':'private'}

def run(args):
    work=args.out;work.mkdir(parents=True,exist_ok=False);(work/'esp/EFI/BOOT').mkdir(parents=True)
    ref=json.loads(lab.REFERENCE.read_text());source=next(s for s in ref['sources'] if s['repository'].endswith('-kernel'))
    head=subprocess.check_output(['git','-C',str(args.kernel_tree),'rev-parse','HEAD'],text=True).strip()
    if head!=source['revision']:raise ValueError('kernel revision changed')
    ugit=['git','--git-dir='+str(args.kernel_tree/'.userland.git'),'--work-tree='+str(args.kernel_tree)]
    userland_head=subprocess.check_output(ugit+['rev-parse','HEAD'],text=True).strip()
    if userland_head!='906425b75e02b4f99eb5d7bb1ef7c9583472d772':raise ValueError('userland revision changed')
    build=json.loads(args.loader_build.read_text());inputs={'loader':lab.verified(args.loader,build['loader_sha256'])}
    for name in ('code','vars'):inputs['efi_'+name]=lab.verified(getattr(args,'efi_'+name),lab.EFI_HASHES[name])
    kernel=args.kernel_tree/'prebuilt/mach.development.bcm2837'
    expected=next(f['sha256'] for f in ref['kernel_prebuilt_integrity']['checks'] if f['path']=='prebuilt/mach.development.bcm2837')
    inputs['kernel']=lab.verified(kernel,expected)
    for name,path in (('root',args.root_image),('system',args.system_image)):
        with path.open('rb') as stream:stream.seek(32);magic=stream.read(4)
        if magic!=b'NXSB':raise ValueError('APFS container required')
        inputs[name]={'path':str(path),'bytes':path.stat().st_size,'sha256':lab.sha256(path)}
    if not 0<args.root_image.stat().st_size<(48<<20):raise ValueError('small image exceeds payload budget')
    if not (1<<30)<args.system_image.stat().st_size<(3<<30):raise ValueError('unexpected resident image size')
    (work/'userland.patch').write_bytes(subprocess.check_output(ugit+['diff','--binary']))
    shutil.copyfile(args.loader,work/'esp/EFI/BOOT/BOOTAA64.EFI');shutil.copyfile(args.efi_vars,work/'vars.fd')
    shutil.copytree(args.tools/'usr/share/qemu',work/'roms')
    shutil.copyfile(args.tools/'usr/share/seabios/vgabios-ramfb.bin',work/'roms/vgabios-ramfb.bin')
    resident=prepare_memory(args.system_image,work/'ram.img');epoch=int(time.time())
    cmdline=f'loader_return_after={args.seconds} epoch={epoch} virtio_input=1 cpus=4'
    mk=args.kernel_tree/'xnuloader/mkpayload.py';expected=next(f['sha256'] for f in source['files_hashed_for_traceability'] if f['path']=='xnuloader/mkpayload.py')
    lab.verified(mk,expected)
    subprocess.run([sys.executable,str(mk),'-o',str(work/'payload.bin'),'kernel='+str(kernel),'ramdisk='+str(args.root_image),
                    '--rdres',f'{args.system_image.stat().st_size:x}','--cmdline',cmdline],check=True)
    cmd=lab.tool_commands(args.tools)['qemu']+['-L',str(work/'roms'),'-M','virt,gic-version=3','-cpu','cortex-a76',
        '-smp','4','-m','7G','-accel','tcg,tb-size=384',
        '-object',f'memory-backend-file,id=ram,size={7<<30},mem-path={work/"ram.img"},share=off','-machine','memory-backend=ram',
        '-global','virtio-mmio.force-legacy=false','-drive',f'if=pflash,format=raw,readonly=on,file={args.efi_code}',
        '-drive',f'if=pflash,format=raw,file={work/"vars.fd"}','-drive',f'file=fat:rw:{work/"esp"},format=raw,if=virtio',
        '-device',f'loader,file={work/"payload.bin"},addr=0xf0000000,force-raw=on',
        '-device','ramfb','-device','virtio-tablet-device','-device','virtio-keyboard-device',
        '-display','none','-serial',f'file:{work/"serial.log"}','-monitor','none','-qmp','stdio','-nic','none','-no-reboot','-S']
    report={'schema_version':1,'scope':'QEMU reference userland run; upstream resident-image ABI, ramfb-fixed reference EFI',
            'kernel_revision':head,'userland_revision':userland_head,'inputs':inputs,'loader_build':build,'resident':resident,
            'userland_patch_sha256':lab.sha256(work/'userland.patch'),'cmdline':cmdline,'command':cmd,
            'own_runner_sha256':lab.sha256(Path(__file__)),'captures':[],'actions':[],
            'Samsung_tested':False,'strict_resource_consumer':False,'UI_visually_verified':False,'stopped_by_control':False}
    (work/'inputs.json').write_text(json.dumps(report,indent=2)+'\n')
    start=time.monotonic();next_capture=15;seen=set();offset=0;error=None;returncode=None
    with (work/'stderr.log').open('wb') as err:
        process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err)
        try:
            console=Console(process,work);console.qmp.command('cont')
            while process.poll() is None and time.monotonic()-start<args.seconds+60:
                elapsed=int(time.monotonic()-start)
                if elapsed>=next_capture:console.capture(f'auto-{elapsed:04d}');next_capture=elapsed+15
                if (work/'serial.log').exists():
                    with (work/'serial.log').open('rb') as stream:stream.seek(offset);chunk=stream.read();offset+=len(chunk)
                    for marker in ('Darwin Kernel Version','launchd.ios','backboardd','SpringBoard','systemShellDidFinishLaunching'):
                        if marker.encode() in chunk:seen.add(marker)
                control=work/'control.json'
                if control.exists():
                    data=json.loads(control.read_text());control.unlink()
                    for action in data.get('actions',[]):console.action(action)
                    if data.get('stop'):report['stopped_by_control']=True;console.qmp.command('quit');break
                report.update(elapsed_seconds=elapsed,markers_seen=sorted(seen),actions=console.events,captures=console.captures)
                (work/'status.json').write_text(json.dumps(report,indent=2)+'\n');time.sleep(1)
            if process.poll() is None:
                if not report['stopped_by_control']:console.qmp.command('quit')
                process.wait(timeout=15)
            returncode=process.returncode
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        finally:
            if process.poll() is None:process.kill();process.wait()
            process.stdin.close();process.stdout.close()
    report.update(returncode=returncode,error=error,elapsed_seconds=round(time.monotonic()-start,2),
                  serial_sha256=lab.sha256(work/'serial.log') if (work/'serial.log').exists() else None)
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(work/'report.json'),'error':error,'returncode':returncode}),flush=True)
    return 2 if error else 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('kernel-tree','loader','loader-build','root-image','system-image','efi-code','efi-vars','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--tools',type=Path,default=ROOT/'tools/root');p.add_argument('--seconds',type=int,default=1800);args=p.parse_args()
    if not 120<=args.seconds<=3600:p.error('seconds must be 120..3600')
    for key,value in vars(args).items():
        if isinstance(value,Path):
            value=value.resolve()
            if ',' in str(value):p.error('comma in QEMU path')
            setattr(args,key,value)
    try:sys.exit(run(args))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:print('Userland setup error: '+str(exc),file=sys.stderr);sys.exit(2)
