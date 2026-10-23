#!/usr/bin/env python3
"""Bounded, hash-bound static CFG of the selected HZC2 final LK calls.

Explores both conditional paths without executing firmware. Initial object
bindings are expansions under explicit assumptions, not runtime target proof.
"""
import argparse
import hashlib
import json
import struct

from inspect_el2_hzc2 import IMAGES, read_exact

START, END = 0xec000, 0x20c630
DELTA = 0xe7f14000
HANDOFF = 0xfbe14
TABLE, TABLE_BASE, TABLE_COUNT = 0x26219c, 0x1b0718, 91


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def flow(word, pc):
    """Decode only the A64 control forms needed by this exact image.

    Unsupported branch/system-control encodings fail closed. Ordinary
    arithmetic/load/store instructions are not interpreted or validated.
    """
    if word >> 26 in (5, 37):
        return ('bl' if word >> 26 == 37 else 'b', pc + 4 * signed(word & 0x3ffffff, 26))
    if word & 0xff000010 == 0x54000000:
        return 'conditional', pc + 4 * signed((word >> 5) & 0x7ffff, 19)
    if word & 0x7e000000 == 0x34000000:
        return 'conditional', pc + 4 * signed((word >> 5) & 0x7ffff, 19)
    if word & 0x7e000000 == 0x36000000:
        return 'conditional', pc + 4 * signed((word >> 5) & 0x3fff, 14)
    kind = word & 0xfffffc1f
    if kind in (0xd61f0000, 0xd63f0000, 0xd65f0000):
        return {0xd61f0000: 'br', 0xd63f0000: 'blr', 0xd65f0000: 'ret'}[kind], (word >> 5) & 31
    if word == 0xd69f03e0:
        return 'eret', None
    if word & 0xffe0001f in (0xd4000001, 0xd4000002, 0xd4000003):
        return 'exception_call', None
    if word >> 24 == 0xd5:
        return 'system', None
    if word == 0:
        return 'udf', None
    if word & 0x1c000000 == 0x14000000:
        raise ValueError(f'unsupported A64 control word {word:08x} at {pc:#x}')
    return 'linear', None


def walk(data, roots, *, bindings=None, terminal=(), start=START, end=END, limit=8192):
    if start < 0 or start % 4 or end % 4 or not start < end <= len(data):
        raise ValueError('invalid file-backed code bounds')
    bindings = bindings or {}
    pending, visited, calls, indirect, systems, exits = list(roots), {}, {}, {}, {}, {}
    while pending:
        pc = pending.pop()
        if pc in visited:
            continue
        if type(pc) is not int or pc % 4 or not start <= pc < end:
            raise ValueError('control target outside aligned LK code')
        if len(visited) >= limit:
            raise ValueError('static PC budget exceeded')
        word, = struct.unpack_from('<I', data, pc)
        kind, target = flow(word, pc)
        visited[pc] = word
        if pc in terminal:
            if kind != 'blr':
                raise ValueError('expected BLR at handoff boundary')
            exits[pc] = {'kind': 'handoff_boundary', 'register': target}
            continue
        if kind in ('b', 'bl', 'conditional'):
            pending.append(target)
            if kind == 'bl':
                calls[pc] = target
        elif kind in ('br', 'blr'):
            expansion = bindings.get(pc, {})
            indirect[pc] = dict(kind=kind, register=target, **expansion)
            pending.extend(expansion.get('targets', ()))
        elif kind == 'system':
            systems[pc] = word
        elif kind in ('eret', 'exception_call', 'udf'):
            exits[pc] = {'kind': kind, 'word': f'{word:08x}'}
        if kind not in ('b', 'br', 'ret', 'eret', 'udf'):
            pending.append(pc + 4)
    packed = b''.join(struct.pack('<II', pc, word) for pc, word in sorted(visited.items()))
    return dict(visited=visited, calls=calls, indirect=indirect, systems=systems, exits=exits,
                instruction_index_sha256=hashlib.sha256(packed).hexdigest())


def table_targets(data, table=TABLE, base=TABLE_BASE, count=TABLE_COUNT):
    if count != 91 or table < 0 or table + 2 * count > len(data):
        raise ValueError('unsupported/truncated formatter table')
    entries = struct.unpack_from('<91h', data, table)
    targets = [base + 4 * entry for entry in entries]
    if any(not 0x1b04e8 <= target < 0x1b10e8 or target % 4 for target in targets):
        raise ValueError('formatter target outside known function')
    return targets


def summarize(graph):
    words = graph['visited']
    ranges = []
    for pc in sorted(words):
        if ranges and ranges[-1][1] == pc:
            ranges[-1][1] = pc + 4
        else:
            ranges.append([pc, pc + 4])
    return dict(
        instruction_count=len(words), instruction_index_sha256=graph['instruction_index_sha256'],
        file_ranges=[[hex(a), hex(b)] for a, b in ranges],
        direct_calls={hex(pc): hex(target) for pc, target in sorted(graph['calls'].items())},
        indirect_edges={hex(pc): dict(edge, targets=[hex(x) for x in edge.get('targets', ())])
                        for pc, edge in sorted(graph['indirect'].items())},
        system_words={hex(pc): f'{word:08x}' for pc, word in sorted(graph['systems'].items())},
        register_write_sites=[hex(pc) for pc, word in sorted(graph['systems'].items())
                              if word & 0xfff00000 == 0xd5100000],
        exits={hex(pc): value for pc, value in sorted(graph['exits'].items())})


def evidence(path):
    data = read_exact(path, *IMAGES['sboot'])
    direct = walk(data, [0xfbde0], terminal=[HANDOFF])
    table = table_targets(data)
    bindings = {pc: dict(targets=[0x1b14e0, 0x1afcb0],
                         basis='fixed callback producers in printf and bounded-buffer formatter; context union')
                for pc in range(0x1b04e8, 0x1b10e8, 4)
                if struct.unpack_from('<I', data, pc)[0] == 0xd63f0260}
    bindings[0x1b0714] = dict(targets=sorted(set(table)), basis='91 signed halfwords, 26 distinct targets')
    bindings[0x20c624] = dict(targets=[0x20c478], basis='initial file-backed operation table; mutable at runtime')
    bindings[0x20c4dc] = dict(targets=[0xff6c8], basis='one known registered object; mutable list, not exhaustive')
    expanded = walk(data, [0xfbde0], bindings=bindings, terminal=[HANDOFF])
    irq = walk(data, [0xee658])
    u64 = lambda off: struct.unpack_from('<Q', data, off)[0]
    pointers = []
    for off, expected in ((0x31fff0, 0x3218b0), (0x3218b8, 0x2906f8),
                          (0x2906f8, 0x20c478), (0x2ef148, 0xff6c8)):
        pointer = u64(off)
        if pointer - DELTA != expected:
            raise ValueError('initial console pointer changed')
        pointers.append(dict(location=hex(off), initial_pointer=hex(pointer), file_offset=hex(expected)))
    blocks = {'smc_caller': (0xfbdc0, 0xfbdd4), 'smc_wrapper': (0xf6088, 0xf6090),
              'formatter_table': (TABLE, TABLE + 2 * TABLE_COUNT),
              'el1_lock_wait': (0x12ced8, 0x12cf4c), 'zero_fill': (0x1af540, 0x1af684),
              'uart_poll': (0xef4c0, 0xef4f4), 'monitor_entry': (0x36c020, 0x36c0b4),
              'monitor_entry_helper_bytes': (0x3813e4, 0x381430),
              'monitor_vector_bytes': (0x385000, 0x385080)}
    return dict(
        mode='static_read_only_hzc2_selected_final_edges', sboot_sha256=IMAGES['sboot'][1],
        roots_after_cache=['0xfbde0'], stop_before_payload='0xfbe14',
        direct_only=summarize(direct), expanded_known_templates=summarize(expanded),
        irq_call_before_cache=summarize(irq), initial_console_pointers=pointers,
        formatter_table=dict(offset=hex(TABLE), entries=91, signed_halfwords=True,
                             target_base=hex(TABLE_BASE), targets=[hex(x) for x in table]),
        blocks={name: dict(start=hex(a), end_exclusive=hex(b),
                           sha256=hashlib.sha256(data[a:b]).hexdigest()) for name, (a, b) in blocks.items()},
        smc_before_cache=dict(call='0xfbdd0', wrapper='0xf6088', words=['d4000003', 'd65f03c0'],
                              x0='0xfffffffffffffc01', x1_x2_x3=0, result_not_tested_by_caller=True,
                              service_semantics_verified=False, monitor_handler_located=False),
        monitor_unresolved=dict(entry_call='0x36c038', target='0x3813e4',
                                target_words=[f'{struct.unpack_from("<I", data, p)[0]:08x}'
                                              for p in range(0x3813e4, 0x3813f4, 4)],
                                vbar_adr='0x36c044', vector_file_offset='0x385000',
                                vector_words=[f'{struct.unpack_from("<I", data, p)[0]:08x}'
                                              for p in range(0x385000, 0x385010, 4)],
                                plaintext_code_verified=False, encryption_proven_by_this_audit=False),
        observations=dict(el1_m_reads=['0x12cee0', '0x12cf1c', '0x1af608'],
                          conditional_zero_by_dc_zva='0x1af664',
                          irq_mask_restore=['0x20c4b0', '0x20c4f0'],
                          uart_poll_without_timeout='0xef4d4',
                          no_msr_register_form_writes_in_expanded_nodes=not summarize(expanded)['register_write_sites']),
        runtime_observed=False, physical_coherency_verified=False, final_state_verified=False,
        runtime_graph_complete=False,
        limitations=['Both conditional paths explored, without argument/path feasibility analysis',
                     'Known formatter callbacks are a context union, not arbitrary indirect targets',
                     'Initial operation table and registered callback do not bound runtime mutations',
                     'No secure handler execution or plaintext recovery; entropy alone is not encryption proof',
                     'No traps, cache/MMU effects, MMIO responses, callback termination or physical entry verified'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('sboot')
    args = p.parse_args()
    try:
        print(json.dumps(evidence(args.sboot), indent=2))
    except (OSError, ValueError, struct.error) as exc:
        p.exit(2, 'Final-edge audit failed: ' + str(exc) + '\n')
