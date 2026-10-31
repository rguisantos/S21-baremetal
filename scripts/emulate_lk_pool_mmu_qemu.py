#!/usr/bin/env python3
"""Execute the original LK table builder in QEMU RAM; install no generated table.

EL1 and a 4K inherited granule are debugger inputs. L2/L3 storage starts zero.
The root initialization fragment and mapper are unchanged original instructions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile
import time

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_pool_mmu import (FLAGS, LAB_DELTAS, TABLE_LOW, TABLE_HIGH,
    build_lk_tables, inspect, walk_tables)
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols

SEGMENTS=((0x189f68,0x18a164),(0x18a22c,0x18a28c))
HOOKS=(0x189404,0x189e50)
STACK=0x46000000
SENTINEL=0xa550000000000000


def call(remote,delta,start,args,stop,counts,*,root_fragment=False):
    for i in range(31):register(remote,i,SENTINEL+i)
    for i,value in enumerate(args):register(remote,i,value)
    if root_fragment:
        register(remote,21,1);register(remote,22,delta+TABLE_LOW)
    for i,value in ((30,stop),(31,STACK),(32,delta+start)):register(remote,i,value)
    deadline=time.monotonic()+30
    for _ in range(1024):
        remote.command('c')
        if time.monotonic()>deadline:raise ValueError('builder exceeds host deadline')
        pc=register(remote,32)
        if pc==stop:break
        offset=pc-delta
        if offset not in HOOKS:raise ValueError(f'unexpected stop {pc:#x}')
        lr=register(remote,30)
        if offset==0x189e50 and register(remote,0)!=1:raise ValueError('unexpected granule EL argument')
        counts[hex(offset)]=counts.get(hex(offset),0)+1
        for i in range(19):register(remote,i,SENTINEL+i)
        register(remote,0,1 if offset==0x189404 else 4096)
        register(remote,32,lr)
    else:raise ValueError('builder exceeds stop budget')
    if register(remote,31)!=STACK:raise ValueError('stack pointer differs')
    if not root_fragment:
        for i in range(19,30):
            if register(remote,i)!=SENTINEL+i:raise ValueError('callee-saved register differs')


def run(path):
    report=inspect(path);data=read_exact(path,*IMAGES['sboot']);rows=[];root_rows=[]
    with tempfile.TemporaryDirectory(prefix='lk-pool-mmu-') as directory:
        build=Path(directory)
        subprocess.run(['make','-s','-C',str(ROOT/'r8'),f'BUILD={build}',str(build/'entry_diag.elf'),str(build/'entry_diag.Image')],check=True,stdout=subprocess.DEVNULL)
        boot=symbols(build/'entry_diag.elf')['diag_image']
        with (build/'qemu.log').open('wb') as log:
            process=subprocess.Popen(['make','-s','--no-print-directory','-C',str(ROOT/'r8'),f'BUILD={build}',
                'DIAG_VIRTUALIZATION=off','run_entry_diag'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
            remote=None
            try:
                remote=Remote(process.stdout,process.stdin)
                assert remote.command(f'Z0,{boot:x},4')=='OK';remote.command('c')
                assert register(remote,32)==boot
                assert remote.command(f'z0,{boot:x},4')=='OK'
                for delta in LAB_DELTAS:
                    base=delta+TABLE_LOW;size=TABLE_HIGH-TABLE_LOW;finish=delta+0x300000;root_stop=delta+0x18a28c
                    points=[finish,root_stop]+[delta+p for p in HOOKS]
                    for a,b in SEGMENTS:remote.write(delta+a,data[a:b])
                    remote.write(base-16,b'\x77'*16+bytes(size)+b'\x77'*16)
                    remote.write(STACK-0x4000-16,b'\x77'*16+b'\xa5'*0x4000+b'\x77'*16)
                    for point in points:assert remote.command(f'Z0,{point:x},4')=='OK'
                    counts={};call(remote,delta,0x18a22c,(),root_stop,counts,root_fragment=True)
                    root=remote.read(base,4096)
                    wanted=b''.join(struct.pack('<Q',(delta+0x323000+i*4096)|3) for i in range(48))+bytes((512-48)*8)
                    if root!=wanted:raise ValueError('original L1 root initialization differs')
                    root_rows.append(dict(laboratory_delta=hex(delta),root_sha256=hashlib.sha256(root).hexdigest(),substitutions=counts))
                    expected=build_lk_tables(delta)
                    for name,physical in (('LK_record',delta+0xec000),('LK_changed_PA_control',delta+0xec000+0x200000)):
                        counts={};call(remote,delta,0x189f68,(delta+0xec000,delta+0x18ec000,physical,FLAGS),finish,counts)
                        actual=remote.read(base,size)
                        if actual!=expected:raise ValueError('original mapper differs from selected table model')
                        pool_first=delta+0xd09000;pool_end=delta+0x18ec000
                        for va in range(pool_first,pool_end,4096):
                            row=walk_tables(actual,base,base,va)
                            if row['physical_address']!=hex(va) or row['attributes']!=report['selected_model']['samples']['pool_first']['attributes']:
                                raise ValueError('pool page walk differs')
                        for address,length in ((base,size),(STACK-0x4000,0x4000)):
                            if remote.read(address-16,16)!=b'\x77'*16 or remote.read(address+length,16)!=b'\x77'*16:raise ValueError('memory guard differs')
                        rows.append(dict(case=name,laboratory_delta=hex(delta),supplied_pa_start=hex(physical),
                            pool_pages_walked=3043,pool_identity=True,pool_attributes=row['attributes'],
                            table_sha256=hashlib.sha256(actual).hexdigest(),substitutions=counts,guards_and_abi_preserved=True))
                    counts={};va=0x80000000;pa=0x90000000
                    call(remote,delta,0x189f68,(va,va+0x200000,pa,FLAGS),finish,counts)
                    wanted=bytearray(expected)
                    struct.pack_into('<Q',wanted,0x1000+(va >> 21)*8,pa|FLAGS)
                    actual=remote.read(base,size)
                    if actual!=wanted:raise ValueError('non-LK block control differs')
                    walked=walk_tables(actual,base,base,va+0x1234)
                    if walked['level']!=2 or walked['physical_address']!=hex(pa+0x1234):raise ValueError('nonidentity control walk differs')
                    for address,length in ((base,size),(STACK-0x4000,0x4000)):
                        if remote.read(address-16,16)!=b'\x77'*16 or remote.read(address+length,16)!=b'\x77'*16:raise ValueError('memory guard differs')
                    rows.append(dict(case='non_LK_nonidentity_block',laboratory_delta=hex(delta),
                        supplied_va=hex(va),supplied_pa=hex(pa),walk=walked,table_sha256=hashlib.sha256(actual).hexdigest(),
                        substitutions=counts,guards_and_abi_preserved=True))
                    for a,b in SEGMENTS:
                        if remote.read(delta+a,b-a)!=data[a:b]:raise ValueError('original instruction bytes changed')
                    for point in points:assert remote.command(f'z0,{point:x},4')=='OK'
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                if remote:remote.close()
    return dict(mode='original_lk_root_and_mapper_qemu',sboot_sha256=report['sboot_sha256'],
        static_instruction_index_sha256=report['instruction_index_sha256'],case_count=len(rows),cases=rows,
        root_fragment_runs=root_rows,segments=[dict(start=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest()) for a,b in SEGMENTS],
        original_code_segments_unchanged=True,el1_and_4k_granule_supplied=True,
        generated_tables_installed=False,physical_samsung_state_observed=False,dma_coherence_established=False,
        limits=['Original builder writes QEMU RAM; system-register installation, MMU enable and Samsung startup are not executed.',
                'EL1 and 4096-byte granule are substituted inputs; no inherited TCR was acquired from the phone.',
                'L2/L3 storage starts zero; only the selected LK record and deliberately changed controls are executed.',
                'Software walks of generated bytes are not physical AT results, DMA mappings or a live page-table capture.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:print(json.dumps(run(args.sboot),indent=2))
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError,AssertionError,TimeoutError,RuntimeError) as exc:
        parser.exit(2,f'emulate_lk_pool_mmu_qemu: {exc}\n')
