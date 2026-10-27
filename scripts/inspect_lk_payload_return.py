#!/usr/bin/env python3
"""Hash-bound static normal-return summaries for LK HZC2. No firmware execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow

DELTA = 0xe7f14000
RANGES = (
    (0xfbc10, 0xfbc28), (0xfbe14, 0xfbe2c),
    (0xfaa40, 0xfab44), (0xfab48, 0xfabf4),
    (0xfa5d0, 0xfa650), (0xf9aa8, 0xf9b08),
    (0x11a1e0, 0x11a200), (0x11a080, 0x11a0cc), (0x11a0e0, 0x11a0f8),
    (0x11aba8, 0x11ac54), (0x18f8a8, 0x18f950),
)
SELECTED = {
    0xfbc10: ('stp', 'x29, x30, [sp, #-80]!'),
    0xfbc1c: ('stp', 'x19, x20, [sp, #16]'),
    0xfbc20: ('str', 'x21, [sp, #32]'),
    0xfbe14: ('blr', 'x4'), 0xfbe18: ('mov', 'w0, #0x0'),
    0xfbe1c: ('ldp', 'x19, x20, [sp, #16]'),
    0xfbe20: ('ldr', 'x21, [sp, #32]'),
    0xfbe24: ('ldp', 'x29, x30, [sp], #80'), 0xfbe28: ('ret', ''),
    0xfaba8: ('ldp', 'x29, x30, [sp], #16'), 0xfabb4: ('b', '0xfbc10'),
    0xfabe4: ('ldp', 'x29, x30, [sp], #16'), 0xfabf0: ('b', '0xfbc10'),
    0xfaa40: ('stp', 'x29, x30, [sp, #-16]!'),
    0xfaa4c: ('ldr', 'x2, [x0, #16]'), 0xfaa50: ('blr', 'x2'),
    0xfaa54: ('mov', 'w0, #0x0'),
    0xfaa58: ('ldp', 'x29, x30, [sp], #16'), 0xfaa5c: ('ret', ''),
    0xfaaac: ('adrp', 'x21, 0xfa000'), 0xfaab8: ('add', 'x21, x21, #0xa40'),
    0xfaad4: ('cbz', 'x0, 0xfaac0'), 0xfaadc: ('tbnz', 'w1, #0, 0xfaac0'),
    0xfab00: ('mov', 'x2, x19'), 0xfab04: ('mov', 'w3, #0x10'),
    0xfab08: ('mov', 'x1, x21'), 0xfab10: ('bl', '0x11a1e0'),
    0x11a1ec: ('mov', 'x3, x2'), 0x11a1f0: ('mov', 'x2, x1'),
    0x11a1fc: ('b', '0x11a068'),
    0x11a080: ('mov', 'x24, x3'), 0x11a090: ('mov', 'x25, x2'),
    0x11a0b8: ('str', 'x25, [x19, #624]'),
    0x11a0c8: ('str', 'x24, [x19, #632]'),
    0x11a0f4: ('bl', '0xfa5f8'),
    0xfa634: ('add', 'x0, x0, #0x5d0'),
    0xfa638: ('stur', 'x0, [x19, #-128]'),
    0xfa63c: ('str', 'x21, [x20, #72]'),
    0xfa5d0: ('stp', 'x29, x30, [sp, #-16]!'),
    0xfa5d8: ('mrs', 'x0, tpidr_el1'),
    0xfa5e4: ('msr', 'daifclr, #0x2'),
    0xfa5e8: ('ldr', 'x1, [x0, #624]'),
    0xfa5ec: ('ldr', 'x0, [x0, #632]'),
    0xfa5f0: ('blr', 'x1'), 0xfa5f4: ('bl', '0x11aba8'),
    0xf9ad8: ('mov', 'sp, x1'), 0xf9adc: ('ldp', 'x30, xzr, [sp], #16'),
    0xf9b04: ('ret', ''),
    0x11abb8: ('mrs', 'x19, tpidr_el1'),
    0x11abd4: ('mov', 'w4, #0x5'),
    0x11abd8: ('str', 'w0, [x19, #640]'),
    0x11abe0: ('str', 'w4, [x19, #44]'),
    0x11ac20: ('bl', '0x119f28'), 0x11ac30: ('bl', '0x18f8a8'),
    0x18f930: ('bl', '0x205788'), 0x18f940: ('bl', '0x17d880'),
    0x18f948: ('bl', '0x205818'), 0x18f94c: ('b', '0x18f938'),
}


def summarize_local(data, root, low, high, *, limit=4096):
    """Explore local control only. Calls have explicitly conditional return edges.

    Does not evaluate registers, stack contents, path feasibility, callee bodies,
    instruction effects or hardware. Out-of-block edges remain frontiers.
    Every call continuation is conditional on the opaque callee returning normally.
    """
    if any(type(x) is not int for x in (root, low, high, limit)) or limit < 1:
        raise ValueError('integer bounds and positive budget required')
    if low < 0 or low % 4 or high % 4 or not low <= root < high <= len(data) or root % 4:
        raise ValueError('invalid aligned block bounds')
    pending = [root]; words = {}; calls = {}; returns = {}; frontiers = []; systems = []

    def edge(source, target, kind):
        if low <= target < high:
            pending.append(target)
        else:
            frontiers.append(dict(pc=hex(source), target=hex(target), kind=kind))

    while pending:
        pc = pending.pop()
        if pc in words:
            continue
        if len(words) >= limit:
            raise ValueError('local static PC budget exceeded')
        raw, = struct.unpack_from('<I', data, pc)
        kind, target = flow(raw, pc)
        words[pc] = raw
        if kind in ('bl', 'blr'):
            calls[hex(pc)] = dict(kind=kind,
                **({'target':hex(target)} if kind == 'bl' else {'register':target}),
                conditional_normal_return=hex(pc+4))
            edge(pc, pc+4, 'conditional_call_return')
        elif kind in ('b', 'conditional'):
            edge(pc, target, kind)
            if kind == 'conditional':
                edge(pc, pc+4, 'fallthrough')
        elif kind == 'ret':
            returns[hex(pc)] = target
        elif kind in ('br', 'eret', 'exception_call', 'udf'):
            frontiers.append(dict(pc=hex(pc), kind=kind, register=target if kind == 'br' else None))
        else:
            if kind == 'system':
                systems.append(hex(pc))
            edge(pc, pc+4, 'fallthrough')
    packed = b''.join(struct.pack('<II', pc, raw) for pc, raw in sorted(words.items()))
    return dict(root=hex(root), low=hex(low), high_exclusive=hex(high), instruction_count=len(words),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        visited_pcs=[hex(pc) for pc in sorted(words)], calls=calls, return_registers=returns,
        frontiers=frontiers, system_sites=systems,
        opaque_calls_assumed_to_return_only_on_their_normal_return_edge=True,
        feasibility_and_runtime_context_established=False)


def application(data):
    name, init, entry, flags, reserve = struct.unpack_from('<5Q', data, 0x29b030)
    if (name, init, entry, flags, reserve) != (DELTA+0x2161e8, 0, DELTA+0xfab48, 0, 0):
        raise ValueError('initial sbl_boot descriptor differs')
    if data[0x2161e8:0x2161f1] != b'sbl_boot\0':
        raise ValueError('application name differs')
    return dict(file_offset='0x29b030', bytes=40, name='sbl_boot',
        init_pointer=init, entry_pointer=hex(entry), nominal_entry_file_offset='0xfab48',
        flags=flags, stack_size_field=reserve, selected_default_stack_request_bytes=0x100000,
        initial_file_binding_only=True)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    app = application(data)
    root = Path(__file__).resolve().parent.parent
    command = ['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for a,b in RANGES:
        lines.update(parse_lines(subprocess.check_output(command+['-D','-b','binary','-m','aarch64',
            f'--start-address={a}',f'--stop-address={b}',str(Path(path).resolve())],text=True)))
    if set(lines) != {pc for a,b in RANGES for pc in range(a,b,4)}:
        raise ValueError('GNU coverage differs')
    branches = {}
    for pc,(raw,op,args) in lines.items():
        if raw != struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):
            raise ValueError(f'GNU instruction differs at {pc:#x}')
        kind,target = flow(raw,pc)
        if kind in ('b','bl','conditional'):
            if target != direct_target(op,args):
                raise ValueError('GNU relative target differs')
            branches[hex(pc)] = dict(kind=kind,target=hex(target))
    for pc,expected in SELECTED.items():
        if lines[pc][1:] != expected:
            raise ValueError(f'GNU operand differs at {pc:#x}: {lines[pc][1:]}')
    graphs = {
        'handoff_epilogue':summarize_local(data,0xfbe18,0xfbe18,0xfbe2c),
        'app_wrapper_after_return':summarize_local(data,0xfaa54,0xfaa54,0xfaa60),
        'app_tail_first':summarize_local(data,0xfaba8,0xfaba8,0xfabb8),
        'app_tail_second':summarize_local(data,0xfabe4,0xfabe4,0xfabf4),
        'thread_bootstrap':summarize_local(data,0xfa5d0,0xfa5d0,0xfa5f8),
        'thread_exit':summarize_local(data,0x11aba8,0x11aba8,0x11ac54),
        'panic_local_body':summarize_local(data,0x18f8a8,0x18f8a8,0x18f950),
    }
    strings = {hex(off):data[off:data.index(0,off)].decode('ascii') for off in (0x2161e8,0x22b200,0x25fa00)}
    packed = b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    rdx = {0x15e210,0x15e578,0x116f18}
    post = ('handoff_epilogue','app_wrapper_after_return','thread_bootstrap','thread_exit','panic_local_body')
    rdx_edges = [dict(graph=name,pc=pc,target=call['target']) for name in post
        for pc,call in graphs[name]['calls'].items() if 'target' in call and int(call['target'],16) in rdx]
    if graphs['thread_exit']['return_registers'] or graphs['panic_local_body']['return_registers'] or rdx_edges:
        raise ValueError('selected return/exit topology changed')
    if graphs['handoff_epilogue']['system_sites'] or graphs['app_wrapper_after_return']['system_sites']:
        raise ValueError('selected epilogues now contain system instructions')
    return dict(mode='static_LK_payload_normal_return',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,hardware_observed=False,payload_modified=False,
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        gnu_words=len(lines),gnu_relative_targets=len(branches),gnu_selected_operands=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        file_ranges=[[hex(a),hex(b)] for a,b in RANGES],branches=branches,
        selected_operands={hex(pc):dict(word=f'{lines[pc][0]:08x}',op=op,args=args)
                           for pc,(op,args) in SELECTED.items()},
        initial_application_descriptor=app,strings=strings,local_graphs=graphs,
        nominal_chain=dict(payload_link_file_offset='0xfbe18',
            nominal_link_with_delta=hex(DELTA+0xfbe18),delta=hex(DELTA),
            handoff_function='0xfbc10',caller_tail_branches=['0xfabb4','0xfabf0'],
            application_wrapper='0xfaa40',application_call='0xfaa50',application_link='0xfaa54',
            wrapper_result_w0=0,thread_entry_call='0xfa5f0',thread_entry_link='0xfa5f4',
            exit_call='0xfa5f4 -> 0x11aba8',payload_return_value_discarded_at='0xfbe18',
            runtime_links_stack_and_initial_binding_observed=False),
        epilogue_stack_equations=dict(basis='K = SP at handoff and at hypothetical normal payload return',
            handoff_frame_bytes=80,reads_relative_to_K={'0x0':'saved X29','0x8':'saved X30 (nominal FAA54)',
                '0x10':'saved X19','0x18':'saved X20','0x20':'saved X21',
                '0x50':'wrapper saved X29','0x58':'wrapper saved X30 (nominal FA5F4)'},
            sp_after_handoff_epilogue='K+0x50',sp_after_wrapper_epilogue='K+0x60',
            system_state_restored_by_these_two_epilogues=False,
            retained_accessible_memory_and_execution_state_established=False),
        selected_direct_edges_to_rdx=rdx_edges,
        conclusion=dict(normal_return_continuation_exists_in_LK=True,
            normal_return_directly_enters_RDX_in_selected_blocks=False,
            nominal_destination='sbl_boot wrapper returns zero, then thread_exit; unexpected scheduler return reaches panic',
            physical_return_contract_validated=False,reset_retention_demonstrated=False),
        limits=['normal call-return summaries only; no register, stack, scheduler or hardware execution',
                'indirect entry bindings are initial file values or declared context provenance, not runtime proof',
                'external callee effects and other threads may differ; no global absence-of-RDX claim',
                'BLR creates a continuation; it does not establish an Android Image callable-return ABI',
                'no RET patch, MMIO/SMC, phone command, USB client or expanded NEWTIME execution'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as error:
        parser.exit(2,f'inspect_lk_payload_return: {error}\n')
