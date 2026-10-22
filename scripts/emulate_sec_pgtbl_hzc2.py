#!/usr/bin/env python3
"""Execute the hash-bound LK caller with explicit mocked SMC replies in Unicorn.

This never executes the LDFW provider, SMC, MMIO or printing implementation.
Only instruction pages are mapped; code, instruction budget and exits are
bounded. Results validate the LK response model, not real service returns.
"""
import argparse
import hashlib
import itertools
import json
import random
import struct

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_sec_pgtbl_hzc2 import U64, inspect, response_model
from inspect_sboot_hzc2 import bl_target

START, STOP = 0xfae2c, 0xfaec8
PRINT_CALLS = {0xfae78, 0xfb5cc, 0xfb5e8, 0xfb600,
               0xfb61c, 0xfb634, 0xfb648, 0xfb77c}


def emulate_caller(sboot, base_result, size_result):
    expected = response_model(base_result, size_result)
    if len(sboot) != IMAGES['sboot'][0] or hashlib.sha256(sboot).hexdigest() != IMAGES['sboot'][1]:
        raise ValueError('emulation requires the exact HZC2 sboot')
    try:
        import unicorn as uc
        from unicorn import arm64_const as registers
    except ImportError as error:
        raise ValueError('optional dependency missing: install unicorn==2.1.4') from error
    cpu = uc.Uc(uc.UC_ARCH_ARM64, uc.UC_MODE_ARM)
    for address, size in ((0xf6000, 0x1000), (0xfa000, 0x2000)):
        cpu.mem_map(address, size, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        cpu.mem_write(address, sboot[address:address + size])
    xregs = [getattr(registers, f'UC_ARM64_REG_X{index}') for index in range(31)]
    events, trace = [], []
    replies = (base_result, size_result)

    def hook(engine, pc, size, _):
        if pc == STOP:
            engine.emu_stop()
            return
        if size != 4 or not (START <= pc < STOP or 0xfb5bc <= pc < 0xfb650
                             or 0xfb76c <= pc < 0xfb788 or pc in (0xf6088, 0xf608c)):
            raise ValueError(f'unexpected execution at {pc:#x}')
        trace.append(hex(pc))
        if pc == 0xf6088:
            index = len(events)
            args = [engine.reg_read(reg) for reg in xregs[:4]]
            if index >= 2 or args != [0x82002060, index + 1, 0, 0]:
                raise ValueError('unexpected SMC arguments or extra service call')
            if struct.unpack_from('<I', sboot, pc)[0] != 0xd4000003:
                raise ValueError('expected SMC #0')
            events.append(dict(selector=index + 1, supplied_x0=hex(replies[index])))
            engine.reg_write(xregs[0], replies[index])
            # Other return registers are intentionally not useful pointers.
            for register in xregs[1:4]:
                engine.reg_write(register, 0xa55a000000000000)
            engine.reg_write(registers.UC_ARM64_REG_PC, pc + 4)
        elif pc in PRINT_CALLS:
            # Skip only the identified printf BL. Poison volatile registers;
            # preserve X19..X29 as the LK/AAPCS64 caller expects.
            if bl_target(struct.unpack_from('<I', sboot, pc)[0], pc) != 0x1b1658:
                raise ValueError('unexpected print target')
            for index, register in enumerate(xregs[:19]):
                engine.reg_write(register, 0xa55a000000000000 | index)
            engine.reg_write(xregs[30], pc + 4)
            engine.reg_write(registers.UC_ARM64_REG_PC, pc + 4)

    cpu.hook_add(uc.UC_HOOK_CODE, hook)
    try:
        cpu.emu_start(START, 0, timeout=1000000, count=256)
    except uc.UcError as error:
        raise ValueError(f'bounded LK emulation failed: {error}') from error
    if cpu.reg_read(registers.UC_ARM64_REG_PC) != STOP or len(events) != 2:
        raise ValueError('emulation did not reach the expected exit within its budget')
    actual = dict(normalized_base=hex(cpu.reg_read(xregs[21])),
                  size_low32=hex(cpu.reg_read(xregs[20]) & 0xffffffff),
                  w22_split_flag=cpu.reg_read(xregs[22]) & 0xffffffff,
                  x27_end_wrapped64=hex(cpu.reg_read(xregs[27])))
    matches = all(expected['lk'][key] == value for key, value in actual.items())
    if not matches:
        raise ValueError(f'executable caller differs from response model: {actual}')
    return dict(mode='unicorn_lk_caller_with_mock_smc', unicorn_version=uc.__version__,
                sboot_sha256=IMAGES['sboot'][1], start_pc=hex(START), stop_pc=hex(STOP),
                inputs=expected['inputs'], mock_smc_calls=events,
                visited_instruction_count=len(trace), trace=trace, registers=actual,
                matches_response_model=matches, provider_executed=False,
                runtime_observed=False, memory_map_verified=False, range_is_free=False,
                assumptions=['SMC supplies only the stated X0 replies and preserves X19..X30',
                             'printf is skipped and X0..X18 are poisoned',
                             'PC values are file offsets; no runtime load-base claim'])


def self_check(sboot):
    bases = (0, 3, U64, 0xffffffff, 0xe0001000, 0xe0000000,
             0x100000000, 0xfffffffffff00000)
    sizes = (0, 3, 0xffffffff, 1, 0x1000, 0x180000, 0x200000,
             0x1234567800200000, 0x1234567800000000, 0x1234567800000003)
    scenarios = list(itertools.product(bases, sizes))
    rng = random.Random(0x82002060)
    for index in range(64):
        base = rng.getrandbits(64)
        if index % 2:
            base &= ~0xfffff
        scenarios.append((base, rng.getrandbits(64)))
    results = []
    covered = set()
    for base, size in scenarios:
        result = emulate_caller(sboot, base, size)
        covered.update(result['trace'])
        results.append(dict(inputs=result['inputs'], registers=result['registers'],
                            matches_response_model=result['matches_response_model']))
    return dict(mode='unicorn_lk_caller_self_check_with_mock_smc',
                unicorn_version=result['unicorn_version'], sboot_sha256=IMAGES['sboot'][1],
                start_pc=hex(START), stop_pc=hex(STOP),
                limits=dict(mapped_instruction_pages=3, max_instruction_visits=256,
                            timeout_microseconds=1000000, mmio_mapped=False),
                assumptions=result['assumptions'],
                scenario_count=len(results), all_match=True,
                visited_instruction_offsets=sorted(covered, key=lambda value: int(value, 0)),
                scenarios=results, provider_executed=False, runtime_observed=False,
                memory_map_verified=False, range_is_free=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    parser.add_argument('ldfw')
    parser.add_argument('--base-result', type=lambda value: int(value, 0))
    parser.add_argument('--size-result', type=lambda value: int(value, 0))
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        if args.base_result is not None or args.size_result is not None:
            parser.error('--self-check does not accept individual replies')
    elif args.base_result is None or args.size_result is None:
        parser.error('supply both explicit replies or --self-check')
    try:
        # Validate BOTH images and the container before any scenario execution.
        evidence = inspect(args.sboot, args.ldfw)
        sboot = read_exact(args.sboot, *IMAGES['sboot'])
        report = self_check(sboot) if args.self_check else emulate_caller(
            sboot, args.base_result, args.size_result)
        report['ldfw_sha256'] = evidence['inputs']['ldfw_sha256']
    except (OSError, ValueError) as error:
        parser.exit(1, f'emulate_sec_pgtbl_hzc2: {error}\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
