#!/usr/bin/env python3
"""Bind selected HZC2 scsirpmb registration, callbacks and SCSI/UFS transport."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_avb_boot import wide_constant
from inspect_lk_avb_signature import relative_targets
from inspect_lk_avb_trust import load_x, pair_store_x
from inspect_lk_build_id import page_plus_add
from inspect_lk_embedded_key import adrp
from inspect_lk_final_edges import flow
from inspect_lk_payload_return import summarize_local
from inspect_lk_precopy_measurement import verify_disassembly


BLOCKS = {
    'registration_caller_fragment': (0x10eabc, 0x10eb10),
    'scsi_device_builder': (0x10c3c8, 0x10c6a0),
    'inquiry_and_lu_setup': (0x10c300, 0x10c3c8),
    'block_object_init': (0x18f380, 0x18f4a4),
    'block_object_register': (0x18f4a8, 0x18f508),
    'block_object_lookup': (0x18eb08, 0x18ebac),
    'generic_write': (0x18e650, 0x18e8a8),
    'generic_read': (0x18e8a8, 0x18eaac),
    'security_in': (0x10c018, 0x10c0d0),
    'security_out': (0x10c0d0, 0x10c188),
    'scsi_status_tail': (0x10bea8, 0x10beb4),
    'scsi_status_classifier': (0x10b9c0, 0x10bac0),
    'ufs_gateway': (0x10e758, 0x10e7c8),
    'ufs_request_executor': (0x10e568, 0x10e758),
    'dispatch_write_fragment': (0x109f78, 0x109f8c),
    'dispatch_read_fragment': (0x109f9c, 0x109fb4),
}
SELECTED = {
    0x109f78: ('ldr', 'x4, [x0, #152]'),
    0x109f88: ('blr', 'x4'),
    0x109f9c: ('ldr', 'x4, [x22, #144]'),
    0x109fb0: ('blr', 'x4'),
    0x10b9c4: ('uxtb', 'w0, w0'),
    0x10b9c8: ('cmp', 'w0, #0x40'),
    0x10b9e0: ('mov', 'w0, #0xffffffd5'),
    0x10b9f8: ('ldrb', 'w0, [x1, w0, uxtw]'),
    0x10ba00: ('add', 'x0, x1, w0, sxtb #2'),
    0x10ba04: ('br', 'x0'),
    0x10ba08: ('mov', 'w0, #0x0'),
    0x10ba24: ('mov', 'w0, #0xffffffd5'),
    0x10bea8: ('adrp', 'x0, 0x8a7000'),
    0x10beac: ('ldrb', 'w0, [x0, #992]'),
    0x10beb0: ('b', '0x10b9c0'),
    0x10c018: ('stp', 'x29, x30, [sp, #-48]!'),
    0x10c01c: ('mov', 'x4, x0'),
    0x10c020: ('mov', 'x2, #0x10'),
    0x10c024: ('mov', 'x29, sp'),
    0x10c028: ('stp', 'x19, x20, [sp, #16]'),
    0x10c02c: ('stp', 'x21, x22, [sp, #32]'),
    0x10c030: ('mov', 'w20, w3'),
    0x10c034: ('adrp', 'x21, 0x8a7000'),
    0x10c038: ('ldr', 'x3, [x4, #40]'),
    0x10c03c: ('add', 'x19, x21, #0x380'),
    0x10c040: ('ldr', 'x22, [x4, #64]'),
    0x10c044: ('mov', 'x0, x19'),
    0x10c048: ('mul', 'w3, w20, w3'),
    0x10c04c: ('str', 'x1, [x19, #24]'),
    0x10c050: ('mov', 'w1, #0x0'),
    0x10c054: ('str', 'w3, [x19, #16]'),
    0x10c058: ('str', 'x22, [x19, #104]'),
    0x10c05c: ('bl', '0x1af540'),
    0x10c060: ('lsl', 'w3, w20, #9'),
    0x10c064: ('mov', 'w4, #0xffffffa2'),
    0x10c068: ('mov', 'w2, #0xffffffec'),
    0x10c06c: ('strb', 'w4, [x21, #896]'),
    0x10c070: ('mov', 'w0, #0x1'),
    0x10c074: ('ldr', 'x1, [x22, #368]'),
    0x10c078: ('lsr', 'w4, w3, #24'),
    0x10c07c: ('strb', 'w2, [x19, #1]'),
    0x10c080: ('strb', 'w0, [x19, #3]'),
    0x10c084: ('lsr', 'w2, w3, #16'),
    0x10c088: ('strb', 'wzr, [x19, #2]'),
    0x10c08c: ('lsr', 'w3, w3, #8'),
    0x10c090: ('strb', 'wzr, [x19, #9]'),
    0x10c094: ('mov', 'x0, x19'),
    0x10c098: ('strb', 'w4, [x19, #6]'),
    0x10c09c: ('strb', 'w2, [x19, #7]'),
    0x10c0a0: ('strb', 'w3, [x19, #8]'),
    0x10c0a4: ('blr', 'x1'),
    0x10c0a8: ('cbz', 'w0, 0x10c0c0'),
    0x10c0d0: ('stp', 'x29, x30, [sp, #-48]!'),
    0x10c0d4: ('mov', 'x4, x0'),
    0x10c0d8: ('mov', 'x2, #0x10'),
    0x10c0dc: ('mov', 'x29, sp'),
    0x10c0e0: ('stp', 'x19, x20, [sp, #16]'),
    0x10c0e4: ('stp', 'x21, x22, [sp, #32]'),
    0x10c0e8: ('mov', 'w20, w3'),
    0x10c0ec: ('adrp', 'x21, 0x8a7000'),
    0x10c0f0: ('ldr', 'x3, [x4, #40]'),
    0x10c0f4: ('add', 'x19, x21, #0x380'),
    0x10c0f8: ('ldr', 'x22, [x4, #64]'),
    0x10c0fc: ('mov', 'x0, x19'),
    0x10c100: ('mul', 'w3, w20, w3'),
    0x10c104: ('str', 'x1, [x19, #24]'),
    0x10c108: ('mov', 'w1, #0x0'),
    0x10c10c: ('str', 'w3, [x19, #16]'),
    0x10c110: ('str', 'x22, [x19, #104]'),
    0x10c114: ('bl', '0x1af540'),
    0x10c118: ('lsl', 'w3, w20, #9'),
    0x10c11c: ('mov', 'w4, #0xffffffb5'),
    0x10c120: ('mov', 'w2, #0xffffffec'),
    0x10c124: ('strb', 'w4, [x21, #896]'),
    0x10c128: ('mov', 'w0, #0x1'),
    0x10c12c: ('ldr', 'x1, [x22, #368]'),
    0x10c130: ('lsr', 'w4, w3, #24'),
    0x10c134: ('strb', 'w2, [x19, #1]'),
    0x10c138: ('strb', 'w0, [x19, #3]'),
    0x10c13c: ('lsr', 'w2, w3, #16'),
    0x10c140: ('strb', 'wzr, [x19, #2]'),
    0x10c144: ('lsr', 'w3, w3, #8'),
    0x10c148: ('strb', 'wzr, [x19, #9]'),
    0x10c14c: ('mov', 'x0, x19'),
    0x10c150: ('strb', 'w4, [x19, #6]'),
    0x10c154: ('strb', 'w2, [x19, #7]'),
    0x10c158: ('strb', 'w3, [x19, #8]'),
    0x10c15c: ('blr', 'x1'),
    0x10c160: ('cbz', 'w0, 0x10c178'),
    0x10c3d8: ('csinc', 'w22, w2, w1, eq'),
    0x10c3ec: ('cmp', 'w1, w22'),
    0x10c410: ('add', 'x0, x27, #0xb20'),
    0x10c414: ('mov', 'x23, x3'),
    0x10c418: ('mov', 'x25, x4'),
    0x10c440: ('bl', '0x1b1160'),
    0x10c450: ('str', 'x28, [x28, #64]'),
    0x10c454: ('str', 'x23, [x28, #368]'),
    0x10c458: ('bl', '0x10c300'),
    0x10c460: ('mov', 'w27, w0'),
    0x10c464: ('b.eq', '0x10c4fc'),
    0x10c468: ('tbnz', 'w0, #31, 0x10c508'),
    0x10c478: ('add', 'x1, x1, #0xb90'),
    0x10c47c: ('mov', 'x20, #0x1000'),
    0x10c4a0: ('mov', 'x5, #0x200'),
    0x10c4a4: ('csel', 'x20, x20, x5, ne'),
    0x10c4b4: ('mov', 'w6, #0x0'),
    0x10c4b8: ('mov', 'x5, #0x0'),
    0x10c4bc: ('mov', 'x4, #0x0'),
    0x10c4c0: ('mov', 'w3, #0xffffffff'),
    0x10c4c8: ('bl', '0x18f380'),
    0x10c4dc: ('stp', 'x1, x0, [x28, #192]'),
    0x10c4e4: ('mov', 'x0, x28'),
    0x10c4f0: ('str', 'w20, [x28, #60]'),
    0x10c4f8: ('bl', '0x18f4a8'),
    0x10e5b4: ('str', 'xzr, [x19, #96]'),
    0x10e5b8: ('str', 'wzr, [x19, #120]'),
    0x10e5c8: ('bl', '0x10c7f8'),
    0x10e5d0: ('bl', '0x10cab8'),
    0x10e5f4: ('cmp', 'w0, #0x1'),
    0x10e5f8: ('b.ls', '0x10e610'),
    0x10e5fc: ('cbz', 'w21, 0x10e688'),
    0x10e600: ('sub', 'w22, w22, #0x1'),
    0x10e604: ('sub', 'w21, w21, #0x1'),
    0x10e608: ('b', '0x10e5a8'),
    0x10e624: ('bl', '0x10dc10'),
    0x10e630: ('dsb', 'st'),
    0x10e648: ('str', 'w4, [x3, #64]'),
    0x10e64c: ('str', 'w23, [x2, #88]'),
    0x10e650: ('bl', '0x10cfb0'),
    0x10e678: ('mov', 'x0, x19'),
    0x10e67c: ('bl', '0x10c888'),
    0x10e680: ('mov', 'w25, w0'),
    0x10e694: ('cbnz', 'w25, 0x10e708'),
    0x10e6c4: ('ldr', 'x0, [x19, #96]'),
    0x10e6c8: ('ldrb', 'w1, [x0, #32]'),
    0x10e6cc: ('cmp', 'w1, #0x70'),
    0x10e6d4: ('ldrb', 'w0, [x0, #34]'),
    0x10e6d8: ('and', 'w0, w0, #0xf'),
    0x10e6dc: ('cmp', 'w0, #0x6'),
    0x10e6f8: ('cmp', 'w22, wzr'),
    0x10e6fc: ('b.gt', '0x10e600'),
    0x10e780: ('ldr', 'w1, [x21, #1808]'),
    0x10e784: ('str', 'x19, [x0, #1016]'),
    0x10e788: ('ldr', 'x0, [x20, w1, sxtw #3]'),
    0x10e78c: ('cbz', 'x0, 0x10e7a8'),
    0x10e7a0: ('b', '0x10e568'),
    0x10e7b4: ('ldrsw', 'x0, [x21, #1808]'),
    0x10e7b8: ('ldr', 'x0, [x20, x0, lsl #3]'),
    0x10e7bc: ('b', '0x10e790'),
    0x10e7c0: ('mov', 'w0, #0xfffffff9'),
    0x10eac0: ('add', 'x20, x20, #0x758'),
    0x10ead4: ('mov', 'x3, x20'),
    0x10eae4: ('bl', '0x10c3c8'),
    0x10eaf8: ('mov', 'x3, x20'),
    0x10eafc: ('add', 'x4, x4, #0xb90'),
    0x10eb00: ('mov', 'w2, #0x0'),
    0x10eb04: ('mov', 'w1, #0x44'),
    0x10eb08: ('add', 'x0, x0, #0x400'),
    0x10eb0c: ('bl', '0x10c3c8'),
    0x18e660: ('ldr', 'x22, [x0, #40]'),
    0x18e66c: ('ldr', 'w24, [x0, #60]'),
    0x18e6b8: ('tbz', 'w1, #1, 0x18e6c4'),
    0x18e710: ('ldr', 'x5, [x26, #200]'),
    0x18e738: ('blr', 'x5'),
    0x18e740: ('cbz', 'w0, 0x18e6f8'),
    0x18e744: ('mov', 'w0, #0xffffffff'),
    0x18e7fc: ('mov', 'w0, #0x0'),
    0x18e8b8: ('ldr', 'x22, [x0, #40]'),
    0x18e910: ('tbz', 'w1, #0, 0x18e91c'),
    0x18e968: ('ldr', 'x5, [x27, #192]'),
    0x18e990: ('blr', 'x5'),
    0x18e998: ('cbz', 'w0, 0x18e950'),
    0x18e9a0: ('mov', 'w0, #0xffffffff'),
    0x18ea24: ('mov', 'w0, #0x0'),
    0x18eb24: ('add', 'x20, x22, #0xf78'),
    0x18eb30: ('ldr', 'x19, [x20, #8]'),
    0x18eb4c: ('ldr', 'x0, [x19, #24]'),
    0x18eb54: ('bl', '0x1b2538'),
    0x18eb58: ('cbnz', 'w0, 0x18eb40'),
    0x18eb64: ('str', 'w0, [x19, #16]'),
    0x18f3b8: ('str', 'x21, [x19, #40]'),
    0x18f3bc: ('str', 'x0, [x19, #24]'),
    0x18f3c0: ('str', 'w20, [x19, #56]'),
    0x18f3f0: ('strb', 'wzr, [x19, #88]'),
    0x18f408: ('stp', 'x3, x2, [x19, #104]'),
    0x18f41c: ('stp', 'x1, x8, [x19, #120]'),
    0x18f420: ('stp', 'x0, x6, [x19, #144]'),
    0x18f440: ('stp', 'wzr, w22, [x19, #92]'),
    0x18f44c: ('str', 'wzr, [x19, #16]'),
    0x18f4c4: ('add', 'x22, x20, #0xf78'),
    0x18f4d8: ('str', 'w2, [x19, #16]'),
    0x18f4e4: ('stp', 'x0, x22, [x19]'),
    0x18f4f4: ('str', 'x19, [x20, #3960]'),
    0x18f4f8: ('str', 'x19, [x1, #8]'),
}
STRINGS = {
    0x226b20: b'scsi%s',
    0x226b28: b'scsi%u',
    0x226b90: b'rpmb',
    0x226b98: b'[SCSI] LU%u\t%s\t%s\t%s\n',
    0x226dc8: b'UFS Invalid host structure: %d\n',
    0x2269b8: b'CHECK CONDITION\n',
    0x2269d0: b'CONDITION MET\n',
    0x2269e0: b'BUSY\n',
    0x2269e8: b'RESERVATION CONFLICT\n',
    0x226a00: b'TASK SET FULL\n',
    0x226a10: b'ACA ACTIVE\n',
    0x226a20: b'TASK ABORTED\n',
    0x226a30: b'reserved\n',
}


def store_unsigned_b(word):
    if (type(word) is not int or not 0 <= word <= 0xffffffff
            or word & 0xffc00000 != 0x39000000):
        raise ValueError('expected STRB unsigned immediate')
    return word & 31, (word >> 5) & 31, (word >> 10) & 0xfff


def callback_bindings(words):
    generic = pair_store_x(words[0x18f420])
    low = pair_store_x(words[0x10c4dc])
    generic_read = page_plus_add(words, 0x18f3ec, 0x18f3fc)
    generic_write = page_plus_add(words, 0x18f404, 0x18f414)
    scsi_read = page_plus_add(words, 0x10c4cc, 0x10c4d4)
    scsi_write = page_plus_add(words, 0x10c4d0, 0x10c4d8)
    if (generic != (0, 6, 19, 144) or low != (1, 0, 28, 192)
            or generic_read[0] != generic[0] or generic_write[0] != generic[1]
            or scsi_read[0] != low[0] or scsi_write[0] != low[1]):
        raise ValueError('callback installer register/slot binding differs')
    for load_pc, call_pc, expected in (
            (0x109f78, 0x109f88, (4, 0, 152)),
            (0x109f9c, 0x109fb0, (4, 22, 144)),
            (0x18e968, 0x18e990, (5, 27, 192)),
            (0x18e710, 0x18e738, (5, 26, 200))):
        if (load_x(words[load_pc]) != expected
                or flow(words[call_pc], call_pc) != ('blr', expected[0])):
            raise ValueError('callback consumer slot/register binding differs')
    lookup_register, lookup = page_plus_add(words, 0x18eb18, 0x18eb24)
    install_register, installed = page_plus_add(words, 0x18f4bc, 0x18f4c4)
    if (lookup_register, install_register) != (20, 22) or lookup != installed:
        raise ValueError('registration and lookup roots differ')
    return dict(registry_relative_address=hex(lookup),
        device_methods={'144': hex(generic_read[1]), '152': hex(generic_write[1])},
        underlying_methods={'192': hex(scsi_read[1]), '200': hex(scsi_write[1])},
        live_installation_and_preservation_established=False)


def security_cdb(words, *, output=False):
    # The two bodies have identical register roles and instruction offsets.
    bias = 0xb8 if output else 0
    at = lambda pc: words[pc+bias]
    op_reg, op_width, opcode = wide_constant([at(0x10c064)])
    proto_reg, proto_width, protocol = wide_constant([at(0x10c068)])
    spec_reg, spec_width, specific = wide_constant([at(0x10c070)])
    register, page = adrp(at(0x10c034), 0x10c034+bias)
    workspace_reg, workspace = page_plus_add(words, 0x10c034+bias, 0x10c03c+bias)
    stores = [store_unsigned_b(at(pc)) for pc in (0x10c06c, 0x10c07c, 0x10c080,
              0x10c088, 0x10c090, 0x10c098, 0x10c09c, 0x10c0a0)]
    expected = [(4, 21, 896), (2, 19, 1), (0, 19, 3), (31, 19, 2),
                (31, 19, 9), (4, 19, 6), (2, 19, 7), (3, 19, 8)]
    if ((op_reg, op_width, proto_reg, proto_width, spec_reg, spec_width) != (4, 32, 2, 32, 0, 32)
            or (register, workspace_reg) != (21, 19) or stores != expected
            or page+stores[0][2] != workspace):
        raise ValueError('security CDB register/store binding differs')
    return dict(workspace_relative_address=hex(workspace),
        opcode=hex(opcode & 255), protocol=hex(protocol & 255), protocol_specific=specific,
        cdb_zeroed_bytes=16, transfer_length='u32(count <<9), big-endian at bytes6..9; byte9 explicitly zero',
        payload_length='u32(count * object_u64_at40), stored at workspace+16',
        payload_pointer_offset=24, parent_pointer_offset=104,
        callback_offset_in_parent=368, original_block_index_used_in_cdb=False)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for low, high in BLOCKS.values():
        parsed = parse_lines(subprocess.check_output(command + [
            '-D', '-z', '-b', 'binary', '-m', 'aarch64', f'--start-address={low}',
            f'--stop-address={high}', str(Path(path).resolve())], text=True))
        if lines.keys() & parsed.keys():
            raise ValueError('duplicate GNU PC across blocks')
        lines.update(parsed)
    branches = verify_disassembly(data, lines, BLOCKS, SELECTED)
    words = {pc: row[0] for pc, row in lines.items()}
    bindings = callback_bindings(words)
    cdb = dict(read=security_cdb(words), write=security_cdb(words, output=True))
    statuses = relative_targets(data, 0x226954, 65, 0x10ba08, *BLOCKS['scsi_status_classifier'])
    for offset, value in STRINGS.items():
        if data[offset:offset+len(value)+1] != value+b'\0':
            raise ValueError(f'literal differs at {offset:#x}')
    packed = b''.join(struct.pack('<II', pc, row[0]) for pc, row in sorted(lines.items()))
    return dict(mode='static_lk_rpmb_callback_and_transport_bindings',
        sboot_sha256=IMAGES['sboot'][1], firmware_executed=False,
        hardware_observed=False, counter_persistence_established=False,
        gnu_words=len(lines), gnu_relative_targets=len(branches), selected_operand_checks=len(SELECTED),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        blocks={name: dict(start=hex(low), end_exclusive=hex(high)) for name, (low, high) in BLOCKS.items()},
        selected_instructions={hex(pc): dict(word=f'{lines[pc][0]:08x}', op=op, args=args)
                               for pc, (op, args) in sorted(SELECTED.items())},
        branches=branches, bindings=bindings, security_cdb=cdb,
        status_switch=dict(table='0x226954', count=65, signed_byte_scale=4, base='0x10ba08',
            routes={hex(i): hex(target) for i, target in enumerate(statuses)},
            result='input low8==0 returns0; every other low8 returns low32 0xffffffd5 (-43)'),
        strings={hex(pc): value.decode('ascii') for pc, value in STRINGS.items()},
        local_graphs={name: summarize_local(data, low, low, high) for name, (low, high) in BLOCKS.items()},
        interpretation=dict(
            registration='selected caller passes start68/end-derived69, suffix rpmb and transport0x10e758; name scsi%s produces scsirpmb',
            object='selected nonnegative setup path initializes 512-byte unit, u32 count0xffffffff, max128 sectors, flags0, self pointer+64 and parent callback+368',
            publication='register0x18f4a8 and lookup0x18eb08 use same relative31ff78 list; lookup uses exact name comparison and increments reference count',
            wrapper='under preserved 512-byte unit and flags0, one frame reaches underlying+192 for read/+200 for write; nonzero underlying result maps to wrapper-1',
            lowlevel='underlying SCSI callbacks return immediate nonzero transport status, otherwise tail-call classifier on workspace+96 byte',
            gateway='0x10e758 selects host through relative8a7710 index and8a7718 pointer table, then tail-calls0x10e568; null request returns-7',
            gateway_null_host='prints diagnostic then reloads/reuses selected host without a local return guard; not a proved safe failure',
            executor='opaque descriptor/preparation0x10c7f8/0x10cab8, MMIO publication and wait0x10cfb0, response0x10c888 plus conditional retries; no completion observed'),
        limits=[
            'nominal static installation is established only for the selected conditional path, not a live object or all boot paths',
            'callees, formatter allocation success, shared workspace ownership, aliases and register preservation remain assumptions',
            'generic wrappers include partial/alignment paths; no whole-input memory-safety or geometry certification',
            'UFS descriptor construction, wait/response implementation and active host state remain frontiers',
            'matching SCSI opcodes with Linux does not prove source identity or interchangeable secure services',
            'no MMIO, SMC, firmware, device request, counter acquisition or persistence test was executed',
            'graphs retain opaque conditional call returns and do not evaluate registers or path feasibility'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.sboot), indent=2))
    except (OSError, ValueError, UnicodeError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_lk_rpmb_transport: {error}\n')


if __name__ == '__main__':
    main()
