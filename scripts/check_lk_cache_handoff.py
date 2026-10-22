#!/usr/bin/env python3
"""Hash-bound LK cache-gate evidence and supplied architectural-register model.

Models the selected helper and final arguments under preserved skipped calls.
Does not model cache contents, translations, traps or the physical handoff.
"""
import argparse
import json
import struct

from inspect_el2_hzc2 import IMAGES, calls, read_exact, words

U64, U32 = (1 << 64) - 1, (1 << 32) - 1
MAX_OPERATIONS = 4096  # Host bound, not a firmware check.
FIELDS = ('current_el', 'sctlr_el1', 'sctlr_el2', 'sctlr_el3', 'daif',
          'clidr_el1', 'csselr_el1', 'ccsidr_by_level', 'kernel_offset')
BLOCKS = {
    'current_el': (0x189404, 0x189414),
    'sctlr_getters': (0x189420, 0x189438),
    'set_way': (0x189848, 0x18989c),
    'cache_walk': (0x18997c, 0x1899f0),
    'clear_mc': (0x189db8, 0x189e10),
    'cache_gate': (0x18a3a8, 0x18a430),
    'final_tail': (0xfbdd4, 0xfbe18),
}


def integer(value, name):
    if isinstance(value, str):
        if len(value) > 20:
            raise ValueError(name + ': integer literal too long')
        try:
            value = int(value, 0)
        except ValueError as error:
            raise ValueError(name + ': invalid integer') from error
    if type(value) is not int or not 0 <= value <= U64:
        raise ValueError(name + ': requires unsigned 64-bit value')
    return value


def normalize(values):
    if not isinstance(values, dict) or set(values) != set(FIELDS):
        raise ValueError('supply exactly: ' + ', '.join(FIELDS))
    result = {key: integer(value, key) for key, value in values.items()
              if key != 'ccsidr_by_level'}
    if result['current_el'] not in (1, 2, 3):
        raise ValueError('host model supports EL1/EL2/EL3 only')
    if result['daif'] & ~0x3c0:
        raise ValueError('DAIF must contain only bits 9:6')
    offset = result['kernel_offset']
    if offset > 0x1f8000 or offset % 0x8000:
        raise ValueError('kernel offset outside traced 64-scenario profile')
    supplied = values['ccsidr_by_level']
    if not isinstance(supplied, dict) or any(key not in tuple(map(str, range(7))) for key in supplied):
        raise ValueError('ccsidr_by_level requires canonical string keys 0..6')
    result['ccsidr_by_level'] = {key: integer(value, 'CCSIDR') for key, value in supplied.items()}
    return result


def read_scenario(path):
    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError('duplicate scenario key: ' + key)
            values[key] = value
        return values
    with open(path, 'rb') as stream:
        data = stream.read(8193)
    if len(data) > 8192:
        raise ValueError('scenario exceeds 8192-byte host limit')
    try:
        value = json.loads(data, object_pairs_hook=unique)
    except RecursionError as error:
        raise ValueError('scenario JSON nesting exceeds parser limit') from error
    return normalize(value)


def model(values):
    v = normalize(values)
    el = v['current_el']
    selected = f'sctlr_el{el}'
    sctlrs = {key: v[key] for key in ('sctlr_el1', 'sctlr_el2', 'sctlr_el3')}
    maintenance = bool(sctlrs[selected] & 1)
    final_daif = v['daif'] | 0x80  # Outer DAIFSet #2 at 0xfbdd4.
    operations = [dict(op='daifset_irq', value=hex(final_daif))]
    levels, operands = [], []
    if maintenance:
        operations.extend([dict(op='daifset_irq', value=hex(final_daif)),
                           dict(op='isb'), dict(op='dsb_sy')])
        loc = (v['clidr_el1'] >> 24) & 7
        for level in range(loc):
            cache_type = (v['clidr_el1'] >> (3 * level)) & 7
            if cache_type > 4:
                raise ValueError('reserved CLIDR cache type outside host profile')
            if cache_type < 2:
                continue
            if str(level) not in v['ccsidr_by_level']:
                raise ValueError('missing CCSIDR for selected data-cache level')
            ccsidr = v['ccsidr_by_level'][str(level)]
            shift = (ccsidr & 7) + 4
            max_way, max_set = (ccsidr >> 3) & 0x3ff, (ccsidr >> 13) & 0x7fff
            count = (max_way + 1) * (max_set + 1)
            if count > MAX_OPERATIONS - len(operands):
                raise ValueError('DC operands exceed 4096-operation host limit')
            levels.append(dict(level=level, cache_type=cache_type, line_shift=shift,
                               way_count=max_way + 1, set_count=max_set + 1))
            operations.extend([dict(op='csselr_write', value=hex(level * 2)), dict(op='isb')])
            way_shift = 32 - max_way.bit_length()  # CLZ W; zero -> 32.
            for set_index in range(max_set, -1, -1):
                for way in range(max_way, -1, -1):
                    operand = (level * 2 | ((set_index << shift) & U32)
                               | ((way << (way_shift & 31)) & U32))
                    operands.append(hex(operand))
                    operations.append(dict(op='dc_cisw', value=hex(operand)))
        operations.extend([dict(op='csselr_write', value='0x0'),
                           dict(op='dsb_sy'), dict(op='isb'),
                           dict(op='daif_write', value=hex(final_daif)), dict(op='isb')])
        sctlrs[selected] &= ~5
        operations.extend([dict(op=selected + '_write', value=hex(sctlrs[selected])), dict(op='isb')])
    target = 0x80080000 + v['kernel_offset']
    encoded = {key: hex(value) for key, value in v.items() if key != 'ccsidr_by_level'}
    encoded['ccsidr_by_level'] = {key: hex(value) for key, value in v['ccsidr_by_level'].items()}
    return dict(
        mode='supplied_lk_cache_gate_and_conditional_final_tail', inputs=encoded,
        selected_sctlr=selected, data_maintenance_taken=maintenance,
        sctlr_after_gate={key: hex(value) for key, value in sctlrs.items()},
        daif_after_preserved_calls=hex(final_daif),
        csselr_after_gate=hex(0 if maintenance else v['csselr_el1']),
        current_el_unchanged=el,
        legacy_cache_levels=levels, dc_cisw_operands=operands,
        system_operation_trace=operations,
        conditional_final_arguments=dict(x0='0x8b080000', x1='0x0', x2='0x0', x3='0x0',
                                         x4=hex(target), x5=hex(v['kernel_offset']),
                                         target=hex(target), link_register='0xfbe18'),
        runtime_observed=False, cache_contents_simulated=False,
        translation_simulated=False, physical_coherency_verified=False,
        final_hardware_state_verified=False,
        assumptions=['Initial state is supplied at 0xfbdd4, after the unmodeled SMC -0x3ff',
                     'SCTLR reads are supplied values; no traps, RES1/RAO/WI or CPU errata modeled',
                     'Legacy CCSIDR fields only; CCIDX and actual cache geometry unverified',
                     'Skipped IRQ-disable, mode/output and printf calls preserve modeled system state',
                     'DC/barrier events are recorded, not proof of cache completion on the phone'])


def evidence(path):
    import hashlib
    data = read_exact(path, *IMAGES['sboot'])
    return dict(
        mode='static_read_only_lk_cache_handoff', sboot_sha256=IMAGES['sboot'][1],
        blocks={name: dict(start=hex(start), end_exclusive=hex(end),
                           sha256=hashlib.sha256(data[start:end]).hexdigest())
                for name, (start, end) in BLOCKS.items()},
        calls=calls(data, (0xfbdd0, 0xfbdd8, 0xfbddc, 0xfbde4, 0xfbdf0, 0x18a3b8,
                           0x18a3f8, 0x18a410, 0x18a420, 0x18a428, 0x1899bc)),
        instruction_words=words(data, (0xfbdc0, 0xfbdc4, 0xfbdc8, 0xfbdcc,
                                      0xfbdd4, 0xfbe08, 0xfbe0c, 0xfbe10, 0xfbe14,
                                      0x18a3fc, 0x18a41c, 0x189848, 0x189854,
                                      0x189858, 0x189860, 0x189864, 0x189868,
                                      0x189884, 0x189990, 0x189994, 0x189998,
                                      0x1899d0, 0x1899d4, 0x1899d8, 0x1899e4,
                                      0x189dd4, 0x189df0, 0x189e04, 0x189e08)),
        gate_changes_el=False, gate_explicit_ic_invalidation=False,
        active_el_only=True, m_zero_c_one_is_preserved=True,
        preceding_smc=dict(call='0xfbdd0', wrapper='0xf6088',
                           supplied_x0_by_caller='0xfffffffffffffc01',
                           signed_service_id='-0x3ff', x1_x2_x3_zero=True,
                           semantics_verified=False),
        callbacks_after_gate=['0xfbde4 -> 0xf29a0', '0xfbdf0 -> 0x1b1658'],
        post_cache_calls=calls(data, (0xf29dc, 0xf29ec, 0xf29fc, 0xf2a0c,
                                     0xf2a1c, 0xf2a34, 0xf2a3c, 0xf2a6c,
                                     0xf2a74, 0x1b16fc, 0x1b1724,
                                     0x1b1778, 0x1b1784)),
        unresolved_output_edges=words(data, (0x20c618, 0x20c61c, 0x20c624,
                                             0x20c4c8, 0x20c4dc, 0x20c4e0)),
        post_mode_direct_mmio=dict(helper_targets=['0x15868500', '0x1586c500'],
                                   final_target='0xf0000180',
                                   status='Static stores only; no peripheral state interpreted'),
        runtime_observed=False, final_hardware_state_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', help='exact raw HZC2 sboot.bin')
    parser.add_argument('--scenario', help='JSON with all nine explicit inputs')
    args = parser.parse_args()
    try:
        result = evidence(args.sboot)
        if args.scenario:
            result['scenario'] = model(read_scenario(args.scenario))
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f'check_lk_cache_handoff: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
