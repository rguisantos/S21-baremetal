#!/usr/bin/env python3
"""Execute original packing blocks with explicit skipped-call returns in RAM.

No BLR preparation/query or BL CHIPID helper is executed. The harness sets
X0, LR and successor PC at those edges, preserving other registers/memory.
Inputs are deterministic laboratory vectors, not device register responses.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import struct
import subprocess
import tempfile

from inspect_bl2_geometry_packing import PREP_CALLS, QUERY_CALLS, TEMPLATES, inspect, pack_four
from inspect_bl2_ram_size import LEAF_START, TABLE, geometry
from inspect_el2_hzc2 import IMAGES, read_exact
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols


def cases():
    zero = ((0, 0, 0, 0), (0, 0, 0, 0))
    first = ((1, 8, 0, 0x18), (0, 0, 0, 0))
    both = ((1, 8, 0, 0x18), (1, 0, 0, 0x18))
    result = []

    def add(name, terms, revision=0, extension=0, seed=0xcafe):
        result.append(dict(name=name, responses=(terms,)*4, revisions=(revision,)*4,
                           extensions=(extension,)*4, initial_slot=seed))

    add('zero_marker', zero)
    add('zero_prior_all_ones', zero, seed=0xffffffffffffffff)
    add('first_only', first)
    add('second_only', (zero[0], both[1]))
    add('both', both)
    add('full_w_gate_zero_low_byte', ((0x100, 8, 9, 0x18), zero[1]))
    add('ignored_on_zero_gate', ((0, 255, 255, 255), (0, 255, 255, 255)))
    result.append(dict(name='slot0_mode3_last_mode0', responses=(both, first, zero, zero),
        revisions=(1, 2, 3, 4), extensions=(0,)*4, initial_slot=0xcafe))
    result.append(dict(name='slot0_mode0_last_mode3', responses=(zero, first, first, both),
        revisions=(0,)*4, extensions=(0,)*4, initial_slot=0xcafe))
    for i in range(16):
        add(f'density_{i}', ((1, 2, 3, i*4+64), (1, 4, 5, i*4+128)))
    for revision in (0, 1, 8, 15):
        add(f'revision_{revision}', first, revision=revision, extension=4)
    for label, terms in (('A', first), ('B', ((1, 8, 0, 0x14), (1, 0, 0, 0x14))), ('C', both)):
        for extension in (0, 3, 4, 15):
            add(f'special_{label}_{extension}', terms, revision=1, extension=extension)
    add('extension_uses_low_nibble', both, revision=1, extension=0xfffffffd)
    rng = random.Random(0x2f130)
    for i in range(8):
        result.append(dict(name=f'seeded_{i}', responses=tuple(tuple(tuple(rng.getrandbits(32)
            for _ in range(4)) for _ in range(2)) for _ in range(4)),
            revisions=tuple(rng.randrange(16) for _ in range(4)),
            extensions=tuple(rng.getrandbits(32) for _ in range(4)), initial_slot=0xcafe))
    return result


def expected_state(vector, result):
    state = bytearray(b'\xa5'*784)
    for slot, item in enumerate(result['slots']):
        struct.pack_into('<Q', state, 752+slot*8, item['packed'])
        for term, responses in enumerate(item['effective_responses']):
            for selector, value in enumerate(responses):
                struct.pack_into('<I', state, 32+selector*32+slot*8+term*4, value)
    state[689] = result['mode_byte']
    return bytes(state)


def run(path):
    report = inspect(path)  # Exact image guard precedes build/QEMU.
    data = read_exact(path, *IMAGES['sboot'])
    vectors, results = cases(), []
    density = struct.unpack_from('<7H', data, TABLE)
    with tempfile.TemporaryDirectory(prefix='bl2-packing-') as directory:
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
                    finish, state, stack, record = (delta+n for n in (0x15000, 0x31688, 0x1f0000, 0x180000))
                    points = (*PREP_CALLS, *QUERY_CALLS, 0x2f360, 0x2f16c, 0x15000)
                    for point in points:
                        assert remote.command(f'Z0,{delta+point:x},4') == 'OK'
                    for vector in vectors:
                        predicted = pack_four(vector['responses'], vector['revisions'], vector['extensions'])
                        initial = bytearray(b'\xa5'*784)
                        struct.pack_into('<4Q', initial, 752, *([vector['initial_slot']]*4))
                        remote.write(state-16, b'\x77'*16+initial+b'\x77'*16)
                        record_bytes = struct.pack('<Q', 0xcafe)+b'\xa5'*(0x2400-8)
                        remote.write(record-16, b'\x77'*16+record_bytes+b'\x77'*16)
                        remote.write(stack-0x800, b'\x77'*32+b'\xa5'*(0x800-32)+b'\x77'*32)
                        for reg in range(31):
                            register(remote, reg, 0xa500000000000000+reg)
                        for reg, value in ((30, finish), (31, stack), (32, delta+0x2f130)):
                            register(remote, reg, value)
                        queries, preparations, clears, revisions = [], 0, [], []
                        for _ in range(300):
                            remote.command('c')
                            pc = register(remote, 32)-delta
                            if pc == 0x15000:
                                break
                            slot = register(remote, 19)
                            assert 0 <= slot < 4
                            if pc == 0x2f16c:
                                assert remote.integer(state+752+slot*8, 8) == 0
                                clears.append(slot)
                                remote.command('s')
                                continue
                            if pc in PREP_CALLS:
                                assert register(remote, 0) == slot
                                assert register(remote, 1) == struct.unpack_from('<Q', data, 0x31040)[0]
                                preparations += 1
                                returned = 0
                            elif pc in QUERY_CALLS:
                                term, selector = register(remote, 1), register(remote, 2)
                                assert register(remote, 0) == slot
                                assert register(remote, QUERY_CALLS[pc]) == struct.unpack_from('<Q', data, 0x30f20)[0]
                                if term == 3:
                                    assert selector == 49
                                    returned = vector['extensions'][slot]
                                else:
                                    assert term in (1, 2) and 5 <= selector <= 8
                                    returned = vector['responses'][slot][term-1][selector-5]
                                queries.append([slot, term, selector, returned])
                            elif pc == 0x2f360:
                                revisions.append(slot)
                                returned = vector['revisions'][slot]
                            else:
                                raise AssertionError(f'unexpected PC {pc:x}')
                            # Explicit edge contract: only X0/LR/PC change; no original call runs.
                            register(remote, 0, returned)
                            register(remote, 30, delta+pc+4)
                            register(remote, 32, delta+pc+4)
                        else:
                            raise AssertionError('packing exceeded bounded stops')
                        expected_queries, active, extended = [], 0, 0
                        for slot, item in enumerate(predicted['slots']):
                            for term, replies in enumerate(vector['responses'][slot], 1):
                                for selector in ((5, 6, 7, 8) if replies[0] else (5,)):
                                    expected_queries.append([slot, term, selector, replies[selector-5]])
                                active += bool(replies[0])
                            if item['queried_extension']:
                                extended += 1
                                expected_queries.append([slot, 3, 49, vector['extensions'][slot]])
                        assert queries == expected_queries and preparations == len(queries)+active+extended
                        assert clears == revisions == [0, 1, 2, 3]
                        state_bytes = expected_state(vector, predicted)
                        assert remote.read(state-16, 816) == b'\x77'*16+state_bytes+b'\x77'*16
                        assert register(remote, 0) == predicted['returned_w0']
                        assert register(remote, 31) == stack and register(remote, 30) == finish
                        for reg in range(19, 30):
                            assert register(remote, reg) == 0xa500000000000000+reg
                        assert remote.read(stack-0x800, 32) == remote.read(stack, 32) == b'\x77'*32
                        slots = [s['packed'] for s in predicted['slots']]
                        # Run the original size leaf separately, with these resulting RAM slots.
                        register(remote, 31, 0x12345678)
                        register(remote, 30, finish)
                        register(remote, 32, delta+LEAF_START)
                        remote.command('c')
                        assert register(remote, 32) == finish and register(remote, 31) == 0x12345678
                        expected_size = geometry(slots, density)['total_bytes']
                        assert register(remote, 0) == expected_size
                        assert remote.read(state-16, 816) == b'\x77'*16+state_bytes+b'\x77'*16
                        assert remote.read(record-16, 0x2420) == b'\x77'*16+record_bytes+b'\x77'*16
                        results.append(dict(case=vector['name'], laboratory_delta=hex(delta),
                            slots=[hex(s) for s in slots], initial_slot=hex(vector['initial_slot']),
                            returned_mode=predicted['returned_w0'], mode_byte=predicted['mode_byte'],
                            zeroed_slots=clears, skipped_query_calls=len(queries),
                            skipped_preparation_calls=preparations, skipped_chipid_calls=len(revisions),
                            extension_queries=extended, size_leaf_bytes=expected_size,
                            query_trace_sha256=hashlib.sha256(json.dumps(queries).encode()).hexdigest(),
                            whole_state_abi_code_record_and_guards_matched=True))
                    for point in points:
                        assert remote.command(f'z0,{delta+point:x},4') == 'OK'
                    for pc, template in TEMPLATES:
                        size = 4*len(template.split())
                        assert remote.read(delta+pc, size) == data[pc:pc+size]
                    assert remote.read(delta+TABLE, 14) == data[TABLE:TABLE+14]
                    for cell in (0x31040, 0x30f20):
                        assert remote.read(delta+cell, 8) == data[cell:cell+8]
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
    return dict(mode='original_packing_blocks_with_supplied_call_returns_qemu',
        sboot_sha256=report['sboot_sha256'], instruction_index_sha256=report['instructions']['index_sha256'],
        case_count=len(results), size_leaf_case_count=len(results), cases=results, vector_seed='0x2f130',
        inputs_are_laboratory_vectors=True, all_query_preparation_and_chipid_calls_skipped=True,
        edge_contract='X0 supplied, LR/PC set to successor, other registers/memory preserved',
        mmio_or_callback_bodies_executed=False, complete_physical_function_executed=False,
        record_pointer_or_alias_verified=False, real_ram_or_final_fdt_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = run(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'emulate_bl2_geometry_packing_qemu: {exc}\n')
    print(json.dumps(result, indent=2))
