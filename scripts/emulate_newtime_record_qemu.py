#!/usr/bin/env python3
"""Execute original NEWTIME blocks with explicit gate-branch dispatch in QEMU.

The harness stops at 0x19770 and selects a successor PC; the MMIO load and
gate instructions are never executed. Parsed metadata, stack, destination
and control flow are laboratory bindings, not a physical callback execution.
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

from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_newtime_hzc2 import REGISTRY, ENTRY, START, AFTER_STORE, ERROR, TEMPLATES as PREFIX
from inspect_newtime_hzc2 import embedded
from inspect_newtime_record_hzc2 import (DATA, DIRECTORY, LIMIT, TEMPLATES,
    allocation, inspect, plan, representatives)
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols

GATE, PARK = 0x19770, 0x18090


def expected_record(raw, tables, result, value, base):
    buffer = bytearray(b'\xa5'*LIMIT)
    struct.pack_into('<Q', buffer, 0, value)
    buffer[8:12] = b'007n'
    buffer[12:16] = raw['parsed']['version']
    struct.pack_into('<Q', buffer, 32, base+DIRECTORY)
    for step in result['steps']:
        struct.pack_into('<4I', buffer, step['descriptor_offset'], step['key'] & 0xffffffff,
                         step['payload_offset'], step['columns'], step['rows'])
        start = tables[step['key']]['offset']+12
        buffer[step['payload_offset']:step['payload_offset']+step['bytes']] = raw['raw_block'][start:start+step['bytes']]
    if result['final_used_field_written']:
        struct.pack_into('<I', buffer, 16, result['cursor'])
    return bytes(buffer)


def run(path):
    report = inspect(path)
    data = read_exact(path, *IMAGES['sboot'])
    raw = embedded(data)
    tables = {t['key']: t for t in raw['parsed']['entries']}
    special = tables[0x11111111]
    cases = [(row, mask, special['cells'][row*17]) for row, mask in representatives(tables)]
    cases += [(0, mask, 0x800000000000cafe) for mask in (0, 511)]
    results, allocator_cases = [], []
    with tempfile.TemporaryDirectory(prefix='newtime-record-') as directory:
        build = Path(directory)
        subprocess.run(['make', '-s', '-C', str(ROOT/'r8'), f'BUILD={build}',
                        str(build/'entry_diag.elf'), str(build/'entry_diag.Image')],
                       check=True, stdout=subprocess.DEVNULL)
        boot = symbols(build/'entry_diag.elf')['diag_image']
        with (build/'qemu.log').open('wb') as log:
            process = subprocess.Popen(['make', '-s', '--no-print-directory', '-C', str(ROOT/'r8'),
                f'BUILD={build}', 'DIAG_VIRTUALIZATION=off', 'run_entry_diag'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, start_new_session=True)
            remote = None
            try:
                remote = Remote(process.stdout, process.stdin)
                assert remote.command(f'Z0,{boot:x},4') == 'OK'
                remote.command('c')
                assert register(remote, 32) == boot and (register(remote, 33) >> 2) & 3 == 1
                assert remote.command(f'z0,{boot:x},4') == 'OK'

                def registers(values):
                    for reg in range(31):
                        register(remote, reg, 0xa500000000000000+reg)
                    for reg, value in values:
                        register(remote, reg, value)

                for delta in (0x40000000, 0x40200000):
                    remote.write(delta+0x16000, data[0x16000:0x32000])
                    remote.write(delta+0x69000, data[0x69000:0x7d000])
                    registry = bytearray(data[REGISTRY:REGISTRY+12*32])
                    for offset in range(0, len(registry), 32):
                        for field in (0, 16):
                            pointer = struct.unpack_from('<Q', registry, offset+field)[0]
                            struct.pack_into('<Q', registry, offset+field, delta+pointer-NOMINAL_DELTA)
                    remote.write(delta+REGISTRY, registry)
                    header, stack, destination = delta+0x100000, delta+0x1f0000, delta+0x180000
                    array = header+24
                    metadata = struct.pack('<I4sI4xQ', 1, b'0.81', len(tables), array)
                    metadata += b''.join(struct.pack('<Q4IQ', t['key'], t['offset'], t['mode'],
                        t['columns'], t['rows'], delta+raw['block_file']+t['offset']+12)
                        for t in raw['parsed']['entries'])
                    remote.write(header, metadata)
                    remote.write(delta+ENTRY+24, struct.pack('<Q', header))
                    remote.write(delta+0x31c18, struct.pack('<Q', delta+0x69000))
                    finish = delta+0x15000
                    for point in (AFTER_STORE, GATE, ERROR, PARK, 0x15000):
                        assert remote.command(f'Z0,{delta+point:x},4') == 'OK'
                    for row, mask, value in cases:
                        expected = plan(tables, row, mask)
                        remote.write(delta+0x30520, struct.pack('<Q', destination))
                        remote.write(destination-16, b'\x77'*16+b'\xa5'*LIMIT+b'\x77'*16)
                        remote.write(stack-0x800, b'\x77'*32+b'\xa5'*(0x800-32)+b'\x77'*32)
                        registers(((0, value), (30, finish), (31, stack), (32, delta+START)))
                        remote.command('c')
                        assert register(remote, 32) == delta+AFTER_STORE
                        assert remote.integer(destination, 8) == value
                        frame = register(remote, 29)
                        assert remote.integer(frame+284) == row
                        remote.command('s')
                        remote.command('c')
                        dispatched = []
                        while register(remote, 32) == delta+GATE:
                            index = remote.integer(frame+280)
                            assert index == len(dispatched) and index < 16
                            selected = bool(index < 9 and mask >> index & 1)
                            dispatched.append(selected)
                            # Explicit branch injection, not an MMIO value or execution of the gate.
                            register(remote, 32, delta+(0x19788 if selected else 0x19810))
                            remote.command('c')
                        assert register(remote, 32) == delta+ERROR
                        assert register(remote, 0) == expected['return_code']
                        expected_dispatches = len(expected['steps'])+(expected['status'] == 'missing_key')
                        assert len(dispatched) == expected_dispatches
                        buffer = expected_record(raw, tables, expected, value, destination)
                        assert remote.read(destination, LIMIT) == buffer
                        assert remote.integer(delta+0x31a50, 8) == destination+expected['cursor']
                        assert remote.integer(delta+0x31a58, 8) == destination+LIMIT
                        remote.command('s')
                        remote.command('c')
                        assert register(remote, 32) == finish and register(remote, 31) == stack
                        assert register(remote, 0) == expected['return_code'] and register(remote, 30) == finish
                        for reg in range(19, 30):
                            assert register(remote, reg) == 0xa500000000000000+reg
                        assert remote.integer(destination, 8) == value
                        assert remote.read(destination-16, 16) == remote.read(destination+LIMIT, 16) == b'\x77'*16
                        assert remote.read(stack-0x800, 32) == remote.read(stack, 32) == b'\x77'*32
                        results.append(dict(laboratory_delta=hex(delta), row=row, branch_mask=hex(mask),
                            supplied_input=hex(value), status=expected['status'], return_code=expected['return_code'],
                            committed_descriptors=len(expected['steps']), record_sha256=hashlib.sha256(buffer).hexdigest(),
                            first_u64_preserved=True, final_used_field_written=expected['final_used_field_written']))
                    for name, size, end_extra in (('exact_fit', 60, 60), ('exhaustion', 60, 56), ('round_to_four', 5, 8)):
                        cursor = destination+DATA
                        result = allocation(cursor, cursor+end_extra, size)
                        remote.write(delta+0x31a50, struct.pack('<QQ', cursor, cursor+end_extra))
                        registers(((0, size), (30, finish), (31, 0x12345678), (32, delta+0x18068)))
                        remote.command('c')
                        assert register(remote, 32) == (delta+PARK if result['parked'] else finish)
                        assert register(remote, 31) == 0x12345678
                        assert remote.integer(delta+0x31a50, 8) == result['cursor_after']
                        if not result['parked']:
                            assert register(remote, 0) == cursor
                        allocator_cases.append(dict(case=name, laboratory_delta=hex(delta),
                            request_w=size, cursor_advance=result['cursor_after']-cursor,
                            parked=result['parked'], matched=True))
                    for point in (AFTER_STORE, GATE, ERROR, PARK, 0x15000):
                        assert remote.command(f'z0,{delta+point:x},4') == 'OK'
                    for pc, template in PREFIX+TEMPLATES:
                        size = 4*len(template.split())
                        assert remote.read(delta+pc, size) == data[pc:pc+size]
                    assert remote.read(delta+0x69000, 0x14000) == data[0x69000:0x7d000]
                    assert remote.read(header, len(metadata)) == metadata
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                if remote is not None:
                    remote.close()
    return dict(mode='original_newtime_blocks_with_explicit_branch_dispatch_qemu',
        sboot_sha256=IMAGES['sboot'][1],
        prefix_instruction_index_sha256=report['prefix_instruction_index_sha256'],
        suffix_instruction_index_sha256=report['instructions']['suffix_index_sha256'],
        case_count=len(results),
        completed=sum(c['return_code'] == 0 for c in results), code4=sum(c['return_code'] == 4 for c in results),
        cases=results, allocator_cases=allocator_cases, code_source_metadata_and_guards_unchanged=True,
        gate_stop='0x19770', branch_entry_points=['0x19788', '0x19810'],
        gate_or_mmio_instructions_executed=False, parsed_metadata_materialized_by_host=True,
        complete_physical_callback_executed=False, hardware_samples_or_record_observed=False,
        limits=['Prefix, selected original suffix blocks, helpers and epilogue execute in QEMU RAM',
                'Harness dispatches every gate branch without executing the address/load/test sequence',
                'Heap, parsed metadata, input, stack, source and record bindings are laboratory state',
                'Byte-for-byte record comparison covers conditional success and partial code4 returns',
                'No physical aliases, gate samples, final RAM or FDT are proved'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = run(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'emulate_newtime_record_qemu: {exc}\n')
    print(json.dumps(result, indent=2))
