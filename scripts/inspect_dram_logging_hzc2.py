#!/usr/bin/env python3
"""Hash-bound BL2/LK DRAM logging paths and the pinned reference driver's test."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_bl2_geometry_record import expect
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_monitor_preparation import word
from inspect_newtime_hzc2 import embedded
from inspect_newtime_record_hzc2 import unsigned

OBSERVED, REFERENCE = 0x0001000850500130, 0x0001000860000110
SOURCE_SHA = '1133eb69f70fed266d34a8dd1718ba5b879119057ca4eb6fc293341fe0b2f7f6'
CACHE = 0xaa7ea0
TEMPLATES = (
    (0x1fe54, 'a9bd53f3 d0000093 911a2274 f9000bfe f9418a80 f9400001 b4000501 f9417a80 910083e3 f9400c24 52800102 d360fc00 3900a3ff 52800201 f90013ff d63f0080 f9418a80 f9400000 b4000080 f9400401 910083e0 d63f0020 911a2274 910083e3 52800102 f9418a81 f9417a80 f9400021 f9400c24 52800201 d63f0080 f9418a80 f9400000 b4000080 f9400401 910083e0 d63f0020 911a2273 f9418a60 f9400000 b40000c0 f9400401 90000080 913aa400 91006c00 d63f0020 f9400bfe a8c353f3 d65f03c0'),
    (0x1e85c, '97fffbf5 f9015f20 9400057c'),
    (0x11b7f0, 'd286c081 d286c000 f2a040e1 f2a040e0 90004c62 b9400021 b9400000 2a0003e0 aa018000 f9075040 d65f03c0'),
    (0x11b820, '90004c60 f9475000 d3483c00 d65f03c0 90004c60 f9475000 d368bc00 d65f03c0 90004c60 f9475000 d3609c00 d65f03c0 90004c60 f9475000 d378ec00 d65f03c0'),
    (0x11b860, '90004c60 f9475001 d3483c21 7100183f 540002c0 7103fc3f 54000200 7100043f 54000140 a9bf7bfd 90000880 910003fd 91172000 94025771 90000880 91170000 a8c17bfd d65f03c0 90000880 91168000 d65f03c0 d503201f 90000880 9116e000 d65f03c0 d503201f 90000880 9116a000 d65f03c0'),
    (0x11b8d8, '90004c60 a9bf7bfd 910003fd f9475001 f9475002 d368bc20 d3609c41 2a002021 7100203f 54000520 54000148 7100143f 54000440 54000369 7100183f 54000261 90000880 9117c000 a8c17bfd d65f03c0 710c183f 54000280 54000409 528200c0 6b00003f 54000200 528220a0 6b00003f 540003c1 90000880 9117a000 a8c17bfd d65f03c0 d503201f 71001c3f 540002e1 90000880 9117e000 a8c17bfd d65f03c0 35000241 90000880 91182000 a8c17bfd d65f03c0 d503201f 90000880 91178000 a8c17bfd d65f03c0 90000880 91180000 a8c17bfd d65f03c0 7104183f 54fffe40 71041c3f 54fffd60 90000880 91184000 94025724 90000880 91170000 a8c17bfd d65f03c0'),
    (0x147d50, 'a9be7bfd 910003fd f9000bf3 94000053 2a0003f3 9400004d 2a0003e2 d0000623 2a1303e1 912b8060 9401a638 97ff4eb9 aa0003e1 b00007a2 9109e040 9401a633 97ff4ed2 aa0003e1 b00007a2 910a4040 9401a62e 97ff4e53 b00007a0 910aa000 9401a62a 97ff4ea7 f9400bf3 b00007a2 2a0003e1 a8c27bfd 910b0040 1401a623'),
    (0x11b6f0, '90004c62 b94ea840 350001c0 d2910901 90004c60 5c000261 f2a04061 f9400021 f9074c01 d354fc20 d35dfc21 b90ea841 9e620000 1e610800 d65f03c0 d503201f 5c000101 90004c60 f9474c00 d354fc00 9e620000 1e610800 d65f03c0 d503201f'),
)
STRINGS = {0x22b5a0: 'Samsung', 0x22b600: 'D1Z',
    0x23c278: 'DRAM Manufacturer = %s\n', 0x23c290: 'DRAM Process ver = %s\n',
    0x23c2a8: 'DRAM Size = %fGB\n'}


def fields(value):
    value = unsigned(value, 64)
    return dict(word=f'{value:016x}', mode=(value >> 4) & 15,
        manufacturer_byte=(value >> 8) & 255,
        process_pair=((value >> 32) & 255) | (((value >> 40) & 255) << 8),
        first_density_index=(value >> 28) & 15, first_factor=(value >> 24) & 15,
        second_density_index=(value >> 20) & 15, second_factor=(value >> 16) & 15,
        reference_driver_exact_match=value == REFERENCE,
        selected_manufacturer_label='Samsung' if (value >> 8) & 255 == 1 else None,
        selected_process_label='D1Z' if (value >> 32) & 65535 == 8 else None)


def inspect(sboot, driver):
    data = read_exact(sboot, *IMAGES['sboot'])
    for pc, template in TEMPLATES:
        expect(data, pc, template)
    for address, value in STRINGS.items():
        if data[address:address+len(value)+1] != value.encode()+b'\0':
            raise ValueError('DRAM logging string differs')
    if struct.unpack_from('<d', data, 0x11b750)[0] != 1/1024:
        raise ValueError('LK size scaling literal differs')
    source = Path(driver).read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA or len(source.splitlines()) != 2702:
        raise ValueError('reference driver differs')
    text = source.decode()
    required = ('ioremap(0x02073600, SZ_1K)', 'if (dram_type == 0x1000860000110)',
        'ret = exynos_init_freq_table(data);')
    if any(v not in text for v in required):
        raise ValueError('reference driver DRAM path differs')
    table = next(t for t in embedded(data)['parsed']['entries'] if t['key'] == 0x11111111)
    rows = [i for i in range(table['rows']) if table['cells'][i*table['columns']] == OBSERVED]
    if rows != [15]:
        raise ValueError('observed word NEWTIME row differs')
    index = b''.join(struct.pack('<II', pc+i*4, word(data, pc+i*4))
        for pc, t in sorted(TEMPLATES) for i in range(len(t.split())))
    return dict(mode='static_dram_logging_hzc2', sboot_sha256=IMAGES['sboot'][1],
        words=len(index)//8, instruction_index_sha256=hashlib.sha256(index).hexdigest(),
        bl2_print=dict(call='0x1e864 -> 0x1fe54', source='state0x31978',
            output='two width8 base16 u32 conversions, high32 then low32'),
        lk=dict(fill='0x11b7f0', high_read='0x02073604', low_read='0x02073600',
            read_is_two_nonatomic_u32_samples=True, cache=hex(CACHE),
            manufacturer='0x11b860: cache bits8..15; 1 -> Samsung',
            process='0x11b8d8: cache bits32..39 | bits40..47 <<8; 8 -> D1Z',
            labels_print='0x147d7c..0x147da0', size_print='0x147da4..0x147db0',
            size_source='0x11b6f0: cached total or u64 AP0x02038848, then (bytes>>20)/1024',
            formatted_size_is_not_an_exact_raw_u64_sample=True),
        reference_driver=dict(commit='756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0', sha256=SOURCE_SHA,
            lines=2702, dram_reference_lines=[1964, 1983, 1985, 1986, 1988, 1989, 1991],
            mif_read='u32 AP0x02073604 then u32 AP0x02073600',
            exact_match=hex(REFERENCE), disabled_frequencies_on_exact_match=[2288000,2535000,2730000],
            stock_kernel_binary_identity_verified=False),
        observed_word=fields(OBSERVED), reference_word=fields(REFERENCE),
        xor=hex(OBSERVED ^ REFERENCE), observed_newtime_row=15,
        labels_can_match_while_full_words_differ=True,
        physical_register_or_all_four_slots_observed=False, final_ram_or_fdt_verified=False)


def gnu(sboot, report):
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for pc, template in TEMPLATES:
        output = subprocess.check_output(command+['-D','-b','binary','-m','aarch64',
            f'--start-address={pc}',f'--stop-address={pc+4*len(template.split())}',
            str(Path(sboot).resolve())],text=True)
        lines.update(parse_lines(output))
    expected = {pc+i*4:int(w,16) for pc,t in TEMPLATES for i,w in enumerate(t.split())}
    if set(lines) != set(expected):
        raise ValueError('GNU logging coverage differs')
    targets = 0
    for pc,(raw,op,args) in lines.items():
        if raw != expected[pc] or op in ('.inst','udf'):
            raise ValueError('GNU logging instruction differs')
        kind,target = flow(raw,pc)
        if kind in ('b','bl','conditional'):
            if direct_target(op,args) != target:
                raise ValueError('GNU logging branch differs')
            targets += 1
    selected = {0x1fe70:('ldr','x0, [x20, #752]'),0x1fe80:('lsr','x0, x0, #32'),
        0x1febc:('ldr','x0, [x20, #752]'),0x11b804:('ldr','w1, [x1]'),
        0x11b808:('ldr','w0, [x0]'),0x11b814:('str','x0, [x2, #3744]'),
        0x11b868:('ubfx','x1, x1, #8, #8'),0x11b87c:('cmp','w1, #0x1'),
        0x11b8ec:('ubfx','x0, x1, #40, #8'),0x11b8f0:('ubfx','x1, x2, #32, #8'),
        0x11b8f4:('orr','w1, w1, w0, lsl #8'),0x11b8f8:('cmp','w1, #0x8'),
        0x11b714:('lsr','x0, x1, #20'),0x11b720:('scvtf','d0, x0'),
        0x147d7c:('bl','0x11b860'),0x147d90:('bl','0x11b8d8'),0x147da4:('bl','0x11b6f0')}
    if any(lines[pc][1:] != value for pc,value in selected.items()):
        raise ValueError('GNU logging operand differs')
    digest=hashlib.sha256(b''.join(struct.pack('<II',pc,expected[pc]) for pc in sorted(expected))).hexdigest()
    if digest != report['instruction_index_sha256']:
        raise ValueError('GNU logging index differs')
    return dict(mode='GNU_dram_logging', sboot_sha256=report['sboot_sha256'],
        instruction_index_sha256=digest,words_matched=len(lines),relative_targets_matched=targets,
        selected_operands_matched=len(selected),strings_checked_by_hash_bound_reader=len(STRINGS),
        scaling_literal_checked_by_hash_bound_reader=True,
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot');parser.add_argument('reference_driver');parser.add_argument('--gnu',action='store_true')
    args=parser.parse_args()
    try:
        result=inspect(args.sboot,args.reference_driver)
        if args.gnu:result=gnu(args.sboot,result)
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'inspect_dram_logging_hzc2: {exc}\n')
    print(json.dumps(result,indent=2))
