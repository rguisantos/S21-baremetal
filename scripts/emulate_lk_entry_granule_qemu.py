#!/usr/bin/env python3
"""Run the original LK EL transition and TG0 getter under supplied QEMU state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_entry_granule import granule_from_tcr, inspect
from inspect_lk_pool_mmu import LAB_DELTAS
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols

SEGMENTS=((0xf9b4c,0xf9bc0),(0x189480,0x189488),(0x189e50,0x189f04))
FIXTURE, STACK = 0x44000000, 0x46000000
SENTINEL=0xa550000000000000
ARGS=(0x1122334455667788,0x123456789abcdef,0xfedcba9876543210,0x9988776655443322)
TCR_BASE=0x11b51c351c  # Synthetic input from the later LK installer, TG0 varied below.


def stop_at(remote, wanted):
    remote.command('c')
    if register(remote,32)!=wanted:
        raise ValueError(f'unexpected QEMU stop {register(remote,32):#x}, expected {wanted:#x}')


def check_stack(remote):
    if register(remote,31)!=STACK:raise ValueError('stack pointer differs')
    for p in (STACK-4096-16,STACK):
        if remote.read(p,16)!=b'\x77'*16:raise ValueError('stack guard differs')


def run(path):
    report=inspect(path);data=read_exact(path,*IMAGES['sboot']);entries=[];getters=[]
    with tempfile.TemporaryDirectory(prefix='lk-entry-granule-') as directory:
        build=Path(directory)
        targets=('entry_diag.elf','entry_diag.Image','lk_entry_state.o','lk_entry_state.bin')
        subprocess.run(['make','-s','-C',str(ROOT/'r8'),f'BUILD={build}']+[str(build/p) for p in targets],check=True,stdout=subprocess.DEVNULL)
        boot=symbols(build/'entry_diag.elf')['diag_image']
        sym=symbols(build/'lk_entry_state.o');fixture=(build/'lk_entry_state.bin').read_bytes()
        read=FIXTURE+sym['lk_state_read'];done=FIXTURE+sym['lk_state_done']
        for initial_el,virtualization,initial_mode in ((1,'off',5),(1,'off',4),(2,'on',9)):
            for delta in LAB_DELTAS:
                for tg0 in range(4):
                    with (build/'qemu.log').open('wb') as log:
                        process=subprocess.Popen(['make','-s','--no-print-directory','-C',str(ROOT/'r8'),f'BUILD={build}',
                            f'DIAG_VIRTUALIZATION={virtualization}','run_entry_diag'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
                        remote=None
                        try:
                            remote=Remote(process.stdout,process.stdin)
                            assert remote.command(f'Z0,{boot:x},4')=='OK';stop_at(remote,boot)
                            assert remote.command(f'z0,{boot:x},4')=='OK'
                            if (register(remote,33) >> 2)&3!=initial_el:raise ValueError('QEMU entry EL differs')
                            if initial_mode==4:
                                register(remote,33,(register(remote,33) & ~15) | 4,size=4)
                            if register(remote,33)&15!=initial_mode:raise ValueError('supplied entry mode differs')
                            for a,b in SEGMENTS:remote.write(delta+a,data[a:b])
                            remote.write(FIXTURE,fixture)
                            remote.write(STACK-4096-16,b'\x77'*16+b'\xa5'*4096+b'\x77'*16)
                            for i in range(31):register(remote,i,SENTINEL+i)
                            for i,value in enumerate(ARGS):register(remote,i,value)
                            supplied_tcr=(TCR_BASE & ~(3 << 14)) | (tg0 << 14)
                            register(remote,9,delta+0xf9b4c);register(remote,10,supplied_tcr)
                            register(remote,30,read);register(remote,31,STACK);register(remote,32,FIXTURE+sym['lk_state_setup'])
                            assert remote.command(f'Z0,{delta+0xf9b4c:x},4')=='OK'
                            assert remote.command(f'Z0,{done:x},4')=='OK'
                            assert remote.command(f'Z0,{delta+0x18f8a8:x},4')=='OK'
                            stop_at(remote,delta+0xf9b4c)
                            if register(remote,11)&1 or register(remote,12)!=supplied_tcr:
                                raise ValueError('fixture requires M=0 and exact TCR readback')
                            initial_sctlr=register(remote,11)
                            assert remote.command(f'z0,{delta+0xf9b4c:x},4')=='OK'
                            stop_at(remote,done)
                            final_mode=initial_mode if initial_el==1 else 5
                            if register(remote,10)!=4 or register(remote,33)&15!=final_mode:
                                raise ValueError('original entry EL1 mode differs')
                            if register(remote,11)!=initial_sctlr or register(remote,12)!=supplied_tcr:
                                raise ValueError('original entry changed SCTLR_EL1 or TCR_EL1')
                            if initial_el==2 and register(remote,13)!=0x300000:
                                raise ValueError('entry CPACR_EL1 differs')
                            expected_x0=ARGS[0] if initial_el==1 else STACK
                            if [register(remote,i) for i in range(4)]!=[expected_x0,*ARGS[1:]]:
                                raise ValueError('entry argument behavior differs')
                            for i in range(19,30):
                                if register(remote,i)!=SENTINEL+i:raise ValueError('entry callee-saved register differs')
                            check_stack(remote)
                            entries.append(dict(initial_el=initial_el,initial_mode='EL1t' if initial_mode==4 else f'EL{initial_el}h',laboratory_delta=hex(delta),tg0=tg0,
                                supplied_tcr=hex(supplied_tcr),observed_tcr_after=hex(register(remote,12)),
                                sctlr_el1=hex(initial_sctlr),cpacr_el1_after=hex(register(remote,13)),
                                final_el=1,final_mode='EL1t' if final_mode==4 else 'EL1h',x0_after=hex(expected_x0),x1_x3_preserved=True,
                                sctlr_el1_preserved=True,stack_preserved=True))
                            for argument in (1,2):
                                for i in range(31):register(remote,i,SENTINEL+i)
                                register(remote,0,argument);register(remote,30,read)
                                register(remote,31,STACK);register(remote,32,delta+0x189e50)
                                expected_stop=done if argument==1 and tg0!=3 else delta+0x18f8a8
                                stop_at(remote,expected_stop)
                                if expected_stop==done:
                                    result=register(remote,0)
                                    if result!=granule_from_tcr(supplied_tcr):raise ValueError('original TG0 getter differs')
                                    if register(remote,12)!=supplied_tcr:raise ValueError('getter changed TCR')
                                    for i in range(19,30):
                                        if register(remote,i)!=SENTINEL+i:raise ValueError('getter callee-saved register differs')
                                    check_stack(remote)
                                    getters.append(dict(initial_el=initial_el,initial_mode=entries[-1]['initial_mode'],laboratory_delta=hex(delta),tg0=tg0,
                                        el_argument=argument,result_bytes=result,assertion_boundary=False,guards_and_abi_preserved=True))
                                else:
                                    wanted_lr=delta+(0x189ecc if argument==1 else 0x189f04)
                                    if register(remote,30)!=wanted_lr:raise ValueError('wrong assertion call site')
                                    if remote.read(STACK-4096-16,16)!=b'\x77'*16 or remote.read(STACK,16)!=b'\x77'*16:
                                        raise ValueError('assertion-path stack guard differs')
                                    getters.append(dict(initial_el=initial_el,initial_mode=entries[-1]['initial_mode'],laboratory_delta=hex(delta),tg0=tg0,
                                        el_argument=argument,result_bytes=None,assertion_boundary=True,
                                        call_site=hex(wanted_lr-delta-4),assertion_executed=False))
                            for a,b in SEGMENTS:
                                if remote.read(delta+a,b-a)!=data[a:b]:raise ValueError('original code changed')
                            if remote.read(FIXTURE,len(fixture))!=fixture:raise ValueError('state fixture changed')
                        finally:
                            if process.poll() is None:
                                os.killpg(process.pid,signal.SIGTERM)
                                try:process.wait(timeout=5)
                                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                            if remote:remote.close()
    return dict(mode='original_lk_entry_and_granule_qemu',sboot_sha256=report['sboot_sha256'],
        static_instruction_index_sha256=report['instruction_index_sha256'],
        segments=[dict(start=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest()) for a,b in SEGMENTS],
        fixture_sha256=hashlib.sha256(fixture).hexdigest(),entry_run_count=len(entries),getter_run_count=len(getters),
        entry_runs=entries,getter_runs=getters,original_code_segments_unchanged=True,
        getter_and_el_transition_substituted=False,physical_samsung_state_observed=False,
        limits=['QEMU virt, one CPU: initial EL1/EL2 and TCR_EL1 are supplied; no phone register is acquired.',
            'EL3 path and complete Samsung startup are not executed. No Samsung MMIO or SMC is executed.',
            'TCR is varied while SCTLR_EL1.M=0. No translation tables are installed or pool mapped by this test.',
            'Reserved TG0 and other EL argument stop at the assertion helper entry; no assertion implementation or return is assumed.',
            'Selected EL lowering preserves supplied TCR; it cannot establish the phone inherited granule or DMA coherence.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:print(json.dumps(run(args.sboot),indent=2))
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError,AssertionError,TimeoutError,RuntimeError) as exc:
        parser.exit(2,f'emulate_lk_entry_granule_qemu: {exc}\n')
