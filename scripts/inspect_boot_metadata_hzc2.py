#!/usr/bin/env python3
"""Hash-bound BL2 NEWTIME callback and LK bootstat provenance.

No supplied register values, live bindings or execution are inferred. All
addresses labelled relative are nominal image/state offsets, not live RAM.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from inspect_bl2_geometry_query import adrp_add
from inspect_bl2_geometry_record import expect, wide64
from inspect_bl2_query_base_rewrite import page_address
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import START, END
from inspect_monitor_preparation import word
from inspect_sboot_hzc2 import bl_target

TEMPLATES = (
    (0x17ffc, '79406000 94001724'),
    (0x17e1c, 'd00000d4'),
    (0x179e8, 'd2802115 f2a2b215 34ffffa0 d00000d3 b94002a0 91290273 52920001 72a04061 0b010001 f9000661 91400421 911f9021 f9001661'),
    (0x17fb8, '91290280 b00000c4 91148083 910b0063 f9400401 91400422 91400c21 91300021 f9000c01 d2813401 91200042 f2a2b0c1 f9029082 52820002 72b40002 b9000022 29468801'),
    (0x1dc94, '900000b3'),
    (0x1dcb4, 'b4000063 911a2260 f9018803'),
    (0x2f6d0, 'd0000001 911a2021 f9417820 f9418821 f9401421 d63f0020'),
    (0x193fc, 'a9ae7bfd 910003fd a90153f3 a9025bf5 a90363f7 a9046bf9 a90573fb f90047a0 910003e0'),
    (0x19454, 'd00000a0 91352000 94000c40 f90083a0 f94083a0 eb1f001f 54000061 52800060 14000162 d2822221 f2a22221 f94083a0 94000cee f9007fa0 f9407fa0 eb1f001f 54000061 52800040 14000158'),
    (0x1967c, 'f00000a0 91148000 f9400000 f9006ba0 f9406ba0 f94047a1 f9000001'),
    (0x149830, 'd0005c42 2a0103e1 9115a042 f8205841 d65f03c0'),
    (0x149848, 'd0005c41 9115a021 f8605820 d65f03c0'),
    (0x1452ac, '52800000 94001166 aa0003e1 d00007a2 91080040 97fffcd6 52800020 94001160 aa0003e1 d00007a2 91088040 97fffcd0 52800040 9400115a aa0003e1 d00007a2 91090040 97fffcca'),
    (0xee6a4, '52800c81 52800000 94016c61 94008d64 aa0003f3 52800000 94016c63 8b000273 d29ef9e1 d343fe73 f2bc6a61 52800020 f2d374a1 f2e41881 9bc17e61 d344fc21 94016c53'),
    (0xeebfc, '94008c11 aa0003f3 52800000 94016b10 8b000273 d29ef9e1 d343fe73 f2bc6a61 52800040 f2d374a1 f2e41881 9bc17e61 d344fc21 94016b00'),
    (0xeed1c, '94008bc9 aa0003f3 52800000 94016ac8 8b000273 d29ef9e1 d343fe73 f2bc6a61 52800040 f2d374a1 f2e41881 9bc17e61 d344fc21 94016ab8'),
    (0x111c40, 'd53be020 d0003ca1 911d0022 f943a021 b9400842 17ffff29'),
)
RANGES = tuple((a, a+4*len(words.split())) for a, words in TEMPLATES)


def c_string(data, offset, limit=64):
    if type(offset) is not int or not 0 <= offset < len(data):
        raise ValueError('string offset outside input')
    stop = data.find(b'\0', offset, min(len(data), offset+limit))
    if stop < 0:
        raise ValueError('unterminated selected string')
    return data[offset:stop].decode('ascii')


def direct_calls(data, target):
    # A file-interval inventory of BL encodings, not a reachable-code census.
    return [pc for pc in range(START, END, 4)
            if word(data, pc) & 0xfc000000 == 0x94000000
            and bl_target(word(data, pc), pc) == target]


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    for start, values in TEMPLATES:
        expect(data, start, values)
    context = adrp_add(data, 0x17fbc, 0x17fc0) + ((word(data, 0x17fc4) >> 10) & 4095)
    state = adrp_add(data, 0x1dc94, 0x1dcb8)
    wrapper_state = adrp_add(data, 0x2f6d0, 0x2f6d4)
    if context != 0x307e0 or state != wrapper_state or state != 0x31688:
        raise ValueError('context/state derivation changed')
    if bl_target(word(data, 0x18000), 0x18000) != 0x1dc90:
        raise ValueError('context argument call changed')
    callback_cell = context + ((word(data, 0x2f6e0) >> 10) & 4095)*8
    raw = struct.unpack_from('<Q', data, callback_cell)[0]
    if raw-NOMINAL_DELTA != 0x193fc:
        raise ValueError('NEWTIME callback binding changed')
    name_address = adrp_add(data, 0x19454, 0x19458)
    name = c_string(data, name_address)
    signature = wide64(data, (0x19478, 0x1947c), 1)
    if name != 'NEWTIME' or signature != 0x11111111:
        raise ValueError('selected lookup key changed')
    pointer_cell = adrp_add(data, 0x1967c, 0x19680)
    initial_pointer = struct.unpack_from('<Q', data, pointer_cell)[0]
    init_cell = page_address(word(data, 0x17fbc), 0x17fbc) + ((word(data, 0x17fe8) >> 10) & 4095)*8
    config = adrp_add(data, 0x17e1c, 0x17fb8)
    offset_register = wide64(data, (0x179e8, 0x179ec), 21)
    if (pointer_cell, init_cell, initial_pointer, config, offset_register) != (0x30520, 0x30520, 0x2075600, 0x31a40, 0x15900108):
        raise ValueError('destination-pointer derivation changed')
    source_base = ((word(data, 0x17a00) >> 5) & 65535) | (((word(data, 0x17a04) >> 5) & 65535) << 16)
    extra = (((word(data, 0x17fcc) >> 10) & 4095) << 12) + ((word(data, 0x17fe0) >> 10) & 4095)
    required_word = (0x2073600 - source_base - extra) & 0xffffffff
    if (source_base, extra, required_word) != (0x2039000, 0x1800, 0x38e00):
        raise ValueError('conditional record alias derivation changed')

    table = adrp_add(data, 0x149830, 0x149838)
    if table != adrp_add(data, 0x149848, 0x14984c) or table != 0xcd3568:
        raise ValueError('bootstat table changed')
    formats = []
    for i, pc in enumerate((0x1452ac, 0x1452c4, 0x1452dc)):
        key = (word(data, pc) >> 5) & 65535
        target = adrp_add(data, pc+12, pc+16)
        fmt = c_string(data, target)
        if key != i or fmt != f'sec_bootstat.boot_time_bl{i+1}=%d':
            raise ValueError('bootstat key/format changed')
        if bl_target(word(data, pc+4), pc+4) != 0x149848 or bl_target(word(data, pc+20), pc+20) != 0x144618:
            raise ValueError('bootstat getter/formatter edge changed')
        formats.append(dict(index=i, getter_call=hex(pc+4), argument_move=hex(pc+8),
                            format_offset=hex(target), format=fmt, formatter_call=hex(pc+20)))
    setter_calls = direct_calls(data, 0x149830)
    if setter_calls != [0xee6ac, 0xee6e4, 0xeec30, 0xeed50]:
        raise ValueError('selected LK setter BL inventory changed')
    multiplier = wide64(data, (0xee6c4, 0xee6cc, 0xee6d4, 0xee6d8), 1)
    if multiplier != 0x20c49ba5e353f7cf:
        raise ValueError('counter-derived conversion changed')
    words = {hex(pc): f'{word(data, pc):08x}' for a, b in RANGES for pc in range(a, b, 4)}
    return dict(
        mode='static_boot_metadata_provenance',
        input=dict(size=len(data), sha256=hashlib.sha256(data).hexdigest()),
        dram_context=dict(
            argument_from=hex(context), argument_call='0x18000', incoming_context_store='0x1dcbc',
            context_state_cell=hex(state+784), caller_state_geometry=hex(state+752),
            callback_cell=hex(callback_cell), initial_callback_pointer=hex(raw),
            nominal_callback='0x193fc', callback_invocation='0x2f6e4',
            live_binding_verified=False,
            selected_lookup=dict(name=name, name_offset=hex(name_address), name_call='0x1945c',
                                 key=hex(signature), key_call='0x19484',
                                 error_if_name_lookup_null=3, error_if_key_lookup_null=2,
                                 data_and_selected_row_observed=False),
            selected_u64_store=dict(offset='0x19694', value='saved_argument_at_frame_plus_136',
                                    initial_saved_value='callback_input_X0',
                                    frame_slot_preservation_verified=False,
                                    destination=f'unknown_live_u64_at_{pointer_cell:#x}',
                                    initial_pointer_value=hex(initial_pointer),
                                    first_dram_record_word_written_verified=False,
                                    note='Later stores/calls and net whole-function effects are not modelled'),
            destination_pointer_writer=dict(
                offset='0x17fe8', cell=hex(pointer_cell), config_base=hex(config),
                config_source_cell=hex(config+8), config_source_writer='0x17a0c',
                offset_register=hex(offset_register), offset_register_width_bits=32,
                expression='((unknown_u32_at_0x15900108 + 0x02039000) & 0xffffffff) + 0x1800',
                record_alias_criterion=dict(destination='0x02073600', register_word_required=hex(required_word),
                                            actual_register_word_observed=False),
                preservation_and_execution_verified=False)),
        bootstat=dict(
            relative_state_table=hex(table), setter='0x149830', getter='0x149848',
            setter_value_bits=32, storage_width_bits=64, stride_bytes=8,
            index_bounds_check_in_these_leaves=False, formats=formats,
            direct_bl_inventory=dict(file_interval=[hex(START), hex(END)],
                                     setter_calls=[hex(v) for v in setter_calls],
                                     indirect_calls_or_aliases_excluded=False),
            selected_writers=[
                dict(call='0xee6ac', index=0, source='literal_100', value=100),
                dict(call='0xee6e4', index=1, source='counter_call_plus_slot_zero_then_integer_conversion'),
                dict(call='0xeec30', index=2, source='counter_call_plus_slot_zero_then_integer_conversion'),
                dict(call='0xeed50', index=2, source='counter_call_plus_slot_zero_then_integer_conversion')],
            counter_reader='0x111c40', counter_reader_system_register='CNTPCT_EL0',
            counter_reader_tail='0x1118f8', counter_conversion_multiplier=hex(multiplier),
            selected_conversion='n=(counter_call_result + slot_zero) mod 2^64; y=UMULH(n >> 3, multiplier) >> 4; store low32(y)',
            counter_call_result_and_time_units_verified=False,
            stage_labels_prove_measured_stage_durations=False,
            final_cmdline_delivery_verified=False, runtime_values_observed=False),
        words=words, firmware_executed=False,
        limits=['The NEWTIME pointer cell has a writer; its file value is not assumed active',
                'The alias criterion is arithmetic, not a supplied or measured register value',
                'Callbacks, row data, bootstat table contents and live values remain unknown',
                'BL inventory scans an interval; it is not a full reachable-code or writer census',
                'No final RAM/FDT, payload entry, physical observation or whole-function state is proved'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        parser.exit(2, f'inspect_boot_metadata_hzc2: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
