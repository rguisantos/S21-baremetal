#!/usr/bin/env python3
"""Hash-bound static consumers of HZC2 NEWTIME; never executes firmware.

File offsets, nominal pointer translations and supplied-word models are
reported separately from runtime reachability. Requires both exact images.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_bl2_ram_size import NOMINAL_DELTA
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_columns_hzc2 import inspect as inspect_columns
from inspect_newtime_hzc2 import embedded
from inspect_newtime_record_hzc2 import unsigned

VDDCAL = (2097152, '2bac8e0eedc9395d7f5630442130a9ccae5a9201e700299a0a60a9565e886e39')
S = 0x31688
RANGES = {
    'sboot': (
        (0x1fcc4, 0x1fce8, '38a39e22109f823f54fed65fc2df2e2b64f9ab18ca238005a5005bd623c1e50d'),
        (0x21dc0, 0x21e74, '0fdc87508c87c7b26db46c8d66dc540d6df887956e5cfe5cf4c89bfb5cbda6ac'),
        (0x21f84, 0x22098, '89d9a17bfe31b36d6e71bcdb7d202d241e187e6c1c5a58e872a3e26e5671d30a'),
        (0x244ac, 0x24518, '56b78e6a09d607ab626d81813ac2a673bff524b8a894481dbb60ebcbf751f514'),
        (0x25050, 0x25070, 'e97c335cdde2ef3bb69bde5cbe4258338e52420a7f3a120d8222c712adc45cf8'),
        (0x257b8, 0x25840, '2cd6f09eb723bd575cdc2cab6edc5e0012dfa35ad04fde56770ed9b3be066eab'),
        (0x259f4, 0x25c5c, '9ce825b3ffb1955c0c6318b2753200df5b22dfba35ca70cb1bc114ff92112911'),
        (0x25cd8, 0x25f0c, 'c196a672bc811141c89c063adad81126b722613baad55fea64e6446c84c59fec'),
        (0x263b4, 0x264e0, '613902045a2327a99042f5f3bee08f1e151a7ebc26bc678f0d09edf92cbde551'),
        (0x269f0, 0x26af8, 'f2e55d60b5e7a3e1426748d12dd8c673f8a12d09561c79847ad1c1282aa84e37'),
        (0x26e14, 0x26f9c, 'c58a687d0c00b0ddd31d3af54d2167f0292ccf17d4d77828914ad3cd521fde7c'),
        (0x27a7c, 0x27af8, '5ba4c46eddcaf83d6ea913d3bc098f811999c40782892f93e41a8c2c9e780f30'),
        (0x28480, 0x284e4, 'eb47bc8f1e3911f01205ed8796f0c809dfc6452ab8b15c8e850c6e5801317548'),
        (0x2cb9c, 0x2ce88, '1fa07a2b5cee83df0aab9b9c714b9c9fc1a6ca1dd0240eede7b0198c1f72ee0e'),
        (0x2d41c, 0x2d468, '1b553222d21c8e90edc4dcbbe54ec49187a08c2d8c2dde0e870c535c87caa0e6'),
        (0x2dc18, 0x2dc84, '39a4741a993beb4b9c2bff62f79bfeaaff0091439aa4f2faca9df7ce2a1159ce'),
        (0x2f098, 0x2f0d8, '543628fb494dea15c84c89709af302868449a2d849957c6fbbee46258267f09a'),
    ),
    'vddcal': ((0x675a4, 0x677d4, '5480bd19f826b532181a0c3638a6e120f7a108dec6da987f9b4fb69f49fba711'),),
}


def occurrences(data, needle):
    """All byte offsets, including unaligned and overlapping matches."""
    if not needle:
        raise ValueError('empty search pattern')
    result, offset = [], 0
    while (offset := data.find(needle, offset)) != -1:
        result.append(offset)
        offset += 1
    return result


def branch_candidates(data, target, first=0x16000, last=0x2fd00):
    """Aligned B/BL encodings in a bounded region, not a reachability proof."""
    if first < 0 or first % 4 or last % 4 or first > last or last > len(data):
        raise ValueError('invalid branch scan bounds')
    result = []
    for pc in range(first, last, 4):
        word = struct.unpack_from('<I', data, pc)[0]
        if word & 0x7c000000 != 0x14000000:
            continue
        immediate = word & 0x3ffffff
        if immediate & 0x2000000:
            immediate -= 1 << 26
        if pc + immediate * 4 == target:
            result.append(dict(pc=hex(pc), opcode=f'{word:08x}', kind='bl' if word >> 31 else 'b'))
    return result


def column12_word(word):
    """Fields read by 2cdb8; calls are conditional on preserved runtime bindings."""
    word = unsigned(word, 32)
    selector = (word >> 12) & 31
    actions = [(word >> shift) & 15 for shift in (8, 4, 0)]
    commands = []
    for action in actions:
        if action <= 7:
            commands.append(dict(w2=9, w3=1 << action))
        elif action <= 10:
            commands.append(dict(w2={8:73, 9:57, 10:59}[action], w3=0))
        else:
            commands.append(None)  # 2cd1c returns without an indirect call.
    return dict(word=hex(word), selector_bits_16_12=selector,
                helper_2cbec_w3_sequence=[1, 1, 1] if selector == 1 else [2, 4, 1],
                action_nibbles_11_8_7_4_3_0=actions, helper_2cd1c_commands=commands)


def directory_entries(data, first, count):
    """Read the candidate 40-byte records without interpreting pointer relocation."""
    if type(count) is not int or not 0 <= count <= 64 or first < 0 or first + count*40 > len(data):
        raise ValueError('directory outside supplied bytes or count limit')
    result = []
    for index in range(count):
        offset = first + index*40
        name_bytes = data[offset+8:offset+24]
        if 0 not in name_bytes:
            raise ValueError('unterminated directory name')
        name = name_bytes.split(b'\0', 1)[0].decode('ascii')
        field, pointer = struct.unpack_from('<QQ', data, offset+24)
        result.append(dict(record_file=hex(offset), name_file=hex(offset+8), name=name,
                           prefix_u64=hex(struct.unpack_from('<Q', data, offset)[0]),
                           field_at_24=field, equals_name_length=field == len(name),
                           pointer_raw=hex(pointer)))
    return result


def instruction_index(data, ranges):
    packed = bytearray()
    for first, last, digest in ranges:
        if hashlib.sha256(data[first:last]).hexdigest() != digest:
            raise ValueError(f'instruction witness changed at {first:#x}')
        for pc in range(first, last, 4):
            packed += struct.pack('<I', pc) + data[pc:pc+4]
    return dict(words=len(packed)//8, sha256=hashlib.sha256(packed).hexdigest(),
                ranges=[dict(first=hex(a), end_exclusive=hex(b), sha256=h) for a,b,h in ranges])


def inspect(sboot_path, vddcal_path):
    data = read_exact(sboot_path, *IMAGES['sboot'])
    vddcal = read_exact(vddcal_path, *VDDCAL)
    previous = inspect_columns(sboot_path)
    tables = {t['key']:t for t in embedded(data)['parsed']['entries']}
    pointers = []
    for table,index in ((0x30e50,25),(0x30e50,26),(0x31408,24),(0x31408,26)):
        cell = table+index*8
        pointer = struct.unpack_from('<Q', data, cell)[0]
        pointers.append(dict(table=hex(table), index=index, cell=hex(cell), raw=hex(pointer),
                             nominal_target=hex(pointer-NOMINAL_DELTA)))
    targets = (0x26e14,0x25b80,0x2d568,0x2d5f8,0x2e4b4,0x244ac,0x244b8,0x25050,0x2cdb8)
    references = [dict(target=hex(t), direct_encoding_candidates=branch_candidates(data,t),
        nominal_u64_occurrences=[hex(i) for i in occurrences(data,struct.pack('<Q',t+NOMINAL_DELTA))])
        for t in targets]
    return dict(mode='static_newtime_consumers',
        images=dict(sboot=dict(bytes=IMAGES['sboot'][0],sha256=IMAGES['sboot'][1]),
                    vddcal=dict(bytes=VDDCAL[0],sha256=VDDCAL[1])),
        instruction_indexes={name:instruction_index(image,RANGES[name])
            for name,image in (('sboot',data),('vddcal',vddcal))},
        previous_column_instruction_index=previous['new_instruction_index_sha256'],
        common_address_anchor=dict(S=hex(S), source_language_object_identity_proven=False,
            fields=[dict(relative=hex(offset-S), file=hex(offset), role=role)
                for offset,role in ((0x31698,'column12 row count byte'),(0x316a0,'column12 payload pointer'),
                    (0x31758,'column1 payload pointer'),(0x31c30,'mutable pointer to 162-byte records'),
                    (0x31f30,'108-byte scratch buffer'),(0x31fa0,'108-byte-stride scratch records, not pointer table'))]),
        pointer_31c30=dict(initial_u64=hex(struct.unpack_from('<Q',data,0x31c30)[0]),
            address_spill='0x25d3c/0x25d44 -> 0x25d48 [sp+128]',
            provider_call='0x25ee8 -> 0x22014 -> 0x21f84 -> 0x21dc0',
            provider_labels=[data[a:data.index(0,a)].decode('ascii') for a in (0x302b5,0x302c1)],
            size_expression='u8(current_object+12) * 162',
            store='0x25eec reload [sp+128]; 0x25ef0 STR X0,[X1]',
            following_zero='0x25f08 -> 0x1f9e8, returned buffer, same count*162 bytes',
            record_use='0x25c18 load pointer; 0x25c14 signed W20*162; 0x25c24 calls 0x25a98',
            helper_input_X3='0x31f30 (108 bytes)', helper_inout_X2='loaded pointer + signed index*162',
            data_direction='108-byte buffer -> selected fields in 162-byte record; not reverse',
            selection_link_to_newtime_proven=False),
        controller_loop=dict(entry='0x26e14', stack_sub=2176, saved_register_frame=96, total_stack=2272,
            passes='2 if byte at0x31939 equals3; otherwise1', iterations_per_pass=64,
            stack_array_offset=544, stack_array_bytes=1728, record_bytes=108,
            stack_array_reused_per_channel_and_pass=True,
            direct_call_modes={'0x244c4':0,'0x244f0':2,'0x25058':1},
            function_269f0_base_table='0x30fc0',
            base_values=[hex(x) for x in struct.unpack_from('<4Q',data,0x30fc0)]),
        dispatch=dict(nominal_delta=hex(NOMINAL_DELTA), initial_pointers=pointers,
            access_28480=dict(writes=['base+0','base+4'], read_result='base+12',
                bases=[hex(x) for x in struct.unpack_from('<5Q',data,0x30f98)]),
            callers={'0x263e4':dict(index=25,w2=26),'0x26478':dict(index=26,w2=26),
                     '0x264d4':dict(index=26,w2=26)},
            actual_runtime_dispatch_verified=False),
        column12=dict(reader='0x2cdb8', count_byte='0x31698', skip_if_count_at_most=1,
            pointer_loads=['0x2ce08','0x2ce28','0x2ce40','0x2ce54'], payload_pointer='0x316a0',
            payload_reads=['0x2ce10 u32','0x2ce30 byte+1','0x2ce44 byte+0','0x2ce58 byte+0'],
            stride=4, pointer_and_count_reloaded=True,
            conditional_sequence_per_word=['2cbec(selector)','2cb9c()','2cd1c(nibble11:8)',
                '2cd1c(nibble7:4)','2cd1c(nibble3:0)','2cb9c()'],
            nominal_writer='slot25 of0x30e50 -> 0x27a7c',
            writer_fields='W1 bits1:0 -> base bits29:28; W2 bits6:0 -> bits26:20; W3 bits7:0 -> base+8',
            writer_stores={'0x27ad8':'base+0 control','0x27ae0':'base+56 =22',
                           '0x27ae8':'base+8 data','0x27aec':'base+4 =16'},
            supplied_payload_models=[dict(key=hex(key),rows=tables[key]['rows'],
                entries=[column12_word(w) for w in tables[key]['cells']]) for key in (0x71,0x73)],
            runtime_alias_pointer_preservation_and_physical_meaning_verified=False),
        reference_search=dict(branch_region=['0x16000','0x2fd00'],branch_alignment=4,
            nominal_pointer_search='entire sboot, all byte offsets; absence is not unreachability',targets=references),
        vddcal=dict(directory=directory_entries(vddcal,0xf7500,5),
            index_raw=[dict(cell=hex(a),value=hex(struct.unpack_from('<Q',vddcal,a)[0]))
                       for a in (0xf89e0,0xf89e8,0xf89f8,0xf8a18)],
            key_u64_occurrences={hex(key):[hex(i) for i in occurrences(vddcal,struct.pack('<Q',key))]
                for key in (0x1000860000110,0x1000850500130)},
            candidate_parser_prologue='0x675e0', candidate_parser_record_bytes=24,
            directory_pointer_low48='0x67630', instruction_at_that_file_offset='ADD X0,X29,#0x18',
            file_offset_67630_is_internal_to_candidate_parser=True,
            pointer_translation_or_handler_binding_proven=False,
            high_pointer_bits_alone_do_not_prove_relocation=True),
        firmware_executed=False, qemu_scope_extended=False, phone_access=False,
        physical_timing_parameter_identified=False)


def gnu(sboot_path, vddcal_path, report):
    root = Path(__file__).resolve().parent.parent
    command = ['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    selected = {
        'sboot': {
            0x25d48:('str','x0, [sp, #128]'),0x25ed8:('ldr','x2, [sp, #128]'),
            0x25eec:('ldr','x1, [sp, #128]'),0x25ef0:('str','x0, [x1]'),
            0x25c14:('smull','x20, w20, w2'),0x25c18:('ldr','x2, [x0, #3120]'),
            0x25ae8:('ldrh','w4, [x3, x4, lsl #1]'),0x25af0:('strh','w4, [x6, #4]'),
            0x25b18:('ldrh','w1, [x0, #72]'),0x25b30:('strh','w1, [x2]'),
            0x26e20:('stp','x19, x20, [sp, #-96]!'),0x26e54:('csinc','w0, w0, wzr, eq'),
            0x263d4:('ldr','x4, [x19, #200]'),0x26470:('ldr','x3, [x0, #208]'),
            0x284d0:('str','w3, [x0]'),0x284d4:('str','w1, [x0, #4]'),
            0x2cdc0:('ldrb','w3, [x1, #16]'),0x2cdf8:('ldrb','w0, [x20, #16]'),
            0x2ce08:('ldr','x0, [x20, #24]'),0x2ce10:('ldr','w1, [x0, x22]'),
            0x2ce18:('ubfx','x1, x1, #12, #5'),0x2ce30:('ldrb','w1, [x0, #1]'),
            0x2ce38:('and','x1, x1, #0xf'),0x2ce4c:('ubfx','x1, x1, #4, #4'),
            0x2ce60:('and','x1, x1, #0xf'),0x27ad8:('str','w4, [x0]'),
            0x27ae0:('str','w1, [x0, #56]'),0x27ae8:('str','w2, [x0, #8]'),
            0x27aec:('str','w1, [x0, #4]'),0x2dc74:('str','w4, [x5, x3]'),
        },
        'vddcal': {0x675e0:('stp','x29, x30, [sp, #-80]!'),0x67630:('add','x0, x29, #0x18'),
                    0x67700:('str','x1, [x0]'),0x67710:('str','w1, [x0, #8]')},
    }
    results = {}
    for name,path,identity in (('sboot',sboot_path,IMAGES['sboot']),('vddcal',vddcal_path,VDDCAL)):
        data = read_exact(path,*identity)
        lines = {}
        for first,last,_ in RANGES[name]:
            output = subprocess.check_output(command+['-D','-b','binary','-m','aarch64',
                f'--start-address={first}',f'--stop-address={last}',str(Path(path).resolve())],text=True)
            lines.update(parse_lines(output))
        expected = [pc for a,b,_ in RANGES[name] for pc in range(a,b,4)]
        if sorted(lines) != expected:
            raise ValueError('GNU witness coverage differs')
        relative = 0
        for pc,(word,op,args) in lines.items():
            if word != struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):
                raise ValueError(f'GNU instruction mismatch at {pc:#x}')
            kind,target = flow(word,pc)
            if kind in ('b','bl','conditional'):
                if target != direct_target(op,args):
                    raise ValueError('GNU relative target differs')
                relative += 1
        for pc,expected_operand in selected[name].items():
            if lines[pc][1:] != expected_operand:
                raise ValueError(f'GNU operand mismatch at {pc:#x}: {lines[pc][1:]}')
        digest = hashlib.sha256(b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))).hexdigest()
        if digest != report['instruction_indexes'][name]['sha256']:
            raise ValueError('GNU instruction index differs')
        results[name] = dict(words=len(lines),relative_targets=relative,
            selected_operands=len(selected[name]),instruction_index_sha256=digest)
    return dict(mode='GNU_newtime_consumers',images=report['images'],results=results,
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        firmware_executed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot'); parser.add_argument('vddcal'); parser.add_argument('--gnu',action='store_true')
    args = parser.parse_args()
    try:
        result = inspect(args.sboot,args.vddcal)
        if args.gnu:
            result = gnu(args.sboot,args.vddcal,result)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'inspect_newtime_consumers_hzc2: {exc}\n')
    print(json.dumps(result,indent=2))
