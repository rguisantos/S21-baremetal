#!/usr/bin/env python3
"""Conditional BL2 packing after the marker; all query replies stay unobserved."""
import argparse
import hashlib
import json
import struct

from inspect_bl2_geometry_record import expect
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_monitor_preparation import word
from inspect_newtime_hzc2 import embedded
from inspect_newtime_record_hzc2 import unsigned

SPECIAL = (0x0001000860000110, 0x0001000850500130, 0x0001000860600130)
TEMPLATES = (
    (0x1e298, 'd286c901 b94c2ac0 f2a040e1 91102299 911a2275 11000400 b90c2ac0 52800182 f9408723 b9000020 d2995fc0 f9017aa0 2a0203e1 f9417aa0 d63f0060 52800181 f9406322 2a0103e0 d63f0040'),
    (0x1e83c, 'd286c901 b94c2ac0 f2a040e1 911a2279 11000400 b90c2ac0 f0000095 b9000020 97fffbf5 f9015f20'),
    (0x1d830, 'a9bf7bf3 900000b3 91102273 f9407e60 d63f0000 f940aa61 d63f0020 35000060 52800060 94000959 900000a0 a8c17bf3 f941ac00 d61f0000'),
    (0x2d568, 'a9be53f3 2a0103f4 a9017bf5 2a0003f5 d286c200 f2a040e0 b9400001 5286c000 72a040e0 0b000020 528b3fe1 72a040e1 6b01001f 5400006d 52800080 97ffca05 d286fa00 90000026 f2a040e0 911a20c2'),
    (0x2d6d0, '911a20d3'),
    (0x2d7d0, 'd286c000 f2a040e0 8b35c075 1b017e81 f9400000 f9017a60 8b21c061 f9000664 f9417a60 f9013a75 d3441c00 390ac660'),
    (0x2f130, 'a9b853f3 52800013 a9015bf5 a90263f7 a9036bf9 a90473fb f9002bfe 93407e78 d0000000 911a2000 91017b01 52800015 52800014 d0000016 f821781f d37ffb00 f90037e0 f94037e0 911a22da 8b34c000 11000694 9100200a 91004009 91006017 9100801b b0000000 913fa019 b82a7b5f b8297b5f 2a1303e0 b8377b5f f9402f21 b83b7b5f a9072be9 d63f0020 b0000000 528000a2 9139401c 2a1403e1 2a1303e0 f9406b8b d63f0160 a9472be9 b82a7b40 b86a7b40 350000a0 b8297b5f b8377b5f b83b7b5f 14000024 f9402f21 2a1303e0 f9003be9 52800075 d63f0020 f9406b8a 528000c2 2a1403e1 2a1303e0 d63f0140 f9403be9 f9402f21 b8297b40 2a1303e0 d63f0020 f9406b89 528000e2 2a1403e1 2a1303e0 d63f0120 b8377b40 f9402f21 2a1303e0 d63f0020 f9406b86 52800102 2a1403e1 2a1303e0 d63f00c0 b83b7b40 f9402f21 2a1303e0 d63f0020 7100069f 1a9f16b5 71000a9f 54fff761 911a22c1 91017b02 f8627820 927cec00 f8227820 924006a0 f8627824 b37c0c04 f8227824 8b180c24 b9408480 f8627825 d3461c00 b3700c05 f8227825 b9408480 f8627824 d3421400 b36c0c04 91004300 d37df000 f8227824 b8606824 f8627825 d3461c84 b3680c85 f8227825 b8606820 f8627824 d3421400 b3640c04 91001300 d37df000 f8227824 b8606820 f8627824 53001c00 b3781c04 91002300 d37df000 f8227824 b8606820 f8627824 53001c00 b3601c04 91003300 d37df000 f8227824 b8606820 f8627824 53001c00 b3581c04 f8227824 97fffc1c f8627824 d2802203 b3500c04 f8227824 f2ac0003 f8627820 f2c00103 f2e00023 eb03001f 540001e0 d2802603 f8627820 f2aa0a03 f2c00103 f2e00023 eb03001f 54000100 f8627820 d2802601 f2ac0c01 f2c00101 f2e00021 eb01001f 54000481 b000001b 2a1303e0 913fa37b 911a22da 91017b14 f9402f61 d63f0020 b0000000 52800622 91394000 52800061 f9406804 2a1303e0 d63f0080 f8747b41 b3480c01 f8347b41 f9402f61 2a1303e0 d63f0020 d2802601 f8747b40 f2ac0c01 f2c00101 9240cc00 f2e00021 eb01001f 54000100 f8747b40 d378ec00 71000c1f 5400008c f8747b40 9244ec00 f8347b40 11000673 7100127f 54ffe7a1 911a22d6 2a1503e0 a94263f7 a9436bf9 390ac6d5 a94473fb a9415bf5 f9402bfe a8c853f3 d65f03c0'),
    (0x2e3d0, 'd2800200 f2a20000 b9400000 d3545c00 d65f03c0'),
    (0x28480, '71000c1f 53001c42 540000c8 90000043 913e6063 f8605863 b9400063 14000007 7100101f 12800003 540001a1 90000043 f947cc63 b9400063 33040423 90000041 913e6021 330c1843 f8605820 52800021 b9000003 b9000401 b9400c03 2a0303e0 d65f03c0'),
    (0x2a24c, '71000c1f 540000c8 d0000021 913f0021 f8605821 b9405021 14000007 7100101f 12800001 54000181 d0000021 f947e021 b9405021 d0000022 32080021 913f0042 f8605840 b9005001 12077821 b9005001 52800001 2a0103e0 d65f03c0'),
    (0x2caec, 'b0000020 52800048 911a2001 52800006 d2800007 90000029 f9417821 d3441c21 71000c3f 1a9f0508 52800005 2a0603e2 911a2004 91017842 d2800003 f8627881 d3483c21 34000241 f8627881 350000a5 f8627882 d35c7c21 d3586c42 14000004 f8627882 d3545c21 d3504c42 7100183f d2800003 54000068 91020123 78615863 d37ff861 7100045f 9a830023 110004a5 8b0300e7 6b05011f 54fffca1 110004c6 710010df 54fffc21 d36cace0 d65f03c0'),
)
PREP_CALLS = (0x2f1b8, 0x2f208, 0x2f230, 0x2f254, 0x2f278, 0x2f3dc, 0x2f410)
QUERY_CALLS = {0x2f1d4: 11, 0x2f21c: 10, 0x2f244: 9, 0x2f268: 6, 0x2f3f8: 4}


def pack_slot(responses, revision, extension):
    """Explicit two terms x four W replies, extracted revision, selector49 W.

    This models skipped call boundaries, not hardware or callback execution.
    Replies 6/7/8 are ignored when the full selector5 W reply is zero.
    """
    if not isinstance(responses, (tuple, list)) or len(responses) != 2:
        raise ValueError('requires exactly two response terms')
    terms = []
    for term in responses:
        if not isinstance(term, (tuple, list)) or len(term) != 4:
            raise ValueError('requires four W replies per term, selectors 5..8')
        values = tuple(unsigned(v, 32) for v in term)
        terms.append(values if values[0] else (0, 0, 0, 0))
    revision, extension = unsigned(revision, 4), unsigned(extension, 32)
    first, second = terms
    mode = 3 if second[0] else 1 if first[0] else 0
    value = ((mode << 4) | ((first[0] & 255) << 8)
        | (((second[3] >> 6) & 3) << 16) | (((second[3] >> 2) & 15) << 20)
        | (((first[3] >> 6) & 3) << 24) | (((first[3] >> 2) & 15) << 28)
        | ((first[1] & 255) << 32) | ((first[2] & 255) << 40) | (revision << 48))
    before_extension = value
    queried_extension = value in SPECIAL
    if queried_extension:
        nibble = extension & 15
        if value == SPECIAL[2] or nibble > 3:
            value |= nibble << 56
    return dict(packed=value, mode=mode, effective_responses=terms,
        before_extension=before_extension, queried_extension=queried_extension,
        query_count=sum(1+3*bool(t[0]) for t in terms)+queried_extension)


def pack_four(responses, revisions, extensions):
    for values in (responses, revisions, extensions):
        if not isinstance(values, (tuple, list)) or len(values) != 4:
            raise ValueError('requires exactly four explicit slots')
    slots = [pack_slot(r, v, e) for r, v, e in zip(responses, revisions, extensions)]
    return dict(slots=slots, returned_w0=slots[3]['mode'], mode_byte=slots[3]['mode'])


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    for pc, template in TEMPLATES:
        expect(data, pc, template)
    bindings = {0x31510: 0x2f6c0, 0x314c8: 0x2d568, 0x31500: 0x2f130,
                0x31558: 0x2fa98, 0x31358: 0x2caec, 0x30f20: 0x28480, 0x31040: 0x2a24c}
    for cell, target in bindings.items():
        if struct.unpack_from('<Q', data, cell)[0]-NOMINAL_DELTA != target:
            raise ValueError('nominal packing callback binding changed')
    pcs = sorted(pc+i*4 for pc, t in TEMPLATES for i in range(len(t.split())))
    index = b''.join(struct.pack('<II', pc, word(data, pc)) for pc in pcs)
    special_table = next(t for t in embedded(data)['parsed']['entries'] if t['key'] == 0x11111111)
    special_rows = [[r for r in range(special_table['rows'])
                     if special_table['cells'][r*special_table['columns']] == value] for value in SPECIAL]
    if special_rows != [[10], [15], [12]]:
        raise ValueError('special packing constants no longer match embedded rows')
    return dict(mode='static_bl2_geometry_packing', sboot_sha256=IMAGES['sboot'][1],
        instructions=dict(words=len(pcs), index_sha256=hashlib.sha256(index).hexdigest(),
            intervals=[[hex(pc), hex(pc+4*len(t.split()))] for pc, t in TEMPLATES]),
        nominal_bindings=[dict(cell=hex(c), target=hex(t)) for c, t in bindings.items()],
        path=dict(marker_store='0x1e2c4', marker='0xcafe', marker_cell='0x31978',
            newtime_call='0x1e2d0', reload_call='0x1e2e0', reload_target='0x2d568',
            reload_source='0x02073600', reload='0x2d7e0 -> 0x2d7e4',
            later_size_helper='0x1e85c -> 0x1d830',
            pack_call='0x1d840', validation_call='0x1d848', leaf_tail='0x1d864',
            intervening_functions_and_reachability_proved=False),
        packing=dict(entry='0x2f130', end_exclusive='0x2f484',
            slots=['0x31978', '0x31980', '0x31988', '0x31990'],
            clear='0x2f168: STR XZR before queries for each slot',
            scratch_state_offsets=dict(selector5=32, selector6=64, selector7=96, selector8=128),
            scratch_slot_stride=8, scratch_term_stride=4,
            queries=dict(selectors=[5, 6, 7, 8], terms=[1, 2], slots=[0, 1, 2, 3],
                selectors6_7_8_require_full_w_selector5_nonzero=True),
            packed_fields=[dict(bits=[4, 7], source='mode: second active=3; else first active=1; else0'),
                dict(bits=[8, 15], source='term1 selector5 low8'),
                dict(bits=[16, 19], source='term2 selector8 bits6..7, zero-extended'),
                dict(bits=[20, 23], source='term2 selector8 bits2..5'),
                dict(bits=[24, 27], source='term1 selector8 bits6..7, zero-extended'),
                dict(bits=[28, 31], source='term1 selector8 bits2..5'),
                dict(bits=[32, 39], source='term1 selector6 low8'),
                dict(bits=[40, 47], source='term1 selector7 low8'),
                dict(bits=[48, 51], source='0x2e3d0: register0x10000010 bits20..23')],
            extension=dict(exact_before_query=[hex(v) for v in SPECIAL], selector=49, term=3,
                destination_bits=[56, 59], low_nibble_only=True,
                matching_embedded_newtime_rows=special_rows,
                clear_nibble_if_lower52_not_third_constant_and_nibble_le3=True),
            final_mode=dict(store='0x2f46c', cell='0x31939', source='last slot mode W21',
                returned_w0='last slot mode W21', size_leaf_mode_source='slot0 bits4..7'),
            direct_store_to_fixed_AP_record_address_in_this_body=False),
        query_boundary=dict(target='0x28480', response='u32 from live_base+12',
            trigger='u32 1 to live_base+4', control='read/modify/write u32 live_base',
            replies_observed=False, bases_mutable=True),
        firmware_executed=False, physical_marker_replacement_observed=False,
        record_contents_or_final_ram_fdt_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot)
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        parser.exit(2, f'inspect_bl2_geometry_packing: {exc}\n')
    print(json.dumps(result, indent=2))
