#!/usr/bin/env python3
"""Selected HZC2 NEWTIME error/debug path; no physical state is inferred."""
import argparse
import hashlib
import json
import struct

from inspect_bl2_geometry_record import expect
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_monitor_preparation import word
from inspect_newtime_record_hzc2 import unsigned, wrapper_result

TEMPLATES = (
    (0x1fdb8, 'a9be53f3 d0000081 2a0003f4 911a2020 f9000bfe aa0103f3 f9418800 f9400000 b4000120 940005e6 2a1403e0 940002dd 5286c000 52803401 72a040e0 940001b8 94000102 911a2261 f9418820 f9400000 b40000a0 f9400401 90000080 913aa400 d63f0020 d503207f f9400bfe a8c253f3 d65f03c0'),
    (0x20958, 'a9bd53f3 d286c483 52800021 f2a040e3 f9000bfe 1ac02021 b9400062 2a020021 b9000061 b0000081 3900a3ff 911a2034 f90013ff f9418a82 f9400042 b40002c2 f9400c44 aa0103f3 910083e3 52800141 52800062 d63f0080 f9418a80 f9400000 b40000c0 f9400401 f0000060 913aa400 91050400 d63f0020 911a2261 f9418820 f9400000 b4000080 f9400401 910083e0 d63f0020 f9400bfe a8c353f3 d65f03c0'),
    (0x204d4, 'a9b953f3 b0000093 a9036bf9 2a0003f9 911a2260 a90263f7 a9015bf5 a90473fb f9002bfe 2a0103f8 3901a3ff f9418800 f90033ff f9400000 b40000c0 f9400401 f0000060 913aa400 91006c00 d63f0020 911a2260 f9418800 f9400000 b40000c0 f9400401 f0000060 913aa400 91020800 d63f0020 911a2260 f9418800 f9400000 b40000c0 f9400401 f0000060 913aa400 91031c00 d63f0020 f0000074 12000f36 913aa694 0b1802d8 52800017 4b160336 52800015 91006e9b 6b1802bf 54000aa2 120006e0 6b1f001f 7a5f02e4 54000100 911a2260 f9418800 f9400000 b4000080 f9400401 aa1b03e0 d63f0020 12000ea0 0b1602ba 350003c0 911a2260 f9418800 f9400000 b4000080 f9400401 91043280 d63f0020 911a227c 910183e3 52800102 52800201 f9418b80 f9400000 f9400c04 2a1a03e0 d63f0080 f9418b80 f9400000 b4000080 f9400401 910183e0 d63f0020 911a2260 f9418800 f9400000 b4000080 f9400401 91043e80 d63f0020 2a1503e1 911a227c 2a1603e0 910183e3 52800102 b8616800 f9418b81 f9400021 f9400c24 52800201 d63f0080 f9418b80 f9400000 b4000080 f9400401 91044680 d63f0020 911a2260 6b1a033f f9418800 f9400000 540000c9 b4000120 f9400401 91045e80 d63f0020 14000005 b4000080 f9400401 910183e0 d63f0020 911a2260 f9418800 f9400000 b4000080 f9400401 91043e80 d63f0020 110012b5 110006f7 17ffffab 911a2273 f9418a60 f9400000 b40000c0 f9400401 f0000060 913aa400 91006c00 d63f0020 a9415bf5 a94263f7 a9436bf9 a94473fb f9402bfe a8c753f3 d65f03c0'),
    (0x20200, 'a9bb53f3 b0000081 d2a20000 a9015bf5 a9037bf9 a90263f7 aa0103f9 52800016 b9400018 d286da00 393c903f d286dc01 390123ff f2a040e0 f2a040e1 f90023ff b8404402 6b1f005f 1a9606d6 eb01001f 54ffff81 b0000095 b0000093 911022a0 f9403c00 d63f0000 53001c00 7100101f 540005a1 f0000074 52800201 913aa694 911a2277 91012a80 97ffff32 f9418ae0 910103e3 52800102 52800201 f9400000 f9400c04 2a1803e0 d63f0080 52800101 910103e0 97ffff27 52800021 91016e80 97ffff24 f9418ae1 d286c480 f2a040e0 910103e3 528000e2 f9400021 b9400000 f9400c24 52800201 d63f0080 528000e1 910103e0 97ffff17 52800041 52800022 2a0103e0 97ffff2e 52800101 91017680 97ffff10 b0000080 397c9321 91310000 97fffefe 911a2260 f9418801 f9400021 b4000c81 f0000074 390dc01f 913aa694 91006e99 911a2277 394dc2e0 35000ba0 911022a0 f9408801 d292d000 f2a01300 d63f0020 f9418ae0 f9400000 b4000080 f9400401 aa1903e0 d63f0020 911a2260 f9418800 f9400000 b4000080 f9400401 91019a80 d63f0020 911a2260 f9418800 f9400000 b4000080 f9400401 9101be80 d63f0020 911a2277 910103e3 52800102 52800201 f9418ae0 f9400000 f9400c04 2a1803e0 d63f0080 f9418ae0 f9400000 b4000080 f9400401 910103e0 d63f0020 911a2260 f9418800 f9400000 b4000080 f9400401 91016e80 d63f0020 911a2277 d286c480 f2a040e0 910103e3 528000e2 f9418ae1 b9400000 f9400021 f9400c24 52800201 d63f0080 f9418ae0 f9400000 b4000080 f9400401 910103e0 d63f0020 52800022 52800041 2a0203e0 97fffed8 52800022 52800001 2a0203e0 97fffed4 52800021 52800082 2a0103e0 97fffed0 52800022 52800061 2a0203e0 97fffecc 52800020 2a1603e2 52800081 97fffec8 911a2260 f9418800 f9400000 b4fff4c0 f9400401 9101e280 d63f0020 17ffffa2 a9415bf5 a94263f7 a9437bf9 a8c553f3 d65f03c0'),
    (0x1ffbc, 'a9b853f3 7100083f a9015bf5 a90263f7 a9036bf9 a90473fb f9002bfe 54000180 34000241 7100043f 540002e0 7100103f 54000fc1 90000093 5281f61b 913aa673 52800016 91007673 14000014 f0000073 5286c016 913aa673 5280341b 9100e273 72a040f6 1400000d f0000073 528c0016 913aa673 5280a01b 9100be73 72a38076 14000006 f0000073 5281c01b 913aa673 52a38096 91009a73 f0000077 b000009a 913aa6f7 2a0103f5 3901e3ff 9124235a 52800019 910106f7 290c0be0 f9003bff b94067e0 6b00033f 54000b02 710012bf 54000081 b9400356 aa1603f4 1400000c 530c2f38 0b160314 35000135 b0000080 91102000 f9402800 d63f0000 7100041f 54000061 114026d4 0b140314 b94063e0 b0000098 7100081f 1100c320 39001e60 54000341 52800101 aa1303e0 5280001c 97ffff99 2a1c03e1 2a1403e0 9101c3e3 52800102 1100139c b8616800 911a2301 f9418821 f9400021 f9400c25 52800201 d63f00a0 52800101 9101c3e0 97ffff8a 6b1b039f 54fffe03 52800101 aa1703e0 97ffff85 14000026 911a2300 f9418800 f9400000 b4000080 f9400401 aa1303e0 d63f0020 5280001c 911a2305 2a1c03e1 2a1403e0 9101c3e3 52800102 f90037e5 b8616800 f94188a1 f9400021 f9400c26 52800201 d63f00c0 f94037e5 f94188a0 f9400000 b4000080 f9400401 9101c3e0 d63f0020 1100139c 6b1b039f 54fffd63 911a2318 f9418b00 f9400000 b4000080 f9400401 aa1703e0 d63f0020 11000739 9100235a 17ffffa7 a9415bf5 a94263f7 a9436bf9 a94473fb f9402bfe a8c853f3 d65f03c0'),
    (0x21574, 'a9bc53f3 90000093 911a2260 f90013fe a9015bf5 3900e3ff f9418800 f9001bff f9400000 b40000c0 f9400401 d0000060 913aa400 91006c00 d63f0020 911a2260 f9418800 f9400000 b40000a0 f9400401 d0000060 913fc000 d63f0020 90000080 39f50000 3100041f 54000161 911a2260 f9418800 f9400000 b40003c0 f9400401 d0000060 913fc000 91002400 d63f0020 1400000f'),
    (0x1ff18, 'd0000082 f81f0ffe d2800003 f944cc42 f9402444 93407c22 aa0003e1 d2806020 f2b04000 d63f0080 d0000080 f84107fe 393c901f d65f03c0'),
    (0x1d430, '2a0203e2 8b020064 3822687f f0000083 cb020082 91130863 eb02009f 540000e0 1ac10805 1b0180a0 38606860 381ffc80 2a0503e0 17fffff9 d65f03c0'),
    (0x1d4c8, 'd2800201 f2a20a81 b9400020 360fffe0 d65f03c0 a9bf7bfd 53001c04 910003fd 97fffff8 d2800400 f2a20a80 b9000004 900000a0 f9461001 b40002c1 52822120 b9400022 72a00160 6b00005f 54000221 29408022 6b02001f 54000048 b9000822 29410c20 0b030043 6b03001f 54000083 52800020 b9000822 b9001420 b9400822 11000440 b9000820 2a0203e2 39000044 a8c17bfd d65f03c0 a9bf7bfd 91000406 910003fd 385ff0c5 34000125 710028bf 54000061 528001a0 97ffffd7 2a0503e0 97ffffd5 910004c6 17fffff7 a8c17bfd d65f03c0'),
)


def error_flags(before, argument):
    """AArch64 variable W shift uses only the low five shift bits."""
    return unsigned(before, 32) | (1 << (unsigned(argument, 32) & 31))


def dump_plan(address, size):
    """Describe LDR addresses without allocating an unbounded list.

    W arithmetic wraps for the limit and displayed address. The actual LDR
    uses zero-extended base/index registers and a 64-bit effective address.
    This describes reads, including blanked words before an unaligned start.
    """
    address, size = unsigned(address, 32), unsigned(size, 32)
    base = address & ~15
    limit = ((address & 15)+size) & 0xffffffff
    finite = limit <= 0xfffffffc
    count = (limit+3)//4 if finite else None
    return dict(base=base, loop_limit=limit, finite=finite, word_count=count,
        cycle_word_count=None if finite else 1 << 30,
        first_read=base if limit else None,
        last_read=base+4*(count-1) if finite and count else None,
        read_end=base+4*count if finite and count else None)


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    for pc, template in TEMPLATES:
        expect(data, pc, template)
    bindings = {0x307e0: 0x30b50, 0x30b58: 0x1d560, 0x30b68: 0x1d430}
    for cell, nominal in bindings.items():
        if struct.unpack_from('<Q', data, cell)[0]-NOMINAL_DELTA != nominal:
            raise ValueError('nominal console binding changed')
    strings = {0x2fea9: b'\nREADY TO DEBUG! \n', 0x2fec4: b'\n',
        0x2ff2b: b'          |          0x0|          0x4|          0x8|          0xC|\n',
        0x2ff70: b'-------------------------------------------------------------------\n',
        0x2ffb5: b'  ', 0x2ffb8: b'|', 0x2ffba: b'     ', 0x2ffc0: b'        ',
        0x304c2: b'0123456789ABCDEF'}
    for address, value in strings.items():
        if data[address:address+len(value)+1] != value+b'\0':
            raise ValueError('debug string changed')
    pcs = sorted(pc+i*4 for pc, template in TEMPLATES for i in range(len(template.split())))
    indexed = b''.join(struct.pack('<II', pc, word(data, pc)) for pc in pcs)
    return dict(mode='static_newtime_error_debug', sboot_sha256=IMAGES['sboot'][1],
        instructions=dict(words=len(pcs), index_sha256=hashlib.sha256(indexed).hexdigest(),
            intervals=[[hex(pc), hex(pc+len(t.split())*4)] for pc, t in TEMPLATES]),
        bindings=dict(context='0x307e0', live_context_cell='0x31998',
            initial_console='0x30b50', console_puts='0x1d560', console_formatter='0x1d430',
            puts_character='0x1d4dc', tx_poll='0x1d4c8',
            tx_status='0x10540010 bit1', tx_word_store='0x10540020',
            optional_log_buffer_pointer_cell='0x31c20', runtime_bindings_observed=False),
        helper=dict(entry='0x1fdb8', console_null_successor='0x1fdfc',
            calls_when_console_present=['0x21574', '0x20958', '0x204d4', '0x20200'],
            metadata_printer_only_prefix_selected=['0x21574', '0x21608'],
            readiness_string='0x2fea9', wfi='0x1fe1c', epilogue=['0x1fe20', '0x1fe2c'],
            unconditional_nonreturn_proved=False),
        wrapper={str(s): wrapper_result(s) for s in range(6)},
        flags=dict(helper='0x20958', load='0x20970', store='0x20978',
            address='0x02073624', record_offset_if_R_is_02073600='0x24',
            formula='before_u32 | (1 << (argument_u32 & 31))',
            wrapper_code_1_3_4_mask=hex(error_flags(0, 27)),
            wrapper_code_2_mask=hex(error_flags(0, 5)), read_modify_write_atomic=False),
        dump=dict(entry='0x204d4', load='0x20654', address_argument='0x02073600',
            size_argument='0x1a0', selected_call_plan=dump_plan(0x02073600, 0x1a0),
            descriptor_region_start_if_R_is_02073600='0x020737a0',
            source_stores_in_selected_dumper=False, output_uses_mutable_callbacks=True,
            source_preservation_requires_disjoint_output_and_stack=True),
        debug=dict(entry='0x20200', first_hardware_read=['0x20220', '0x10000000'],
            header_scan=['0x020736d0', '0x020736e0'],
            indirect_callback_table='0x31408', first_slot_offset=120,
            loop='0x20344', back_edges=['0x204ac', '0x204bc'],
            flag_byte='0x319f8', null_console_exit='0x204c0',
            additional_dump_helper='0x1ffbc', output_callback_at='0x1ff3c',
            complete_transitive_effects_verified=False),
        strings=[dict(file=hex(a), text=v.decode('ascii'),
            sha256=hashlib.sha256(v+b'\0').hexdigest()) for a, v in strings.items()],
        firmware_executed=False, hardware_or_record_observed=False,
        first_u64_preserved_through_complete_error_path_proved=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        parser.exit(2, f'inspect_newtime_error_hzc2: {exc}\n')
    print(json.dumps(result, indent=2))
