#!/usr/bin/env python3
"""Check pinned QEMU ramfb and capture an EFI diagnostic; not iOS UI."""
import argparse
import json
import os
from pathlib import Path
import re
import select
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.xnu import efi_lab as efi, ramfb
from scripts import run_xnu_lab as lab

PROBE = '''
    /* Guest-side test pattern, deliberately not an iOS screenshot. */
    for (uint32_t y = 0; y < SCREEN.height; ++y) {
        volatile uint32_t *row = (volatile uint32_t *)(uintptr_t)(SCREEN.base + y * SCREEN.stride);
        for (uint32_t x = 0; x < SCREEN.width; ++x) {
            uint32_t color = y < SCREEN.height / 2 ?
                (x < SCREEN.width / 2 ? 0x00ff0000 : 0x0000ff00) :
                (x < SCREEN.width / 2 ? 0x000000ff : 0x00ffff00);
            if (x < 8 || y < 8 || x >= SCREEN.width - 8 || y >= SCREEN.height - 8)
                color = 0x00ffffff;
            row[x] = color;
        }
    }
    __asm__ volatile("dsb sy" ::: "memory");
    print("S21 RAMFB PROBE: drawn %d x %d base %x stride %d\\n",
          (uint64_t)SCREEN.width, (uint64_t)SCREEN.height, SCREEN.base, (uint64_t)SCREEN.stride);
    for (;;) __asm__ volatile("wfe");
'''


class QMP:
    """Bounded stdio transport; no host sockets or network required."""
    def __init__(self, process):
        self.process, self.buffer = process, bytearray()
        if 'QMP' not in self.read(): raise ValueError('invalid QMP greeting')
        self.command('qmp_capabilities')

    def read(self):
        deadline = time.monotonic() + 15
        while b'\n' not in self.buffer:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.process.stdout], [], [], left)[0]:
                raise TimeoutError('QMP deadline')
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data: raise ValueError('QMP disconnected')
            self.buffer.extend(data)
        line, _, rest = self.buffer.partition(b'\n'); self.buffer = bytearray(rest)
        return json.loads(line)

    def command(self, name, **arguments):
        self.process.stdin.write(json.dumps({'execute': name, 'arguments': arguments}).encode() + b'\n')
        self.process.stdin.flush()
        while True:
            response = self.read()
            if 'error' in response: raise ValueError(str(response['error']))
            if 'return' in response: return response['return']


def compile_probe(source, tree, llvm, out, diagnostic=True):
    out.mkdir()
    anchor = '\tinstall_exception_hook();'
    if source.count(anchor) != 1: raise ValueError('probe anchor changed')
    if diagnostic: source = source.replace(anchor, PROBE + '\n' + anchor)
    (out / 'loader.c').write_text(source)
    for name in ('efi.h', 'identity.h'): shutil.copyfile(tree / 'xnuloader' / name, out / name)
    env = dict(os.environ, LD_LIBRARY_PATH=str(llvm / 'usr/lib/x86_64-linux-gnu') + ':' + str(llvm / 'usr/lib/llvm-19/lib'))
    flags = [str(llvm / 'usr/lib/llvm-19/bin/clang'), '--target=aarch64-unknown-windows', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fshort-wchar', '-mgeneral-regs-only', '-O1',
             '-Wall', '-Wextra', '-Wno-unused-parameter']
    commands = [flags + ['-c', str(out / 'loader.c'), '-o', str(out / 'loader.obj')],
                flags + ['-S', str(out / 'loader.c'), '-o', str(out / 'loader.s')],
                [str(llvm / 'usr/lib/llvm-19/bin/lld-link'), '/subsystem:efi_application', '/entry:efi_main',
                 '/nodefaultlib', '/base:0xA1000000', '/timestamp:0', '/out:' + str(out / 'loader.efi'), str(out / 'loader.obj')]]
    with (out / 'build.log').open('wb') as log:
        for cmd in commands: subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=45)
    return {'commands': commands, 'sources_sha256': {n: lab.sha256(out / n) for n in ('loader.c', 'efi.h', 'identity.h')},
            'loader_sha256': lab.sha256(out / 'loader.efi'), 'assembly_sha256': lab.sha256(out / 'loader.s')}


def run_case(args, name, loader, payload=None):
    from PIL import Image
    out = args.out / name
    (out / 'esp/EFI/BOOT').mkdir(parents=True)
    esp = out / 'esp/EFI/BOOT/BOOTAA64.EFI'
    shutil.copyfile(loader, esp)  # fresh ESP, unconditional copy (no cp -u)
    shutil.copyfile(args.efi_vars, out / 'vars.fd')
    roms = args.out / 'roms'
    cmd = lab.tool_commands(args.tools)['qemu'] + [
        '-L', str(roms), '-M', 'virt,gic-version=3', '-cpu', 'cortex-a76',
        '-smp', '1', '-m', '6G', '-accel', 'tcg,tb-size=128',
        '-drive', f'if=pflash,format=raw,readonly=on,file={args.efi_code}',
        '-drive', f'if=pflash,format=raw,file={out/"vars.fd"}',
        '-drive', f'file=fat:rw:{out/"esp"},format=raw,if=virtio',
        '-device', 'ramfb', '-display', 'none', '-serial', f'file:{out/"serial.log"}',
        '-qmp', 'stdio', '-monitor', 'none', '-no-reboot', '-nic', 'none']
    if payload: cmd += ['-device', f'loader,file={payload},addr=0xF0000000,force-raw=on']
    with (out / 'stderr.log').open('wb') as err:
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, bufsize=0)
        try:
            qmp = QMP(process)
            marker = (b'S21 RAMFB: REJECT DMA' if name in ('dma-error','dma-timeout') else
                      b'display ' if name in ('published','rebuilt-original') else b'S21 RAMFB PROBE: drawn')
            deadline = time.monotonic() + 90
            while True:
                serial = (out/'serial.log').read_bytes() if (out/'serial.log').exists() else b''
                if re.search(re.escape(marker) + rb'[^\r\n]*\r?\n', serial): break
                if time.monotonic() > deadline or process.poll() is not None: raise ValueError('probe not reached: ' + name)
                time.sleep(.02)
            qmp.command('stop')
            if name == 'published':
                # Derived from disassembly of the SHA-256 checked prebuilt at its
                # preferred base. cfg=0xa101c258; DMA descriptor=0xa101c278.
                if b'image=a1000000' not in serial: raise ValueError('unexpected PE relocation')
                qmp.command('pmemsave', val=0xa101c258, size=48, filename=str(out/'dma-memory.bin'))
            qmp.command('screendump', filename=str(out / 'screen.png'), format='png')
            qmp.command('quit'); process.wait(timeout=15)
        finally:
            if process.poll() is None: process.kill(); process.wait()
            process.stdin.close(); process.stdout.close()
    serial = (out / 'serial.log').read_bytes()
    match = re.search(rb'display (\d+) x (\d+) at ([0-9a-f]+)', serial)
    declared = [int(match[1]), int(match[2])] if match else None
    with Image.open(out / 'screen.png') as frame:
        frame = frame.convert('RGB'); size = list(frame.size)
        points = [(frame.width//4,frame.height//4),(3*frame.width//4,frame.height//4),
                  (frame.width//4,3*frame.height//4),(3*frame.width//4,3*frame.height//4),(0,0)]
        pixels = [list(frame.getpixel(p)) for p in points]
    completion = None
    if name == 'published':
        memory = (out/'dma-memory.bin').read_bytes()
        base, fourcc, flags, width, height, stride = struct.unpack_from('>Q5I', memory)
        control, length, address = struct.unpack_from('>IIQ', memory, 32)
        completion = {'physical_address':'0xa101c278','control':control,'length':length,
                      'configuration_address':hex(address),'framebuffer':hex(base),
                      'dimensions':[width,height],'stride':stride,'fourcc':hex(fourcc),'flags':flags,
                      'memory_sha256':efi.sha(memory),'read_only_qmp':True}
    checks = {'actual_esp_hash_matches': lab.sha256(esp) == lab.sha256(loader)}
    if name in ('dma-error','dma-timeout'):
        checks.update(rejected=b'S21 RAMFB: REJECT DMA status ' in serial,
                      no_pattern=b'S21 RAMFB PROBE:' not in serial, no_handoff=b'jumping to ' not in serial,
                      no_display_claim=declared is None)
        if name == 'dma-error': checks['device_error_bit'] = b'S21 RAMFB: REJECT DMA status 1\r\n' in serial
        else:
            status = int(re.search(rb'REJECT DMA status ([0-9a-f]+)',serial)[1],16)
            checks['pending_not_error'] = status != 0 and not (status & 1)
    elif name in ('fixed-probe','original-probe','rebuilt-original'):
        checks.update(mode_matches=declared == size == [1125,2436],
                      no_dma_failure=b'after the request' not in serial and b'REJECT DMA' not in serial)
        if name != 'rebuilt-original':
            checks['visible_pattern'] = pixels == [[255,0,0],[0,255,0],[0,0,255],[255,255,0],[255,255,255]]
    else:
        checks.update(mismatch_reproduced=declared == [800,600] and size == [1125,2436],
                      stale_status_reported=b'ramfb: control ' in serial and b'after the request' in serial,
                      device_completed_in_memory=control == 0 and length == 28 and address == 0xa101c258,
                      configured_mode_matches_qemu=[width,height] == size and stride == width*4)
    result = {'case': name, 'checks': checks, 'passed': all(checks.values()), 'command': cmd,
              'loader_sha256': lab.sha256(loader), 'esp_loader_sha256': lab.sha256(esp),
              'dma_completion': completion, 'declared_dimensions': declared, 'qemu_dimensions': size, 'sampled_rgb': pixels,
              'artifacts_sha256': {p: lab.sha256(out / p) for p in ('serial.log','screen.png')},
              'payload_sha256': lab.sha256(payload) if payload else None}
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(name + (': PASS' if result['passed'] else ': FAIL'), flush=True)
    return result


def run(args):
    ref = json.loads(lab.REFERENCE.read_text())
    pinned = next(x for x in ref['sources'] if x['repository'].endswith('-kernel'))
    head = subprocess.check_output(['git','-C',str(args.kernel_tree),'rev-parse','HEAD'],text=True).strip()
    if head != efi.REVISION: raise ValueError('wrong upstream revision')
    inputs = {}
    for name in ('loader.c','efi.h'):
        expected = next(x['sha256'] for x in pinned['files_hashed_for_traceability'] if x['path'] == 'xnuloader/' + name)
        inputs[name] = lab.verified(args.kernel_tree / 'xnuloader' / name, expected)
    identity = subprocess.check_output(['git','-C',str(args.kernel_tree),'show',head+':xnuloader/identity.h'])
    inputs['identity.h'] = lab.verified(args.kernel_tree / 'xnuloader/identity.h', efi.sha(identity))
    expected = next(x['sha256'] for x in ref['kernel_prebuilt_integrity']['checks'] if x['path'] == 'prebuilt/loader.efi')
    inputs['prebuilt'] = lab.verified(args.kernel_tree / 'prebuilt/loader.efi', expected)
    for name in ('code','vars'): inputs['efi_'+name] = lab.verified(getattr(args,'efi_'+name),lab.EFI_HASHES[name])
    previous = json.loads((args.lab_run/'report.json').read_text())
    if not previous.get('passed') or previous.get('negative_fixture'): raise ValueError('positive baseline required')
    inputs['payload'] = lab.verified(args.lab_run/'payload.bin', previous['artifacts']['payload.bin']['sha256'])
    args.out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(args.tools/'usr/share/qemu', args.out/'roms')
    shutil.copyfile(args.tools/'usr/share/seabios/vgabios-ramfb.bin', args.out/'roms/vgabios-ramfb.bin')
    source = (args.kernel_tree/'xnuloader/loader.c').read_text(); corrected = ramfb.patch(source)
    # Test injection: writing the read-only signature selector provokes a real device error.
    fault = corrected.replace('dma.control = be32(select << 16 | FW_CFG_DMA_SELECT | FW_CFG_DMA_WRITE);',
                              'dma.control = be32(FW_CFG_DMA_SELECT | FW_CFG_DMA_WRITE);')
    # Test injection: omit the trigger, leaving completion pending until the bounded poll expires.
    trigger = '*(volatile uint64_t *)(FW_CFG_BASE + 16) = __builtin_bswap64((uint64_t)(uintptr_t)&dma);'
    timeout = corrected.replace(trigger, '(void)dma; /* TEST: no device trigger */')
    builds, cases = {}, {}
    cases['published'] = run_case(args,'published',args.kernel_tree/'prebuilt/loader.efi',args.lab_run/'payload.bin')
    out = args.out/'build-rebuilt-original'
    builds['rebuilt-original'] = compile_probe(source,args.kernel_tree,args.llvm_root,out,diagnostic=False)
    cases['rebuilt-original'] = run_case(args,'rebuilt-original',out/'loader.efi',args.lab_run/'payload.bin')
    for name,text in (('original-probe',source),('fixed-probe',corrected),('dma-error',fault),('dma-timeout',timeout)):
        out = args.out/('build-'+name); builds[name] = compile_probe(text,args.kernel_tree,args.llvm_root,out)
        cases[name] = run_case(args,name,out/'loader.efi')
    report = {'scope':'QEMU published EFI and instrumented source probes; no iOS userland', 'date':'2026-10-23',
              'upstream_revision':head,'inputs':inputs,'builds':builds,'cases':cases,
              'qemu_version':subprocess.check_output(lab.tool_commands(args.tools)['qemu']+['--version'],text=True).splitlines()[0],
              'own_sources_sha256':{p:lab.sha256(ROOT/p) for p in ('scripts/check_xnu_ramfb.py','lab/xnu/ramfb.py')},
              'passed':all(x['passed'] for x in cases.values()),'iOS_gui_tested':False,'Samsung_tested':False}
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('kernel-tree','llvm-root','efi-code','efi-vars','lab-run','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--tools',type=Path,default=ROOT/'tools/root')
    args = parser.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):
            value = value.resolve()
            if ',' in str(value): parser.error('comma in QEMU path')
            setattr(args,key,value)
    try: sys.exit(run(args))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print('ramfb audit error: '+str(exc),file=sys.stderr); sys.exit(2)
