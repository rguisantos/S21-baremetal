#!/usr/bin/env python3
"""Original LK bank writer and FDT editor in QEMU RAM with synthetic trees.

snprintf, strtoul and diagnostic printf are debugger substitutions. No Samsung
initialization, MMIO, service or physical FDT is executed or acquired.
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
import time

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_proton import fdt_nodes
from check_lk_uh_ranges import model as ranges_model
from test_entry_diag import register
from test_fdt import encode, node, text, u32, u64
from test_payload_loader import ROOT, Remote, symbols

SEGMENTS = ((0xf12c8, 0xf164c), (0x11e5e0, 0x11ff68),
            (0x1af3c0, 0x1af688), (0x1b2250, 0x1b2900),
            (0x20e000, 0x20f800), (0x22c000, 0x22d000))
HOOKS = (0x1b1160, 0x1af890, 0x1b1658)
RESULTS = {0xf15bc: 'create', 0xf160c: 'reg', 0xf1638: 'device_type'}
SLOT = 0x4740f8
FDT, STACK = 0x41000000, 0x42000000
CASES = (
    ('no_space', 0, False, False, 0),
    ('node_only', 32, False, False, 0),
    ('reg_without_type', 64, False, False, 0),
    ('zero_complete', 128, False, False, 0),
    ('replace_existing', 128, True, False, 0),
    ('hidden_reg_failure', 0, True, True, 0),
    ('nonzero_control', 128, False, False, 0x1000),
    ('size_high_bits_truncated', 128, False, False, 0x100000000),
)


def fixture(slack, existing=False, omit_reg=False):
    props = {'device_type': text('memory' if omit_reg else 'old')}
    if not omit_reg:
        props['reg'] = u64(0xc0000000) + u32(0x1234)
    children = [node('memory@c0000000', props)] if existing else []
    blob = bytearray(encode(node('', {'#address-cells': u32(2), '#size-cells': u32(1)}, children)))
    struct.pack_into('>I', blob, 4, len(blob) + slack)
    return bytes(blob) + bytes(slack)


def cstring(remote, address, limit=256):
    return remote.read(address, limit).split(b'\0', 1)[0].decode('ascii')


def substitute(remote, pc):
    args = [register(remote, i) for i in range(6)]
    lr = register(remote, 30)
    if pc == 0x1b1160:
        fmt = cstring(remote, args[2])
        if fmt == 'memory@%lx':
            out = f'memory@{args[3]:x}'
        elif fmt == '/memory@%lx':
            out = f'/memory@{args[3]:x}'
        elif fmt == '<0x%x 0x%x 0x%x>':
            out = '<' + ' '.join(f'0x{x & 0xffffffff:x}' for x in args[3:6]) + '>'
        elif fmt == 'memory':
            out = 'memory'
        else:
            raise ValueError('unexpected formatter or call')
        if args[1] != 4096 or len(out) >= args[1]:
            raise ValueError('unexpected formatter bound')
        remote.write(args[0], out.encode() + b'\0')
        result = len(out)
    elif pc == 0x1af890:
        if args[2] != 0:
            raise ValueError('unexpected integer base')
        match = re.match(r'\s*(0x[0-9a-f]+|[0-9]+)', cstring(remote, args[0]))
        if not match:
            raise ValueError('unexpected integer token')
        result = int(match.group(1), 0)
        remote.write(args[1], struct.pack('<Q', args[0] + match.end()))
    elif pc == 0x1b1658:
        result = 0  # Only suppress the error diagnostic; do not dereference its strings.
    else:
        raise ValueError('unexpected substitution')
    for i in range(19):
        register(remote, i, 0xa550000000000000 + i)
    register(remote, 0, result)
    register(remote, 32, lr)


def check_result(name, size, calls, props, final_w0):
    """Independent expected effects for the deliberately bounded fixtures."""
    expected_calls = {'no_space': (1, 1, 1), 'node_only': (0, 1, 1),
        'reg_without_type': (0, 0, 1), 'replace_existing': (1, 0, 0),
        'hidden_reg_failure': (1, 1, 0)}.get(name, (0, 0, 0))
    assert tuple(calls[key] for key in ('create', 'reg', 'device_type')) == expected_calls
    assert final_w0 == expected_calls[-1]
    if name == 'no_space':
        assert props is None
        return
    expected = {}
    if name not in ('node_only', 'hidden_reg_failure'):
        expected['reg'] = struct.pack('>QI', 0xc0000000, size & 0xffffffff)
    if name not in ('node_only', 'reg_without_type'):
        expected['device_type'] = b'memory\0'
    assert props == expected


def run(path):
    data = read_exact(path, *IMAGES['sboot'])
    rows = []
    with tempfile.TemporaryDirectory(prefix='lk-bank-editor-') as directory:
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
                assert register(remote, 32) == boot
                assert remote.command(f'z0,{boot:x},4') == 'OK'
                for delta in (0x40000000, 0x40200000):
                    finish = delta + 0x300000
                    points = [finish] + [delta + p for p in (*HOOKS, *RESULTS)]
                    for a, b in SEGMENTS:
                        remote.write(delta + a, data[a:b])
                    for pc in points:
                        assert remote.command(f'Z0,{pc:x},4') == 'OK'
                    for name, slack, existing, omit_reg, size in CASES:
                        blob = fixture(slack, existing, omit_reg)
                        remote.write(FDT - 16, b'\x77'*16 + blob + b'\x77'*16)
                        remote.write(delta + SLOT, struct.pack('<Q', FDT))
                        remote.write(STACK - 0x4000, b'\x77'*16 + b'\xa5'*0x3ff0 + b'\x77'*16)
                        for i in range(31):
                            register(remote, i, 0xa550000000000000 + i)
                        for i, v in ((0, 0xc0000000), (1, size), (30, finish),
                                     (31, STACK), (32, delta + 0xf1570)):
                            register(remote, i, v)
                        calls, hook_counts = {}, {hex(p): 0 for p in HOOKS}
                        deadline = time.monotonic() + 15
                        for _ in range(64):
                            remote.command('c')
                            if time.monotonic() > deadline:
                                raise ValueError('writer case exceeds host deadline')
                            pc = register(remote, 32)
                            if pc == finish:
                                break
                            offset = pc - delta
                            if offset in HOOKS:
                                substitute(remote, offset)
                                hook_counts[hex(offset)] += 1
                            elif offset in RESULTS:
                                value = register(remote, 0) & 0xffffffff
                                calls[RESULTS[offset]] = value - (1 << 32) if value >> 31 else value
                                assert remote.command(f'z0,{pc:x},4') == 'OK'
                                remote.command('s')
                                assert register(remote, 32) == pc + 4
                                assert remote.command(f'Z0,{pc:x},4') == 'OK'
                            else:
                                raise ValueError(f'unexpected stop at {pc:#x}')
                        else:
                            raise ValueError('writer exceeds stop budget')
                        assert set(calls) == set(RESULTS.values())
                        assert register(remote, 31) == STACK
                        for i in range(19, 30):
                            assert register(remote, i) == 0xa550000000000000 + i
                        assert remote.read(FDT-16, 16) == remote.read(FDT+len(blob), 16) == b'\x77'*16
                        assert remote.read(STACK-0x4000, 16) == remote.read(STACK, 16) == b'\x77'*16
                        output = remote.read(FDT, len(blob))
                        nodes = fdt_nodes(output)
                        props = nodes.get('/memory@c0000000')
                        final_w0 = register(remote, 0) & 0xffffffff
                        check_result(name, size, calls, props, final_w0)
                        assert nodes['/'] == {'#address-cells': u32(2), '#size-cells': u32(1)}
                        assert len(nodes) == 1 + int(props is not None)
                        row = dict(case=name, laboratory_delta=hex(delta), slack=slack,
                            existing=existing, supplied_size=hex(size), helper_returns=calls,
                            final_w0=final_w0, node_present=props is not None,
                            properties={k: v.hex() for k, v in (props or {}).items()},
                            output_sha256=hashlib.sha256(output).hexdigest(), substitutions=hook_counts,
                            guards_and_callee_saved_preserved=True)
                        if props is not None and 'reg' in props:
                            row['lk_uh_callback_model'] = ranges_model(output)['submitted_ranges']
                            assert row['lk_uh_callback_model'][0]['uh_initial_nonzero_guard_passes'] == bool(size & 0xffffffff)
                        rows.append(row)
                    for a, b in SEGMENTS:
                        assert remote.read(delta+a, b-a) == data[a:b]
                    for pc in points:
                        assert remote.command(f'z0,{pc:x},4') == 'OK'
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
    for name, *_ in CASES:
        matches = [row for row in rows if row['case'] == name]
        assert len(matches) == 2
        assert matches[0]['output_sha256'] == matches[1]['output_sha256']
        assert matches[0]['helper_returns'] == matches[1]['helper_returns']
    return dict(mode='original_lk_bank_writer_editor_qemu', sboot_sha256=IMAGES['sboot'][1],
        segments=[dict(start=hex(a), end=hex(b), sha256=hashlib.sha256(data[a:b]).hexdigest())
                  for a, b in SEGMENTS], cases=rows, case_count=len(rows),
        original_code_segments_unchanged=True, both_placements_match=True,
        writer_and_editor_executed_in_qemu=True, physical_fdt_observed=False,
        services_executed=False, is_final_fdt=False,
        limits=['Synthetic FDTs and two laboratory relocations; not Samsung runtime addresses',
                'snprintf/strtoul/diagnostic printf substituted with guarded host operations',
                'Bank constructor, later edits, LK walker and uH are not executed',
                'LK-to-uH callback arguments modeled from resulting synthetic bytes only'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.sboot), indent=2))
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError,
            AssertionError, TimeoutError, RuntimeError) as error:
        parser.exit(2, f'emulate_lk_bank_editor_qemu: {error}\n')
