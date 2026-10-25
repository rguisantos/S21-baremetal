#!/usr/bin/env python3
"""Original LK cache/label helpers with AP-shaped addresses mapped to QEMU RAM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile

from emulate_bl2_geometry_publication_qemu import page_tables
from inspect_dram_logging_hzc2 import CACHE, OBSERVED, REFERENCE, STRINGS, TEMPLATES, inspect
from inspect_el2_hzc2 import IMAGES, read_exact
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols


def run(sboot, driver):
    report=inspect(sboot,driver)
    data=read_exact(sboot,*IMAGES['sboot'])
    results=[]
    with tempfile.TemporaryDirectory(prefix='lk-dram-labels-') as directory:
        build=Path(directory)
        subprocess.run(['make','-s','-C',str(ROOT/'r8'),f'BUILD={build}',
            str(build/'entry_diag.elf'),str(build/'entry_diag.Image'),str(build/'entry_diag_state.bin')],
            check=True,stdout=subprocess.DEVNULL)
        boot=symbols(build/'entry_diag.elf')['diag_image']
        fixture=(build/'entry_diag_state.bin').read_bytes()
        with (build/'qemu.log').open('wb') as log:
            process=subprocess.Popen(['make','-s','--no-print-directory','-C',str(ROOT/'r8'),
                f'BUILD={build}','DIAG_VIRTUALIZATION=off','run_entry_diag'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
            remote=None
            try:
                remote=Remote(process.stdout,process.stdin)
                assert remote.command(f'Z0,{boot:x},4')=='OK';remote.command('c')
                assert register(remote,32)==boot
                assert remote.command(f'z0,{boot:x},4')=='OK'
                for delta,backing in ((0x40000000,0x41000000),(0x40200000,0x41200000)):
                    tables=page_tables(backing);remote.write(0x40040000,tables)
                    remote.write(0x40014000,fixture);finish=delta+0x15000
                    assert remote.command(f'Z0,{finish:x},4')=='OK'
                    for reg,value in ((16,1),(17,finish),(32,0x40014000)):register(remote,reg,value)
                    remote.command('c')
                    assert register(remote,32)==finish and register(remote,15)&5==1
                    for pc,template in TEMPLATES:
                        remote.write(delta+pc,data[pc:pc+4*len(template.split())])
                    remote.write(delta+0x22b5a0,data[0x22b5a0:0x22b620])
                    stack=delta+0x1f0000
                    for name,value in (('reference_A',REFERENCE),('observed_B',OBSERVED),('reference_C',0x1000860600130)):
                        remote.write(0x02073600-16,b'\x77'*16+struct.pack('<Q',value)+b'\x77'*16)
                        remote.write(delta+CACHE-16,b'\x77'*16+bytes(8)+b'\x77'*16)
                        remote.write(stack-64,b'\x77'*16+b'\xa5'*48+b'\x77'*16)
                        outputs={}
                        for pc,key,wanted in ((0x11b7f0,'cached',value),
                                (0x11b860,'manufacturer',delta+0x22b5a0),
                                (0x11b8d8,'process',delta+0x22b600)):
                            for reg in range(31):register(remote,reg,0xa500000000000000+reg)
                            active_sp=0x12345678 if key=='cached' else stack
                            for reg,v in ((30,finish),(31,active_sp),(32,delta+pc)):register(remote,reg,v)
                            remote.command('c')
                            assert register(remote,32)==finish and register(remote,0)==wanted
                            assert register(remote,31)==active_sp and register(remote,30)==finish
                            for reg in range(19,30):assert register(remote,reg)==0xa500000000000000+reg
                            if key!='cached':
                                outputs[key]=remote.read(wanted,16).split(b'\0',1)[0].decode()
                            assert remote.integer(delta+CACHE,8)==value
                        assert outputs==dict(manufacturer='Samsung',process='D1Z')
                        guard=b'\x77'*16+struct.pack('<Q',value)+b'\x77'*16
                        assert remote.read(0x02073600-16,40)==guard
                        assert remote.read(backing+0x73600-16,40)==guard
                        assert remote.read(delta+CACHE-16,40)==guard
                        assert remote.read(stack-64,16)==remote.read(stack,16)==b'\x77'*16
                        results.append(dict(case=name,laboratory_delta=hex(delta),word=f'{value:016x}',
                            **outputs,cache_and_guards_matched=True,abi_sp_preserved=True))
                    for pc,template in TEMPLATES:
                        size=4*len(template.split());assert remote.read(delta+pc,size)==data[pc:pc+size]
                    assert remote.read(delta+0x22b5a0,128)==data[0x22b5a0:0x22b620]
                    assert remote.read(0x40040000,len(tables))==tables
                    assert remote.command(f'z0,{finish:x},4')=='OK'
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                if remote:remote.close()
    return dict(mode='original_lk_dram_cache_and_labels_qemu',sboot_sha256=report['sboot_sha256'],
        instruction_index_sha256=report['instruction_index_sha256'],case_count=len(results),cases=results,
        original_helpers=['0x11b7f0','0x11b860','0x11b8d8'],calls_per_case=3,
        synthetic_mmu_alias=True,device_or_print_routine_executed=False,
        observed_word_is_from_supplied_log_not_a_live_register_read=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot');parser.add_argument('reference_driver');args=parser.parse_args()
    try:result=run(args.sboot,args.reference_driver)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'emulate_lk_dram_labels_qemu: {exc}\n')
    print(json.dumps(result,indent=2))
