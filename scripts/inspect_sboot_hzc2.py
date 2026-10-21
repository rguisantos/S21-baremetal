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
