#!/usr/bin/env python3
"""Original LK selector/getter/RMW fragments with QEMU RAM replacing MMIO cells."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile

from inspect_el2_hzc2 import IMAGES,read_exact
from inspect_lk_pool_mmu import LAB_DELTAS
from inspect_lk_ufs_iocc import BLOCKS,inspect,select_table,selected_writes
from test_entry_diag import register
from test_payload_loader import ROOT,Remote,symbols

PHY,IOCC,STACK=0x44000000,0x44001000,0x46000000
SCENARIOS=(
    ('stable_zero',(0,),0,True),
    ('stable_one',(1,1),1,True),
    ('stable_two',(2,2),2,True),
    ('primary_then_query_one',(1,0),1,True),
    ('alternate_then_query_zero',(1,1),0,True),
    ('zero_then_query_one',(0,),1,True),
    ('other_u32_then_query_other',(0xffffffff,1),0xffffffff,True),
    ('synthetic_null_iocc_pointer',(1,1),None,False),
)


def execute_until(remote,delta,stop,values):
    values=list(values);reads=0
    for _ in range(12):
        remote.command('c');pc=register(remote,32)
        if pc==stop:
            if values:raise ValueError('unconsumed supplied query values')
            return reads
        if pc!=delta+0x147ea8 or not values:raise ValueError('unexpected selector/getter stop')
        remote.write(delta+0xcd31c8,struct.pack('<I',values.pop(0)));reads+=1
        # Step the original ADRP, then continue through the native LDR/RET.
        # The getter result is never substituted by a debugger register write.
        remote.command('s')
        if register(remote,32)!=delta+0x147eac:raise ValueError('native getter step differs')
    raise ValueError('query stop budget exceeded')


def run(path):
    report=inspect(path);data=read_exact(path,*IMAGES['sboot']);rows=[]
    with tempfile.TemporaryDirectory(prefix='lk-ufs-iocc-') as directory:
        build=Path(directory)
        subprocess.run(['make','-s','-C',str(ROOT/'r8'),f'BUILD={build}',str(build/'entry_diag.elf'),str(build/'entry_diag.Image')],check=True,stdout=subprocess.DEVNULL)
        boot=symbols(build/'entry_diag.elf')['diag_image']
        with (build/'qemu.log').open('wb') as log:
            process=subprocess.Popen(['make','-s','--no-print-directory','-C',str(ROOT/'r8'),f'BUILD={build}','DIAG_VIRTUALIZATION=off','run_entry_diag'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
            remote=None
            try:
                remote=Remote(process.stdout,process.stdin)
                assert remote.command(f'Z0,{boot:x},4')=='OK';remote.command('c')
                if register(remote,32)!=boot or (register(remote,33) >> 2)&3!=1:raise ValueError('EL1 fixture boot differs')
                assert remote.command(f'z0,{boot:x},4')=='OK'
                for delta in LAB_DELTAS:
                    for a,b in BLOCKS.values():remote.write(delta+a,data[a:b])
                    stops=(delta+0x10e878,delta+0x10e8f4,delta+0x147ea8)
                    for p in stops:assert remote.command(f'Z0,{p:x},4')=='OK'
                    for name,selection,query,enabled in SCENARIOS:
                        for old in (0,0xa5c0a5a4):
                            for cell in (PHY,IOCC):remote.write(cell-16,b'\x77'*16+struct.pack('<I',old)+b'\x77'*16)
                            for i in range(31):register(remote,i,0xa550000000000000+i)
                            register(remote,31,STACK)
                            for p in (0x303198,0x3038d8):
                                table=bytearray(data[p:p+64])
                                struct.pack_into('<QQ',table,40,PHY,IOCC if enabled else 0)
                                remote.write(delta+p,table)
                            register(remote,32,delta+0x10e868)
                            reads=execute_until(remote,delta,delta+0x10e878,selection)
                            selected=select_table(selection[0],selection[1] if len(selection)>1 else None)
                            if register(remote,20)!=delta+selected:raise ValueError('native table selection differs')
                            register(remote,32,delta+0x10e8a8);remote.command('s')
                            if register(remote,32)!=delta+0x10e8ac or (register(remote,3),register(remote,4))!=(PHY,IOCC if enabled else 0):raise ValueError('native pointer pair differs')
                            # Padding-control instructions between these fragments are omitted.
                            register(remote,32,delta+0x10e8c8)
                            reads+=execute_until(remote,delta,delta+0x10e8f4,() if query is None else (query,))
                            wanted=selected_writes(old,old,0 if query is None else query,enabled=enabled)
                            actual_phy=remote.integer(PHY);actual_iocc=remote.integer(IOCC)
                            if (actual_phy,actual_iocc)!=(wanted['phy_after'],wanted['iocc_after']):raise ValueError('native RMW result differs')
                            if reads!=len(selection)+int(enabled):raise ValueError('native getter read count differs')
                            for cell in (PHY,IOCC):
                                if remote.read(cell-16,16)!=b'\x77'*16 or remote.read(cell+4,16)!=b'\x77'*16:raise ValueError('RAM cell guard differs')
                            if register(remote,31)!=STACK:raise ValueError('fragment changed SP')
                            for i in (19,*range(21,30)):
                                if register(remote,i)!=0xa550000000000000+i:raise ValueError('unrelated register differs')
                            rows.append(dict(case=name,laboratory_delta=hex(delta),selection_queries=list(selection),
                                rmw_query=query,selected_table_relative=hex(selected),initial_cell=hex(old),
                                phy_after=hex(actual_phy),iocc_after=hex(actual_iocc),or_mask=hex(wanted['iocc_or_mask']),
                                iocc_pointer_nonzero=enabled,native_getter_reads=reads,ram_guards_and_unrelated_registers_preserved=True))
                    for a,b in BLOCKS.values():
                        if remote.read(delta+a,b-a)!=data[a:b]:raise ValueError('original code changed')
                    for p in stops:assert remote.command(f'z0,{p:x},4')=='OK'
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                if remote:remote.close()
    return dict(mode='original_lk_ufs_iocc_fragments_qemu_ram',sboot_sha256=report['sboot_sha256'],
        static_instruction_index_sha256=report['instruction_index_sha256'],case_count=len(rows),cases=rows,
        segments=[dict(start=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest()) for a,b in BLOCKS.values()],
        original_code_segments_unchanged=True,getter_result_substituted=False,samsung_mmio_executed=False,
        dma_coherence_established=False,
        limits=['QEMU RAM cells and modified data-table pointer fields replace Samsung MMIO; no cache/device/coherence model.',
            'Selector, pointer pair load and RMW are executed as separate original fragments; intervening padding-control instructions and full initializer are omitted.',
            'Debugger supplies cd31c8 storage immediately before each original getter read; mixed sequences are controls, not observed device behavior.',
            'Null IOCC pointer is a synthetic skip control; both pinned data tables have nonzero pointers.',
            'Guarded u32 RAM writes do not establish IOCC delivery/readback, SMMU/bus identity, ownership or successful UFS transfer.'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');a=p.parse_args()
    try:print(json.dumps(run(a.sboot),indent=2))
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError,AssertionError,TimeoutError,RuntimeError) as exc:p.exit(2,f'emulate_lk_ufs_iocc_qemu: {exc}\n')
