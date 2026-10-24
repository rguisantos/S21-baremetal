#!/usr/bin/env python3
"""Original dump/formatter and flag fragment in QEMU RAM with a lab sink.

    The console puts slot is rebound to a RET in RAM. GDB observes its
    strings and every original source LDR. No original UART/debug loop runs.
    The four flag instructions receive X3 from the harness, not hardware.
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
from inspect_newtime_error_hzc2 import TEMPLATES, dump_plan, error_flags, inspect
from test_entry_diag import register
from test_payload_loader import ROOT, Remote, symbols


def transcript(base, offset, size, source):
    """Independent textual expectation: the dump prints complete u32 words."""
    plan = dump_plan(base+offset, size)
    text = '\n          |          0x0|          0x4|          0x8|          0xC|\n'
    text += '-------------------------------------------------------------------\n'
    for index in range(plan['word_count']):
        if index and index % 4 == 0:
            text += '\n'
        address = base+index*4
        if index % 4 == 0:
            text += f'  {address:08X}|'
        value = struct.unpack_from('<I', source, index*4)[0]
        text += '     '+('        ' if address < base+offset else f'{value:08X}')+'|'
    return (text+'\n').encode('ascii')


def run(path):
    report = inspect(path)  # Reject wrong images before building or starting QEMU.
    data = read_exact(path, *IMAGES['sboot'])
    results, flag_cases = [], []
    cases = [(0, 0x1a0), (0, 0), (0, 1), (0, 4), (0, 17),
        (1, 0), (3, 1), (15, 0), (15, 2), (3, 17),
        (3, 0xfffffffd), (15, 0xfffffff1), (3, 0xffffffff)]
    with tempfile.TemporaryDirectory(prefix='newtime-error-') as directory:
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
                    context, console = delta+0x100000, delta+0x100100
                    source_base, stack = delta+0x180000, delta+0x1f0000
                    sink, finish = delta+0x15000, delta+0x15010
                    remote.write(sink, struct.pack('<I', 0xd65f03c0))  # Lab RET; not firmware output.
                    context_bytes = struct.pack('<Q', console)
                    console_bytes = struct.pack('<4Q', 0, sink, 0, delta+0x1d430)
                    remote.write(delta+0x31998, struct.pack('<Q', context))
                    remote.write(context, context_bytes)
                    remote.write(console, console_bytes)
                    points = (sink, finish, delta+0x20654, delta+0x2097c)
                    for point in points:
                        assert remote.command(f'Z0,{point:x},4') == 'OK'
                    source = bytes((i*37+11) & 255 for i in range(0x2400))
                    for offset, size in cases:
                        remote.write(source_base-16, b'\x77'*16+source+b'\x77'*16)
                        remote.write(stack-0x800, b'\x77'*32+b'\xa5'*(0x800-32)+b'\x77'*32)
                        for reg in range(31):
                            register(remote, reg, 0xa500000000000000+reg)
                        for reg, value in ((0, source_base+offset), (1, size),
                                (30, finish), (31, stack), (32, delta+0x204d4)):
                            register(remote, reg, value)
                        output, reads = bytearray(), []
                        for _ in range(2000):
                            remote.command('c')
                            pc = register(remote, 32)
                            if pc == finish:
                                break
                            if pc == sink:
                                chunk = remote.read(register(remote, 0), 128)
                                assert b'\0' in chunk
                                output.extend(chunk.split(b'\0', 1)[0])
                            elif pc == delta+0x20654:
                                address = register(remote, 0)+register(remote, 1)
                                reads.append(address)
                            else:
                                raise AssertionError(f'unexpected PC {pc:x}')
                            remote.command('s')  # Execute original LDR or the lab sink RET.
                        else:
                            raise AssertionError('dump exceeded bounded laboratory steps')
                        plan = dump_plan(source_base+offset, size)
                        assert reads == [source_base+4*i for i in range(plan['word_count'])]
                        assert output == transcript(source_base, offset, size, source)
                        assert remote.read(source_base-16, len(source)+32) == b'\x77'*16+source+b'\x77'*16
                        assert remote.read(stack-0x800, 32) == remote.read(stack, 32) == b'\x77'*32
                        assert register(remote, 31) == stack and register(remote, 30) == finish
                        for reg in range(19, 30):
                            assert register(remote, reg) == 0xa500000000000000+reg
                        results.append(dict(laboratory_delta=hex(delta), offset=offset, size_w=hex(size),
                            reads=len(reads), first_read=hex(reads[0]) if reads else None,
                            last_read=hex(reads[-1]) if reads else None,
                            transcript_bytes=len(output), transcript_sha256=hashlib.sha256(output).hexdigest(),
                            source_unchanged=True, abi_and_guards_matched=True))
                    # Only LSL/LDR/ORR/STR run. X3 is a RAM binding supplied here.
                    for before, argument in ((0, 27), (0, 5), (0x12345678, 27),
                            (0x08000000, 27), (0, 32), (0, 33), (0, 0xffffffff)):
                        region = bytearray(source)
                        struct.pack_into('<I', region, 0x24, before)
                        remote.write(source_base-16, b'\x77'*16+region+b'\x77'*16)
                        for reg, value in ((0, argument), (1, 1), (3, source_base+0x24),
                                (32, delta+0x2096c)):
                            register(remote, reg, value)
                        remote.command('c')
                        assert register(remote, 32) == delta+0x2097c
                        struct.pack_into('<I', region, 0x24, error_flags(before, argument))
                        assert remote.read(source_base-16, len(region)+32) == b'\x77'*16+region+b'\x77'*16
                        flag_cases.append(dict(laboratory_delta=hex(delta), before=hex(before),
                            argument=hex(argument), after=hex(error_flags(before, argument)),
                            only_field_24_changed=True))
                    for point in points:
                        assert remote.command(f'z0,{point:x},4') == 'OK'
                    for pc, template in TEMPLATES:
                        length = 4*len(template.split())
                        assert remote.read(delta+pc, length) == data[pc:pc+length]
                    assert remote.read(context, len(context_bytes)) == context_bytes
                    assert remote.read(console, len(console_bytes)) == console_bytes
                    assert remote.integer(delta+0x31998, 8) == context
                    for item in report['strings']:
                        address = int(item['file'], 16)
                        length = len(item['text'])+1
                        assert remote.read(delta+address, length) == data[address:address+length]
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
    return dict(mode='original_dump_formatter_and_flag_fragment_with_lab_bindings_qemu',
        sboot_sha256=report['sboot_sha256'], instruction_index_sha256=report['instructions']['index_sha256'],
        dump_case_count=len(results), flag_fragment_case_count=len(flag_cases),
        dump_cases=results, flag_fragment_cases=flag_cases,
        original_dump_and_formatter_instructions_unchanged=True,
        console_puts_rebound_to_ram_ret=True, original_uart_or_debug_loop_executed=False,
        flags_fragment=['0x2096c', '0x2097c'], flags_X3_supplied_by_harness=True,
        full_error_helper_or_physical_record_executed=False,
        limits=['Lab context, stack, source and sink; original dump and formatter execute in RAM',
                'Sink strings and source LDR addresses observed by GDB, no UART/MMIO responses',
                'Flag test executes four instructions with supplied RAM X3, not the address producer',
                'No complete transitive effects, real console bindings, hardware state or FDT proved'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = run(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'emulate_newtime_error_qemu: {exc}\n')
    print(json.dumps(result, indent=2))
