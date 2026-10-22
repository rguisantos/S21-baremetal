#!/usr/bin/env python3
"""Read-only, hash-bound evidence report for the received HZC2 sboot.

Accepts a decompressed sboot.bin, never extracts or modifies firmware. Region
labels are candidates from the cited detector, not signature verification.
No third-party packages are required. See docs/sboot-layout-hzc2.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

SIZE = 0x400000
SHA256 = 'a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91'
REGIONS = (
    ('fwbl1', 0, 0x3000),
    ('epbl', 0x3000, 0x16000),
    ('bl2', 0x16000, 0xec000),
    ('lk', 0xec000, 0x36c000),
    ('el3_mon', 0x36c000, 0x3ac000),
    ('tail_unclassified', 0x3ac000, SIZE),
)


def offsets(data, needle):
    found = []
    pos = 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            return found
        found.append(hex(pos))
        pos += 1


def bl_target(word, off):
    if word >> 26 != 0b100101:
        raise ValueError(f'not an A64 BL instruction at {off:#x}')
    immediate = word & 0x3ffffff
    if immediate & 0x2000000:
        immediate -= 0x4000000
    return off + immediate * 4


def inspect(path):
    with Path(path).open('rb') as stream:
        data = stream.read(SIZE + 1)
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != SIZE or digest != SHA256:
        raise ValueError('unsupported image: requires the exact 4 MiB HZC2 sboot '
                         f'(received {len(data)} bytes, sha256 {digest})')

    u32 = lambda off: struct.unpack_from('<I', data, off)[0]
    u64 = lambda off: struct.unpack_from('<Q', data, off)[0]
    # A64 BL uses a signed imm26 scaled by four, relative to the instruction.
    call_offset = 0xec000
    helper = bl_target(u32(call_offset), call_offset)

    bl1_end = u32(0) * 512
    epbl_end = bl1_end + u32(bl1_end) * 512
    footer_offset = epbl_end - 0x210
    footer = data[footer_offset:footer_offset + 12]
    strings = ['Samsung LK Boot', 'load_boot_images', 'configure_dtb',
               'Starting kernel...', 'JUMP2K', 'bootargs_init', 'set_bootargs',
               'EPBL Self Decryption success', 'EPBL Self Decryption fail']
    words = (0xf9b4c, 0xf9b50, 0xf9b58, 0xf9b5c, 0xf9b78, 0xf9b7c,
             0xf9b8c, 0xf9b90, 0xf9bb8, 0xf9bbc, 0x1efcd0)
    spsr_values = []
    for off in (0xf9b78, 0xf9b8c):
        movz = u32(off)
        if movz & 0xff800000 != 0xd2800000 or movz & 31 != 4:
            raise ValueError('unexpected instruction at SPSR value producer')
        spsr_values.append(((movz >> 5) & 0xffff) << (((movz >> 21) & 3) * 16))

    return {
        'sha256': digest, 'size': len(data), 'mode': 'static_read_only',
        'region_status': 'candidate labels; no signature verification',
        'regions': [dict(label=name, start=hex(start), end_exclusive=hex(end),
                         size=end-start, sha256=hashlib.sha256(data[start:end]).hexdigest())
                    for name, start, end in REGIONS],
        'header_bounds': dict(bl1_end=hex(bl1_end), epbl_end=hex(epbl_end)),
        'footer': dict(epbl_offset=hex(footer_offset), prefix_hex=footer.hex(),
                       little_endian_words=list(struct.unpack('<3I', footer)),
                       exact_matches=offsets(data, footer),
                       lk_end_has_same_prefix=data[0x36c000-0x210:0x36c000-0x210+12] == footer),
        'string_byte_matches': {s: offsets(data, s.encode()) for s in strings},
        'lk_entry': dict(file_offset=hex(call_offset), bl_target_file_offset=hex(helper),
                         target_relative_to_lk=hex(helper-call_offset),
                         spsr_values=[hex(v) for v in spsr_values],
                         target_modes=[v & 15 for v in spsr_values],
                         mode_5_meaning='EL1h; applies to the decoded entry helper'),
        'instruction_words_le': {hex(off): f'{u32(off):08x}' for off in words},
        'negative_bl_example': dict(instruction_offset='0x1efcd0',
                                    target_offset=hex(bl_target(u32(0x1efcd0), 0x1efcd0))),
        'entry_literals': {hex(off): hex(u64(off)) for off in (0xec030, 0xec038, 0xec040)},
        'late_handoff': dict(
            cache_prepare_call=hex(bl_target(u32(0xfbddc), 0xfbddc)),
            post_cache_calls={hex(off): hex(bl_target(u32(off), off))
                              for off in (0xfbde4, 0xfbdf0)},
            explicit_irq_mask_word=f'{u32(0xfbdd4):08x}',
            final_jump_word=f'{u32(0xfbe14):08x}'),
        'console_static_chain': dict(
            assumed_lk_runtime_delta='0xe7f14000',
            stdout_pointer=hex(u64(0x31fff0)),
            object_ops_pointer=hex(u64(0x3218b8)),
            ops_write_pointer=hex(u64(0x2906f8)),
            byte_output_call=hex(bl_target(u32(0x20c510), 0x20c510)),
            instruction_words={hex(off): f'{u32(off):08x}' for off in
                               (0xef3f4, 0xef420, 0xef4cc, 0xef4d0,
                                0xef4d8, 0xef4e0)},
            status='Static path selects 0x10540000; execution and pin routing unobserved'),
        'jig_gate': dict(
            status_helper='0x18b560',
            referenced_name_offsets={'ifconn_get_jig_status': '0x25eb28',
                                     'ifconn_is_muic_jig_device': '0x25ebe8'},
            muic_table_offset='0x25ead4',
            muic_table_hex=data[0x25ead4:0x25eada].hex(),
            muic_adc_targets={hex(adc): hex(0x18b6b8 + struct.unpack('b', data[0x25ead4+adc-24:0x25ead4+adc-23])[0]*4)
                              for adc in range(24, 30)},
            suppression_call_target=hex(bl_target(u32(0xedba4), 0xedba4)),
            limit='Static dispatch and table only; no device ADC or routing observation'),
        'memory_log_callback': dict(
            callback_pointer=hex(u64(0x2ef148)),
            callback_file_offset=hex(u64(0x2ef148)-0xe7f14000),
            registration_call_target=hex(bl_target(u32(0xff948), 0xff948)),
            copy_call_target=hex(bl_target(u32(0xff738), 0xff738)),
            tail_zero_call_target=hex(bl_target(u32(0xff764), 0xff764)),
            instruction_words={hex(off): f'{u32(off):08x}' for off in
                               (0xff6c8, 0xff6d4, 0xff6e8, 0xff708,
                                0xff728, 0xff748, 0xff778, 0xff77c)},
            status='Matches source debug_snapshot/log_kernel; no runtime dump acquired'),
        'kernel_copy_chain': dict(
            context_setup_words={hex(off): f'{u32(off):08x}' for off in
                                 (0xfba04, 0xfba08, 0xfba10, 0xfba18)},
            dispatch_calls={hex(off): hex(bl_target(u32(off), off))
                            for off in (0xfbba0, 0xfbbb0)},
            copy_calls={hex(off): hex(bl_target(u32(off), off))
                        for off in (0x12e420, 0x12e88c)},
            copy_setup_words={hex(off): f'{u32(off):08x}' for off in
                              (0x12e068, 0x12e070, 0x12e418, 0x12e41c,
                               0x12e560, 0x12e568, 0x12e880, 0x12e884, 0x12e888)},
            status='Static source/destination chain; no execution of Samsung LK'),
        'kernel_v3_tail': dict(
            calls={hex(off): hex(bl_target(u32(off), off)) for off in
                   (0x12e7f8, 0x12e848, 0x12e850, 0x12e860, 0x151b18)},
            instruction_words={hex(off): f'{u32(off):08x}' for off in
                               (0xfba0c, 0x12e56c, 0x12e710, 0x12e728,
                                0x12e754, 0x12e770, 0x12e79c, 0x12e7a8,
                                0x12e7ac, 0x12e7b0, 0x12e7b8, 0x12e7c0,
                                0x12e7d8, 0x12e7f0, 0x12e820, 0x12e828,
                                0x12e830, 0x12e83c, 0x12e840, 0x12e84c,
                                0x149188, 0x14918c, 0x149190,
                                0x150320, 0x150324, 0x150328, 0x15032c)},
            limit='Copy/registration evidence only; later processing and final FDT unverified'),
        'dtb_pipeline': dict(
            calls={hex(off): hex(bl_target(u32(off), off)) for off in
                   (0x149214, 0x149444, 0x149334, 0x1490c4,
                    0x149084, 0x1490c0, 0x14935c, 0x149384,
                    0x1493a0, 0x1493d0, 0x1493ec, 0xfb4fc)},
            instruction_words={hex(off): f'{u32(off):08x}' for off in
                               (0x14918c, 0x149074, 0x1490d4, 0x148d80,
                                0x148d8c, 0x148d98, 0x148ddc, 0x148df0,
                                0x148df8, 0x148e04, 0x148e0c, 0x148d60,
                                0x149374, 0x14937c, 0x149380, 0x1493ac,
                                0x1493e4)},
            merge_result_destination='0x8b080000', dpm_buffer_candidate='0xf0005000',
            selector='First inclusive range; REV limits when REV(custom1)<=0xff, raw LE otherwise',
            limit='Conditional static branches; revision, UFDT output and final FDT not observed'),
        'dynamic_fdt_writes': dict(
            calls={hex(off): hex(bl_target(u32(off), off)) for off in
                   (0xfb42c, 0xfb49c, 0xfb4a4, 0xfb4d8, 0xfad84, 0x147310,
                    0x1487b8, 0x1487d8, 0x148afc, 0x148b1c, 0x148b38,
                    0x148b60, 0x148bcc, 0x148bf4, 0x148c2c)},
            instruction_words={hex(off): f'{u32(off):08x}' for off in
                               (0xfb408, 0xfb4a8, 0xfb4ac, 0xfb4b4,
                                0x12e9b8, 0x12e9bc, 0x12e9c8, 0x12e9cc,
                                0xf14ac, 0xf14b4, 0x148ae8, 0x148aec,
                                0x148b18, 0x148b20, 0x148b3c, 0x148b48,
                                0x148b58, 0x1486e8, 0x14870c,
                                0x11b764, 0x11b76c, 0x11b770)},
            string_literals={hex(off): data[off:data.index(0, off)].decode('ascii')
                             for off in (0x216468, 0x216578, 0x216580, 0x216600,
                                         0x22cb40, 0x22cb50, 0x23c688,
                                         0x23c690, 0x23c6a0, 0x23c6b0, 0x23c6c0,
                                         0x23bca8, 0x23bcc8)},
            limit='Conditional writers, not observed FDT properties or a complete memory map'),
        'uart_pinmux_audit': dict(
            lk_routine_offset='0xef3e0',
            instruction_words={hex(off): f'{u32(off):08x}' for off in
                               (0xef3e0, 0xef3e8, 0xef3ec, 0xef410, 0xef418, 0xef41c)},
            direct_register_address='0x10430080',
            preserve_mask='0x00ffffff', inserted_value='0x33000000',
            literal_gpg0_matches=offsets(data, struct.pack('<I', 0x10430120)),
            limit='Literal matches are raw bytes; no executed reference or pin routing proof'),
        'early_uart': dict(
            region='candidate BL2; runtime execution unobserved',
            pinmux_offset='0x1d46c',
            pinmux_instruction_words={hex(off): f'{u32(off):08x}' for off in
                                     range(0x1d46c, 0x1d488, 4)},
            direct_calls={hex(off): hex(bl_target(u32(off), off))
                          for off in (0x17e4c, 0x1d5ac, 0x1d5c0)},
            argument_words={hex(off): f'{u32(off):08x}' for off in
                            (0x1d5b0, 0x1d5b4, 0x1d5b8, 0x1d5bc)},
            scale_constant_offset='0x1d428',
            scale_constant=struct.unpack_from('<d', data, 0x1d428)[0],
            limit='Compatible source pinmux, not proof of final clock, UART access or use of the separate data word'),
        'uart_clock_stages': dict(
            primary_mux_table_offset='0x30670',
            primary_mux_bytes=list(data[0x30670:0x30670+11]),
            primary_div_table_offset='0x30680',
            primary_div_u16=list(struct.unpack_from('<11H', data, 0x30680)),
            second_mux_table_offset='0x369c8',
            second_mux_bytes=list(data[0x369c8:0x369c8+11]),
            second_div_table_offset='0x369d8',
            second_div_u16=list(struct.unpack_from('<11H', data, 0x369d8)),
            calls={hex(off): hex(bl_target(u32(off), off)) for off in
                   (0x160bc, 0x160c0, 0x18020, 0x178f8, 0x17674, 0x17684,
                    0x36944, 0x36738, 0x36748)},
            wrapper_argument_words={hex(off): f'{u32(off):08x}' for off in
                                    (0x1d4b4, 0x1d4b8, 0x1d4bc, 0x1d4c0)},
            wrapper_tail_branch_word=f'{u32(0x1d4c4):08x}',
            lk_divisor_word=f'{u32(0xef474):08x}',
            limit='Static nominal configuration; not a measured frequency or final handoff state'),
        'uart_upstream_clock': dict(
            top_divisor_store_offset='0x1699c',
            top_mux_store_offset='0x169a8',
            instruction_words={hex(off): f'{u32(off):08x}' for off in
                               (0x16988, 0x1698c, 0x16990, 0x16994,
                                0x1699c, 0x169a4, 0x169a8,
                                0x17688, 0x1768c, 0x17694, 0x17698)},
            duplicate_top_words={hex(off): f'{u32(off):08x}' for off in
                                 (0x36524, 0x36528, 0x3652c, 0x36530,
                                  0x36538, 0x36540, 0x36544)},
            limit='Source maps TOP mux value 2 to PLL_SHARED2_D2; QCH/gate handoff state unobserved'),
        'limits': ['No runtime EL observation at the kernel jump',
                   'No final FDT, RAM allocation, PSCI conduit or UART initialization proof',
                   'Not an image packer, flash tool or generic sboot parser'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path, help='decompressed HZC2 sboot.bin')
    args = parser.parse_args()
    try:
        report = inspect(args.sboot)
    except (OSError, ValueError) as exc:
        print(f'inspect_sboot_hzc2: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
