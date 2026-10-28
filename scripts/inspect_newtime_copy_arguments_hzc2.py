#!/usr/bin/env python3
"""Audit arguments at all 47 selected NEWTIME copy references. Static only.

The descriptions below are manual dataflow deductions over hash-bound code,
with GNU instruction witnesses. This is not a general symbolic executor.
Unknown pointers and mutable source contents stay unknown.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_consumers_hzc2 import branch_candidates, occurrences
from inspect_newtime_transports_hzc2 import CELL, TABLE, project_cell

DELTA = 0x020ea000
COPY = 0x1fcc4
SCAN = (0x16000, 0xec000)
RANGES = (
    (0x1da50, 0x1db5c), (0x1fcc4, 0x1fd04), (0x1ff50, 0x1ffbc),
    (0x200d0, 0x20140), (0x20274, 0x20314),
    (0x21d3c, 0x21e74), (0x21f84, 0x2217c),
    (0x22370, 0x225d0), (0x24168, 0x24284),
    (0x246f4, 0x2475c), (0x2497c, 0x249b4), (0x24a78, 0x24aa4),
    (0x24b10, 0x24b78), (0x24fb0, 0x24fdc), (0x25400, 0x254ec),
    (0x259f4, 0x25a98), (0x25d3c, 0x25d4c), (0x25eb8, 0x25ef4),
    (0x26910, 0x2698c), (0x26e14, 0x26f60), (0x28090, 0x281b0),
    (0x2aa40, 0x2ab60), (0x2ac24, 0x2acc4),
    (0x2b1a8, 0x2b24c), (0x2b28c, 0x2b2ec), (0x2b2f4, 0x2b36c),
    (0x2b3ac, 0x2b40c), (0x2b498, 0x2b508), (0x2c084, 0x2c114),
    (0x2e850, 0x2e8bc),
)


def copy_length(w2):
    """The exact loop copies max(signed32(W2), 0) bytes on valid accesses."""
    if type(w2) is not int or not 0 <= w2 < 1 << 32:
        raise ValueError('W2 must be an unsigned 32-bit integer')
    return w2 if w2 < 1 << 31 else 0


def assess_source(source, w2):
    """Unknowns are not exclusions; no conclusion about an unknown destination."""
    if source is not None and (type(source) is not int or not 0 <= source < 1 << 64):
        raise ValueError('invalid source')
    length = None if w2 is None else copy_length(w2)
    if length is None:
        return dict(bytes=None, source_intersects_cell=None, whole_cell_source=None)
    if length == 0:
        return dict(bytes=0, source_intersects_cell=False, whole_cell_source=False)
    if source is None:
        return dict(bytes=length, source_intersects_cell=None,
                    whole_cell_source=False if length < 8 else None)
    if source + length > 1 << 64:
        raise ValueError('wrapping copy interval is outside this analysis')
    return dict(bytes=length,
                source_intersects_cell=source < CELL + 8 and CELL < source + length,
                whole_cell_source=project_cell(source, source + length, 0, CELL) is not None)


def indexed_source(base, windex, stride):
    """Only the two signed-W-index address forms inspected in this report."""
    if base not in (0x31630, 0x31668) or stride != (4 if base == 0x31630 else 32):
        raise ValueError('unsupported indexed source form')
    if type(windex) is not int or not 0 <= windex < 1 << 32:
        raise ValueError('index must be unsigned W bits')
    signed = windex if windex < 1 << 31 else windex - (1 << 32)
    return (DELTA + base + signed * stride) % (1 << 64)


def file_string(data, offset):
    """An initial file sample, never a measured runtime strlen result."""
    end = data.find(b'\0', offset, offset + 256)
    if end < 0:
        raise ValueError('bounded initial source string has no NUL')
    text = data[offset:end].decode('ascii')
    return dict(file_offset=hex(offset), nominal=hex(DELTA + offset),
                initial_text=text, initial_strlen=end - offset,
                initial_file_source_assessment=assess_source(DELTA + offset, end - offset),
                runtime_length_verified=False)


def argument_sites(data):
    sites = {}

    def add(pc, group, source, destination, length, witnesses, *, source_value=None,
            w2=None, deduction=None):
        if pc in sites:
            raise ValueError('duplicate classified site')
        sites[pc] = dict(pc=hex(pc), group=group, X1_source=source,
                         X0_destination=destination, W2_length=length,
                         witness_pcs=[hex(p) for p in witnesses],
                         literal_argument_assessment=assess_source(source_value, w2),
                         destination_alias_excluded=False)
        if deduction:
            sites[pc]['conditional_deduction'] = deduction

    add(0x1db2c, 'configuration_buffer', 'nominal(0x31630)', 'M64[S+672]',
        'W19; 4 after the loop, conditional on intervening calls preserving X19',
        [0x1dabc, 0x1dad0, 0x1dad8, 0x1dadc, 0x1db1c, 0x1db20, 0x1db24, 0x1db28],
        source_value=DELTA + 0x31630,
        deduction='Source is above the cell; a forward nonwrapping copy cannot read it. '
                  'W19=4 is a dataflow deduction under the stated ABI condition, not a runtime capture.')
    add(0x1db58, 'configuration_buffer', 'nominal(0x31668)', 'M64[S+672]+4', '32',
        list(range(0x1db44, 0x1db58, 4)), source_value=DELTA + 0x31668, w2=32)
    add(0x1ff98, 'incoming_buffer', 'entry(0x1ff50).X0',
        'nominal(0x31c40)+M8[nominal(0x31f24)]', 'u8(entry.W1)',
        [0x1ff60, 0x1ff6c, 0x1ff84, 0x1ff88, 0x1ff8c, 0x1ff90, 0x1ff94],
        deduction='Generic source is unresolved; eight direct wrapper references are inventoried separately.')
    add(0x21fe4, 'archive_wrapper', 'entry(0x21f84).X1', 'return(0x21dc0)',
        'entry.W2 preserved in W19',
        [0x21f94, 0x21f98, 0x21fcc, 0x21fd0, 0x21fd4, 0x21fd8, 0x21fdc, 0x21fe0],
        deduction='Wrapper callers include dynamic channel buffers and the 0x22014 source; no general exclusion.')
    add(0x22010, 'archive_wrapper', 'zero_extend(M32[lookup_result+16])',
        'entry(0x21ff8).X1', 'M32[lookup_result+20]',
        [0x21ffc, 0x22000, 0x22004, 0x22008, 0x2200c],
        deduction='Lookup metadata is mutable. A 32-bit source is not a file offset or a pointer to the table.')

    for pc, source, dest, length, evidence in (
        (0x224f4, 'X25 derived from AP header fields', 'SP+0x60', '160', range(0x224dc, 0x224f4, 4)),
        (0x22504, 'X20 derived from AP header fields', 'SP+0x100', '72', range(0x224f8, 0x22504, 4)),
        (0x22518, 'X19 derived from AP header fields', 'SP+0x148', '4*M8[nominal(0x31688)]', range(0x22508, 0x22518, 4)),
        (0x2258c, 'SP+0x60', 'X25 derived from AP header fields', '160', range(0x22580, 0x2258c, 4)),
        (0x2259c, 'SP+0x100', 'X20 derived from AP header fields', '72', range(0x22590, 0x2259c, 4)),
        (0x225b0, 'SP+0x148', 'X19 derived from AP header fields', '4*M8[nominal(0x31688)]', range(0x225a0, 0x225b0, 4)),
    ):
        add(pc, 'save_restore', source, dest, length, evidence,
            w2=int(length) if length.isdecimal() else None,
            deduction='Selected sources/destinations are symbolic; AP fields, current SP and aliases are unresolved. '
                      'The byte controlling the variable length is reloaded, not proved preserved.')

    # Each source is formed by an ADRP+ADD in the witnessed path. strlen
    # and copy run on mutable memory; only the source pointer is fixed here.
    string_paths = (
        ((0x241f8, 0x24268), 0x30438, 0x319a4, 'X21', 'X20'),
        ((0x24210, 0x24280), 0x300c0, 0x319d6, 'X22', 'X19'),
        ((0x28118, 0x28194), 0x30457, 0x319a4, 'X22', 'X20'),
        ((0x28130, 0x281ac), 0x30090, 0x319d6, 'X20', 'X21'),
        ((0x2aac8, 0x2ab44), 0x3046c, 0x319a4, 'X23', 'X21'),
        ((0x2aae0, 0x2ab5c), 0x300a0, 0x319d6, 'X21', 'X22'),
        ((0x2aca4,), 0x3046c, 0x319a4, 'X24', 'X23'),
        ((0x2acc0,), 0x300b0, 0x319d6, 'X23', 'X22'),
        ((0x2b230, 0x2b2d0, 0x2b350, 0x2b3f0), 0x3046c, 0x319a4, 'X22', 'X19'),
        ((0x2b248, 0x2b2e8, 0x2b368, 0x2b408), 0x300d8, 0x319d6, 'X21', 'X20'),
        ((0x2c0f4,), 0x3046c, 0x319a4, 'X22', 'X21'),
        ((0x2c110,), 0x300f0, 0x319d6, 'X21', 'X20'),
    )
    for pcs, source, destination, src_reg, dst_reg in string_paths:
        for pc in pcs:
            add(pc, 'literal_string', f'nominal({source:#x}) via {src_reg}',
                f'nominal({destination:#x}) via {dst_reg}', 'return_W0(strlen at 0x1fce8)',
                range(pc - 24, pc, 4), source_value=DELTA + source,
                deduction='Initial file string ends before the cell, if preserved. '
                          'Runtime strlen/content is not established; no runtime exclusion is claimed.')
            sites[pc]['initial_source_sample'] = file_string(data, source)
            sites[pc]['source_file_offset'] = hex(source)
            sites[pc]['destination_file_offset'] = hex(destination)

    for pc, source, dest, length, evidence in (
        (0x24750, 'M64[nominal(0x31908)+8*i]+0x28', 'SP+0x100+160*i', 160, range(0x24738, 0x24750, 4)),
        (0x249a4, 'SP+0x100+160*i', 'M64[nominal(0x31908)+8*i]+0x28', 160, range(0x2497c, 0x249a4, 4)),
        (0x24a98, 'SP+0x100+160*i', 'M64[nominal(0x31908)+8*i]+0x28', 160, range(0x24a78, 0x24a98, 4)),
        (0x24b6c, 'M64[nominal(0x31908)+8*i]+0x540', 'SP+0xb0+200*i', 200, range(0x24b54, 0x24b6c, 4)),
        (0x24fd0, 'SP+0xb0+200*i', 'M64[nominal(0x31908)+8*i]+0x540', 200, range(0x24fb0, 0x24fd0, 4)),
    ):
        add(pc, 'channel_save_restore', source, dest, str(length), evidence, w2=length,
            deduction='i=0..3 on the selected loop under call/ABI preservation; '
                      'channel pointers, stack and aliasing are not measured or resolved.')

    for pc, base, stride, length, dest, evidence in (
        (0x25438, 0x31630, 4, 4, 'M64[S+672]', range(0x2541c, 0x25438, 4)),
        (0x2549c, 0x31668, 32, 32, 'M64[S+672]+4', range(0x25478, 0x2549c, 4)),
    ):
        add(pc, 'signed_index', f'nominal({base:#x})+signed32(entry.W3)*{stride}',
            dest, str(length), evidence, w2=length,
            deduction='The one scanned direct caller supplies a nonnegative loop counter, '
                      'conditional on X20 preservation. This does not constrain indirect/internal callers.')

    for pc, source, dest in (
        (0x26950, 'SP+0x11f+0x11a*i', 'M64[nominal(0x31908)+8*i]+12*signed32(W24)+0xe1c'),
        (0x26978, 'SP+0x1ac+0x11a*i', 'M64[nominal(0x31908)+8*i]+12*signed32(W24)+0xe22'),
    ):
        add(pc, 'six_byte_copy', source, dest, '6', range(pc - 20, pc, 4), w2=6,
            deduction='Six bytes cannot carry a whole eight-byte cell in this single call. '
                      'Partial reads, aggregation and writes through an alias remain possible. '
                      'The second call requires W23=2.')
    add(0x26f1c, 'scratch_to_stack', 'nominal(0x31f30)',
        'SP+0x220+0x1b0*i+0x6c*j', '108',
        [0x26e3c, 0x26e44, 0x26e8c, 0x26e90, 0x26e9c,
         0x26f10, 0x26f14, 0x26f18, 0x26f3c, 0x26f40, 0x26f48, 0x26f4c],
        source_value=DELTA + 0x31f30, w2=108,
        deduction='Source is above the cell; destination remains relative to an unmeasured stack. '
                  'Inspecting this path statically does not execute 0x26e14.')
    add(0x2b504, 'incoming_optional_buffer', 'entry(0x2b498).X5', 'SP+0x70', '64',
        [0x2b498, 0x2b4f4, 0x2b4f8, 0x2b4fc, 0x2b500], w2=64,
        deduction='Skipped when X5=0. Nonzero source has no reconstructed value here.')
    add(0x2e8b8, 'fixed_external_source', 'literal 0x021ab6a4', 'SP+0x88', '52',
        list(range(0x2e8a4, 0x2e8b8, 4)), source_value=0x021ab6a4, w2=52)
    return sites


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    sites = argument_sites(data)
    scans = {target: branch_candidates(data, target, first=SCAN[0], last=SCAN[1])
             for target in (COPY, 0x1ff50, 0x21f84, 0x21ff8, 0x25400, 0x2b498)}
    if set(sites) != {int(c['pc'], 16) for c in scans[COPY]} or len(sites) != 47:
        raise ValueError('classified sites differ from complete direct-reference scan')
    pcs = {p for a, b in RANGES for p in range(a, b, 4)}
    pcs |= {int(c['pc'], 16) for calls in scans.values() for c in calls}
    if not all(int(p, 16) in pcs for site in sites.values() for p in site['witness_pcs']):
        raise ValueError('argument witness missing from GNU coverage')
    runs = []
    for pc in sorted(pcs):
        if runs and runs[-1][1] == pc:
            runs[-1][1] = pc + 4
        else:
            runs.append([pc, pc + 4])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root'),
               str(root / 'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version = subprocess.check_output(command + ['--version'], text=True).splitlines()[0]
    lines = {}
    for a, b in runs:
        lines.update(parse_lines(subprocess.check_output(command + [
            '-D', '-b', 'binary', '-m', 'aarch64', f'--start-address={a}',
            f'--stop-address={b}', str(Path(path).resolve())], text=True)))
    if set(lines) != pcs:
        raise ValueError('GNU instruction coverage differs')
    relative = 0
    for pc, (word, op, args) in lines.items():
        if word != struct.unpack_from('<I', data, pc)[0] or op in ('.inst', 'udf'):
            raise ValueError(f'GNU word/instruction differs at {pc:#x}')
        kind, target = flow(word, pc)
        if kind in ('b', 'bl', 'conditional'):
            if direct_target(op, args) != target:
                raise ValueError(f'GNU branch target differs at {pc:#x}')
            relative += 1
        elif direct_target(op, args) is not None:
            raise ValueError('unclassified GNU branch')

    # Check the operations that are especially easy to confuse: widths,
    # signed indexes, mutable metadata and reloaded length versus a pointer.
    selected = {
        0x1fcc8: ('sub', 'w4, w2, w3'), 0x1fcd0: ('b.le', '0x1fce4'),
        0x1fcd4: ('ldrb', 'w4, [x1, x3]'), 0x1fcd8: ('strb', 'w4, [x0, x3]'),
        0x1ff60: ('uxtb', 'w21, w1'), 0x22004: ('ldp', 'w1, w2, [x0, #16]'),
        0x22508: ('ldrb', 'w2, [x22, #1672]'), 0x225a0: ('ldrb', 'w2, [x22, #1672]'),
        0x2542c: ('add', 'x1, x1, w3, sxtw #2'), 0x25484: ('sbfiz', 'x3, x3, #5, #32'),
        0x259fc: ('mov', 'x20, #0x0'), 0x25a3c: ('cmp', 'w20, w24'),
        0x25a40: ('b.ge', '0x25a7c'), 0x25a48: ('mov', 'w3, w20'),
        0x25a70: ('add', 'x20, x20, #0x1'),
        0x26940: ('mov', 'w2, #0x6'), 0x26968: ('mov', 'w2, #0x6'),
        0x26e44: ('add', 'x26, x25, #0xf30'), 0x26f10: ('mov', 'w2, #0x6c'),
        0x2b4f4: ('cbz', 'x5, 0x2b508'), 0x2b4f8: ('mov', 'w2, #0x40'),
        0x25d3c: ('adrp', 'x0, 0x31000'), 0x25d44: ('add', 'x0, x0, #0xc30'),
        0x25d48: ('str', 'x0, [sp, #128]'), 0x25ed8: ('ldr', 'x2, [sp, #128]'),
        0x24168: ('adrp', 'x21, 0x30000'), 0x24178: ('add', 'x21, x21, #0x309'),
        0x24180: ('add', 'x21, x21, #0x12f'),
        0x241c0: ('add', 'x22, x22, #0xc0'), 0x24230: ('add', 'x22, x22, #0xc0'),
        0x280e0: ('add', 'x22, x22, #0x457'), 0x2815c: ('add', 'x22, x22, #0x457'),
        0x28114: ('add', 'x20, x23, #0x90'), 0x28190: ('add', 'x20, x23, #0x90'),
        0x2aa90: ('add', 'x23, x23, #0x46c'), 0x2ab0c: ('add', 'x23, x23, #0x46c'),
        0x2aac4: ('add', 'x21, x26, #0xa0'), 0x2ab40: ('add', 'x21, x26, #0xa0'),
        0x2ac58: ('add', 'x24, x24, #0x46c'), 0x2aca8: ('add', 'x23, x23, #0xb0'),
        0x2b1e4: ('add', 'x22, x22, #0x46c'), 0x2b1fc: ('add', 'x21, x21, #0xd8'),
        0x2b304: ('add', 'x22, x22, #0x46c'), 0x2b31c: ('add', 'x21, x21, #0xd8'),
        0x2c0ac: ('add', 'x22, x22, #0x46c'), 0x2c0f8: ('add', 'x21, x21, #0xf0'),
    }
    for pc, expected in selected.items():
        if lines[pc][1:] != expected:
            raise ValueError(f'selected operand differs at {pc:#x}')
    for target, calls in scans.items():
        for call in calls:
            pc = int(call['pc'], 16)
            if lines[pc][1:] != (call['kind'], hex(target)):
                raise ValueError('wrapper/direct-reference operand differs')

    channel_cells = (0x31908, 0x31910, 0x31918, 0x31920)
    metadata_sources = []
    for pc, cell in zip((0x22148, 0x22158, 0x22168, 0x22178), channel_cells):
        metadata_sources.append(dict(call=hex(pc), wrapper='0x21f84',
            source=f'M64[nominal({cell:#x})]', bytes=4016,
            source_resolved=False, whole_cell_source=None))
    packed = b''.join(struct.pack('<II', p, lines[p][0]) for p in sorted(pcs))
    return dict(
        mode='static_newtime_copy_arguments', schema_version=1,
        sboot_sha256=IMAGES['sboot'][1], sboot_bytes=len(data), nominal_delta=hex(DELTA),
        cell_file='0x31580', cell_nominal=hex(CELL), table_window=[hex(x) for x in TABLE],
        scan=dict(first=hex(SCAN[0]), end_exclusive=hex(SCAN[1]),
                  aligned_words=(SCAN[1] - SCAN[0]) // 4,
                  interpretation='B/BL encodings are candidates, not a reachability proof'),
        direct_copy_references=47, newly_classified_references=44,
        group_counts=dict(sorted(Counter(s['group'] for s in sites.values()).items())),
        sites=[sites[p] for p in sorted(sites)],
        wrapper_references={hex(target): calls for target, calls in scans.items() if target != COPY},
        archive_channel_sources=metadata_sources,
        optional_buffer_binding=dict(entry='0x2b498', table_file='0x30fe8', index=20,
            cell_file='0x31088', initial_pointer=hex(struct.unpack_from('<Q', data, 0x31088)[0]),
            nominal_pointer_occurrences=[hex(p) for p in occurrences(data, struct.pack('<Q', DELTA + 0x2b498))],
            incoming_X5_resolved=False, note='Initial pointer only; indirect dispatch and preservation remain open'),
        archive_lookup=dict(entry='0x21ff8', call='0x22000', lookup='0x21d3c',
            descriptor_stride=24, descriptor_name_offset=0x34,
            returned_name_pointer=True, source_u32_at_return_plus=16, length_u32_at_return_plus=20,
            origin='metadata selected by name; no source/length instance measured',
            bounds_or_authentication_proved=False),
        concrete_archive_source=dict(call='0x25ee8', wrapper='0x22014 -> 0x21f84',
            X2_source='address of nominal(0x31c30), not its loaded pointer',
            W3_length='162*u8(current_object+12), at most 41310',
            conditional_nonwrapping_source_excludes_cell=True,
            witness_pcs=['0x25d3c', '0x25d44', '0x25d48', '0x25ed8', '0x25edc', '0x25ee8',
                         '0x22018', '0x22038', '0x22078', '0x2207c', '0x22084']),
        signed_index_caller=dict(target='0x25400', scanned_direct_call='0x25a58',
            index='W20 starts at zero; call only while signed W20 < signed W24',
            maximum_index_under_this_loop=(1 << 31) - 2,
            conditions=['normal function entry', 'intervening callees preserve X20 and X24 under AAPCS64'],
            consequence='nonnegative source offset above cell in both selected paths',
            other_callers_or_internal_entries_constrained=False),
        initial_channel_cells={hex(p): hex(struct.unpack_from('<Q', data, p)[0]) for p in channel_cells},
        gnu=dict(version=version, words=len(lines), relative_targets=relative,
                 selected_operands=len(selected), instruction_index_sha256=hashlib.sha256(packed).hexdigest()),
        ranges=[dict(first=hex(a), end_exclusive=hex(b),
                     sha256=hashlib.sha256(data[a:b]).hexdigest()) for a, b in RANGES],
        witnesses=[dict(pc=hex(p), word=f'{w:08x}', op=op, args=args)
                   for p, (w, op, args) in sorted(lines.items())],
        limits=[
            'Manual symbolic argument deductions, not a general dataflow or whole-program proof',
            'Literal initial file strings do not establish mutable runtime content or strlen',
            'SP-relative sources do not exclude aliasing the nominal table without a stack contract',
            'Channel/incoming pointers, archive metadata and destinations retain unresolved aliases',
            'Six-byte/other partial copies may aggregate; single-copy whole-cell exclusion is narrower',
            'No global absence of transport, overwrite, caller, export or runtime rebind is established',
        ],
        transport_of_cell_found=False, incoming_X0_resolved=False,
        firmware_executed=False, qemu_scope_extended=False, physical_device_tested=False,
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        report = inspect(args.sboot)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(report, indent=2))
