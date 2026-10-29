#!/usr/bin/env python3
"""Static ACPM channel1 -> FVP command6 -> DVFS bridge and reply projection."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal, thumb_target, thumb_pair, thumb_wide
from inspect_el2_hzc2 import IMAGES, read_exact

U32 = (1 << 32)-1
RANGES = ((0x386bc,0x3879a), (0x38b04,0x38bd4), (0x38e2a,0x38e92),
          (0x391c4,0x39250), (0x3928e,0x392a4), (0x398e8,0x39964),
          (0x399be,0x399ca), (0x39b48,0x39b88), (0x39bba,0x39bc4), (0x39cc2,0x39cca),
          (0x39d52,0x39d84), (0x3f000,0x3f016), (0x3f0d0,0x3f16c), (0x3f16c,0x3f1aa),
          (0x3f1c6,0x3f1f4), (0x3f248,0x3f2dc), (0x3f38c,0x3f3aa),
          (0x3f3e4,0x3f40e), (0x3f49a,0x3f53e), (0x3f644,0x3f690),
          (0x3f6a4,0x3f6bc), (0x56e00,0x56e0a), (0x5bb6c,0x5bbe4))
SELECTED = {
    0x386e4:('ldr','r2, [r3, #40]'), 0x386ea:('ldr','r2, [r3, #44]'),
    0x386f0:('adds','r2, #1'), 0x386fa:('cmp','r5, r2'),
    0x386fc:('beq.n','0x3871a'), 0x38734:('wfi',''),
    0x38736:('b.n','0x38734'), 0x3876a:('bl','0x386bc'),
    0x3877a:('lsrs','r3, r3, #16'), 0x3877c:('lsls','r3, r3, #16'),
    0x3877e:('orrs','r3, r2'), 0x38780:('dsb','sy'),
    0x38784:('str','r3, [r0, #0]'), 0x38796:('str','r6, [r2, #0]'),
    0x38b22:('cmp','r3, r1'), 0x38b24:('bls.n','0x38b36'),
    0x38b32:('ldrb','r2, [r3, r2]'), 0x38b58:('ldr','r2, [r3, #12]'),
    0x38b5a:('ldr','r2, [r2, #12]'), 0x38b62:('ldr','r0, [r0, #0]'),
    0x38b64:('ldr','r3, [r3, #20]'), 0x38b68:('tst','r3, r2'),
    0x38b6a:('bne.n','0x38b74'), 0x38b9e:('ldr','r3, [r3, #12]'),
    0x38ba2:('blx','r3'), 0x38e46:('str','r2, [r1, #0]'),
    0x38e48:('adds','r1, #48'), 0x38e80:('ldr','r3, [r3, #4]'),
    0x38e90:('blx','r8'), 0x391ce:('adds','r2, #20'),
    0x391e6:('adds','r2, #72'), 0x3923e:('ldr','r1, [r3, #24]'),
    0x39240:('ldr','r3, [r3, #28]'), 0x39244:('add','r2, ip'),
    0x39248:('str','r3, [sp, #12]'), 0x3928e:('ldr','r3, [r3, #12]'),
    0x39290:('ldr','r3, [r3, #0]'), 0x39296:('ldr','r1, [sp, #16]'),
    0x39298:('add','r0, sp, #24'), 0x3929a:('blx','r3'),
    0x398ec:('movw','r2, #1080'), 0x398f8:('ldr','r2, [r0, #72]'),
    0x39912:('str','r1, [r3, #40]'), 0x39918:('str','r1, [r3, #44]'),
    0x39920:('str','r2, [r3, #48]'), 0x39942:('str','r2, [r3, #24]'),
    0x3994a:('str','r5, [r3, #16]'), 0x39952:('str','r5, [r3, #20]'),
    0x39956:('adds','r3, #72'), 0x399c2:('str','r1, [r3, #100]'),
    0x39b5e:('str','r3, [r0, #8]'), 0x39b70:('str','r3, [r0, #12]'),
    0x39b80:('str','r3, [r0, #68]'), 0x39b86:('str','r3, [r0, #76]'),
    0x39bbc:('str','r2, [r4, #72]'),
    0x39cc6:('cmp','r2, #2'), 0x39cc8:('beq.n','0x39d52'),
    0x39d5e:('str','r3, [r7, #0]'), 0x39d6c:('movs','r0, #2'),
    0x39d6e:('movs','r1, #72'), 0x3f00a:('str','r3, [r0, #12]'),
    0x3f0da:('str','r2, [sp, #20]'), 0x3f10e:('ldr','r0, [r3, #0]'),
    0x3f110:('add','r2, sp, #20'), 0x3f114:('str','r2, [sp, #0]'),
    0x3f116:('ldr','r4, [r3, #28]'), 0x3f118:('movs','r1, #7'),
    0x3f11a:('add','r3, sp, #16'), 0x3f11c:('add','r2, sp, #12'),
    0x3f11e:('blx','r4'), 0x3f2cc:('bl','0x3f0d0'),
    0x3f176:('ldr','r3, [r0, #0]'), 0x3f17c:('ldr','r2, [r3, #4]'),
    0x3f182:('ldr','r5, [r3, #8]'), 0x3f186:('cmp','r1, #15'),
    0x3f19c:('cmp','r5, #6'), 0x3f19e:('bls.n','0x3f1a2'),
    0x3f1a8:('mov','pc, r3'), 0x3f1d0:('ands','r6, r0'),
    0x3f1de:('orrs','r4, r6'), 0x3f1e0:('str','r4, [r0, #0]'),
    0x3f1e4:('str','r2, [r3, #0]'), 0x3f1f2:('blx','r3'),
    0x3f39a:('ldr','r3, [sp, #16]'), 0x3f39e:('cmp','r3, #1'),
    0x3f3a2:('b.n','0x3f6a4'), 0x3f4b0:('str','r6, [r2, #4]'),
    0x3f6aa:('ldr','r6, [sp, #20]'), 0x3f6ba:('b.n','0x3f49a'),
    0x56e04:('str','r3, [r0, #12]'), 0x5bb70:('ldr','r4, [r2, #0]'),
    0x5bbb4:('cmp','r4, #16'), 0x5bbbe:('cbz','r3, 0x5bbc8'),
    0x5bbc0:('ldr','r0, [r0, #0]'), 0x5bbc2:('ldr','r1, [r1, #0]'),
    0x5bbc4:('blx','r3'),
}


def u32(value):
    if type(value) is not int or not 0 <= value <= U32:
        raise ValueError('expected host u32')
    return value


def core_file(address):
    u32(address)
    if 0x4000 <= address < 0x9000:
        return address+0x34000
    if 0xf800 <= address < 0x39800:
        return address+0x2d800
    raise ValueError('outside selected nominal Thumb copy mappings')


def thumb_lsl(value, count):
    u32(value); u32(count)
    shift = count & 255
    return (value << shift)&U32 if shift < 32 else 0


def allocate_channels(start, descriptors):
    """Bounded host fixture for zero-pointer rows of 398e8, not a RAM guard."""
    u32(start)
    if not 1 <= len(descriptors) <= 15:
        raise ValueError('host channel fixture limit')
    result = []
    for row in descriptors:
        for key in ('tx','rx','count','stride'):
            u32(row[key])
        if row['tx'] or row['rx']:
            result.append(dict(allocated=False, **row))
            continue
        size = row['count']*row['stride'] & U32
        result.append(dict(allocated=True, tx=(start+size+32)&U32, rx=(start+16)&U32,
            tx_read=(start+size+24)&U32, tx_write=(start+size+28)&U32,
            rx_read=(start+8)&U32, rx_write=(start+12)&U32,
            count=row['count'], stride=row['stride']))
        start = (start+2*((size+16)&U32))&U32
    return dict(rows=result, next=start)


def fvp_packet(words, channel):
    if len(words) != 4:
        raise ValueError('host packet requires four words')
    for v in words: u32(v)
    u32(channel)
    return dict(channel15_special=channel==15, domain=words[0]&65535,
                header=words[0]&0xffff0000, value=words[1], command=words[2],
                generic_switch=channel!=15 and words[2]<=6)


def service_allowed(count, enabled, callback, callers, caller, target=7):
    for v in (count,enabled,callback,callers,caller,target): u32(v)
    return count>target and enabled!=0 and callback!=0 and bool(callers & thumb_lsl(1,caller))


def response_projection(header, internal_result):
    """Private stable reply slot: FVP -> 386bc -> 38738; no hardware execution."""
    for v in (header,internal_result): u32(v)
    constructed = (header & 0xffff0000) | (internal_result & 65535)
    # 386bc captures the high half of the allocated slot; 38738 captures it
    # again after the callback has written 'constructed', then projects it.
    captured = constructed & 0xffff0000
    published = (constructed & 0xffff0000) | captured
    return dict(constructed=constructed, published=published,
                BL2_word_matches=published == (header & 0xffff0000))


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    cmd = ['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
           str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for lo,hi in RANGES:
        if lo%2 or hi%2: raise ValueError('unaligned Thumb range')
        output = subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',
            f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True)
        lines.update(parse_thumb(output))
    covered=set();relative=0;literals=0
    for pc,(raw,op,args) in sorted(lines.items()):
        if raw!=data[pc:pc+len(raw)] or op in ('.short','.word','.inst','udf'):
            raise ValueError(f'GNU Thumb word differs at {pc:#x}')
        span=set(range(pc,pc+len(raw),2))
        if span&covered: raise ValueError('overlapping Thumb instructions')
        covered |= span
        target=thumb_target(data,pc)
        if target is not None:
            printed=int(args.split('@')[0].split(',')[-1].strip(),0)
            if target!=printed: raise ValueError(f'GNU relative target differs at {pc:#x}')
            relative+=1
        # The selected ranges use short branches and BL, covered by thumb_target.
        elif op in ('b.n','b.w','bl','beq.n','bne.n','bcc.n','bcs.n','bhi.n','bls.n','cbz','cbnz'):
            raise ValueError(f'unhandled relative branch at {pc:#x}')
        if op=='ldr' and '[pc,' in args:
            reg=int(args.split(',')[0][1:]);lit,_=thumb_literal(data,pc,reg)
            if f'(0x{lit:x})' not in args: raise ValueError('GNU literal target differs')
            literals+=1
    if covered != {p for lo,hi in RANGES for p in range(lo,hi,2)}:
        raise ValueError('GNU Thumb coverage differs')
    for pc,expected in SELECTED.items():
        raw,op,args=lines[pc]
        if (op,args.split('@')[0].strip())!=expected:
            raise ValueError(f'GNU selected operand differs at {pc:#x}: {(op,args)}')
    word=lambda p:struct.unpack_from('<I',data,p)[0]
    def wides(lo,hi,reg):
        a,b=thumb_wide(data,lo),thumb_wide(data,hi,True)
        if a[0]!=reg or b[0]!=reg: raise ValueError('wide register differs')
        return a[1]|b[1]<<16
    if (thumb_pair(data,0x39b48,3),wides(0x39b54,0x39b5a,3),
        wides(0x38e3a,0x38e42,2))!=(0x7150,0x73c0,0x710c):
        raise ValueError('core table constants differ')
    counts=[]
    for i in range(2):
        fields=struct.unpack_from('<18I',data,0x3b3c0+72*i)
        counts.append(dict(tx=fields[6],rx=fields[12],count=fields[13],stride=fields[14]))
    allocation=allocate_channels(word(0x39c2c),counts)
    c=allocation['rows'][1]
    expected=dict(tx=0x8a50,rx=0x8a10,tx_read=0x8a48,tx_write=0x8a4c,
                  rx_read=0x8a08,rx_write=0x8a0c,count=3,stride=16)
    if any(c[k]!=v for k,v in expected.items()): raise ValueError('selected channel plan differs')
    init=word(0x39a50)|1
    methods=thumb_pair(data,0x3f000,3)
    callback=word(core_file(methods))
    jump=word(0x3f46c);target=word(core_file(jump)+6*4)
    dvfs_methods=word(0x56e74);dvfs_callback=word(core_file(dvfs_methods)+12)
    dispatch=word(0x5bbe8);slot0=word(core_file(dispatch))
    if (init,methods,callback,jump,target,dvfs_methods,dvfs_callback,dispatch,slot0)!=(
        0x11801,0x1205c,0x1196d,0x11f84,0x11b8c,0x2e828,0x2e36d,0x2f400,0x2c3e5):
        raise ValueError('selected plugin pointers differ')
    mask=word(0x3b150+7*48+20)
    if [word(0x3b10c+i) for i in (12,16,28)] != [0x46bd,0x4739,0x4b05]:
        raise ValueError('selected API method pointers differ')
    names={}
    for i in (2,7):
        name_at=core_file(word(0x3b150+48*i+44))
        names[str(i)]=data[name_at:name_at+64].split(b'\0')[0].decode('ascii')
    return dict(mode='static_newtime_command6_ACPM_bridge_hzc2',source_base='a2b02e29b62705e739d2c97d4a78b450912c5e48',
        sboot_sha256=IMAGES['sboot'][1],
        mapping=dict(first_copy=dict(file=['0x38000','0x3d000'],core=['0x4000','0x9000']),
            second_copy=dict(file=['0x3d000','0x67000'],core=['0xf800','0x39800']),
            AP_if_alias='u32(core+0x02039000)',alias_physically_verified=False),
        channel1=dict(producer='0x39b5e: core8008=73c0',record_core='0x7408',record_stride=72,
            allocator='0x398e8',first2_plan=allocation,
            candidate_AP=dict(tx=hex(c['tx']+0x2039000),rx=hex(c['rx']+0x2039000)),
            assumptions='selected allocator starts at core8800, both initial pointer pairs zero, first two rows preserved',
            initial_indices_assumed=False),
        route=dict(singleton_event_kind=128,singleton_mask=2,selector='0x39cc6 -> 0x39d52',
            channel=1,plugin=2,plugin_names=names,plugin_init_file=hex(core_file(init&~1)),
            descriptor_core='0x71b0',api_installed='0x38e46: descriptor+8=core710c',
            methods_core=hex(methods),receive_pointer=hex(callback),receive_file=hex(core_file(callback&~1)),
            call='0x3929a',arguments='R0=&request_slot_pointer; R1=channel1',
            runtime_event_and_dispatch_observed=False),
        command=dict(source_word=2,word0='domain low16 / header high16',value_word=1,
            jump_table_core=hex(jump),entry6_core=hex(target),entry6_file=hex(core_file(target)),
            selected_domain=0,selected_request='store requested value at core120f4 (0x3f4b0)',
            policy='effective word also depends on state+8/+12, cap+16 and global policies; not always raw request',
            temporary_NEWTIME_B_consumption_proved=False),
        service=dict(api28_initial_pointer=hex(word(0x3b10c+28)),relay_file='0x38b04',
            caller_plugin=2,target_plugin=7,target_methods_core=hex(dvfs_methods),
            target_method_offset=12,target_pointer=hex(dvfs_callback),target_file=hex(core_file(dvfs_callback&~1)),
            initial_allow_mask=hex(mask),caller_bit='0x4',allowed_by_initial_mask=bool(mask&4),
            guards='count>7, target enabled byte+32, nonzero callback, allow mask bitcaller',
            arguments='pointers to domain0, effective value and mode0; actual calls/returns require stable frames and roots',
            dispatch_table_core=hex(dispatch),initial_mode0_pointer=hex(slot0),next_target_file=hex(core_file(slot0&~1)),
            next_target_effects='open; no hardware result inferred'),
        reply=dict(construction='0x3f1de/0x3f1e0: header_high16 | low16(internal_result)',
            first2_words_only='selected path writes word0 and word1; does not initialize reply words2/3',
            publish_api16_pointer='0x4739',publish_file='0x38738',reacquire='0x3876a -> 0x386bc',
            projection='0x3877a/0x3877c clear low16; OR saved high16 from the same stable reply slot',
            selected_published_word0=0,internal_result_recoverable_from_BL2_match=False,
            caveat='normal private stable slot/config; unrelated writers or aliases can invalidate this projection',
            full_reply_slot_poll='0x386fc -> 0x38734 WFI loop',has_success_inference=False),
        conditions=['copy mappings, SRAM and MMIO local/AP aliases, init order and pointer publication are conditional',
            'queue config/indices, plugin callbacks, enabled flags, access masks, stack and packets preserved',
            'BL/BLX/logging/policy calls return normally, preserve carried registers/private frames and selected roots/words',
            'the local/API relay result is opaque; header projection is not proof of successful physical DVFS',
            'no exclusion of dynamic aliases, global writers, other events, plugin routes or slot47 callers'],
        gnu=dict(version=subprocess.check_output(cmd+['--version'],text=True).splitlines()[0],
            instructions=len(lines),halfwords=len(covered),relative_targets=relative,literal_xrefs=literals,
            selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(pc),bytes=raw.hex(),op=op,args=args) for pc,(raw,op,args) in sorted(lines.items())],
        firmware_executed=False,qemu_scope_extended=False,physical_device_tested=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try: report=inspect(args.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'inspect_newtime_command6_hzc2: {exc}\n')
    print(json.dumps(report,indent=2))
