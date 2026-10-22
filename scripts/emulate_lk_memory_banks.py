#!/usr/bin/env python3
"""Check LK RAM-node arguments in bounded Unicorn sections with supplied inputs.

SMC replies, the RAM getter and the Harx helper are replaced. FDT setup and
the 0xfd bootargs branch are skipped; bank calls are recorded, not executed.
This executes neither secure firmware nor an FDT editor or physical MMIO.
"""
import argparse
import hashlib
import itertools
import json
import random
import struct

from check_lk_memory_banks import CHUNK, FIELDS, LOW_BASE, evidence, model, normalize, read_scenario
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_sec_pgtbl_hzc2 import U32, U64
from inspect_sboot_hzc2 import bl_target

START, STOP = 0xfad60, 0xfaf84
CALLS = {0xfaf34, 0xfaf50, 0xfaf74, 0xfb678, 0xfb690,
         0xfb740, 0xfb7a8, 0xfb7c8}
PARKS = {0xfadc4: 'soc_version_park_0xfadc4',
         0xfb66c: 'soc_base_park_0xfb66c',
         0xfb65c: 'soc_size_park_0xfb65c'}
SP_BASE, SP_SIZE = 0x70000000, 0x20000


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
    for address, size in ((0xf6000, 0x1000), (0xfa000, 0x2000)):
        cpu.mem_map(address, size, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        cpu.mem_write(address, sboot[address:address + size])
    cpu.mem_map(SP_BASE, SP_SIZE, uc.UC_PROT_READ | uc.UC_PROT_WRITE)
    x = [getattr(r, f'UC_ARM64_REG_X{i}') for i in range(31)]
    for i, register in enumerate(x):
        cpu.reg_write(register, 0xa55a000000000000 | i)
    cpu.reg_write(r.UC_ARM64_REG_SP, SP_BASE + SP_SIZE)
    service = U64 - 0x12d  # Sign-extended -0x12e in X0.
    replies = [(service, 0, v['soc_version_x0']),
               (service, 2, v['soc_base_x0']),
               (service, 1, v['soc_reserved_size_x0']),
               (0x82002060, 1, v['pgtbl_base_x0']),
               (0x82002060, 2, v['pgtbl_size_x0'])]
    smcs, requests, trace = [], [], []
    stopped = None
    bypasses = 0

    def supplied_return(engine, pc, result):
        # Simulate only a callee-saved ABI return; poison all volatile values.
        for i, register in enumerate(x[:19]):
            engine.reg_write(register, 0xa55a000000000000 | i)
        engine.reg_write(x[0], result)
        engine.reg_write(x[30], pc + 4)
        engine.reg_write(r.UC_ARM64_REG_PC, pc + 4)

    def hook(engine, pc, size, _):
        nonlocal stopped, bypasses
        if pc == STOP or pc in PARKS:
            stopped = PARKS.get(pc, 'bank_calls_complete')
            engine.emu_stop()
            return
        allowed = (START <= pc <= 0xfaef4 or 0xfaf28 <= pc < STOP
                   or 0xfb5bc <= pc < 0xfb670 or 0xfb670 <= pc < 0xfb698
                   or 0xfb730 <= pc < 0xfb748 or 0xfb748 <= pc < 0xfb788
                   or 0xfb788 <= pc < 0xfb7d0 or pc in (0xf6088, 0xf608c))
        if size != 4 or not allowed:
            raise ValueError(f'unexpected execution at {pc:#x}')
        trace.append(hex(pc))
        if pc == 0xfaef4:
            # Both bootargs paths rejoin at FAF28. Do not execute setup,
            # global loads, the MMIO boot flag or either FDT operation.
            bypasses += 1
            engine.reg_write(r.UC_ARM64_REG_PC, 0xfaf28)
            return
        word = struct.unpack_from('<I', sboot, pc)[0]
        if pc == 0xf6088:
            i = len(smcs)
            args = [engine.reg_read(register) for register in x[:4]]
            if i >= len(replies) or args != [*replies[i][:2], 0, 0] or word != 0xd4000003:
                raise ValueError('unexpected SMC instruction, arguments or extra call')
            smcs.append(dict(service=hex(args[0]), index=args[1], supplied_x0=hex(replies[i][2])))
            for j, register in enumerate(x[1:19]):
                engine.reg_write(register, 0xa55a000000000001 + j)
            engine.reg_write(x[0], replies[i][2])
            engine.reg_write(r.UC_ARM64_REG_PC, pc + 4)
        elif word >> 26 == 0b100101:
            target = bl_target(word, pc)
            if target == 0xf6088 and pc in (0xfada0, 0xfadd8, 0xfadf8, 0xfae40, 0xfae90):
                pass  # Execute BL/RET; intercept only the SMC instruction.
            elif target == 0x1b1658:
                supplied_return(engine, pc, 0)
            elif pc == 0xfad84 and target == 0x11b758:
                supplied_return(engine, pc, v['total_ram_bytes'])
            elif pc == 0xfaee8 and target == 0xf9320:
                pointers = [engine.reg_read(register) for register in x[:2]]
                if not all(SP_BASE <= p <= SP_BASE + SP_SIZE - 8 for p in pointers):
                    raise ValueError('Harx output pointers outside the stack')
                engine.mem_write(pointers[0], struct.pack('<Q', v['harx_base']))
                engine.mem_write(pointers[1], struct.pack('<Q', v['harx_size']))
                supplied_return(engine, pc, v['harx_status_w0'])
            elif pc in CALLS and target == 0xf1570:
                requests.append(dict(call_offset=hex(pc),
                                     base=hex(engine.reg_read(x[0])),
                                     size_low32=hex(engine.reg_read(x[1]) & U32)))
                supplied_return(engine, pc, 0)
            else:
                raise ValueError(f'unexpected BL at {pc:#x} to {target:#x}')

    cpu.hook_add(uc.UC_HOOK_CODE, hook)
    try:
        cpu.emu_start(START, 0, timeout=1000000, count=4096)
    except uc.UcError as error:
        raise ValueError(f'bounded bank emulation failed: {error}') from error
    projected = [{key: row[key] for key in ('call_offset', 'base', 'size_low32')}
                 for row in expected['requested_nodes']]
    expected_smcs = 5 if expected['stop'] == 'bank_calls_complete' else {
        'soc_version_park_0xfadc4': 1, 'soc_base_park_0xfb66c': 2,
        'soc_size_park_0xfb65c': 3}[expected['stop']]
    if (stopped != expected['stop'] or requests != projected
            or len(smcs) != expected_smcs
            or bypasses != int(stopped == 'bank_calls_complete')):
        raise ValueError('executable bank-call sequence differs from supplied-input model')
    return dict(
        mode='unicorn_lk_bank_sections_with_supplied_inputs',
        unicorn_version=uc.__version__, sboot_sha256=IMAGES['sboot'][1],
        inputs=expected['inputs'], stop=stopped, requested_calls=requests,
        supplied_smc_calls=smcs, visited_instruction_count=len(trace), trace=trace,
        matches_model=True, provider_executed=False, runtime_observed=False,
        mmio_mapped=False, fdt_editor_executed=False, memory_map_verified=False,
        assumptions=['RAM getter, Harx helper, SMC and printf preserve X19..X29',
                     'FDT preparation and both bootargs paths omitted at FAEF4 -> FAF28',
                     'Writer calls captured before execution; no FDT success claim',
                     'PCs are file offsets, not a recovered runtime mapping'])


def scenarios():
    # Synthetic values for reproducible checks; none are device observations.
    seed = dict(zip(FIELDS, (0xa0000000, 0x66001000, 0xc0000000, 0x2000000,
                            0xe0000000, 0x200000, 0, 0xc4000000, 0x1400000)))
    pg_pairs = ((0, 0), (3, 3), (U64, U32), (0xe0001000, 0x180001),
                (0xe0000000, 0x1003), (0xfffffffffff00000, 0x200000))
    harx_states = ((0, 0xc4000000, 0x1400000), (1, 0xc4000000, 0x1400000),
                   (0, 0, 0x1400000), (0, 0xc4000000, 0))
    totals = (0, 0x40000000, 0x7fffffff, LOW_BASE, LOW_BASE + 1,
              0xa0000000, 3 << 30, 12 << 30)
    values = []
    for total, pg, harx in itertools.product(totals, pg_pairs, harx_states):
        v = dict(seed, total_ram_bytes=total, pgtbl_base_x0=pg[0],
                 pgtbl_size_x0=pg[1], harx_status_w0=harx[0],
                 harx_base=harx[1], harx_size=harx[2])
        values.append(v)
    for key, value in [('soc_version_x0', 0), ('soc_version_x0', U64),
                       ('soc_base_x0', U64), ('soc_reserved_size_x0', U32),
                       ('soc_reserved_size_x0', 0x12345678ffffffff),
                       ('soc_version_x0', 0x1234567866001000),
                       ('soc_base_x0', 0xfffffffffffffffe),
                       ('soc_reserved_size_x0', 0x1234567800200000)]:
        values.append(dict(seed, **{key: value}))
    values.extend([
        dict(seed, total_ram_bytes=LOW_BASE + 126 * CHUNK,
             pgtbl_base_x0=0, pgtbl_size_x0=0, harx_status_w0=1),
        dict(seed, soc_base_x0=U64-1, soc_reserved_size_x0=1,
             pgtbl_base_x0=0, pgtbl_size_x0=0, harx_status_w0=1),
        dict(seed, harx_base=U64-1, harx_size=2),
        dict(seed, pgtbl_size_x0=0x1234567800000003),
    ])
    rng = random.Random(0xfad60)
    for _ in range(64):
        v = dict(seed, total_ram_bytes=rng.randrange(16 << 30),
                 soc_base_x0=rng.getrandbits(64),
                 soc_reserved_size_x0=rng.getrandbits(64),
                 pgtbl_base_x0=rng.getrandbits(64) & ~0xfffff,
                 pgtbl_size_x0=rng.getrandbits(64),
                 harx_status_w0=rng.getrandbits(32),
                 harx_base=rng.getrandbits(64), harx_size=rng.getrandbits(64))
        values.append(v)
    return values


def self_check(sboot):
    rows, covered, stops = [], set(), {}
    maximum_visits = maximum_calls = 0
    for values in scenarios():
        result = emulate(sboot, values)
        covered.update(result['trace'])
        stops[result['stop']] = stops.get(result['stop'], 0) + 1
        maximum_visits = max(maximum_visits, result['visited_instruction_count'])
        maximum_calls = max(maximum_calls, len(result['requested_calls']))
        rows.append({key: result[key] for key in ('inputs', 'stop', 'requested_calls')})
    encoded = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()
    return dict(
        mode='unicorn_lk_bank_sections_self_check', unicorn_version=result['unicorn_version'],
        sboot_sha256=IMAGES['sboot'][1], scenario_count=len(rows), all_match=True,
        deterministic_scenario_results_sha256=hashlib.sha256(encoded).hexdigest(),
        scenario_generation='192 Cartesian + 12 boundary + 64 seed-0xfad60 cases',
        stop_counts=stops, maximum_instruction_visits=maximum_visits,
        maximum_requested_calls=maximum_calls,
        visited_instruction_offsets=sorted(covered, key=lambda value: int(value, 0)),
        limits=dict(instruction_pages=3, stack_bytes=SP_SIZE, timeout_microseconds=1000000,
                    instruction_budget_per_case=4096, requested_calls_host_limit=128),
        assumptions=result['assumptions'], provider_executed=False,
        runtime_observed=False, fdt_editor_executed=False,
        mmio_mapped=False, memory_map_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', help='exact raw HZC2 sboot.bin')
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--scenario', help='JSON with all nine explicit inputs')
    choice.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    try:
        evidence(args.sboot)
        sboot = read_exact(args.sboot, *IMAGES['sboot'])
        result = self_check(sboot) if args.self_check else emulate(sboot, read_scenario(args.scenario))
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f'emulate_lk_memory_banks: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
