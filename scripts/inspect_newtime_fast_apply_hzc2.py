#!/usr/bin/env python3
"""Hash-bound DVFS fast-apply loop and dependency dispatch; no device execution."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal, thumb_target
from inspect_el2_hzc2 import IMAGES, read_exact

DOM = 0x2f44c
RANGES = ((0x56e98, 0x56eac), (0x5a938, 0x5a99e),
          (0x5ba90, 0x5baa2), (0x5baa4, 0x5bada),
          (0x59a8c, 0x59a8e), (0x599ec, 0x59a00),
          (0x5b790, 0x5ba00))
SELECTED = {
    0x56e9c: ('ldr', 'r2, [r3, #0]'),
    0x56ea4: ('bl', '0x5a938'),
    0x5a950: ('subs', 'r3, #8'),
    0x5a954: ('bls.n', '0x5a944'),
    0x5a956: ('cmp', 'r4, #19'),
    0x5a958: ('beq.n', '0x5a994'),
    0x5a95a: ('ldr', 'r3, [r5, #12]'),
    0x5a95c: ('ldrh', 'r3, [r3, #22]'),
    0x5a96c: ('ldr', 'r1, [r3, #32]'),
    0x5a972: ('bl', '0x5ba90'),
    0x5a97a: ('bl', '0x5baa4'),
    0x5a986: ('ldr', 'r1, [r3, #32]'),
    0x5a98c: ('bl', '0x59a8c'),
    0x5a998: ('str', 'r2, [r3, #0]'),
    0x5a99a: ('movs', 'r0, #0'),
    0x5ba92: ('ldr', 'r3, [r0, #44]'),
    0x5ba96: ('blx', 'r3'),
    0x5ba9a: ('movs', 'r2, #2'),
    0x5ba9c: ('bl', '0x5b790'),
    0x5baaa: ('ldrb', 'r6, [r3, #9]'),
    0x5bab2: ('ldr', 'r3, [r7, #12]'),
    0x5bab8: ('ldrb', 'r0, [r3, #0]'),
    0x5bac4: ('ldr', 'r1, [r3, #24]'),
    0x5bacc: ('bl', '0x5ba90'),
    0x5bad2: ('cmp', 'r6, r4'),
    0x5bad6: ('movs', 'r0, #0'),
    0x59a8c: ('bx', 'lr'),
    0x599ee: ('bl', '0x59e34'),
    0x599f2: ('bl', '0x5a004'),
    0x599f6: ('movs', 'r0, #2'),
    0x599f8: ('bl', '0x5a2b8'),
    0x599fc: ('movs', 'r0, #0'),
    0x5b87a: ('bl', '0x5adb0'),
    0x5b904: ('blx', 'r7'),
    0x5b97a: ('blx', 'r5'),
    0x5b9ec: ('movs', 'r0, #0'),
}


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    cmd = ['bash', str(root / 'scripts/cross-run.sh'), str(root / 'tools/root'),
           str(root / 'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    rows, literals, covered = {}, {}, set()
    relative = 0
    for lo, hi in RANGES:
        part = parse_thumb(subprocess.check_output(cmd + [
            '-D', '-z', '-b', 'binary', '-m', 'arm', '-M', 'force-thumb',
            f'--start-address={lo}', f'--stop-address={hi}',
            str(Path(path).resolve())], text=True))
        if rows.keys() & part.keys():
            raise ValueError('overlapping ranges')
        rows.update(part)
    for pc, (raw, op, args) in rows.items():
        if raw != data[pc:pc + len(raw)] or op.startswith('.') or op == 'udf':
            raise ValueError('GNU byte mismatch')
        covered.update(range(pc, pc + len(raw), 2))
        target = thumb_target(data, pc)
        if target is not None:
            if int(args.split('@')[0].split(',')[-1].strip(), 0) != target:
                raise ValueError('branch mismatch')
            relative += 1
        if op == 'ldr' and '[pc,' in args:
            at, value = thumb_literal(data, pc, int(args.split(',')[0][1:]))
            if f'(0x{at:x})' not in args:
                raise ValueError('literal mismatch')
            literals[at] = value
    if covered != {pc for lo, hi in RANGES for pc in range(lo, hi, 2)}:
        raise ValueError('coverage mismatch')
    for pc, expected in SELECTED.items():
        _, op, args = rows[pc]
        if (op, args.split('@')[0].strip()) != expected:
            raise ValueError(f'operand mismatch {pc:#x}')
    word = lambda a: struct.unpack_from('<I', data, a)[0]
    anchors = {0x5a9a0: DOM, 0x5a9a4: 0xa590010c, 0x5badc: DOM,
               0x56eac: 0xa590010c, 0x56eb0: 0xabcd1234,
               0x5cc78: 0x2c1ed, 0x5ba14: 0x2eccc,
               0x5c4dc: 0x2a321, 0x5c4e0: 0x29af9}
    if any(word(at) != value for at, value in anchors.items()):
        raise ValueError('anchor mismatch')
    magic_bytes = struct.pack('<I', 0xabcd1234)
    occurrences, cursor = [], 0
    while True:
        cursor = data.find(magic_bytes, cursor)
        if cursor < 0:
            break
        occurrences.append(hex(cursor))
        cursor += 1
    return dict(
        source_base='f7caa3ecd3e37c8ce75b67d88462f8aafae4040b',
        sboot_sha256=IMAGES['sboot'][1],
        scope='local loop, dependency wrapper and selected fallback edges; opaque callees remain conditional',
        loop=dict(entry='0x5a938',descriptor_base=hex(DOM),stride=48,
            direct_indices=list(range(1,8))+list(range(11,19)),
            skipped_indices=[0,8,9,10],terminal_index=19,
            selector='M16[u32(M32[entry+12]+22)] != 0',
            direct='0x5a972 ->0x5ba90(entry,M32[entry+32]>>8)',
            dependencies='0x5a97a ->0x5baa4(entry)',
            after_call='reload M32[entry+32]>>8, call0x59a8c(index,value); literal BX LR leaf',
            callee_results='not tested in loop; dependency wrapper also ignores child returns',
            completion='after selected callees return, clear0xa590010c at0x5a998 and return0',
            physical_success=False),
        wrapper=dict(entry='0x5ba90',custom='M32[entry+44] nonzero ->BLX custom(entry,value)',
            fallback='zero ->0x5b790(entry,value,2)',
            dependency_count='capture M8[u32(M32[entry+12]+9)] once',
            dependency_ids='reload parent+12 each iteration, read u8(header+36+j)',
            dependency_target='u32(DOM+48*id); read M32[M32[target+12]+24] as full u32',
            local_id_filter=False,duplicate_filter=False,dependency_recursion=False,
            count_reloaded=False,
            caveat='no recursion in local dependency wrapper; callbacks/fallback may have further effects'),
        domain0=dict(file_callback='0x599ec',initial_core_pointer='0x2c1ed',
            selected_path='dependency id0 ->wrapper custom+44 ->0x599ec if preserved',
            callees=['0x59e34','0x5a004','0x5a2b8'],last_argument0=2,
            callee_results='first R0 feeds second; third is supplied R0=2; returns discarded at end',
            return_value=0,subcmd8_9_reachability_proven=False),
        fallback=dict(entry='0x5b790',opaque_for_host_tests=True,
            lookup='0x5b87a calls0x5adb0; other calls/branches remain state-dependent',
            interface='core0x2eccc+16/+20 ->initial0x57b20/0x572f8 under preserved table',
            local_return='0x5b9ec returns0 after selected callees return; no physical acknowledgement inferred'),
        initial_descriptors=[dict(index=i,file=hex(0x5cc4c+48*i),
            words=list(struct.unpack_from('<12I',data,0x5cc4c+48*i))) for i in range(19)],
        magic_search=dict(kind='exact four-byte little-endian occurrence, all sboot bytes',
            value='0xabcd1234',occurrences=occurrences,
            meaning='the selected match is a comparison literal, not a demonstrated writer',
            producer_resolved=False,computed_or_external_producers_excluded=False),
        conditions=['installed/preserved code and descriptor roots; explicit readable headers',
            'callback magic and event reach method0; MMIO alias/freshness/visibility unverified',
            'callees return and preserve carried ABI state; hooks do not model physical effects'],
        not_proven=['producer of0xabcd1234','all transitive effects or readers of0x104',
            'direct-channel release of DMC8/9','ordering init9 versus late mask stores','slot47/X0'],
        anchors={hex(a):v for a,v in anchors.items()},
        literals={hex(a):v for a,v in sorted(literals.items())},
        witnesses=[dict(pc=hex(p),bytes=raw.hex(),op=op,args=args)
                   for p,(raw,op,args) in sorted(rows.items())],
        gnu=dict(instructions=len(rows),halfwords=len(covered),relative_targets=relative,
                 literals=len(literals),selected_operands=len(SELECTED)),
        firmware_executed=False,slot47_resolved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sboot');p.add_argument('--json',required=True);a=p.parse_args()
    try:
        result=inspect(a.sboot)
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        p.exit(2,str(error)+'\n')
    Path(a.json).write_text(json.dumps(result,indent=1)+'\n')
    print(json.dumps(result['gnu']))


if __name__=='__main__':
    main()
