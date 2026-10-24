#!/usr/bin/env python3
"""Hash-bound HZC2 ACPM publisher and BL2 consumer; no firmware execution.

The public DTS names AP resources. Core-local/AP aliases and runtime
preservation remain hypotheses, even when the selected constants agree.
"""
import argparse
import json
import re
import struct

from inspect_bl2_geometry_query import adrp_add
from inspect_bl2_geometry_record import expect, wide64
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_descriptor_provenance import copy_loop
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import signed
from inspect_monitor_preparation import word
from inspect_sboot_hzc2 import bl_target

DTS_PATH = 'arch/arm64/boot/dts/exynos/exynos2100.dts'
DTS_COMMIT = '756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0'
DTS_ID = (501932, 'a92a3c3a2dcba40460d51343a23590d5f48c0ad3330ba33864e77aa446859f4e')
A64 = (
    (0x161b0, '58000c40 58000c61 58000c82 a8c11003 a8811043 eb01001f 54ffffab d5033f9f d5033fdf d65f03c0'),
    (0x16228, '580008c0 58000a21 58000902 a8c11003 a8811043 eb01001f 54ffffab d5033f9f d5033fdf d65f03c0 58000900 58000921 58000942 a8c11003 a8811043 eb01001f 54ffffab d5033f9f d5033fdf d65f03c0'),
    (0x17974, 'a9be53f3 d2802114 900000d3 a9017bf5 940012eb f2a2b214 d2802000 d2802081 f2a2b200 f2a2b201 b900001f b900003f 52800801 b900029f b900001f d2808680 f2a2b040 b9000001 d2a34940 d286c401 f2a2b0c1 b900001f b9400020 32000000 b9000020 91354260 940016e1 aa1303e2 b9400280 d2802115 f2a2b215 34ffffa0 d00000d3 b94002a0 91290273 52920001 72a04061 0b010001 f9000661 91400421 911f9021 f9001661 97ffffce f9400660 f9000a60 91400400 911f9000 f9000e60 91354040 91001400 940016c9 9400057e f9401660 b9403261 b9001001 b90002bf'),
    (0x17eb0, '97fffeb1'),
    (0x17fb8, '91290280 b00000c4 91148083 910b0063 f9400401 91400422 91400c21 91300021 f9000c01 d2813401 91200042 f2a2b0c1 f9029082'),
)
THUMB = (
    (0x38260, 'f000 fa04 4903 6008 4803 f380 8808 f000 fd0f'),
    (0x38c9a, 'f647 1a60 b5e0 f2c0 0a00 f248 0600 4653 f2c0 0600 b087 0030 685b 4798'),
    (0x38e4e, 'f248 0000 4653 f2c0 0000 681b 4798'),
    (0x38e6a, '6973 b343 2400 2500 f240 0920 464a 6833 191b 5c9a b1d2 685b 4698 6a3b 4798 4643 b113 6833 1918 47c0'),
    (0x38eb6, '6973 3501 3430 429d d3da'),
    (0x3998c, '6803 b510 f646 01d5 001c 2200 34c0 f2c0 0100 605a 625a 6061 6262 4926 3201 4311 6359 4925 6559 4925 3490 4311 6061 4924 6261'),
    (0x39b48, 'f247 1350 f2c0 0300 b570 6003 f247 33c0 220d f2c0 0300 6083 2100 2314 6042 6142 3202 6182 3201 0004 60c3 6101 61c3 6283'),
    (0x56e00, 'b570 4b1c 60c3 4b1c 6018 2200 216d 481b f000 f850 2200 4b1a 701a f003 fddf f000 f85f'),
    (0x56ee0, 'b5f0 465f 4656 464d 4644 b4f0 b083 4b3a 4a3a 601a 001a 6813 2b00 d1fc 4c37 4b38 601c f641 0300 18e2 4b36 601a'),
    (0x3f558, 'f24a 6200 f2c0 0203 6811 f24a 6204 f2c0 0203 6810 f240 1210 f2c6 0200 2500 4291 d000 e62c 2208 f2c0 0201 0035 4290 d000 e625'),
)
LITERALS = {0x38274: 0x7f4c, 0x38278: 0xf800, 0x3b960: 0x598d,
            0x3b964: 0x5b49, 0x39a40: 0xf800, 0x39a48: 0x29600,
            0x3b2a0: 7, 0x3b2c0: 1, 0x56fd8: 0xa5900108,
            0x56fdc: 0x38e00, 0x56fe0: 0x2fbf4, 0x56fe4: 0x2fd98}


def half(data, pc):
    if pc < 0 or pc % 2 or pc+2 > len(data):
        raise ValueError('unaligned/outside Thumb halfword')
    return struct.unpack_from('<H', data, pc)[0]


def thumb_wide(data, pc, top=False):
    a, b = half(data, pc), half(data, pc+2)
    if a & 0xfbf0 != (0xf2c0 if top else 0xf240) or b & 0x8000:
        raise ValueError('expected Thumb MOVW/MOVT')
    return (b >> 8) & 15, ((a & 15) << 12) | (((a >> 10) & 1) << 11) | (((b >> 12) & 7) << 8) | (b & 255)


def thumb_pair(data, pc, register):
    lo, hi = thumb_wide(data, pc), thumb_wide(data, pc+4, True)
    if lo[0] != register or hi[0] != register:
        raise ValueError('Thumb wide register mismatch')
    return lo[1] | hi[1] << 16


def thumb_literal(data, pc, register):
    h = half(data, pc)
    if h & 0xf800 != 0x4800 or (h >> 8) & 7 != register:
        raise ValueError('expected Thumb LDR literal T1')
    at = ((pc+4) & ~3) + (h & 255)*4
    return at, word(data, at)


def thumb_target(data, pc):
    a = half(data, pc)
    if a & 0xf800 == 0xf000:
        b = half(data, pc+2)
        if b & 0xd000 != 0xd000:
            return None
        s = (a >> 10) & 1
        imm = s << 24 | (1 ^ ((b >> 13) & 1) ^ s) << 23 | (1 ^ ((b >> 11) & 1) ^ s) << 22 | (a & 1023) << 12 | (b & 2047) << 1
        return pc+4+signed(imm, 25)
    if a & 0xf000 == 0xd000 and (a >> 8) & 15 < 14:
        return pc+4+signed(a & 255, 8)*2
    if a & 0xf800 == 0xe000:
        return pc+4+signed(a & 2047, 11)*2
    if a & 0xf500 == 0xb100:
        return pc+4+((a >> 9) & 1)*64+((a >> 3) & 31)*2
    return None


def inspect(sboot, dts):
    data = read_exact(sboot, *IMAGES['sboot'])
    source = read_exact(dts, *DTS_ID).decode('utf-8')
    node = re.search(r'\n\tacpm_ipc \{(.*?)\n\t\};', source, re.S)
    if node is None:
        raise ValueError('ACPM DTS node missing')
    for text in ('compatible = "samsung,exynos-acpm-ipc";',
                 'reg = <0x00 0x15900000 0x1000 0x00 0x2039000 0x41000>;',
                 'initdata-base = <0x8000>;'):
        if text not in node[1]:
            raise ValueError('ACPM DTS resource changed')
    for pc, template in A64:
        expect(data, pc, template)
    for pc, template in THUMB:
        raw = b''.join(struct.pack('<H', int(h, 16)) for h in template.split())
        if data[pc:pc+len(raw)] != raw:
            raise ValueError(f'Thumb witness changed at {pc:#x}')
    if any(word(data, pc) != v for pc, v in LITERALS.items()):
        raise ValueError('selected literal changed')
    copies = [copy_loop(data, pc, 16) for pc in (0x16228, 0x16250)]
    mappings = []
    for row in copies:
        start, end = (int(v, 16) for v in row['source'])
        dst = int(row['destination'][0], 16)
        mappings.append(dict(copy=row['start'], file_interval=[hex(start-NOMINAL_DELTA), hex(end-NOMINAL_DELTA)],
                             ap_destination=row['destination'],
                             core_interval_if_sram_alias=[hex(dst-0x2039000), hex(dst-0x2039000+end-start)]))
    if thumb_target(data, 0x56e1e) != 0x56ee0 or bl_target(word(data, 0x17eb0), 0x17eb0) != 0x17974:
        raise ValueError('selected direct call changed')
    for pc, reg, at in ((0x56eee, 3, 0x56fd8), (0x56ef0, 2, 0x56fdc),
                        (0x399b2, 1, 0x39a48)):
        if thumb_literal(data, pc, reg)[0] != at:
            raise ValueError('selected literal xref changed')
    record = thumb_pair(data, 0x3f558, 2)
    high_address = thumb_pair(data, 0x3f562, 2)
    signature_low = thumb_pair(data, 0x3f56c, 2)
    signature_high = (half(data, 0x3f57c) & 255) | thumb_wide(data, 0x3f57e, True)[1] << 16
    if (record, high_address, signature_low, signature_high) != (0x3a600, 0x3a604, 0x60000110, 0x10008):
        raise ValueError('selected DRAM comparison changed')
    register = wide64(data, (0x179e8, 0x179ec), 21)
    config = adrp_add(data, 0x179f4, 0x179fc)
    base = ((word(data, 0x17a00) >> 5) & 65535) | (((word(data, 0x17a04) >> 5) & 65535) << 16)
    extra = (((word(data, 0x17fcc) >> 10) & 4095) << 12) + ((word(data, 0x17fe0) >> 10) & 4095)
    published = LITERALS[0x56fdc]
    destination = ((published+base) & 0xffffffff)+extra
    if (register, config, base, extra, destination) != (0x15900108, 0x31a40, 0x2039000, 0x1800, 0x2073600):
        raise ValueError('conditional NEWTIME destination changed')
    return dict(mode='static_acpm_handshake_candidate', input=dict(size=len(data), sha256=IMAGES['sboot'][1]),
        public_dts=dict(repository='xfwdrev/android_kernel_samsung_ex2100', commit=DTS_COMMIT,
                        path=DTS_PATH, size=DTS_ID[0], sha256=DTS_ID[1],
                        ipc_resource=['0x15900000', '0x15901000'], sram_resource=['0x2039000', '0x207a000'],
                        initdata_offset='0x8000', runtime_match_verified=False),
        copy_mappings=mappings,
        nominal_thumb_entry=dict(vector_file='0x38000', initial_sp=hex(word(data, 0x38000)),
                                 reset_thumb_pointer=hex(word(data, 0x38004)), reset_file='0x38260', main_file='0x38c90'),
        selected_initializer=dict(hardware_ops_file='0x3b960', initdata_core='0x8000',
            descriptors_core='0x7150', descriptor_stride=48, selected_index=7,
            initial_descriptor_flag=1, configured_callback_core='0x29601', nominal_callback_file='0x56e00',
            indirect_call='0x38e90', publisher_call='0x56e1e', publisher_file='0x56ee0',
            selected_fields_and_call_preserved_verified=False),
        publisher=dict(store='0x56ef2', core_register=hex(LITERALS[0x56fd8]), width_bits=32,
            value=hex(published), poll='0x56ef6', back_edge='0x56efa', exits_when='read_u32_is_zero',
            next_stores=[dict(pc='0x56f00', core_cell='0x2fbf4', value='0x38e00'),
                         dict(pc='0x56f0a', core_cell='0x2fd98', value='0x3a600')]),
        bl2_consumer=dict(call='0x17eb0', function='0x17974', ap_register=hex(register),
            initial_clear='0x179a8', poll='0x179e4', back_edge='0x179f0', exits_when='read_u32_is_nonzero',
            final_read='0x179f8', poll_and_final_sample_equal_verified=False,
            config_store='0x17a0c', config_cell=hex(config+8), final_clear='0x17a50',
            newtime_pointer_store='0x17fe8', newtime_pointer_cell='0x30520',
            conditional_destination=hex(destination), publication_read_and_preservation_verified=False),
        corroborating_consumer=dict(file='0x3f558', core_low_address=hex(record), core_high_address=hex(high_address),
            ap_address_if_sram_alias=hex(base+record), compare_u64=hex(signature_high << 32 | signature_low),
            loaded_value_observed=False, selected_sample_atomic_verified=False),
        conditions=dict(core_0xa5900108_aliases_ap_0x15900108_verified=False,
                        core_zero_aliases_ap_0x02039000_verified=False,
                        firmware_executed=False, dram_record_value_observed=False,
                        newtime_frame_and_pointer_preserved_verified=False, final_ram_or_fdt_verified=False),
        limits=['Static matching publication and consumer, not a completed hardware handshake',
                'Selected initialization and callbacks require placement, execution and preservation',
                'No complete writer census, boot path, final memory map or physical observation'],
        a64_words={hex(pc): f'{word(data, pc):08x}' for a, t in A64 for pc in range(a, a+4*len(t.split()), 4)},
        thumb_halfwords={hex(pc): f'{half(data, pc):04x}' for a, t in THUMB for pc in range(a, a+2*len(t.split()), 2)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    parser.add_argument('dts', help='pinned exynos2100.dts from xfwdrev/rebased-11')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot, args.dts)
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        parser.exit(2, f'inspect_acpm_handshake_hzc2: {exc}\n')
    print(json.dumps(result, indent=2))
