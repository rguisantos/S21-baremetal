#!/usr/bin/env python3
"""Execute bounded LK cache/tail instructions with supplied system registers.

System accesses and DC/barriers are recorded rather than applied to a CPU
cache/MMU. Three external calls are skipped under an explicit preservation
assumption. No physical memory or payload instruction is executed.
"""
import argparse
import hashlib
import itertools
import json
import random
import struct

from check_lk_cache_handoff import BLOCKS, U64, evidence, model, normalize, read_scenario
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_sboot_hzc2 import bl_target

START = 0xfbdd4
SP_BASE, SP_SIZE, SP_INITIAL = 0x70000000, 0x2000, 0x70001000
SKIPPED = {0xfbdd8: 0xee658, 0xfbde4: 0xf29a0, 0xfbdf0: 0x1b1658}


def emulate(sboot, values):
    v = normalize(values)
    expected = model(v)
    if len(sboot) != IMAGES['sboot'][0] or hashlib.sha256(sboot).hexdigest() != IMAGES['sboot'][1]:
        raise ValueError('emulation requires the exact HZC2 sboot')
    try:
        import unicorn as uc
        from unicorn import arm64_const as r
    except ImportError as error:
        raise ValueError('optional dependency missing: install unicorn==2.1.4') from error
    cpu = uc.Uc(uc.UC_ARCH_ARM64, uc.UC_MODE_ARM)
    for address in (0xfb000, 0x189000, 0x18a000):
        cpu.mem_map(address, 0x1000, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        cpu.mem_write(address, sboot[address:address+0x1000])
    cpu.mem_map(SP_BASE, SP_SIZE, uc.UC_PROT_READ | uc.UC_PROT_WRITE)
    cpu.mem_map(0x4a0000, 0x1000, uc.UC_PROT_READ | uc.UC_PROT_WRITE)
    cpu.mem_write(0x4a0048, struct.pack('<I', v['kernel_offset']))
    target = int(expected['conditional_final_arguments']['target'], 0)
    cpu.mem_map(target & ~0xfff, 0x1000, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
    cpu.mem_write(target, struct.pack('<I', 0xd503201f))  # Synthetic stop, never executed.
    x = [getattr(r, f'UC_ARM64_REG_X{i}') for i in range(31)]
    for i, register in enumerate(x):
        cpu.reg_write(register, 0xa55a000000000000 | i)
    cpu.reg_write(r.UC_ARM64_REG_SP, SP_INITIAL)
    state = {key: v[key] for key in ('sctlr_el1', 'sctlr_el2', 'sctlr_el3', 'daif', 'csselr_el1')}
    events, trace, skipped = [], [], []
    gate_observation = None
    stopped = False

    def advance(engine, pc):
        engine.reg_write(r.UC_ARM64_REG_PC, pc+4)

    def hook(engine, pc, size, _):
        nonlocal stopped, gate_observation
        if pc == target:
            stopped = True
            engine.emu_stop()
            return
        if size != 4 or not any(start <= pc < end for start, end in BLOCKS.values()):
            raise ValueError(f'unexpected execution at {pc:#x}')
        trace.append(hex(pc))
        if pc == 0xfbde0:
            gate_observation = dict(state)
        word = struct.unpack_from('<I', sboot, pc)[0]
        if pc in SKIPPED:
            if bl_target(word, pc) != SKIPPED[pc]:
                raise ValueError('unexpected skipped-call target')
            skipped.append(dict(call=hex(pc), target=hex(SKIPPED[pc])))
            for i, register in enumerate(x[:19]):
                engine.reg_write(register, 0x55aa000000000000 | i)
            engine.reg_write(x[30], pc+4)
            advance(engine, pc)
            return
        reads = {0xd5384240: (0, v['current_el'] << 2),
                 0xd5381000: (0, state['sctlr_el1']),
                 0xd53c1000: (0, state['sctlr_el2']),
                 0xd53e1000: (0, state['sctlr_el3']),
                 0xd53b422e: (14, state['daif']),
                 0xd539002a: (10, v['clidr_el1'])}
        if word in reads:
            register, value = reads[word]
            engine.reg_write(x[register], value)
            advance(engine, pc)
        elif word == 0xd5390004:  # MRS X4, CCSIDR_EL1.
            level = state['csselr_el1'] >> 1
            if state['csselr_el1'] & 1 or str(level) not in v['ccsidr_by_level']:
                raise ValueError('unexpected selected CCSIDR')
            engine.reg_write(x[4], v['ccsidr_by_level'][str(level)])
            advance(engine, pc)
        elif word in (0xd5181000, 0xd51c1000, 0xd51e1000):
            key = {0xd5181000: 'sctlr_el1', 0xd51c1000: 'sctlr_el2', 0xd51e1000: 'sctlr_el3'}[word]
            state[key] = engine.reg_read(x[0])
            events.append(dict(op=key+'_write', value=hex(state[key])))
            advance(engine, pc)
        elif word in (0xd51a0000, 0xd51a0001):
            state['csselr_el1'] = engine.reg_read(x[word & 31])
            events.append(dict(op='csselr_write', value=hex(state['csselr_el1'])))
            advance(engine, pc)
        elif word == 0xd50342df:
            state['daif'] |= 0x80
            events.append(dict(op='daifset_irq', value=hex(state['daif'])))
            advance(engine, pc)
        elif word == 0xd51b422d:
            state['daif'] = engine.reg_read(x[13]) & 0x3c0
            events.append(dict(op='daif_write', value=hex(state['daif'])))
            advance(engine, pc)
        elif word in (0xd5033fdf, 0xd5033f9f):
            events.append(dict(op='isb' if word == 0xd5033fdf else 'dsb_sy'))
            advance(engine, pc)
        elif word == 0xd5087e47:
            events.append(dict(op='dc_cisw', value=hex(engine.reg_read(x[7]))))
            advance(engine, pc)
        elif word & 0xffc00000 == 0xd5000000 and word != 0xd503201f:
            raise ValueError(f'unmodeled system instruction at {pc:#x}')

    cpu.hook_add(uc.UC_HOOK_CODE, hook)
    try:
        cpu.emu_start(START, 0, timeout=1000000, count=50000)
    except uc.UcError as error:
        raise ValueError(f'bounded cache/tail emulation failed: {error}') from error
    actual = {f'x{i}': hex(cpu.reg_read(x[i])) for i in range(6)}
    actual.update(target=hex(cpu.reg_read(r.UC_ARM64_REG_PC)),
                  link_register=hex(cpu.reg_read(x[30])))
    final_sctlrs = {key: hex(state[key]) for key in ('sctlr_el1', 'sctlr_el2', 'sctlr_el3')}
    if (not stopped or gate_observation is None or len(skipped) != 3
            or events != expected['system_operation_trace']
            or actual != expected['conditional_final_arguments']
            or final_sctlrs != expected['sctlr_after_gate']
            or hex(state['daif']) != expected['daif_after_preserved_calls']
            or hex(state['csselr_el1']) != expected['csselr_after_gate']
            or cpu.reg_read(r.UC_ARM64_REG_SP) != SP_INITIAL
            or cpu.reg_read(x[19]) != 0xa55a000000000013):
        raise ValueError('executable cache/tail behavior differs from the supplied-state model')
    return dict(
        mode='unicorn_lk_cache_and_tail_with_supplied_system_state',
        unicorn_version=uc.__version__, sboot_sha256=IMAGES['sboot'][1],
        inputs=expected['inputs'], matches_model=True,
        system_operation_trace=events, sctlr_after_gate=final_sctlrs,
        daif_after_preserved_calls=hex(state['daif']),
        conditional_final_arguments=actual, skipped_calls=skipped,
        visited_instruction_count=len(trace), trace=trace,
        runtime_observed=False, cache_contents_simulated=False,
        translation_simulated=False, system_accesses_supplied_or_recorded=True,
        physical_coherency_verified=False, final_hardware_state_verified=False,
        payload_instruction_executed=False, assumptions=expected['assumptions'])


def scenarios():
    # Small synthetic legacy geometries, not the A55/A78/X1 cache topology.
    profiles = [
        (0, {}),
        (0x01000001, {}),
        (0x01000002, {'0': 2 | (1 << 3) | (3 << 13)}),
        (0x02000023, {'0': 2 | (3 << 3) | (7 << 13), '1': 2 | (2 << 3) | (2 << 13)}),
        (0x03000108, {'2': 2 | (1 << 3) | (4 << 13)}),
        (0x07000000 | (4 << 18), {'6': 2 | (1 << 13)}),
    ]
    result = []
    for el, flags, profile, daif in itertools.product(range(1, 4), range(8), profiles, (0, 0x3c0)):
        m, c, i = flags & 1, (flags >> 1) & 1, (flags >> 2) & 1
        v = dict(current_el=el, sctlr_el1=0x1105, sctlr_el2=0x2205,
                 sctlr_el3=0x3305, daif=daif, clidr_el1=profile[0],
                 csselr_el1=3, ccsidr_by_level=profile[1],
                 kernel_offset=(len(result) % 64)*0x8000)
        v[f'sctlr_el{el}'] = 0x40 | m | (c << 2) | (i << 12)
        result.append(v)
    rng = random.Random(0x18a3a8)
    for _ in range(64):
        el = rng.randrange(1, 4)
        loc = rng.randrange(1, 5)
        clidr, geometries = loc << 24, {}
        for level in range(loc):
            ctype = rng.randrange(5)
            clidr |= ctype << (level*3)
            if ctype >= 2:
                geometries[str(level)] = rng.randrange(4) | (rng.randrange(8) << 3) | (rng.randrange(16) << 13)
        result.append(dict(current_el=el, sctlr_el1=rng.getrandbits(64),
                           sctlr_el2=rng.getrandbits(64), sctlr_el3=rng.getrandbits(64),
                           daif=rng.randrange(16) << 6, clidr_el1=clidr,
                           csselr_el1=rng.randrange(16), ccsidr_by_level=geometries,
                           kernel_offset=rng.randrange(64)*0x8000))
    return result


def self_check(sboot):
    rows, covered, offsets = [], set(), set()
    counts = dict(maintenance_taken=0, maintenance_skipped=0)
    maximum_visits = maximum_dc = 0
    for values in scenarios():
        result = emulate(sboot, values)
        dc = sum(event['op'] == 'dc_cisw' for event in result['system_operation_trace'])
        taken = bool(values[f'sctlr_el{values["current_el"]}'] & 1)
        counts['maintenance_taken' if taken else 'maintenance_skipped'] += 1
        maximum_visits = max(maximum_visits, result['visited_instruction_count'])
        maximum_dc = max(maximum_dc, dc)
        covered.update(result['trace'])
        offsets.add(values['kernel_offset'])
        rows.append({key: result[key] for key in ('inputs', 'system_operation_trace',
                                                 'sctlr_after_gate', 'conditional_final_arguments')})
    encoded = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()
    return dict(
        mode='unicorn_lk_cache_handoff_self_check', unicorn_version=result['unicorn_version'],
        sboot_sha256=IMAGES['sboot'][1], scenario_count=len(rows), all_match=True,
        scenario_generation='288 matrix cases + 64 seed-0x18a3a8 cases',
        deterministic_results_sha256=hashlib.sha256(encoded).hexdigest(),
        branch_counts=counts, distinct_kernel_offsets=len(offsets),
        maximum_instruction_visits=maximum_visits, maximum_dc_operands=maximum_dc,
        visited_instruction_offsets=sorted(covered, key=lambda value: int(value, 0)),
        limits=dict(original_instruction_pages=3, synthetic_target_pages=1,
                    stack_bytes=SP_SIZE, state_pages=1, instruction_budget=50000,
                    timeout_microseconds=1000000, dc_operands_host_limit=4096),
        runtime_observed=False, cache_contents_simulated=False, translation_simulated=False,
        system_accesses_supplied_or_recorded=True, physical_coherency_verified=False,
        final_hardware_state_verified=False, payload_instruction_executed=False,
        assumptions=result['assumptions'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', help='exact raw HZC2 sboot.bin')
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--scenario', help='JSON with all explicit system values')
    choice.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    try:
        evidence(args.sboot)
        sboot = read_exact(args.sboot, *IMAGES['sboot'])
        result = self_check(sboot) if args.self_check else emulate(sboot, read_scenario(args.scenario))
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f'emulate_lk_cache_handoff: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
