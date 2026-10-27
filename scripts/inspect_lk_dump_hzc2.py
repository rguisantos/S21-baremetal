#!/usr/bin/env python3
"""Hash-bound static RDX export evidence. Never executes firmware or opens a device."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow

LIMIT = 1 << 64
DELTA = 0xe7f14000
TABLE = 0x245340
STRIDE = 40
# Conservative envelope for the previously reconstructed 64 candidate entries
# and the probe's <1 MiB ADR bound. This is not measured RAM or an allocation.
PROBE_ENVELOPE = (0x80080000, 0x80378000)
RANGES = (
    (0x11b6c0, 0x11b6f0), (0x12df28, 0x12dfe4), (0x148020, 0x14802c), (0x148030, 0x148040),
    (0x147ed8, 0x147ee4), (0x147ee8, 0x147f5c),
    (0x159528, 0x159588), (0x15e0e8, 0x15e16c), (0x15e1b8, 0x15e358),
    (0x15e6cc, 0x15e6d8), (0x15e6fc, 0x15e760), (0x15e7d0, 0x15e8d4),
    (0x116e88, 0x116e9c), (0x17b8d0, 0x17b8e8),
    (0x116f70, 0x116f88), (0x117260, 0x117274),
    (0x11786c, 0x1178f0), (0x117a7c, 0x117ae4), (0x112338, 0x112414),
)
SELECTED = {
    0x12df58: ('add', 'x0, x19, #0x10'),
    0x12df88: ('str', 'w0, [x20]'),
    0x12df90: ('mov', 'x2, #0xf'),
    0x12df94: ('add', 'x0, x20, #0x4'),
    0x12dfa0: ('sub', 'x2, x19, #0x1'),
    0x12dfa8: ('add', 'x2, x2, x21'),
    0x12dfac: ('add', 'x0, x20, #0x28'),
    0x12dfb0: ('stp', 'x21, x2, [x20, #24]'),
    0x12dfdc: ('str', 'w4, [x5, #1816]'),
    0x15e12c: ('mov', 'x0, x19'),
    0x15e134: ('add', 'w21, w21, #0x2'),
    0x15e138: ('ldr', 'x2, [x20], #32'),
    0x15e13c: ('add', 'x19, x19, #0x28'),
    0x15e140: ('add', 'x3, x3, x1'),
    0x15e270: ('mov', 'w0, #0x11'),
    0x15e214: ('mov', 'w0, #0x10000'),
    0x15e218: ('mov', 'w1, #0x1'),
    0x15e230: ('bl', '0x147ee8'),
    0x15e6d0: ('mov', 'w0, #0x10000'),
    0x15e6d4: ('bl', '0x147ee8'),
    0x147edc: ('ldr', 'w0, [x0, #1260]'),
    0x147f48: ('orr', 'w2, w2, w0'),
    0x147f4c: ('str', 'w2, [x1, #836]'),
    0x15e314: ('cmp', 'w24, #0x5'),
    0x15e6fc: ('adrp', 'x1, 0x245000'),
    0x15e700: ('mov', 'x2, #0xa0'),
    0x15e704: ('add', 'x1, x1, #0x340'),
    0x15e730: ('add', 'x21, x0, #0xa0'),
    0x15e734: ('ldp', 'x2, x3, [x19, #16]'),
    0x15e740: ('add', 'x22, x4, #0x28'),
    0x15e748: ('bl', '0x12df68'),
    0x15e75c: ('bl', '0x15e0e8'),
    0x159550: ('bl', '0x149a90'),
    0x159554: ('cbnz', 'w0, 0x159570'),
    0x159568: ('b', '0x15e210'),
    0x15957c: ('mov', 'w0, #0x0'),
    0x15e85c: ('bl', '0x149a90'),
    0x15e860: ('cbnz', 'w0, 0x15e8b0'),
    0x15e878: ('mov', 'w0, #0x1'),
    0x15e8cc: ('bl', '0x146ba0'),
    0x15e8d0: ('b', '0x15e864'),
    0x116e90: ('add', 'x1, x1, #0xcf8'),
    0x116e94: ('add', 'x0, x0, #0xd00'),
    0x17b8d8: ('str', 'x0, [x2, #408]'),
    0x17b8e0: ('str', 'x1, [x3, #8]'),
    0x116f74: ('bl', '0x147ed8'),
    0x116f78: ('tbz', 'w0, #17, 0x117260'),
    0x117260: ('bl', '0x147ed8'),
    0x117264: ('tbz', 'w0, #16, 0x116f38'),
    0x117878: ('ldr', 'x1, [x1, #2208]'),
    0x11789c: ('ldr', 'x3, [x22, #2304]'),
    0x1178a0: ('sub', 'x19, x1, x0'),
    0x1178a4: ('mov', 'x2, #0x80000'),
    0x1178b0: ('csel', 'x19, x19, x2, ls'),
    0x1178c0: ('mov', 'w1, w19'),
    0x1178c4: ('bl', '0x112400'),
    0x112400: ('adrp', 'x2, 0x8a7000'),
    0x112410: ('b', '0x112338'),
    0x1123b4: ('mov', 'w2, w1'),
    0x1123bc: ('mov', 'x1, x21'),
    0x1123c4: ('bl', '0x18c4c8'),
}


def span(base, size):
    """Host validation of a nonempty, nonwrapping u64 span, not firmware policy."""
    if type(base) is not int or type(size) is not int or not 0 <= base < LIMIT or not 0 < size <= LIMIT-base:
        raise ValueError('invalid nonwrapping u64 span')
    return base, base+size


def encoded_end(base, size):
    """The writer's end=start+size-1 wraps; size zero is not rejected there."""
    if any(type(x) is not int or not 0 <= x < LIMIT for x in (base, size)):
        raise ValueError('u64 writer arguments required')
    return (base+size-1) % LIMIT


def overlaps(first, second):
    a, b = first; c, d = second
    if any(type(x) is not int for x in (a,b,c,d)) or not 0 <= a < b <= LIMIT or not 0 <= c < d <= LIMIT:
        raise ValueError('invalid half-open spans')
    return a < d and c < b


def templates(data, offset=TABLE, count=4):
    if type(offset) is not int or type(count) is not int or offset < 0 or not 0 < count <= 128 or offset+count*STRIDE > len(data):
        raise ValueError('template table outside supplied bytes')
    rows=[]
    for index in range(count):
        start=offset+index*STRIDE; name=data[start:start+16]
        if b'\0' not in name or any(name[name.index(0):]):
            raise ValueError('invalid bounded template name')
        name=name.split(b'\0')[0].decode('ascii')
        if not name or any(ord(c)<32 or ord(c)>126 for c in name):
            raise ValueError('invalid printable template name')
        base,size,flag=struct.unpack_from('<3Q',data,start+16)
        a,b=span(base,size)
        rows.append(dict(index=index,file_offset=hex(start),name=name,base=hex(a),bytes=size,
                         end_exclusive=hex(b),initial_flag=flag,
                         overlaps_candidate_probe_envelope=overlaps((a,b),PROBE_ENVELOPE)))
    return rows


def inspect(path):
    data=read_exact(path,*IMAGES['sboot'])
    rows=templates(data)
    root=Path(__file__).resolve().parent.parent
    command=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
             str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for a,b in RANGES:
        lines.update(parse_lines(subprocess.check_output(command+['-D','-b','binary','-m','aarch64',
            f'--start-address={a}',f'--stop-address={b}',str(Path(path).resolve())],text=True)))
    wanted={pc for a,b in RANGES for pc in range(a,b,4)}
    if set(lines)!=wanted:raise ValueError('GNU coverage differs')
    branches={}
    for pc,(raw,op,args) in lines.items():
        if raw!=struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):raise ValueError(f'GNU instruction differs at {pc:#x}')
        kind,target=flow(raw,pc)
        if kind in ('b','bl','conditional'):
            if target!=direct_target(op,args):raise ValueError('GNU relative target differs')
            branches[hex(pc)]=dict(kind=kind,target=hex(target))
    for pc,expected in SELECTED.items():
        if lines[pc][1:]!=expected:raise ValueError(f'GNU operand differs at {pc:#x}: {lines[pc][1:]}')
    if (int(rows[1]['base'],16),rows[1]['bytes'])!=(0xec000+DELTA,0x36c000-0xec000):
        raise ValueError('boot_ram no longer matches the nominal LK window')
    index=b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    strings={hex(off):data[off:data.index(0,off)].decode('ascii') for off in
             (0x22aa30,0x22ab90,0x22abb8,0x2431d8,0x2453e0,0x245430,0x245440,0x2455e8)}
    return dict(mode='static_LK_RDX_selected_paths',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,device_client_implemented=False,
        file_ranges=[[hex(a),hex(b)] for a,b in RANGES],
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        gnu_words=len(lines),gnu_relative_targets=len(branches),gnu_selected_operands=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(index).hexdigest(),branches=branches,
        selected_operands={hex(pc):dict(word=f'{lines[pc][0]:08x}',op=op,args=args)
                           for pc,(op,args) in SELECTED.items()},strings=strings,
        fixed_bootloader_templates=rows,
        candidate_probe_comparison=dict(start=hex(PROBE_ENVELOPE[0]),end_exclusive=hex(PROBE_ENVELOPE[1]),
            basis='64 previously reconstructed LK candidate entries, 0x80080000+0..0x1f8000, and probe ADR extent <1 MiB',
            observed_or_allocated=False),
        log_template_includes_snapshot_header=overlaps(span(int(rows[0]['base'],16),rows[0]['bytes']),(0xf0000000,0xf0010000)),
        nominal_lk_mapping=dict(delta=hex(DELTA),file_start='0xec000',file_end_exclusive='0x36c000',
                               mapped_start=hex(0xec000+DELTA),mapped_end_exclusive=hex(0x36c000+DELTA)),
        output_descriptor=dict(builder='0x12df68',stride=40,enabled_offset=0,name_offset=4,name_max_bytes=15,
            start_offset=24,inclusive_end_offset=32,header_bytes=16,
            end_arithmetic='(start + size - 1) modulo 2^64; no zero/overflow guard in this body'),
        dynamic_append=dict(helper='0x15e0e8',source_getter='0x148030',source_relative='0xcd31d0',
            source_stride=32,size_expression='u64(entry[8] + entry[24])',count_helper='0x11b6c0',
            count_basis='cached u32, else AP0x02038848 >> 29 truncated to u32',counter_step=2,
            generic_path_condition='0x12dbc8(index=0x11) returned 5 at 0x15e314',bootloader_path_call='0x15e75c',
            entries_or_preservation_observed=False),
        callback_registration=dict(call_from_upload='0x15e34c',helper='0x116e88',store_helper='0x17b8d0',
            transmit_callback='0x116d00',receive_callback='0x116cf8',runtime_binding_observed=False),
        send_window=dict(start_pc='0x11786c',end_pc_exclusive='0x1178f0',
            start_relative='0x8a78c8',inclusive_end_relative='0x8a78a0',chunk_limit=0x80000,
            call='0x1178c4',target='0x112400',tail_target='0x112338',backend_call='0x18c4c8',
            direct_memory_condition='context pointer null or u32(context+4)==0; alternate branch calls 0x162cc8 with a buffer/context, associated with handle_storage_dump; helper not reconstructed',
            runtime_memory_read_available='not_established'),
        receive_dispatch=dict(helper='0x147ed8',first_test='bit17 at 0x116f78',
            fallback_test='bit16 at 0x117264',flag_relative='0xcd34ec',
            bit16_set_by_calls=['0x15e230','0x15e6d4'],setter='0x147ee8',
            setter_arguments=dict(w0='0x10000',w1=1),
            setting_index_0x11_is_a_separate_input=True,
            flag_values_and_full_gate_analysis='not_established'),
        policy=dict(shell_entry='0x159528',helper='0x149a90',argument=1,
            nonzero_result='0x159570 prints FMM denial; returns zero, no tail branch to upload',
            other_wrapper='0x15e7d0 logs FMM denial, passes fmm_lock_upload to 0x146ba0 and joins a return-one tail; helper effects not reconstructed',
            fmm_state_observed=False,bootloader_lock_equivalence_established=False),
        limits=['selected static paths and templates only; not complete protocol/authorization analysis',
                'fixed-template non-overlap does not exclude appended runtime descriptions or other profiles',
                'runtime relative addresses are not acquired physical memory values',
                'no guarantee of retention, availability, writable ownership or progress on the phone',
                'storage dump path present by names; implementation/readback not reconstructed here'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try: result=inspect(args.sboot)
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as error:
        parser.exit(2,f'inspect_lk_dump_hzc2: {error}\n')
    print(json.dumps(result,indent=2))
