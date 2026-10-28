#!/usr/bin/env python3
"""Original HZC2 PSCI FDT rewriter in QEMU; no PSCI instruction is invoked."""
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

from emulate_lk_bank_editor_qemu import SEGMENTS as BANK_SEGMENTS, FDT, STACK
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_proton import fdt_nodes
from test_entry_diag import register
from test_fdt import encode, node, text, u32, u64
from test_payload_loader import ROOT, Remote, symbols

SEGMENTS = tuple((a, b) for a, b in BANK_SEGMENTS
                 if a in (0x11e5e0, 0x1af3c0, 0x1b2250, 0x22c000)) + (
    (0xf9470, 0xf9618), (0x214000, 0x215000), (0x22b000, 0x22c000),
    (0x26d000, 0x26e000))
FLAG = 0x487c90
# name, flag, property bytes, node present, slack, null pointer, expected method, W0
CASES = (
    ('flag_zero', 0, b'smc\0', True, 32, False, b'smc\0', -1),
    ('smc_to_hvc', 1, b'smc\0', True, 32, False, b'hvc\0', 0),
    ('already_hvc', 1, b'hvc\0', True, 32, False, b'hvc\0', 0),
    ('unknown_method', 1, b'foo\0', True, 32, False, b'foo\0', -1),
    ('missing_node', 1, None, False, 32, False, None, -1),
    ('missing_method', 1, None, True, 32, False, None, -1),
    ('null_fdt', 1, b'smc\0', True, 32, True, b'smc\0', -1),
    ('empty_property', 1, b'', True, 32, False, b'hvc\0', 0),
    ('smc_prefix_only', 1, b's', True, 32, False, b'hvc\0', 0),
    ('hvc_prefix_only', 1, b'hv', True, 32, False, b'hv', 0),
    ('embedded_nul_tail', 1, b'smc\0tail', True, 32, False, b'hvc\0', 0),
    ('no_room_to_grow', 1, b'', True, 0, False, b'', -1),
)


def fixture(method, psci, slack):
    children = [node('memory@c0000000', {'device_type': text('memory'),
                'reg': u64(0xc0000000) + u32(0)})]
    if psci:
        children.append(node('psci', {} if method is None else {'method': method}))
    blob = bytearray(encode(node('', {'#address-cells': u32(2), '#size-cells': u32(1)}, children)))
    struct.pack_into('>I', blob, 4, len(blob) + slack)
    return bytes(blob) + bytes(slack)


def run(path):
    data = read_exact(path, *IMAGES['sboot'])
    rows = []
    with tempfile.TemporaryDirectory(prefix='lk-psci-final-') as directory:
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
                    finish, diagnostic = delta + 0x300000, delta + 0x1b1658
                    for a, b in SEGMENTS:
                        remote.write(delta+a, data[a:b])
                    for pc in (finish, diagnostic):
                        assert remote.command(f'Z0,{pc:x},4') == 'OK'
                    for name, flag, method, psci, slack, null, wanted, status in CASES:
                        blob = fixture(method, psci, slack)
                        before = fdt_nodes(blob)
                        remote.write(FDT-16, b'\x77'*16 + blob + b'\x77'*16)
                        flag_bytes = b'\x77'*16 + bytes([flag]) + b'\x77'*16
                        remote.write(delta+FLAG-16, flag_bytes)
                        remote.write(STACK-0x1000, b'\x77'*16 + b'\xa5'*0xff0 + b'\x77'*16)
                        for i in range(31):
                            register(remote, i, 0xa550000000000000+i)
                        for i, value in ((0, 0 if null else FDT), (30, finish),
                                         (31, STACK), (32, delta+0xf9470)):
                            register(remote, i, value)
                        prints, deadline = 0, time.monotonic()+15
                        for _ in range(16):
                            remote.command('c')
                            if time.monotonic() > deadline:
                                raise ValueError('PSCI writer case exceeds host deadline')
                            pc = register(remote, 32)
                            if pc == finish:
                                break
                            if pc != diagnostic:
                                raise ValueError(f'unexpected stop at {pc:#x}')
                            lr = register(remote, 30)
                            for i in range(19):
                                register(remote, i, 0xa550000000000000+i)
                            register(remote, 0, 0)
                            register(remote, 32, lr)
                            prints += 1
                        else:
                            raise ValueError('PSCI writer exceeds stop budget')
                        actual = register(remote, 0) & 0xffffffff
                        assert actual == status & 0xffffffff, name
                        assert register(remote, 31) == STACK
                        for i in range(19, 30):
                            assert register(remote, i) == 0xa550000000000000+i
                        assert remote.read(FDT-16, 16) == remote.read(FDT+len(blob), 16) == b'\x77'*16
                        assert remote.read(STACK-0x1000, 16) == remote.read(STACK, 16) == b'\x77'*16
                        assert remote.read(delta+FLAG-16, len(flag_bytes)) == flag_bytes
                        output = remote.read(FDT, len(blob))
                        after = fdt_nodes(output)
                        expected = {k: dict(v) for k, v in before.items()}
                        if psci and wanted is not None:
                            expected['/psci']['method'] = wanted
                        assert after == expected, name
                        if wanted == method:
                            assert output == blob, name
                        assert after['/memory@c0000000'] == before['/memory@c0000000']
                        rows.append(dict(case=name, laboratory_delta=hex(delta), flag=flag,
                            supplied_method_hex=None if method is None else method.hex(),
                            result_method_hex=None if wanted is None else wanted.hex(),
                            final_w0_signed=status, diagnostic_calls_suppressed=prints,
                            input_sha256=hashlib.sha256(blob).hexdigest(),
                            output_sha256=hashlib.sha256(output).hexdigest(),
                            zero_bank_unchanged=True, guards_and_callee_saved_preserved=True))
                    for a, b in SEGMENTS:
                        assert remote.read(delta+a, b-a) == data[a:b]
                    for pc in (finish, diagnostic):
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
        results = [r for r in rows if r['case'] == name]
        assert len(results) == 2 and results[0]['output_sha256'] == results[1]['output_sha256']
    return dict(mode='original_lk_psci_property_rewriter_qemu', sboot_sha256=IMAGES['sboot'][1],
        case_count=len(rows), cases=rows, both_placements_match=True,
        segments=[dict(start=hex(a), end=hex(b), sha256=hashlib.sha256(data[a:b]).hexdigest())
                  for a, b in SEGMENTS], original_code_segments_unchanged=True,
        diagnostic_printf_substituted=True, comparison_and_fdt_editor_original=True,
        psci_smc_hvc_executed=False, physical_final_fdt_captured=False,
        limits=['Synthetic FDTs and supplied Harx flag; not a live register snapshot',
                'Only diagnostic printf is substituted; no console hardware is used',
                'A zero bank remains unchanged by this routine only; later calls stay opaque'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.sboot), indent=2))
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError,
            AssertionError,TimeoutError,RuntimeError) as error:
        parser.exit(2, f'emulate_lk_psci_final_qemu: {error}\n')
