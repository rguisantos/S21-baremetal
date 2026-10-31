#!/usr/bin/env python3
"""Original LK heap/page/UFS allocators in QEMU with supplied pool and stub locks.

The nominal pool binding and Samsung startup are not executed. A small laboratory
pool, empty deferred list and zeroed contexts are supplied afresh for each case.
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
from inspect_lk_heap import BLOCKS, inspect, request_layout
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols

SEGMENTS = tuple(BLOCKS[k] for k in ('pool_constructor','page_allocator',
    'page_request','heap_seed','heap_init','allocation_wrappers','page_tail',
    'seed_tail','free_chunk','heap_allocator','heap_constructor')) + ((0x10ec98,0x10ede8),)
HOOKS = (0x119d60,0x119d90,0x119e28,0x1af540,0x1b1658,0x18fbf0)
POOL, POOL_SIZE, BITMAP, STACK = 0x41000000, 0x20000, 0x41400000, 0x42000000
CASES = ((0,0),(1,0),(8,0),(9,0),(4096,0),(8192,4096),
         (64,4096),(160,4096),(64,1),(64,3),(64,0x10000000),
         (0xfffffffffffffff0,0))
SENTINEL = 0xa550000000000000


def substitute(remote, offset, delta, counts):
    args=[register(remote,i) for i in range(3)]
    lr=register(remote,30)
    if offset in (0x119d60,0x119d90,0x119e28):
        if args[0] not in (delta+0xd07910,delta+0xd089b8+32):
            raise ValueError('unexpected mutex context')
        result=0  # No scheduling, IRQ or contention semantics are supplied.
    elif offset==0x1af540:
        address,value,size=args
        if not (size<=POOL_SIZE and (POOL<=address<=POOL+POOL_SIZE-size
                or BITMAP<=address<=BITMAP+0x1000-size)):
            raise ValueError('memset leaves supplied pool/bitmap')
        remote.write(address,bytes([value & 255])*size)
        result=address
    elif offset==0x1b1658:
        result=0  # Capture that diagnostics were called; no formatting or device I/O.
    else:
        raise ValueError('unexpected deferred-list helper')
    counts[hex(offset)]=counts.get(hex(offset),0)+1
    for i in range(19): register(remote,i,SENTINEL+i)
    register(remote,0,result);register(remote,32,lr)


def call(remote, delta, offset, args, finish, counts):
    for i in range(31): register(remote,i,SENTINEL+i)
    for i,value in enumerate(args): register(remote,i,value)
    for i,value in ((30,finish),(31,STACK),(32,delta+offset)):register(remote,i,value)
    deadline=time.monotonic()+15
    for _ in range(256):
        remote.command('c')
        if time.monotonic()>deadline:raise ValueError('allocation call exceeds deadline')
        pc=register(remote,32)
        if pc==finish:break
        if pc-delta not in HOOKS:raise ValueError(f'unexpected QEMU stop {pc:#x}')
        substitute(remote,pc-delta,delta,counts)
    else:raise ValueError('allocation call exceeds stop budget')
    if register(remote,31)!=STACK:raise ValueError('stack pointer differs')
    for i in range(19,30):
        if register(remote,i)!=SENTINEL+i:raise ValueError('callee-saved register differs')
    return register(remote,0)


def guards(remote):
    for base,size in ((POOL,POOL_SIZE),(BITMAP,0x1000),(STACK-0x4000,0x4000)):
        if remote.read(base-16,16)!=b'\x77'*16 or remote.read(base+size,16)!=b'\x77'*16:
            raise ValueError('laboratory memory guard differs')


def prepare(remote,delta,finish,counts,pages=32):
    for base,size,fill in ((POOL,POOL_SIZE,0xa5),(BITMAP,0x1000,0),(STACK-0x4000,0x4000,0xa5)):
        remote.write(base-16,b'\x77'*16+bytes([fill])*size+b'\x77'*16)
    remote.write(delta+0xd07910,bytes(128))
    remote.write(delta+0xd089b8,bytes(104))
    deferred=delta+0x31ffd0
    remote.write(deferred,struct.pack('<QQ',deferred,deferred))
    remote.write(delta+0x8a7700,bytes(32))
    call(remote,delta,0x18d808,(delta+0xd07910,0,POOL,pages*4096,BITMAP,pages),finish,counts)
    if remote.integer(delta+0xd07910+64,8)!=pages or remote.integer(delta+0xd07910+80,8)!=POOL:
        raise ValueError('page constructor differs')
    call(remote,delta,0x18fd30,(),finish,counts)
    if remote.integer(delta+0xd089b8,8)!=POOL or remote.read(BITMAP,32)!=b'\x01'+bytes(31):
        raise ValueError('heap initial page differs')


def run(path):
    report=inspect(path)  # Hash and selected machine-code witnesses precede QEMU.
    data=read_exact(path,*IMAGES['sboot']);rows=[];ufs=[]
    with tempfile.TemporaryDirectory(prefix='lk-heap-') as directory:
        build=Path(directory)
        subprocess.run(['make','-s','-C',str(ROOT/'r8'),f'BUILD={build}',
            str(build/'entry_diag.elf'),str(build/'entry_diag.Image')],check=True,stdout=subprocess.DEVNULL)
        boot=symbols(build/'entry_diag.elf')['diag_image']
        with (build/'qemu.log').open('wb') as log:
            process=subprocess.Popen(['make','-s','--no-print-directory','-C',str(ROOT/'r8'),
                f'BUILD={build}','DIAG_VIRTUALIZATION=off','run_entry_diag'],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=log,start_new_session=True)
            remote=None
            try:
                remote=Remote(process.stdout,process.stdin)
                assert remote.command(f'Z0,{boot:x},4')=='OK';remote.command('c')
                assert register(remote,32)==boot
                assert remote.command(f'z0,{boot:x},4')=='OK'
                for delta in (0x40000000,0x40200000):
                    finish=delta+0x300000
                    points=[finish]+[delta+p for p in HOOKS]
                    for a,b in SEGMENTS:remote.write(delta+a,data[a:b])
                    for point in points:assert remote.command(f'Z0,{point:x},4')=='OK'
                    for size,align in CASES:
                        counts={};prepare(remote,delta,finish,counts)
                        pointer=call(remote,delta,0x20c098,(size,align),finish,counts)
                        layout=request_layout(size,align)
                        if not layout['accepted'] or align==0x10000000:
                            if pointer!=0:raise ValueError('expected allocation refusal')
                            header=None
                        else:
                            chunk,charged=struct.unpack('<QQ',remote.read(pointer-16,16))
                            if not (POOL<=chunk<=pointer-16<POOL+POOL_SIZE and charged>=layout['requested_chunk_bytes']
                                    and chunk+charged<=POOL+POOL_SIZE):
                                raise ValueError('allocated header/extent differs')
                            if align and pointer % layout['effective_alignment']:
                                raise ValueError('alignment differs')
                            header=dict(chunk=hex(chunk),charged=charged)
                        bitmap=remote.read(BITMAP,32)
                        if any(v not in (0,1) for v in bitmap):raise ValueError('page bitmap value differs')
                        guards(remote)
                        rows.append(dict(laboratory_delta=hex(delta),size=hex(size),alignment=align,
                            pointer=hex(pointer),header=header,pages_marked=sum(bitmap),
                            arithmetic=layout,substitutions=counts,guards_and_abi_preserved=True))
                    for pages in (32,4):
                        counts={};prepare(remote,delta,finish,counts,pages)
                        result=call(remote,delta,0x10ec98,(),finish,counts) & 0xffffffff
                        host=remote.integer(delta+0x8a7718,8)
                        if not POOL<=host<=POOL+pages*4096-8176:raise ValueError('UFS host allocation differs')
                        pointers={str(slot):remote.integer(host+slot,8) for slot in (8112,144,152,160)}
                        if pages==32:
                            if result:raise ValueError('expected UFS success')
                            for slot,size in ((8112,32),(144,8192),(152,64),(160,160)):
                                p=pointers[str(slot)]
                                if not POOL<=p<=POOL+pages*4096-size or (slot!=8112 and p%4096):
                                    raise ValueError('UFS allocated pointer/extent differs')
                        elif result!=0xffffffff or not pointers['8112'] or any(pointers[str(k)] for k in (144,152,160)):
                            raise ValueError('expected partial UFS allocation failure')
                        if remote.integer(delta+0x8a7710)!=0:raise ValueError('UFS index differs')
                        if remote.read(POOL+pages*4096,POOL_SIZE-pages*4096)!=b'\xa5'*(POOL_SIZE-pages*4096):
                            raise ValueError('allocator wrote beyond supplied pool')
                        guards(remote)
                        ufs.append(dict(laboratory_delta=hex(delta),pool_pages=pages,return_w0=hex(result),host=hex(host),
                            field_pointers={k:hex(v) for k,v in pointers.items()},
                            objects=hex(remote.integer(delta+0x8a7708,8)),pages_marked=sum(remote.read(BITMAP,pages)),
                            substitutions=counts,guards_and_abi_preserved=True))
                    for a,b in SEGMENTS:
                        if remote.read(delta+a,b-a)!=data[a:b]:raise ValueError('original code changed')
                    for point in points:assert remote.command(f'z0,{point:x},4')=='OK'
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                if remote:remote.close()
    for index in range(len(CASES)):
        left,right=rows[index],rows[index+len(CASES)]
        for key in ('pointer','header','pages_marked','arithmetic'):
            if left[key]!=right[key]:raise ValueError('relocated arithmetic/result differs')
    for left,right in zip(ufs[:2],ufs[2:]):
        for key in ('return_w0','field_pointers','host','pages_marked','objects'):
            if left[key]!=right[key]:raise ValueError('relocated UFS results differ')
    return dict(mode='original_lk_heap_pages_and_ufs_allocator_qemu',sboot_sha256=report['sboot_sha256'],
        static_instruction_index_sha256=report['instruction_index_sha256'],
        segments=[dict(start=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest()) for a,b in SEGMENTS],
        case_count=len(rows)+len(ufs),arithmetic_cases=rows,ufs_cases=ufs,
        original_code_segments_unchanged=True,both_placements_match=True,
        synthetic_pool=dict(base=hex(POOL),bytes=POOL_SIZE,pages=32),
        physical_samsung_state_observed=False,dma_mapping_or_coherence_established=False,
        limits=['Synthetic fresh pool, bitmap and empty deferred list; no Samsung startup or nominal pool binding execution.',
                'Mutex helpers and bounded memset are debugger substitutions; no contention/cache/DMA semantics.',
                'All callees execute only inside the laboratory QEMU VM; no phone, MMIO or secure service is accessed.',
                'Two laboratory relocations and supplied inputs do not establish runtime heap state or free RAM.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:print(json.dumps(run(args.sboot),indent=2))
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError,AssertionError,TimeoutError,RuntimeError) as exc:
        parser.exit(2,f'emulate_lk_heap_qemu: {exc}\n')
