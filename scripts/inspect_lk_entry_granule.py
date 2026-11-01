#!/usr/bin/env python3
"""Bind the LK EL transition, inherited TG0 getter and bounded TCR writer census."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_payload_return import summarize_local
from inspect_lk_precopy_measurement import verify_disassembly

BLOCKS = {
    'entry_call': (0xec000, 0xec004),
    'el_transition': (0xf9b4c, 0xf9bc0),
    'save_system_state': (0xededc, 0xedf18),
    'restore_system_state': (0xedf38, 0xedf78),
    'tcr_reader': (0x189480, 0x189488),
    'tcr_writer': (0x1894a0, 0x1894a8),
    'granule_getter': (0x189e50, 0x189f04),
    'mapper_queries': (0x189f88, 0x189fa8),
    'install_new_tcr': (0x18a1d0, 0x18a1e0),
    'root_query': (0x18a23c, 0x18a24c),
    'links_query': (0x18a264, 0x18a278),
}
SELECTED = {
    0xec000: ('bl', '0xf9b4c'),
    0xf9b4c: ('mrs', 'x4, currentel'),
    0xf9b50: ('cmp', 'x4, #0x4'),
    0xf9b54: ('b.ne', '0xf9b5c'),
    0xf9b58: ('ret', ''),
    0xf9b5c: ('cmp', 'x4, #0x8'),
    0xf9b60: ('b.eq', '0xf9b84'),
    0xf9b64: ('mrs', 'x4, scr_el3'),
    0xf9b68: ('orr', 'x4, x4, #0x400'),
    0xf9b6c: ('msr', 'scr_el3, x4'),
    0xf9b70: ('adr', 'x4, 0xf9bbc'),
    0xf9b74: ('msr', 'elr_el3, x4'),
    0xf9b78: ('mov', 'x4, #0x3c5'),
    0xf9b7c: ('msr', 'spsr_el3, x4'),
    0xf9b84: ('adr', 'x4, 0xf9bbc'),
    0xf9b88: ('msr', 'elr_el2, x4'),
    0xf9b8c: ('mov', 'x4, #0x3c5'),
    0xf9b90: ('msr', 'spsr_el2, x4'),
    0xf9b94: ('mov', 'x0, #0x33ff'),
    0xf9b98: ('msr', 'cptr_el2, x0'),
    0xf9b9c: ('mov', 'x0, #0x80000000'),
    0xf9ba0: ('msr', 'hcr_el2, x0'),
    0xf9ba4: ('mov', 'x0, #0x300000'),
    0xf9ba8: ('msr', 'cpacr_el1, x0'),
    0xf9bac: ('mov', 'x0, sp'),
    0xf9bb0: ('msr', 'sp_el1, x0'),
    0xf9bb8: ('eret', ''),
    0xf9bbc: ('ret', ''),
    0xedee8: ('mrs', 'x4, tcr_el1'),
    0xedf08: ('stp', 'x3, x4, [x0, #272]'),
    0xedf40: ('ldp', 'x3, x4, [x0, #272]'),
    0xedf5c: ('msr', 'tcr_el1, x4'),
    0x189480: ('mrs', 'x0, tcr_el1'),
    0x1894a0: ('msr', 'tcr_el1, x0'),
    0x189e54: ('cmp', 'w0, #0x1'),
    0x189e64: ('b.ne', '0x189ee0'),
    0x189e68: ('bl', '0x189480'),
    0x189e6c: ('ubfx', 'x0, x0, #14, #2'),
    0x189e74: ('b.eq', '0x189ed0'),
    0x189e78: ('cbz', 'x0, 0x189e98'),
    0x189e80: ('b.ne', '0x189ea8'),
    0x189e84: ('mov', 'x0, #0x4000'),
    0x189e98: ('mov', 'x0, #0x1000'),
    0x189ec8: ('bl', '0x18f8a8'),
    0x189ed0: ('mov', 'x0, #0x10000'),
    0x189f00: ('bl', '0x18f8a8'),
    0x189f94: ('bl', '0x189e50'),
    0x189fa4: ('bl', '0x189e50'),
    0x18a1d0: ('mov', 'x0, #0x351c'),
    0x18a1d4: ('movk', 'x0, #0xb51c, lsl #16'),
    0x18a1d8: ('movk', 'x0, #0x11, lsl #32'),
    0x18a1dc: ('bl', '0x1894a0'),
    0x18a244: ('bl', '0x189e50'),
    0x18a270: ('bl', '0x189e50'),
}


def granule_from_tcr(tcr, el=1):
    """Selected getter semantics; an assertion call is a boundary, not a size."""
    if type(tcr) is not int or not 0 <= tcr < 1 << 64:
        raise ValueError('u64 TCR required')
    if type(el) is not int or el != 1:
        raise ValueError('getter requires EL argument 1')
    tg0 = (tcr >> 14) & 3
    if tg0 == 3:
        raise ValueError('reserved TG0 reaches assertion boundary')
    return (4096, 65536, 16384)[tg0]


def tcr_writers(data, start=0, end=None):
    """Candidate aligned MSR TCR_EL1 words, including possible data matches."""
    end = len(data) if end is None else end
    if (type(start) is not int or type(end) is not int or start < 0
            or start % 4 or end % 4 or not start <= end <= len(data)):
        raise ValueError('aligned census bounds required')
    rows = []
    for pc in range(start, end, 4):
        word, = struct.unpack_from('<I', data, pc)
        if word & 0xffffffe0 == 0xd5182040:
            rows.append(dict(file_offset=hex(pc),source_register=word & 31,word=f'{word:08x}'))
    return rows


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    command=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for a,b in BLOCKS.values():
        parsed=parse_lines(subprocess.check_output(command+['-D','-z','-b','binary','-m','aarch64',f'--start-address={a}',f'--stop-address={b}',str(Path(path).resolve())],text=True))
        if lines.keys() & parsed.keys():raise ValueError('duplicate GNU PC')
        lines.update(parsed)
    branches=verify_disassembly(data,lines,BLOCKS,SELECTED)
    writers=tcr_writers(data)
    if [(r['file_offset'],r['source_register']) for r in writers]!=[('0xedf5c',4),('0x1894a0',0)]:
        raise ValueError('TCR writer census differs')
    packed=b''.join(struct.pack('<II',p,row[0]) for p,row in sorted(lines.items()))
    return dict(mode='static_lk_entry_and_inherited_granule',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,
        gnu_words=len(lines),gnu_relative_targets=len(branches),selected_operand_checks=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        blocks={k:dict(start=hex(a),end_exclusive=hex(b)) for k,(a,b) in BLOCKS.items()},
        selected_instructions={hex(p):dict(word=f'{lines[p][0]:08x}',op=op,args=args) for p,(op,args) in sorted(SELECTED.items())},
        branches=branches,local_graphs={k:summarize_local(data,a,a,b) for k,(a,b) in BLOCKS.items()},
        entry=dict(call='0xec000 -> 0xf9b4c',el1='returns immediately; X0-X3 unchanged',
            el2='SPSR_EL2=0x3c5; ELR_EL2=local RET; HCR_EL2=0x80000000; CPTR_EL2=0x33ff; CPACR_EL1=0x300000; SP_EL1=incoming SP; ERET targets EL1h',
            el3='static path requests SPSR_EL3=0x3c5 and SCR.RW; not executed in this round',
            x0_on_lowering='incoming SP, not preserved argument X0',
            tcr_el1_written_by_selected_helper=False),
        getter=dict(start='0x189e50',reader='0x189480',field='TCR_EL1[15:14]',
            cases=[dict(tg0=tg,bytes=granule_from_tcr(tg << 14)) for tg in range(3)],
            reserved_tg0_3='assertion call 0x189ec8 -> 0x18f8a8; no return semantics assumed',
            other_el_argument='assertion call 0x189f00 -> 0x18f8a8'),
        census=dict(start='0x0',end_exclusive=hex(len(data)),alignment=4,
            opcode='MSR TCR_EL1,Xn',candidates=writers,
            roles={'0xedf5c':'restore saved context +280 through X4; not a constant granule initializer',
                   '0x1894a0':'generic writer; selected installer calls it only after constructing the tables'},
            global_writer_uniqueness_proved=False),
        limits=['The EL transition is a selected helper, not a complete startup execution or proof of later CurrentEL.',
            'TCR_EL1 is inherited at the getter; the selected entry helper does not select TG0.',
            'Aligned exact-opcode census covers this 4 MiB file only; it does not recover all boundaries or exclude other images, copied code, external agents or context restores.',
            'TG0=0 remains an input condition of the earlier EL1/4K pool model; no phone register was captured.',
            'EL3 path, exception/trap policy, physical tables, DMA and cache coherence remain unobserved.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'inspect_lk_entry_granule: {exc}\n')
