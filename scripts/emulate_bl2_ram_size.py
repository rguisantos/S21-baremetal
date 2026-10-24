#!/usr/bin/env python3
"""Execute only HZC2's original 44-instruction size leaf in QEMU virt RAM.

All four geometry words are synthetic. The Samsung initializer, callbacks,
MMIO, secure services and store to 0x02038848 are deliberately outside this run.
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

from inspect_bl2_ram_size import (LEAF_START, LEAF_END, TABLE, SLOTS,
                                 geometry, inspect)
from inspect_el2_hzc2 import IMAGES, read_exact
from test_entry_diag import register
from test_payload_loader import Remote, symbols, ROOT


def cases():
    result = [
        ('disabled', [0x61610030]*4),
        ('one_term_8gib', [0x60000100]*4),
        ('two_terms_12gib', [0x60400130]*4),
        ('maximum_32gib', [0x61610130]*4),
        ('mode_only_from_slot0', [0x60000100, 0x61610130, 0, 0]),
        ('two_terms_mixed_modes', [0x60000130, 0x61610100, 0, 0]),
        ('gate_high_bit', [0x60008000, 0, 0, 0]),
        ('factor_two_is_not_double', [0x62000100]*4),
        ('upper_bits_ignored', [0xffffffff61610130]*4),
    ]
    # Every selector, including the out-of-table 7..15, in both term positions.
    result += [(f'index_{i}', [(i << 28) | (i << 20) | 0x130]*4) for i in range(16)]
    rng = random.Random(0x2caec)
    result += [(f'seeded_{i}', [rng.getrandbits(64) for _ in range(4)]) for i in range(8)]
    return result


def run(path):
    evidence = inspect(path)
    data = read_exact(path, *IMAGES['sboot'])
    code, table_bytes = data[LEAF_START:LEAF_END], data[TABLE:TABLE+14]
    table = struct.unpack('<7H', table_bytes)
    results = []
    with tempfile.TemporaryDirectory(prefix='bl2-ram-leaf-') as directory:
        build = Path(directory)
        # This Image is only a boot carrier. Stop before its first instruction.
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
                assert register(remote, 32) == boot
                assert (register(remote, 33) >> 2) & 3 == 1
                assert remote.command(f'z0,{boot:x},4') == 'OK'
                for delta in (0x40000000, 0x40200000):
                    finish = delta + LEAF_END
                    assert remote.command(f'Z0,{finish:x},4') == 'OK'
                    for name, slots in cases():
                        packed = struct.pack('<4Q', *slots)
                        segments = ((delta+LEAF_START, code), (delta+TABLE, table_bytes),
                                    (delta+SLOTS, packed))
                        for address, payload in segments:
                            remote.write(address-16, b'\x77'*16 + payload + b'\x77'*16)
                        for reg in range(31):
                            register(remote, reg, 0xa500000000000000 + reg)
                        register(remote, 30, finish)
                        register(remote, 31, 0x12345678)  # invalid stack, no SP access allowed
                        register(remote, 32, delta + LEAF_START)
                        remote.command('c')
                        assert register(remote, 32) == finish, f'{name}: escaped leaf'
                        expected = geometry(slots, table)
                        actual = register(remote, 0)
                        assert actual == expected['total_bytes'], (name, actual, expected)
                        assert register(remote, 31) == 0x12345678
                        assert register(remote, 30) == finish
                        for reg in range(19, 30):
                            assert register(remote, reg) == 0xa500000000000000 + reg
                        for address, payload in segments:
                            assert remote.read(address-16, len(payload)+32) == b'\x77'*16 + payload + b'\x77'*16
                        results.append(dict(case=name, laboratory_delta=hex(delta),
                                            slots=[hex(v) for v in slots],
                                            result_bytes=actual, matched=True))
                    assert remote.command(f'z0,{finish:x},4') == 'OK'
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
    return dict(mode='isolated_original_leaf_qemu_virt', input=evidence['input'],
                leaf=evidence['leaf'], case_count=len(results), cases=results,
                table_sha256=hashlib.sha256(table_bytes).hexdigest(),
                seed='0x2caec', stack_unchanged=True, callee_saved_unchanged=True,
                code_table_inputs_and_guards_unchanged=True,
                physical_execution_verified=False, geometry_runtime_observed=False,
                initializer_executed=False, callbacks_executed=False,
                destination_0x02038848_written=False, memory_map_verified=False,
                limits=['Two page-aligned laboratory placements, not Samsung physical addresses',
                        'Synthetic geometry only; no DRAM initialization, MMIO, SMC or FDT edits',
                        'Validates the selected leaf, not callback resolution or reachability'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    print(json.dumps(run(args.sboot), indent=2))


if __name__ == '__main__':
    main()
