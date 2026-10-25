#!/usr/bin/env python3
"""Original caller -> wrapper -> prefix with a synthetic MMU alias in QEMU.

AP-shaped virtual addresses map only to QEMU RAM supplied by this harness.
This is not an observed Exynos bus alias. No call or firmware address register
is skipped/rebound; execution stops after the first store or before the error
epilogue. Three cases explicitly change the slot between its two loads.
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

from emulate_bl2_geometry_packing_qemu import cases as packing_cases
from inspect_bl2_geometry_packing import pack_four
from inspect_bl2_geometry_publication import (ALTERNATE, RECORD, WINDOW, TEMPLATES,
    inspect, phase_counter, publication)
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_newtime_hzc2 import REGISTRY, ENTRY, AFTER_STORE, ERROR, embedded
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols


def cases(table):
    result = []

    def add(name, value, reloaded=None, destination=RECORD, control=None, counter=0x10203040):
        result.append(dict(name=name, caller_value=value,
            wrapper_value=value if reloaded is None else reloaded, destination=destination,
            control=control, counter_before=counter))

    for row in range(table['rows']):
        add(f'embedded_row_{row}', table['cells'][row*table['columns']])
    for vector in packing_cases():
        model = pack_four(vector['responses'], vector['revisions'], vector['extensions'])
        # Materialized prior-model output; this runner does not execute the packer.
        add('packed_'+vector['name'], model['slots'][0]['packed'])
    add('alternate_R_match', 0x1000860000110, destination=ALTERNATE)
    add('alternate_R_miss', 0xdeadbeef, destination=ALTERNATE)
    add('changed_A_to_B', 0x1000860000110, reloaded=0x1000850500130)
    add('changed_marker_to_miss', 0xcafe, reloaded=0xdeadbeef)
    add('changed_miss_to_A', 0xdeadbeef, reloaded=0x1000860000110)
    add('missing_name', 0xcafe, control='name')
    add('missing_key', 0xcafe, control='key')
    add('signed_input_and_counter_wrap', 0x800000000000cafe, counter=0xffffffff)
    return result


def page_tables(backing):
    """48-bit VA L0/L1/L2; RW normal RAM, cache remains disabled."""
    if backing not in (0x41000000, 0x41200000):
        raise ValueError('unsupported laboratory backing')
    tables = bytearray(0x3000)
    for offset, value in ((0, 0x40041003), (0x1000, 0x40042003),
                          (0x1008, 0x40000701), (0x2080, backing | 0x701)):
        struct.pack_into('<Q', tables, offset, value)
    return bytes(tables)


def run(path):
    report = inspect(path)
    data = read_exact(path, *IMAGES['sboot'])
    raw = embedded(data)
    entries = raw['parsed']['entries']
    table = next(t for t in entries if t['key'] == 0x11111111)
    vectors, results, mappings = cases(table), [], []
    with tempfile.TemporaryDirectory(prefix='bl2-publication-') as directory:
        build = Path(directory)
        subprocess.run(['make', '-s', '-C', str(ROOT/'r8'), f'BUILD={build}',
            str(build/'entry_diag.elf'), str(build/'entry_diag.Image'), str(build/'entry_diag_state.bin')],
            check=True, stdout=subprocess.DEVNULL)
        boot = symbols(build/'entry_diag.elf')['diag_image']
        fixture = (build/'entry_diag_state.bin').read_bytes()
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
                for delta, backing in ((0x40000000, 0x41000000), (0x40200000, 0x41200000)):
                    tables = page_tables(backing)
                    remote.write(0x40040000, tables)
                    remote.write(0x40014000, fixture)
                    finish = delta+0x15000
                    assert remote.command(f'Z0,{finish:x},4') == 'OK'
                    for reg, value in ((16, 1), (17, finish), (32, 0x40014000)):
                        register(remote, reg, value)
                    remote.command('c')  # Original lab fixture enables M and invalidates TLBs.
                    assert register(remote, 32) == finish
                    assert register(remote, 12) & 1 == register(remote, 13) & 1 == 0
                    assert register(remote, 15) & 5 == 1  # Installed SCTLR: M=1, data cache off.
                    remote.write(delta+0x16000, data[0x16000:0x32000])
                    remote.write(delta+0x69000, data[0x69000:0x7d000])
                    registry = bytearray(data[REGISTRY:REGISTRY+12*32])
                    for offset in range(0, len(registry), 32):
                        for field in (0, 16):
                            pointer = struct.unpack_from('<Q', registry, offset+field)[0]
                            struct.pack_into('<Q', registry, offset+field, delta+pointer-NOMINAL_DELTA)
                    header, context, stack = delta+0x100000, delta+0x110000, delta+0x1f0000
                    metadata = struct.pack('<I4sI4xQ', 1, b'0.81', len(entries), header+24)
                    metadata += b''.join(struct.pack('<Q4IQ', t['key'], t['offset'], t['mode'],
                        t['columns'], t['rows'], delta+raw['block_file']+t['offset']+12) for t in entries)
                    context_bytes = bytearray(data[0x307e0:0x30820])
                    struct.pack_into('<Q', context_bytes, 40, delta+0x193fc)
                    remote.write(context, context_bytes)
                    remote.write(delta+0x31998, struct.pack('<Q', context))
                    remote.write(delta+0x31510, struct.pack('<Q', delta+0x2f6c0))
                    for point in (0x2f6d0, AFTER_STORE, ERROR):
                        assert remote.command(f'Z0,{delta+point:x},4') == 'OK'
                    for vector in vectors:
                        prediction = publication(table, vector['caller_value'], vector['wrapper_value'], vector['control'])
                        active_registry, active_metadata = bytearray(registry), bytearray(metadata)
                        struct.pack_into('<Q', active_registry, ENTRY-REGISTRY+24, header)
                        if vector['control'] == 'name':
                            struct.pack_into('<Q', active_registry, ENTRY-REGISTRY, delta+0x30486)
                        if vector['control'] == 'key':
                            struct.pack_into('<Q', active_metadata, 24, 0)
                        remote.write(delta+REGISTRY, active_registry)
                        remote.write(header, active_metadata)
                        remote.write(delta+0x30520, struct.pack('<Q', vector['destination']))
                        remote.write(delta+0x31978, struct.pack('<Q', vector['caller_value']))
                        remote.write(delta+0x31c28, struct.pack('<I', vector['counter_before']))
                        window = bytearray(b'\xa5'*WINDOW)
                        for address in (RECORD, ALTERNATE):
                            struct.pack_into('<Q', window, address-RECORD, 0xcafe)
                        remote.write(RECORD-16, b'\x77'*16+window+b'\x77'*16)
                        remote.write(stack-0x1000, b'\x77'*32+b'\xa5'*(0x1000-32)+b'\x77'*32)
                        for reg in range(31):
                            register(remote, reg, 0xa500000000000000+reg)
                        for reg, value in ((19, delta+0x31000), (20, delta+0x31000),
                                (22, delta+0x31000), (23, 5), (24, 11),
                                (30, finish), (31, stack), (32, delta+0x1ea18)):
                            register(remote, reg, value)
                        remote.command('c')
                        assert register(remote, 32) == delta+0x2f6d0
                        assert remote.integer(RECORD+0x38, 8) == vector['caller_value']
                        counter = phase_counter(vector['counter_before'])
                        assert remote.integer(RECORD+0x48) == remote.integer(delta+0x31c28) == counter
                        # A declared data change between the two actual loads, not a hardware sample.
                        if vector['caller_value'] != vector['wrapper_value']:
                            remote.write(delta+0x31978, struct.pack('<Q', vector['wrapper_value']))
                        remote.command('s')
                        remote.command('c')
                        frame = stack-16-288
                        assert register(remote, 29) == frame
                        assert remote.integer(frame+136, 8) == vector['wrapper_value']
                        assert remote.integer(stack-16, 8) == delta+0x1ea4c
                        assert remote.integer(frame+8, 8) == delta+0x2f6e8
                        struct.pack_into('<Q', window, 0x38, vector['caller_value'])
                        struct.pack_into('<I', window, 0x48, counter)
                        if prediction['first_store_reached']:
                            assert register(remote, 32) == delta+AFTER_STORE
                            assert register(remote, 0) == vector['destination']
                            assert register(remote, 1) == vector['wrapper_value']
                            assert remote.integer(frame+284) == prediction['row']
                            tail = table['cells'][prediction['row']*17+1:(prediction['row']+1)*17]
                            assert remote.read(remote.integer(frame+168, 8), 128) == struct.pack('<16Q', *tail)
                            struct.pack_into('<Q', window, vector['destination']-RECORD, vector['wrapper_value'])
                        else:
                            assert register(remote, 32) == delta+ERROR
                            assert register(remote, 0) == prediction['prefix_error']
                        observed = b'\x77'*16+window+b'\x77'*16
                        assert remote.read(RECORD-16, WINDOW+32) == observed
                        physical = backing+(RECORD-0x02000000)
                        assert remote.read(physical-16, WINDOW+32) == observed
                        assert remote.read(stack-0x1000, 32) == remote.read(stack, 32) == b'\x77'*32
                        assert remote.read(delta+REGISTRY, len(active_registry)) == active_registry
                        assert remote.read(header, len(active_metadata)) == active_metadata
                        assert remote.integer(delta+0x31978, 8) == vector['wrapper_value']
                        assert remote.integer(delta+0x30520, 8) == vector['destination']
                        results.append(dict(case=vector['name'], laboratory_delta=hex(delta),
                            caller_sample=hex(vector['caller_value']), wrapper_sample=hex(vector['wrapper_value']),
                            destination_virtual=hex(vector['destination']), counter_after=hex(counter),
                            fixed_copy=hex(remote.integer(RECORD+0x38, 8)),
                            fixed_first_u64=hex(remote.integer(RECORD, 8)),
                            first_store_reached=prediction['first_store_reached'], row=prediction['row'],
                            prefix_error=prediction['prefix_error'],
                            window_sha256=hashlib.sha256(window).hexdigest(),
                            original_indirect_calls_taken=True, synthetic_mapping_only=True))
                    for point in (0x2f6d0, AFTER_STORE, ERROR, 0x15000):
                        assert remote.command(f'z0,{delta+point:x},4') == 'OK'
                    for pc, template in TEMPLATES:
                        size = 4*len(template.split())
                        assert remote.read(delta+pc, size) == data[pc:pc+size]
                    assert remote.read(delta+0x69000, 0x14000) == data[0x69000:0x7d000]
                    assert remote.read(context, len(context_bytes)) == context_bytes
                    assert remote.integer(delta+0x31510, 8) == delta+0x2f6c0
                    assert remote.read(0x40040000, len(tables)) == tables
                    assert remote.read(0x40014000, len(fixture)) == fixture
                    mappings.append(dict(laboratory_delta=hex(delta), virtual_block='0x02000000..0x02200000',
                        physical_ram_block=hex(backing), page_tables_sha256=hashlib.sha256(tables).hexdigest()))
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
    return dict(mode='original_publication_calls_and_prefix_with_synthetic_mmu_qemu',
        sboot_sha256=report['sboot_sha256'], instruction_index_sha256=report['instructions']['index_sha256'],
        case_count=len(results), first_stores=sum(r['first_store_reached'] for r in results),
        prefix_errors=len([r for r in results if not r['first_store_reached']]), cases=results,
        mappings=mappings, mmu_fixture_sha256=hashlib.sha256(fixture).hexdigest(),
        firmware_instructions_patched=False, publication_calls_skipped=False,
        address_register_rebinding=False, parsed_metadata_materialized_by_host=True,
        packing_outputs_materialized_from_prior_model=True,
        explicit_between_load_slot_changes=sum(r['caller_sample'] != r['wrapper_sample'] for r in results),
        mmu_enabled_data_cache_disabled=True, gate_mmio_or_error_helper_executed=False,
        callback_completion_or_physical_alias_verified=False, final_ram_or_fdt_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = run(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'emulate_bl2_geometry_publication_qemu: {exc}\n')
    print(json.dumps(result, indent=2))
