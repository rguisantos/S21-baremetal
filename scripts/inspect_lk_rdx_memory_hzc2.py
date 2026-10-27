#!/usr/bin/env python3
"""Static HZC2 RDX memory provenance; never executes firmware or contacts a device."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_lk_dump_hzc2 import DELTA, PROBE_ENVELOPE, encoded_end

UNIT = 0x20000000
LOW = 0x80000000
HIGH = 0x880000000
SOURCE = 0xcd31d0
MODEL_LIMIT = 64  # Host output budget, not a firmware bound or source-array capacity.
RANGES = (
    (0xee370, 0xee478), (0xee660, 0xee674), (0xee980, 0xeea18),
    (0xfa7b0, 0xfa8cc), (0xfa948, 0xfaa28),
    (0x11b6c0, 0x11b74c), (0x11b758, 0x11b794), (0x11b798, 0x11b7e8),
    (0x1472e8, 0x147314), (0x147e88, 0x147e94),
    (0x148020, 0x14802c), (0x148030, 0x148040),
    (0x15e0e8, 0x15e16c), (0x15e180, 0x15e1b8),
    (0x15e210, 0x15e328), (0x15e578, 0x15e594), (0x15e6cc, 0x15e7d0),
    (0x111f28, 0x111f94), (0x116e88, 0x116e9c), (0x17b8d0, 0x17b8e8),
    (0x116f70, 0x116f88), (0x117260, 0x117298),
    (0x1177ec, 0x117818), (0x117844, 0x1178f0),
    (0x117990, 0x117a14), (0x117a68, 0x117ae4), (0x117b00, 0x117b14),
    (0x112338, 0x112414), (0x113a60, 0x113a6c),
    (0x18c4c8, 0x18c504), (0x18c508, 0x18c534),
    (0x18d1b0, 0x18d1bc), (0x18d210, 0x18d28c),
    (0x114fe0, 0x115008), (0x114c18, 0x114c50),
)
SELECTED = {
    0xee380: ('bl', '0x147e88'), 0xee388: ('mov', 'x19, x0'),
    0xee38c: ('bl', '0x11b6c0'), 0xee398: ('mov', 'w20, w0'),
    0xee3c8: ('mov', 'x3, #0x20000000'),
    0xee3cc: ('mov', 'x0, #0x80000000'),
    0xee3d0: ('cmp', 'w20, #0x1'), 0xee3d4: ('mov', 'x4, #0x80000000'),
    0xee3d8: ('stp', 'x0, x3, [x19, #40]'),
    0xee3dc: ('movk', 'x4, #0x8, lsl #32'),
    0xee3e0: ('b.le', '0xee428'), 0xee3e4: ('add', 'x0, x19, #0x28'),
    0xee3f0: ('ldr', 'x2, [x0]'), 0xee3fc: ('add', 'x2, x2, x3'),
    0xee400: ('stp', 'x2, x3, [x0, #16]'),
    0xee404: ('add', 'x0, x0, #0x10'),
    0xee40c: ('cmp', 'w1, #0x4'), 0xee41c: ('stp', 'x4, x3, [x19, #104]'),
    0xee66c: ('bl', '0xee370'), 0xfa9a0: ('bl', '0xee660'),
    0xfa99c: ('bl', '0xfa7b0'), 0xfa9a8: ('mov', 'w1, #0x20000'),
    0xfa9b0: ('bl', '0xfa7b0'), 0xfa9fc: ('mov', 'w1, #0x60000'),
    0xfaa04: ('bl', '0xfa7b0'), 0xfa858: ('ldr', 'x1, [x22, #8]'),
    0xfa85c: ('blr', 'x1'),
    0x147e8c: ('add', 'x0, x0, #0x1a8'),
    0x148034: ('add', 'x0, x0, #0x1a8'), 0x148038: ('add', 'x0, x0, #0x28'),
    0x11b6c4: ('ldr', 'w0, [x2, #3752]'),
    0x11b6d8: ('ldr', 'x1, [x1]'), 0x11b6e0: ('lsr', 'x1, x1, #29'),
    0x11b6e4: ('str', 'w1, [x2, #3752]'),
    0x11b71c: ('str', 'w1, [x2, #3752]'),
    0x11b77c: ('str', 'w2, [x1, #3752]'),
    0x11b79c: ('lsl', 'x0, x0, #30'),
    0x11b7ac: ('cmp', 'x0, x2'), 0x11b7c4: ('str', 'w2, [x1, #3752]'),
    0x11b7e4: ('str', 'w2, [x1, #3752]'),
    0x14730c: ('and', 'x0, x21, #0xf'), 0x147310: ('bl', '0x11b798'),
    0x15e100: ('bl', '0x148030'), 0x15e108: ('bl', '0x11b6c0'),
    0x15e128: ('ldr', 'x1, [x20, #24]'),
    0x15e130: ('ldr', 'x3, [x20, #8]'),
    0x15e134: ('add', 'w21, w21, #0x2'),
    0x15e138: ('ldr', 'x2, [x20], #32'),
    0x15e140: ('add', 'x3, x3, x1'), 0x15e148: ('bl', '0x12df68'),
    0x15e150: ('b.gt', '0x15e128'),
    0x15e190: ('bl', '0xee370'), 0x15e590: ('bl', '0x15e180'),
    0x15e314: ('cmp', 'w24, #0x5'), 0x15e320: ('bl', '0x15e0e8'),
    0x15e75c: ('bl', '0x15e0e8'), 0x15e774: ('bl', '0x116e88'),
    0xee980: ('bl', '0x15e7d0'), 0xeea14: ('bl', '0x15e210'),
    0x111f70: ('bl', '0x116f18'),
    0x116f78: ('tbz', 'w0, #17, 0x117260'),
    0x117264: ('tbz', 'w0, #16, 0x116f38'),
    0x1177f4: ('cmp', 'x23, #0x1'), 0x1177fc: ('cmp', 'x23, #0x2'),
    0x117804: ('cmp', 'x23, #0x3'),
    0x117a0c: ('str', 'x3, [x0, #2208]'),
    0x117b0c: ('str', 'x3, [x0, #2248]'),
    0x1178a4: ('mov', 'x2, #0x80000'), 0x1178c4: ('bl', '0x112400'),
    0x1123c4: ('bl', '0x18c4c8'), 0x1123cc: ('bl', '0x18c508'),
    0x113a64: ('add', 'x0, x0, #0x530'), 0x113a68: ('b', '0x18d1b0'),
    0x18d1b4: ('str', 'x0, [x1, #224]'),
    0x18d25c: ('ldr', 'x1, [x19, #104]'),
    0x18d278: ('blr', 'x1'), 0x18d27c: ('str', 'x0, [x19, #96]'),
    0x18c4d4: ('ldr', 'x5, [x0, #104]'),
    0x18c4dc: ('ldr', 'x5, [x5, #56]'), 0x18c4f8: ('br', 'x5'),
    0x18c51c: ('ldr', 'x2, [x2, #72]'), 0x18c528: ('br', 'x2'),
    0x114ff4: ('mov', 'w3, w4'), 0x115004: ('b', '0x114eb8'),
    0x114c38: ('bl', '0x114b10'),
}


def units(value):
    if type(value) is not int or not 0 <= value <= MODEL_LIMIT:
        raise ValueError('host model requires 0..64 supplied units')
    return value


def producer_banks(count):
    """Equations of ee370's stores, not a memory read or firmware execution.

    Entry zero is written even for count zero. No zero-filled tail is invented.
    """
    count = units(count)
    return [(LOW + i * UNIT if i < 4 else HIGH + (i-4) * UNIT, UNIT)
            for i in range(max(1, count))]


def append_pairs(banks, count):
    """Model the two-size sum. Missing odd tail and noncontiguity stay visible."""
    count = units(count)
    if len(banks) < count:
        raise ValueError('not enough supplied source entries')
    for base, size in banks:
        if any(type(x) is not int or not 0 <= x < 1 << 64 for x in (base, size)):
            raise ValueError('source fields must be u64')
    result = []
    for i in range(0, count, 2):
        base, size = banks[i]
        second = banks[i+1] if i+1 < len(banks) else None
        size_sum = (size + second[1]) % (1 << 64) if second is not None else None
        end = encoded_end(base, size_sum) if size_sum is not None else None
        result.append(dict(first_source_index=i, start=hex(base),
            size=size_sum, inclusive_end=hex(end) if end is not None else None,
            second_size_known=second is not None,
            source_pair_contiguous=(base + size == second[0]) if second is not None else None,
            probe_envelope_contained=(base <= PROBE_ENVELOPE[0] and PROBE_ENVELOPE[1] <= base+size_sum)
                if size_sum is not None and 0 < size_sum <= (1 << 64)-base else None))
    return result


def pointers(data, table=0x305530, delta=DELTA):
    result = []
    for slot, target in ((0, 0x116960), (0x38, 0x114fe0), (0x48, 0x114c18), (0x68, 0x113958)):
        if table < 0 or table+slot+8 > len(data):
            raise ValueError('truncated operation table')
        raw, = struct.unpack_from('<Q', data, table+slot)
        if raw != delta+target:
            raise ValueError('operation pointer differs')
        result.append(dict(location=hex(table+slot), slot=hex(slot),
                           initial_pointer=hex(raw), nominal_file_target=hex(target)))
    return result


def init_records(data):
    result = []
    for off, level, function, name in ((0x29b148, 0x20000, 0x113a60, 'dwc3_gadget_probe'),
                                      (0x29b178, 0x60002, 0x18d210, 'usb_dev_gadget')):
        actual_level, flags, pointer, name_pointer = struct.unpack_from('<IIQQ', data, off)
        if (actual_level, flags, pointer) != (level, 1, DELTA+function):
            raise ValueError('init record differs')
        name_offset = name_pointer-DELTA
        if not 0 <= name_offset < len(data) or data[name_offset:name_offset+len(name)+1] != name.encode()+b'\0':
            raise ValueError('init name differs')
        result.append(dict(file_offset=hex(off), level=hex(level), flags=flags,
                           function=hex(function), name=name, name_offset=hex(name_offset)))
    return result


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    if data[0x245458:0x24545b] != b'ap\0':
        raise ValueError('appended descriptor name differs')
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for a, b in RANGES:
        lines.update(parse_lines(subprocess.check_output(command+['-D', '-b', 'binary', '-m', 'aarch64',
            f'--start-address={a}', f'--stop-address={b}', str(Path(path).resolve())], text=True)))
    wanted = {pc for a, b in RANGES for pc in range(a, b, 4)}
    if set(lines) != wanted:
        raise ValueError('GNU coverage differs')
    branches = {}
    for pc, (raw, op, args) in lines.items():
        if raw != struct.unpack_from('<I', data, pc)[0] or op in ('.inst', 'udf'):
            raise ValueError(f'GNU word differs at {pc:#x}')
        kind, target = flow(raw, pc)
        if kind in ('b', 'bl', 'conditional'):
            if target != direct_target(op, args):
                raise ValueError('GNU relative target differs')
            branches[hex(pc)] = dict(kind=kind, target=hex(target))
    for pc, expected in SELECTED.items():
        if lines[pc][1:] != expected:
            raise ValueError(f'GNU operand differs at {pc:#x}: {lines[pc][1:]}')
    packed = b''.join(struct.pack('<II', pc, lines[pc][0]) for pc in sorted(lines))
    examples = []
    for n in (0, 1, 2, 4, 5, 24):
        banks = producer_banks(n)
        examples.append(dict(supplied_units=n, supplied_equivalent_bytes=n*UNIT,
            physical_observation=False, banks_written=[dict(start=hex(a), size=s) for a, s in banks],
            advertised_pairs=append_pairs(banks, n)))
    helpers = (0xee370, 0xee660, 0x147e88, 0x148030, 0x148020, 0x11b798,
               0x15e180, 0x15e210, 0x15e0e8, 0x18d1b0)
    refs = {hex(target): [] for target in helpers}
    for pc in range(0xec000, 0x20c630, 4):
        raw, = struct.unpack_from('<I', data, pc)
        if raw >> 26 in (5, 37):
            kind, target = flow(raw, pc)
            if target in helpers:
                refs[hex(target)].append(dict(pc=hex(pc), kind=kind))
    return dict(mode='static_LK_RDX_memory_provenance', sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False, hardware_observed=False,
        gnu_version=subprocess.check_output(command+['--version'], text=True).splitlines()[0],
        gnu_words=len(lines), gnu_relative_targets=len(branches), gnu_selected_operands=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        file_ranges=[[hex(a), hex(b)] for a, b in RANGES], branches=branches,
        selected_operands={hex(pc): dict(word=f'{lines[pc][0]:08x}', op=op, args=args)
                           for pc, (op, args) in SELECTED.items()},
        source=dict(object_relative='0xcd31a8', table_relative=hex(SOURCE),
            producer='0xee370', getter='0x148030', logical_entry_bytes=16,
            size_bytes=hex(UNIT), low_start=hex(LOW), high_start_at_index4=hex(HIGH),
            entry_zero_store='0xee3d8', high_discontinuity_store='0xee41c',
            count_cache='0xaa7ea8', uncached_source='u64(AP0x02038848) >> 29, truncated to u32',
            other_selected_cache_writers=['0x11b6f0', '0x11b758', '0x11b798'],
            cache_limit_call='0x147310', actual_units_and_entries_observed=False),
        append=dict(helper='0x15e0e8', output_name='ap', name_file_offset='0x245458',
            input_step=32, units_per_iteration=2,
            second_start_checked=False, last_odd_second_size_initialized_by_producer=False,
            output_builder='0x12df68', output_stride=40,
            bootloader_call='0x15e75c', generic_call='0x15e320', generic_setting_index_0x11=5),
        initial_usb_operation_slots=pointers(data), initial_usb_init_records=init_records(data),
        usb_binding=dict(setter='0x18d1b0', operations_relative='0xd060e0',
            context_relative='0xd060d8', context_store='0x18d27c',
            send_slot='+0x38 -> nominal 0x114fe0 -> 0x114eb8',
            completion_slot='+0x48 -> nominal 0x114c18 -> 0x114b10',
            receive_count_slot='+0x68 -> nominal 0x113958',
            binding_and_usb_progress_observed=False),
        receive_state=dict(memory_branch_condition='nonempty input, bit17 clear and bit16 set',
            first_state_read='0x1177f0', states={'1':'metadata/start selection', '2':'end selection', '3':'data'},
            start_store='0x117b0c -> relative 0x8a78c8',
            inclusive_end_store='0x117a0c -> relative 0x8a78a0',
            range_matches_exported_descriptors_enforced_in_selected_blocks=False,
            malformed_input_or_full_authorization_audited=False),
        synthetic_examples=examples,
        aligned_direct_reference_candidates=dict(file_start='0xec000', file_end_exclusive='0x20c630', refs=refs,
            limitation='aligned B/BL matches only, not exhaustive runtime reachability or alias analysis'),
        conclusion=dict(first_pair_contains_probe_envelope_if_initialized_with_at_least_two_units=True,
            physical_recovery_demonstrated=False, reset_retention_demonstrated=False,
            probe_return_not_analyzed_by_this_firmware_extractor=True),
        limits=['equations and nominal init bindings only; not execution, free RAM, final FDT or device availability',
                'unit examples explicitly supplied by the host; 24 is not a measured AP0x02038848 value',
                'source entries may change after initialization; full writer/alias inventory not established',
                'odd count consumes an additional size not initialized by this producer',
                'no MMIO/SMC, USB client, flash, policy change or expanded NEWTIME QEMU scope'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_rdx_memory_hzc2: {error}\n')
