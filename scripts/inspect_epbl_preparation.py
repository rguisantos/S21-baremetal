#!/usr/bin/env python3
"""HZC2 EPBL preparation and common SMC dispatcher, without hardware execution.

Nominal pointer translation is an explicit hypothesis. No decryption, device
keys, actual service response or complete secure dispatch is provided.
"""
import argparse
import hashlib
import json
import struct

from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import signed
from inspect_monitor_preparation import word


def uint(value,bits):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'explicit unsigned {bits}-bit value required')
    return value


def common_id(x0):
    """Model 0x4424 onward, separately from the optional bit-30 entry guard."""
    original=uint(x0,64)&0xffffffff
    normalized=original
    legacy=original & 0xffff0000 == 0xffff0000
    if legacy:
        normalized=0x82000000 | ((~original+1)&0xffffffff)
    owner=((normalized >> 24)&63)|(((normalized >> 31)&1)<<6)
    return dict(input_w0=hex(original),common_normalized_w0=hex(normalized),
                legacy_prefix_matched=legacy,owner_index=owner,
                rejects_if_entered_at_0x43d8=bool(original & (1<<30)),
                actual_entry_verified=False,handler_resolved=False)


def file_offset(pointer,delta,width=1):
    uint(pointer,64)
    uint(delta,64)
    if type(width) is not int or width<=0:
        raise ValueError('invalid nominal translation')
    offset=pointer-delta
    if not 0x3000 <= offset < 0x16000 or offset+width>0x16000:
        raise ValueError('pointer outside candidate EPBL file range')
    return offset


def adrp_ldr_pointer(data,adrp_pc,ldr_pc):
    """Decode the two pinned address instructions, not intervening execution."""
    a,b=word(data,adrp_pc),word(data,ldr_pc)
    if a & 0x9f000000 != 0x90000000 or b & 0xffc00000 != 0xf9400000:
        raise ValueError('expected ADRP and LDR X unsigned immediate')
    if a&31==31 or (b>>5)&31 != a&31:
        raise ValueError('pointer producer base mismatch')
    page=(adrp_pc&~4095)+(signed(((a>>29)&3)|(((a>>5)&0x7ffff)<<2),21)<<12)
    slot=page+((b>>10)&4095)*8
    if slot<0 or slot%8 or slot+8>len(data):
        raise ValueError('pointer slot outside aligned bytes')
    return slot,struct.unpack_from('<Q',data,slot)[0]


def dispatcher_slot(classification):
    value=uint(classification,8)
    if value&128:
        return dict(rejected=True,slot_file_offset=None)
    return dict(rejected=False,slot_file_offset=hex(0xe410+32*value),
                target_pointer_bytes=8,runtime_pointer_known=False)


def evidence(path):
    data=read_exact(path,*IMAGES['sboot'])
    u64=lambda p:struct.unpack_from('<Q',data,p)[0]
    source_slot,source=adrp_ldr_pointer(data,0x37f0,0x3804)
    end_slot,end=adrp_ldr_pointer(data,0x37f4,0x3808)
    if not source<end or end-source>0xffffffff:
        raise ValueError('unsupported request extent')
    # Nominal hypothesis anchored to a version string and corroborating records.
    if not data[0x4540:].startswith(b'v1.5(release):Athens-'):
        raise ValueError('version anchor changed')
    delta=u64(0xfdf8)-0x4540
    anchors=[]
    for slot,marker in ((0xfe18,b'EBRS'),(0xfe30,b'EBHS')):
        off=file_offset(u64(slot),delta,4)
        if data[off:off+4]!=marker:
            raise ValueError('nominal pointer/record anchors differ')
        anchors.append(dict(slot=hex(slot),pointer=hex(u64(slot)),file_offset=hex(off),marker=marker.decode()))
    first,last=file_offset(source,delta),file_offset(end-1,delta)+1
    expected={0x380c:0xf90073b4,0x3810:0xcb140000,0x3814:0xb900eba0,
              0x3818:0xb900fba0,0x382c:0xf9007bb4,0x3878:0x94000274,
              0x43d8:0x37f00660,0x4434:0x2a0003eb,0x4438:0x2a1f03ec,
              0x443c:0x2a2b018c,0x4440:0x1100058c,0x4448:0x2a0c0160,
              0x4458:0x1004fdcb,0x445c:0x5800036e,0x4460:0x387069cf,
              0x4468:0x373801af,0x4470:0x531b69ea,0x4474:0xf86a496f,0x4494:0xd63f01e0}
    if any(word(data,p)!=w for p,w in expected.items()):
        raise ValueError('request/dispatcher witness changed')
    blocks={'entry_to_preparation':(0x3020,0x3070),'marker_and_seed':(0x312c,0x31f0),
            'first_mmio_poll':(0x350c,0x3574),'second_poll_failure':(0x37bc,0x37ec),
            'in_place_request':(0x37f0,0x387c),'preparation_result':(0x39e8,0x3a8c),
            'transform_wrapper':(0x4248,0x4294),'common_dispatcher':(0x43d8,0x44b0),
            'request_consumer':(0x3ad4,0x3b30),'mmio_words':(0x3d38,0x3db8)}
    ids=(0xffffffffffffFF1a,0xffffffffffffff19,0xffffffffffffff18,
         0xffffffffffffff17,0xffffffffffffff13,0xfffffffffffffc01,
         0xfffffffffffffb00,0x82002011)
    owner=common_id(ids[0])['owner_index']
    classification_pointer=u64(0x44c8)
    class_file=file_offset(classification_pointer,delta,128)+owner
    return dict(date='2026-10-23',mode='static_EPBL_preparation_and_common_dispatch',sboot_sha256=IMAGES['sboot'][1],
                nominal_mapping=dict(delta=hex(delta),candidate_entry_address=hex(delta+0x3020),
                                     version_pointer_slot='0xfdf8',version_file_offset='0x4540',
                                     corroborating_records=anchors,runtime_mapping_verified=False),
                in_place_request=dict(source_pointer_slot=hex(source_slot),end_pointer_slot=hex(end_slot),
                                      source_nominal=hex(source),destination_nominal=hex(source),bytes=end-source,
                                      candidate_file_range=[hex(first),hex(last)],call='0x3878',wrapper='0x4248',
                                      consumer='0x3ad4',plaintext_recovered=False,algorithm_verified=False,
                                      hardware_request_executed=False),
                preparation_gates=dict(entry_call='0x3044',entry_flag_address='0x15860990',
                                       skips_call_if_flag_nonzero=True,marker_comparison='0x3160-0x31b8',
                                       marker_success_bytes='SUCC',existing_marker_skips_preparation=True,
                                       preparing_marker_bytes='STAR',failure_marker_bytes='FAIL',
                                       state_or_execution_observed=False),
                hardware_dependency=dict(mmio_base='0x18330000',status_read_offsets=['0x18c','0x1010'],
                                         output_reads=['0x11c0','0x11ec'],
                                         first_poll_failure_value='0x1106',second_poll_failure_value='0x1107',
                                         values_are_internal_preparation_status_not_SMC_returns=True,
                                         verified_response_or_key_available=False),
                dispatcher=dict(common_block='0x4424',guarded_entry='0x43d8',
                                prefix_mask=hex(word(data,0x44bc)),legacy_base=hex(word(data,0x44c0)),
                                examples=[common_id(x) for x in ids],
                                classification_pointer=hex(classification_pointer),
                                candidate_classification_file_offset=hex(class_file),
                                raw_file_classification_byte=data[class_file],runtime_classification_known=False,
                                table_file_range=['0xe410','0xf410'],entry_stride=32,
                                table_inside_candidate_transform_region=first<=0xe410 and 0xf410<=last,
                                target_pointer_initial_bytes_sha256=hashlib.sha256(data[0xe410:0xe418]).hexdigest(),
                                class_bit7_rejects=True,actual_handler_linked=False),
                blocks={n:dict(start=hex(a),end_exclusive=hex(b),sha256=hashlib.sha256(data[a:b]).hexdigest())
                        for n,(a,b) in blocks.items()},
                secure_service_executed=False,firmware_modified=False,physical_device_tested=False,
                limitations=['Common-block normalization does not establish vector selection or passage of the bit-30 entry guard',
                             'Nominal delta is an explicit mapping hypothesis, not RAM ownership or runtime relocation proof',
                             'In-place request and self-decryption strings do not supply an algorithm, key, hardware response or verified plaintext',
                             'Raw classification byte and table bytes are not authenticated runtime bindings',
                             'SMC -0xe6/-0xe7/-0x3ff/-0x500 remain distinct unresolved handlers'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');args=p.parse_args()
    try:
        print(json.dumps(evidence(args.sboot),indent=2))
    except (OSError,ValueError,struct.error) as exc:
        p.exit(2,'EPBL preparation audit failed: '+str(exc)+'\n')
