#!/usr/bin/env python3
"""Bounded original callback trace; stop before any memory access outside lab RAM.

GDB single steps the unchanged callback/helper instructions. GNU supplies the
instruction spelling; every load/store address is checked BEFORE stepping.
No gate value, successor PC, MMIO stub or SMC reply is supplied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import tempfile

from check_epbl_protocol_gnu import parse_lines
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_newtime_hzc2 import ENTRY, REGISTRY, START, ERROR, embedded, TEMPLATES as PREFIX
from inspect_newtime_record_hzc2 import TEMPLATES, LIMIT, inspect
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols

MAX_STEPS = 20000
ALLOWED_FUNCTIONS = ((START, 0x19a20), (0x18054, 0x1809c),
    (0x1b37c, 0x1b3a4), (0x1c540, 0x1c5b4), (0x1c83c, 0x1c87c))


def memory_access(op, operands, regs):
    """Decode GNU integer load/store addressing, fail closed for other memory ops."""
    supported = ('ldr', 'ldrb', 'ldrh', 'ldrsw', 'ldrsb', 'ldrsh',
        'str', 'strb', 'strh', 'ldur', 'ldurb', 'ldurh', 'ldursw',
        'stur', 'sturb', 'sturh', 'ldp', 'stp', 'ldpsw')
    if op not in supported:
        if '[' in operands or op.startswith(('ld', 'st', 'prf')):
            raise ValueError('unsupported memory instruction')
        return None
    match = re.fullmatch(r'(.+), \[([^\]]+)\](!)?(?:, (#-?(?:0x[0-9a-f]+|[0-9]+)))?', operands)
    if not match:
        raise ValueError('unsupported memory operand')
    targets, address, pre, post = match.groups()
    targets = targets.split(', ')
    pair = op in ('ldp', 'stp', 'ldpsw')
    if len(targets) != (2 if pair else 1) or any(not re.fullmatch(r'[xw](?:[0-9]+|zr)', t) for t in targets):
        raise ValueError('unsupported memory register class')

    def value(name):
        if name in ('xzr', 'wzr'): return 0
        if name == 'sp': return regs[31]
        if not re.fullmatch(r'[xw](?:[0-9]|[12][0-9]|30)', name):
            raise ValueError('unsupported address register')
        return regs[int(name[1:])] & ((1 << (32 if name[0] == 'w' else 64))-1)

    parts = address.split(', ')
    base = value(parts[0]); offset = 0
    if len(parts) == 2 and parts[1].startswith('#'):
        offset = int(parts[1][1:], 0)
    elif len(parts) in (2, 3):
        offset = value(parts[1])
        if len(parts) == 3:
            extend = re.fullmatch(r'(lsl|sxtw|uxtw|sxtx)(?: #([0-3]))?', parts[2])
            if not extend: raise ValueError('unsupported address extension')
            kind, shift = extend.groups()
            bits = 32 if kind.endswith('w') else 64
            offset &= (1 << bits)-1
            if kind.startswith('sxt') and offset >> (bits-1): offset -= 1 << bits
            offset <<= int(shift or 0)
    elif len(parts) != 1:
        raise ValueError('unsupported address shape')
    if post and (len(parts) != 1 or pre):
        raise ValueError('unsupported writeback combination')
    size = 1 if op.endswith('b') else 2 if op.endswith('h') else 4 if op.endswith('sw') or targets[0][0] == 'w' else 8
    return dict(address=(base+offset) & ((1 << 64)-1), size=size*len(targets),
        operation='read' if op.startswith('ld') else 'write')


def access_allowed(access, regions):
    address, size = access['address'], access['size']
    return any(first <= address and address+size <= last and
        (access['operation'] == 'read' or writable) for first, last, writable in regions)


def instruction_map(path, data):
    expected = {pc+i*4:int(w,16) for pc,t in PREFIX+TEMPLATES for i,w in enumerate(t.split())
        if any(a <= pc+i*4 < b for a,b in ALLOWED_FUNCTIONS)}
    command = ['bash',str(ROOT/'scripts/cross-run.sh'),str(ROOT/'tools/root'),
        str(ROOT/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for first,last in ALLOWED_FUNCTIONS:
        output = subprocess.check_output(command+['-D','-b','binary','-m','aarch64',
            f'--start-address={first}',f'--stop-address={last}',str(Path(path).resolve())],text=True)
        lines.update({pc:row for pc,row in parse_lines(output).items() if pc in expected})
    if set(lines) != set(expected) or any(lines[pc][0] != value for pc,value in expected.items()):
        raise ValueError('GNU callback/helper instruction coverage differs')
    return lines


def run(path, max_steps=MAX_STEPS):
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_STEPS:
        raise ValueError('instruction budget outside supported bounds')
    report = inspect(path)  # Exact firmware guard before GNU/build/QEMU.
    data = read_exact(path,*IMAGES['sboot']); raw = embedded(data)
    lines = instruction_map(path,data)
    table = next(t for t in raw['parsed']['entries'] if t['key'] == 0x11111111)
    source = raw['block_file']+table['offset']+12
    results = []
    with tempfile.TemporaryDirectory(prefix='newtime-columns-') as directory:
        build = Path(directory)
        subprocess.run(['make','-s','-C',str(ROOT/'r8'),f'BUILD={build}',
            str(build/'entry_diag.elf'),str(build/'entry_diag.Image')],check=True,stdout=subprocess.DEVNULL)
        boot = symbols(build/'entry_diag.elf')['diag_image']
        with (build/'qemu.log').open('wb') as log:
            process = subprocess.Popen(['make','-s','--no-print-directory','-C',str(ROOT/'r8'),
                f'BUILD={build}','DIAG_VIRTUALIZATION=off','run_entry_diag'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
            remote = None
            try:
                remote = Remote(process.stdout,process.stdin)
                assert remote.command(f'Z0,{boot:x},4') == 'OK'; remote.command('c')
                assert register(remote,32) == boot and (register(remote,33) >> 2) & 3 == 1
                assert remote.command(f'z0,{boot:x},4') == 'OK'
                for delta in (0x40000000,0x40200000):
                    remote.write(delta+0x16000,data[0x16000:0x32000])
                    remote.write(delta+0x69000,data[0x69000:0x7d000])
                    registry = bytearray(data[REGISTRY:REGISTRY+12*32])
                    for off in range(0,len(registry),32):
                        for field in (0,16):
                            original = struct.unpack_from('<Q',registry,off+field)[0]
                            struct.pack_into('<Q',registry,off+field,delta+original-NOMINAL_DELTA)
                    remote.write(delta+REGISTRY,registry)
                    header,stack,destination = delta+0x100000,delta+0x1f0000,delta+0x180000
                    entries = raw['parsed']['entries']; array = header+24
                    metadata = struct.pack('<I4sI4xQ',1,b'0.81',len(entries),array)
                    metadata += b''.join(struct.pack('<Q4IQ',t['key'],t['offset'],t['mode'],
                        t['columns'],t['rows'],delta+raw['block_file']+t['offset']+12) for t in entries)
                    remote.write(header,metadata)
                    remote.write(delta+ENTRY+24,struct.pack('<Q',header))
                    remote.write(delta+0x31c18,struct.pack('<Q',delta+0x69000))
                    regions = [(delta+0x16000,delta+0x30000,False),
                        (delta+0x30000,delta+0x32000,True),
                        (delta+0x69000,delta+0x7d000,False),
                        (header,header+len(metadata),False),
                        (destination-16,destination+LIMIT+16,True),
                        (stack-0x2000,stack+32,True)]
                    for row in (10,15):
                        value = table['cells'][row*17]
                        remote.write(delta+0x31a50,data[0x31a50:0x31a60])
                        remote.write(delta+0x30520,struct.pack('<Q',destination))
                        remote.write(destination-16,b'\x77'*16+b'\xa5'*LIMIT+b'\x77'*16)
                        remote.write(stack-0x2000,b'\x77'*32+b'\xa5'*(0x2000-32)+b'\x77'*32)
                        for reg in range(31): register(remote,reg,0xa500000000000000+reg)
                        for reg,v in ((0,value),(30,delta+0x15000),(31,stack),(32,delta+START)):
                            register(remote,reg,v)
                        events,executed = [],[]; stopped = None
                        for step in range(max_steps):
                            state = bytes.fromhex(remote.command('g'))
                            regs = struct.unpack_from('<33Q',state); pc = regs[32]-delta
                            if pc == ERROR:
                                stopped = dict(reason='shared_epilogue',pc=hex(pc),w0=regs[0]&0xffffffff); break
                            if pc not in lines:
                                stopped = dict(reason='outside_allowed_code',pc=hex(pc)); break
                            word,op,args = lines[pc]
                            if op in ('smc','hvc','svc','msr','mrs','dc','ic','at','sys','prfm'):
                                stopped = dict(reason='system_instruction',pc=hex(pc)); break
                            access = memory_access(op,args,regs)
                            if access and not access_allowed(access,regions):
                                stopped = dict(reason='before_access_outside_lab_ram',pc=hex(pc),
                                    address=hex(access['address']),size=access['size'],operation=access['operation']); break
                            before = remote.read(access['address'],access['size']) if access else None
                            remote.command('s')
                            executed.append(struct.pack('<II',pc,word))
                            if access:
                                after = remote.read(access['address'],access['size']) if access['operation']=='write' else before
                                events.append(dict(step=step,pc=hex(pc),address=hex(access['address']),
                                    size=access['size'],operation=access['operation'],value_hex_le=after.hex()))
                        else:
                            stopped = dict(reason='instruction_budget',limit=max_steps)
                        scratch = remote.integer(stack-288+168,8) if len(executed)>1 else 0
                        watched = []
                        for event in events:
                            address = int(event['address'],16)
                            for kind,base in (('embedded_row',delta+source+row*0x88),('copied_tail',scratch-8)):
                                for column in (1,12):
                                    start = base+column*8
                                    if start <= address and address+event['size'] <= start+8:
                                        watched.append(dict(**event,region=kind,column=column,cell_byte_offset=address-start))
                        if stopped['reason']=='before_access_outside_lab_ram':
                            assert stopped['pc']=='0x19774' and stopped['address']=='0x158609bc'
                            assert remote.integer(stack-288+284)==row
                            assert remote.integer(destination,8)==value
                            assert remote.read(scratch,128)==struct.pack('<16Q',*table['cells'][row*17+1:(row+1)*17])
                            assert remote.integer(destination+32,8)==destination+0x1a0
                            assert remote.integer(delta+0x31a50,8)==destination+0x2a0
                            record=bytearray(b'\xa5'*LIMIT)
                            struct.pack_into('<Q',record,0,value)
                            record[8:12]=b'007n';record[12:16]=raw['parsed']['version']
                            struct.pack_into('<Q',record,32,destination+0x1a0)
                            assert remote.read(destination,LIMIT)==record
                        expected_registry=bytearray(registry)
                        struct.pack_into('<Q',expected_registry,ENTRY-REGISTRY+24,header)
                        assert remote.read(delta+REGISTRY,len(registry))==expected_registry
                        assert remote.integer(delta+0x30520,8)==destination
                        assert remote.integer(delta+0x31c18,8)==delta+0x69000
                        assert remote.read(destination-16,16)==remote.read(destination+LIMIT,16)==b'\x77'*16
                        assert remote.read(stack-0x2000,32)==remote.read(stack,32)==b'\x77'*32
                        assert remote.read(header,len(metadata))==metadata
                        assert remote.read(delta+0x69000,0x14000)==data[0x69000:0x7d000]
                        for address,(raw_word,_,_) in lines.items():
                            assert remote.integer(delta+address)==raw_word
                        trace = b''.join(executed)+json.dumps(events,sort_keys=True,separators=(',',':')).encode()
                        results.append(dict(row=row,key=f'{value:016x}',laboratory_delta=hex(delta),
                            executed_instructions=len(executed),memory_accesses=len(events),stop=stopped,
                            watched_accesses=watched,trace_sha256=hashlib.sha256(trace).hexdigest(),
                            record_header_accesses=[e for e in events if destination <= int(e['address'],16)
                                and int(e['address'],16)+e['size'] <= destination+40],
                            output_directory_accesses=[e for e in events if destination+0x1a0 <= int(e['address'],16)
                                and int(e['address'],16)+e['size'] <= destination+0x2a0],
                            post_copy_tail_reads=sum(e['region']=='copied_tail' and e['operation']=='read' for e in watched),
                            callback_return_observed=False,immutable_code_source_metadata_and_guards_matched=True))
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL);process.wait()
                if remote: remote.close()
    return dict(mode='bounded_original_newtime_callback_before_external_access',sboot_sha256=IMAGES['sboot'][1],
        prefix_instruction_index_sha256=report['prefix_instruction_index_sha256'],
        suffix_instruction_index_sha256=report['instructions']['suffix_index_sha256'],
        instruction_budget_per_case=max_steps,case_count=len(results),cases=results,
        gnu_callback_chain_instruction_words=len(lines),
        tracing='GNU-addressed GDB single step with preflight for every integer memory access',
        original_flow_continuous_until_stop=True,parsed_metadata_materialized_by_host=True,
        gate_value_or_branch_successor_supplied=False,mmio_or_smc_executed=False,
        physical_controller_parameter_identified=False,phone_execution=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot');parser.add_argument('--max-steps',type=int,default=MAX_STEPS)
    args=parser.parse_args()
    try: result=run(args.sboot,args.max_steps)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'trace_newtime_columns_qemu: {exc}\n')
    print(json.dumps(result,indent=2))
