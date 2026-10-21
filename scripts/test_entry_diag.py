#!/usr/bin/env python3
"""Observe the raw ARM64 Image in QEMU at EL1/EL2 and relocated addresses."""
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile
from test_payload_loader import Remote, symbols, ROOT


def register(remote, number, value=None, size=8):
    if value is None:
        return int.from_bytes(bytes.fromhex(remote.command(f'p{number:x}')), 'little')
    assert remote.command(f'P{number:x}={value.to_bytes(size,"little").hex()}') == 'OK'


def main():
    with tempfile.TemporaryDirectory(prefix='entry-diag-') as directory:
        build = Path(directory)
        subprocess.run(['make', '-s', '-C', str(ROOT/'r8'), f'BUILD={build}',
                        str(build/'entry_diag.elf'), str(build/'entry_diag.Image')], check=True)
        sym = symbols(build/'entry_diag.elf')
        image = (build/'entry_diag.Image').read_bytes()
        base = sym['diag_image']
        assert struct.unpack_from('<QQQ', image, 8) == (0x80000, len(image), 8)
        assert image[32:56] == bytes(24) and image[56:64] == b'ARM\x64\0\0\0\0'
        assert len(image) == sym['diag_end']-base
        for el, virtualization in ((1, 'off'), (2, 'on')):
            for offset in (0, 0x8000, 0x1f8000):
                with (build/'qemu.log').open('wb') as log:
                    process = subprocess.Popen(['make', '-s', '--no-print-directory', '-C', str(ROOT/'r8'),
                        f'BUILD={build}', f'DIAG_VIRTUALIZATION={virtualization}', 'run_entry_diag'],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, start_new_session=True)
                    remote = None
                    try:
                        remote = Remote(process.stdout, process.stdin)
                        # Let QEMU's real raw-Image boot stub establish the entry context.
                        assert remote.command(f'Z0,{base:x},4') == 'OK'
                        remote.command('c')
                        assert register(remote, 32) == base
                        assert remote.command(f'z0,{base:x},4') == 'OK'
                        pstate = register(remote, 33)
                        assert (pstate >> 2) & 3 == el
                        address = base + offset
                        if offset:
                            remote.write(address, image)
                            register(remote, 32, address)
                        # Distinct arguments, including an intentionally invalid FDT pointer:
                        # the probe must record it without dereferencing it.
                        args = (0x1122334455667788, 0x0123456789abcdef, 0xfedcba9876543210, 0x9988776655443322)
                        for i, value in enumerate(args): register(remote, i, value)
                        register(remote, 31, 0x12345678)  # no stack access permitted
                        guards = b'\x77'*16
                        remote.write(address-16, guards)
                        remote.write(address+len(image), guards)
                        record = sym['diag_record']+offset
                        remote.write(record, b'\xa5'*128)
                        done = sym['diag_done']+offset
                        assert remote.command(f'Z0,{done:x},4') == 'OK'
                        remote.command('c')
                        assert register(remote, 32) == done
                        data = remote.read(record, 128)
                        assert struct.unpack_from('<QII', data) == (0x5952544e45313253, 1, 128)
                        values = struct.unpack_from('<14Q', data, 16)
                        assert values[:4] == args
                        assert values[4] == el*4 and values[5] == pstate & 0x3c0
                        assert values[6] & 5 == 0
                        assert values[8] == pstate & 1 and values[9] == 0x12345678
                        assert values[10:12] == (address, record) and values[12:] == (0, 0)
                        assert register(remote, 31) == 0x12345678
                        assert register(remote, 33) & 0x3c0 == 0x3c0
                        assert remote.read(address-16, 16) == guards
                        assert remote.read(address+len(image), 16) == guards
                        assert remote.read(address, record-address) == image[:record-address]
                        print(f'ENTRY DIAG PASS: EL{el}, relocation +0x{offset:x}, arguments/state/guards intact')
                    finally:
                        if remote: remote.close()
                        if process.poll() is None: os.killpg(process.pid, signal.SIGTERM)
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL); process.wait()
        print('ENTRY DIAG: 6/6 QEMU cases PASS; one CPU, no Samsung hardware claim')

if __name__ == '__main__': main()
