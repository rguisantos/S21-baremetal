#!/usr/bin/env python3
"""Execute the original NEWTIME parser and first-store prefix in QEMU RAM.

The ECT bytes are real file data. Registry pointers, heap, stack, destination
and inputs are laboratory bindings. No MMIO replies or helper stubs are used.
Stop before the later callback body; this is not a Samsung firmware boot.
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

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_newtime_hzc2 import (REGISTRY, ENTRY, START, STORE, AFTER_STORE,
                                 ERROR, TEMPLATES, embedded, inspect, selection)
from inspect_bl2_ram_size import NOMINAL_DELTA
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols


def scenarios(table):
    result = [(f'embedded_row_{i}', table['cells'][i*table['columns']], None)
              for i in range(table['rows'])]
    result += [('negative_bit63_low32_cafe', 0x800000000000cafe, None),
               ('negative_high_bits_low32_cafe', 0xffff00000000cafe, None),
               ('row_miss', 0xdeadbeef, None),
               ('positive_high_bits_do_not_truncate', 0x100000000cafe, None),
               ('missing_name', 0xcafe, 'name'), ('missing_key', 0xcafe, 'key')]
    return result


def run(path):
    report = inspect(path)
    data = read_exact(path, *IMAGES['sboot'])
    raw = embedded(data)
    table = next(t for t in raw['parsed']['entries'] if t['key'] == 0x11111111)
    results, parsers = [], []
    with tempfile.TemporaryDirectory(prefix='newtime-qemu-') as directory:
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
                for delta in (0x40000000, 0x40200000):
                    remote.write(delta+0x16000, data[0x16000:0x32000])
                    remote.write(delta+raw['block_file'], raw['raw_block'])
                    registry = bytearray(data[REGISTRY:REGISTRY+12*32])
                    for offset in range(0, len(registry), 32):
                        for field in (0, 16):
                            original = struct.unpack_from('<Q', registry, offset+field)[0]
                            struct.pack_into('<Q', registry, offset+field, delta+original-NOMINAL_DELTA)
                    remote.write(delta+REGISTRY, registry)
                    heap, stack, destination = delta+0x100000, delta+0x1f0000, delta+0x180000
                    remote.write(heap-16, b'\x77'*16+b'\xa5'*0x800+b'\x77'*16)
                    remote.write(delta+0x31c08, struct.pack('<Q', heap))
                    finish = delta+0x15000
                    assert remote.command(f'Z0,{finish:x},4') == 'OK'
                    for reg in range(31):
                        register(remote, reg, 0xa500000000000000+reg)
                    for reg, value in ((0, delta+raw['block_file']), (1, delta+ENTRY),
                                       (30, finish), (31, stack), (32, delta+0x1c3dc)):
                        register(remote, reg, value)
                    remote.command('c')
                    assert register(remote, 32) == finish and register(remote, 0) == 0
                    assert register(remote, 31) == stack
                    header = remote.integer(delta+ENTRY+24, 8)
                    assert header == heap
                    assert remote.read(header, 12) == struct.pack('<I4sI', 1, b'0.81', 57)
                    array = remote.integer(header+16, 8)
                    expected_entries = b''.join(struct.pack('<Q4IQ', t['key'], t['offset'], t['mode'],
                        t['columns'], t['rows'], delta+raw['block_file']+t['offset']+12)
                        for t in raw['parsed']['entries'])
                    assert array == heap+24 and remote.read(array, len(expected_entries)) == expected_entries
                    assert remote.read(heap-16, 16) == remote.read(heap+0x800, 16) == b'\x77'*16
                    parsers.append(dict(laboratory_delta=hex(delta), entry_count=57,
                                        all_fields_and_data_pointers_matched=True))
                    assert remote.command(f'z0,{finish:x},4') == 'OK'
                    for point in (STORE, ERROR):
                        assert remote.command(f'Z0,{delta+point:x},4') == 'OK'
                    for name, value, control in scenarios(table):
                        remote.write(delta+ENTRY, struct.pack('<Q', delta+(0x30486 if control == 'name' else 0x304ba)))
                        remote.write(array, struct.pack('<Q', 0 if control == 'key' else 0x11111111))
                        remote.write(delta+0x30520, struct.pack('<Q', destination))
                        remote.write(destination-16, b'\x77'*16+b'\xa5'*8+b'\x77'*16)
                        remote.write(stack-0x800, b'\x77'*32+b'\xa5'*(0x800-32)+b'\x77'*32)
                        for reg in range(31):
                            register(remote, reg, 0xa500000000000000+reg)
                        for reg, val in ((0, value), (30, finish), (31, stack), (32, delta+START)):
                            register(remote, reg, val)
                        remote.command('c')
                        expected = selection(table, value) if control is None else None
                        frame = register(remote, 29)
                        assert frame == stack-288 and remote.integer(frame+136, 8) == value
                        case = dict(case=name, laboratory_delta=hex(delta), supplied_input=hex(value),
                                    frame_input_preserved=True, control=control)
                        if expected is None:
                            status = {'name': 3, 'key': 2, None: 1}[control]
                            assert register(remote, 32) == delta+ERROR and register(remote, 0) == status
                            assert remote.read(destination, 8) == b'\xa5'*8
                            case.update(error_code_before_epilogue=status, record_untouched=True)
                        else:
                            assert register(remote, 32) == delta+STORE
                            assert register(remote, 0) == destination and register(remote, 1) == value
                            assert remote.integer(frame+284) == expected['row']
                            scratch = remote.integer(frame+168, 8)
                            tail = struct.pack('<16Q', *expected['tail'])
                            assert remote.read(scratch, len(tail)) == tail
                            remote.command('s')
                            assert register(remote, 32) == delta+AFTER_STORE
                            assert remote.integer(destination, 8) == value
                            case.update(selected_row=expected['row'], comparison_key=hex(expected['comparison_key']),
                                        first_u64_written=hex(value), tail_sha256=hashlib.sha256(tail).hexdigest())
                        assert remote.read(destination-16, 16) == remote.read(destination+8, 16) == b'\x77'*16
                        assert remote.read(stack-0x800, 32) == remote.read(stack, 32) == b'\x77'*32
                        results.append(case)
                    for point in (STORE, ERROR):
                        assert remote.command(f'z0,{delta+point:x},4') == 'OK'
                    for pc, template in TEMPLATES:
                        size = 4*len(template.split())
                        assert remote.read(delta+pc, size) == data[pc:pc+size]
                    assert remote.read(delta+raw['block_file'], len(raw['raw_block'])) == raw['raw_block']
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
    return dict(mode='original_newtime_parser_and_prefix_qemu_virt', sboot_sha256=IMAGES['sboot'][1],
        instruction_index_sha256=report['instructions']['index_sha256'],
        parser_runs=parsers, case_count=len(results), cases=results,
        code_and_source_block_unchanged=True, record_and_stack_guards_unchanged=True,
        original_code_executed=True, samsung_firmware_boot_executed=False,
        later_callback_body_executed=False, mmio_or_smc_executed=False,
        phone_record_or_memory_map_verified=False,
        limits=['Two QEMU RAM placements; original instructions, relocated absolute registry data',
                'Heap, stack, destination and all input/negative controls are laboratory bindings',
                'Stop after first u64 store or before error epilogue; no later MMIO/table copies',
                'Does not prove physical aliases, live metadata, preservation outside this prefix or final RAM/FDT'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = run(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'emulate_newtime_qemu: {exc}\n')
    print(json.dumps(result, indent=2))
