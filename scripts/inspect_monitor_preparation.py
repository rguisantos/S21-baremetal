#!/usr/bin/env python3
"""Static HZC2 BL2 request constructors and LK callback mutation sites.

No secure service, MMIO or firmware is executed. Request arguments and
constant-gate witnesses do not establish runtime state or service semantics.
"""
import argparse
import hashlib
import json
import struct

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import DELTA, START, END, flow

U64 = (1 << 64) - 1


def word(data, pc):
    if pc < 0 or pc % 4 or pc + 4 > len(data):
        raise ValueError('instruction outside aligned file bytes')
    return struct.unpack_from('<I', data, pc)[0]


def immediate(data, pc, register):
    w = word(data, pc)
    if w & 31 != register or w & 0xff800000 not in (0xd2800000, 0x92800000):
        raise ValueError('expected X MOVZ/MOVN producer')
    value = ((w >> 5) & 0xffff) << (((w >> 21) & 3) * 16)
    return value if w & 0xff800000 == 0xd2800000 else U64 ^ value


def request(data, mode, entry=0x16500, veneer=0x16420):
    """Reconstruct only the selected fixed wrapper, stopping before SMC."""
    if type(mode) is not int or not 0 <= mode <= 0xffffffff:
        raise ValueError('mode requires explicit unsigned W0')
    if word(data, entry) != 0xa9bf7bfd or word(data, entry+8) != 0x910003fd:
        raise ValueError('unexpected wrapper prologue')
    if word(data, entry+12) != 0x34000080 or word(data, entry+24) != 0x9a8113e1:
        raise ValueError('unexpected mode branch/selection')
    cmp = word(data, entry+16)
    if cmp & 0xffc003ff != 0x7100001f:
        raise ValueError('expected CMP W0 immediate')
    selector = (cmp >> 10) & 0xfff
    source = immediate(data, entry+4, 1) if mode == 0 else (
        immediate(data, entry+20, 1) if mode == selector else 0)
    if flow(word(data, entry+40), entry+40) != ('bl', veneer):
        raise ValueError('unexpected secure veneer call')
    if (word(data, veneer), word(data, veneer+4)) != (0xd4000003, 0xd65f03c0):
        raise ValueError('secure veneer is not SMC/RET')
    return {'mode_w0': hex(mode), 'x0': hex(immediate(data, entry+36, 0)),
            'x1': hex(source), 'x2': hex(immediate(data, entry+32, 2)),
            'x3': hex(immediate(data, entry+28, 3)), 'stopped_before_smc': True}


def branch_candidates(data, target, start=START, end=END):
    if not 0 <= start < end <= len(data) or start % 4 or end % 4:
        raise ValueError('invalid branch scan bounds')
    result = []
    for pc in range(start, end, 4):
        w = word(data, pc)
        if w >> 26 in (5, 37):
            kind, destination = flow(w, pc)
            if destination == target:
                result.append({'offset': hex(pc), 'kind': kind})
    return result


def zero_gate(data, call, gate=0x170750):
    """A narrow proof for BL gate; UXTB W0; CBZ/CBNZ W0 only."""
    if (word(data, gate), word(data, gate+4)) != (0x52800000, 0xd65f03c0):
        raise ValueError('gate is not the pinned MOV W0,0 / RET')
    if flow(word(data, call), call) != ('bl', gate) or word(data, call+4) != 0x53001c00:
        raise ValueError('unsupported gate call/UXTB witness')
    w = word(data, call+8)
    if w & 0x7e00001f != 0x34000000 or w & 0x80000000:
        raise ValueError('expected CBZ/CBNZ W0')
    kind, target = flow(w, call+8)
    if kind != 'conditional':
        raise ValueError('missing gate branch')
    taken = not bool(w & 0x01000000)
    return {'call': hex(call), 'gate': hex(gate), 'gate_w0': '0x0',
            'branch': hex(call+8), 'branch_taken': taken,
            'next_pc': hex(target if taken else call+12),
            'assumption': 'unmodified pinned instructions, normal call/return, no traps'}


def evidence(path):
    data = read_exact(path, *IMAGES['sboot'])
    blocks = {'request_a': (0x16500, 0x16534), 'request_b': (0x36218, 0x3624c),
              'request_caller': (0x1cb04, 0x1cb80), 'mode_table': (0x2fdf8, 0x2fe03),
              'handoff_request': (0x16534, 0x1654c), 'insert': (0x20c578, 0x20c5c8),
              'remove': (0x20c5c8, 0x20c608), 'conditional_insert': (0x16f6b8, 0x16f6e8),
              'conditional_remove': (0x16f6e8, 0x16f718), 'constant_gate': (0x170750, 0x170758),
              'dormant_callback_gate': (0x16f018, 0x16f03c),
              'dormant_callback_return': (0x16f0a4, 0x16f0b8),
              'secure_veneer_a': (0x16420, 0x16428),
              'secure_veneer_b': (0x36138, 0x36140),
              'metadata_query_wrapper': (0xf6178, 0xf6190),
              'metadata_query_caller': (0xf9838, 0xf9864),
              'dormant_callback_return': (0x16f0a4, 0x16f0b8),
              'secure_veneer_a': (0x16420, 0x16428),
              'secure_veneer_b': (0x36138, 0x36140),
              'metadata_query_wrapper': (0xf6178, 0xf6190),
              'metadata_query_caller': (0xf9838, 0xf9864),
              'monitor_header_words': (0x36c300, 0x36c324)}
    if data[0x16500:0x16534] != data[0x36218:0x3624c]:
        raise ValueError('duplicated request wrappers differ')
    examples = []
    for mode in (0, 0x20, 0x14, 0x40, 0xffffffff):
        first, second = request(data, mode), request(data, mode, 0x36218, 0x36138)
        if first != second:
            raise ValueError('duplicate wrapper requests differ')
        examples.append(first)
    objects = []
    for base in (0x2ef138, 0x31e5c8):
        pointer, = struct.unpack_from('<Q', data, base+16)
        objects.append({'object_file_offset': hex(base), 'initial_callback_pointer': hex(pointer),
                        'callback_file_offset_under_lk_delta': hex(pointer-DELTA)})
    return {
        'date': '2026-10-23', 'mode': 'static_read_only_hzc2_monitor_request_and_callback_sites',
        'sboot_sha256': IMAGES['sboot'][1],
        'blocks': {name: {'start': hex(a), 'end_exclusive': hex(b),
                          'sha256': hashlib.sha256(data[a:b]).hexdigest()} for name, (a,b) in blocks.items()},
        'bl2_request': {'wrappers_byte_identical': True, 'examples': examples,
                        'wrapper_a_callers': branch_candidates(data, 0x16500, 0x16000, 0xec000),
                        'wrapper_b_callers': branch_candidates(data, 0x36218, 0x16000, 0xec000),
                        'caller_zero_test_word': f'{word(data,0x1cb6c):08x}',
                        'caller_nonzero_w0_self_loop': '0x1cb70',
                        'x1_units_verified': False, 'x3_role_verified': False,
                        'service_id': '-0xe7', 'secure_handler_executed': False,
                        'correlations_only': {'0x36c_times_4096': hex(0x36c*4096),
                                              '0x1b61_times_512': hex(0x1b61*512),
                                              'candidate_monitor_container': ['0x36c000','0x3ac000']},
                        'later_request': {'tail_branch': '0x1612c', 'wrapper': '0x16534',
                                           'service_id': '-0xe8', 'x1': '0x0', 'x2': '0x0',
                                           'x3': '0xbffff000', 'semantics_verified': False}},
        'monitor_header_raw_words': {hex(pc): f'{word(data,pc):08x}'
                                     for pc in range(0x36c310,0x36c324,4)},
        'monitor_metadata_query': {'call': '0xf9844', 'wrapper': '0xf6178', 'smc': '0xf6188',
                                   'service_id': '-0x12d', 'buffer_bytes': '0xb4',
                                   'plaintext_handler_dump_proven': False},
        'callback_mutation': {
            'scan_range_file_offsets': [hex(START),hex(END)],
            'insert_direct_candidates': branch_candidates(data,0x20c578),
            'remove_direct_candidates': branch_candidates(data,0x20c5c8),
            'gate_witnesses': [zero_gate(data,pc) for pc in (0x16f6c0,0x16f6f0,0x16f030)],
            'initial_objects': objects,
            'insert_stores': {'0x20c590':'E[0]=H; E[8]=old_H8',
                               '0x20c598':'old_H8[0]=E', '0x20c59c':'H[8]=E'},
            'remove_stores': {'0x20c5d8':'E8[0]=E0', '0x20c5e0':'E0[8]=E8',
                               '0x20c5e4':'E[0]=0; E[8]=0'},
            'E_is_supplied_node': True, 'H_is_list_head_file_offset': '0x3218c0',
            'dormant_object': '0x31e5c8',
            'runtime_list_complete': False, 'operation_table_immutability_proven': False},
        'runtime_observed': False, 'smc_minus_3ff_semantics_verified': False,
        'firmware_modified': False, 'Samsung_tested': False,
        'limitations': ['B/BL census scans aligned words in declared LK code; not all possible aliases or indirect calls',
                        'No whole-program pointer analysis or runtime code/table/list mutation bounds',
                        'Arguments identify a request, not read/verify/decrypt/copy semantics or actual storage units',
                        'Header literals, nominal LK delta and mode samples do not establish RAM ownership',
                        'No secure response supplied or executed; SMC -0x3ff remains a separate unresolved service']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');args=p.parse_args()
    try:
        print(json.dumps(evidence(args.sboot),indent=2))
    except (OSError,ValueError,struct.error) as exc:
        p.exit(2,'Monitor preparation audit failed: '+str(exc)+'\n')
