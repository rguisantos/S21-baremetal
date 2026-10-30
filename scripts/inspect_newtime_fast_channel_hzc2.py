#!/usr/bin/env python3
"""Selected ACPM direct channel3 and DVFS method+0; no physical readiness claim."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from check_acpm_handshake_gnu import parse_thumb
from check_epbl_protocol_gnu import parse_lines, direct_target
from inspect_acpm_handshake_hzc2 import thumb_literal, thumb_target, thumb_wide
from inspect_bl2_geometry_record import wide64
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow

RANGES=((0x386bc,0x386e4),(0x38738,0x38768),(0x3933c,0x39470),
        (0x398e8,0x39964),(0x39964,0x3998c),(0x39c34,0x39c5a),
        (0x39cc2,0x39d52),(0x39d72,0x39d84),(0x56e98,0x56eac),
        (0x5a994,0x5a99e),(0x3a004,0x3a030),(0x397a4,0x397be),
        (0x39ca4,0x39cbe),(0x545d2,0x545e2))
SELECTED={0x386d2:('ldr','r2, [r3, #12]'),0x386e0:('ldr','r0, [r3, #48]'),
 0x38762:('blx','r2'),0x39368:('blx','r3'),0x3938e:('blx','r5'),
 0x393a0:('ldr','r2, [r3, #24]'),0x393a4:('str','r2, [sp, #16]'),
 0x393aa:('ldr','r3, [r2, #0]'),0x393c6:('ldr','r3, [r3, #0]'),
 0x39414:('add','r0, sp, #16'),0x39416:('blx','r3'),
 0x39904:('cbnz','r1, 0x39956'),0x39908:('cbnz','r1, 0x39956'),
 0x39956:('adds','r3, #72'),0x39966:('beq.n','0x39984'),
 0x39d22:('ldr','r2, [r5, r2]'),0x39d28:('mov','ip, r3'),
 0x39d2c:('str','r3, [r7, #0]'),0x39d46:('ldr','r0, [r3, r2]'),
 0x56e9c:('ldr','r2, [r3, #0]'),0x56ea0:('cmp','r2, r3'),
 0x56ea2:('bne.n','0x56ea8'),0x56ea4:('bl','0x5a938'),
 0x56ea8:('movs','r0, #0'),0x5a998:('str','r2, [r3, #0]')}


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
         str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    target=str(Path(path).resolve());rows={};literals={};relative=0
    for lo,hi in RANGES:
        found=parse_thumb(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',
            f'--start-address={lo}',f'--stop-address={hi}',target],text=True))
        if {h for p,(raw,_,_) in found.items() for h in range(p,p+len(raw),2)}!=set(range(lo,hi,2)):
            raise ValueError('Thumb coverage mismatch')
        rows.update(found)
    for pc,(raw,op,args) in rows.items():
        if raw!=data[pc:pc+len(raw)] or op.startswith('.'):raise ValueError('Thumb word mismatch')
        to=thumb_target(data,pc)
        if to is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=to:raise ValueError('branch mismatch')
            relative+=1
        if op=='ldr' and '[pc,' in args:
            at,v=thumb_literal(data,pc,int(args.split(',')[0][1:]));literals[at]=v
            if f'(0x{at:x})' not in args:raise ValueError('literal mismatch')
    for pc,expected in SELECTED.items():
        _,op,args=rows[pc]
        if (op,args.split('@')[0].strip())!=expected:raise ValueError(f'operand mismatch {pc:#x}')
    a64=parse_lines(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','aarch64',
        '--start-address=0x18000','--stop-address=0x1801c',target],text=True))
    if set(a64)!=set(range(0x18000,0x1801c,4)):raise ValueError('A64 coverage mismatch')
    for pc,(w,op,args) in a64.items():
        if w!=struct.unpack_from('<I',data,pc)[0]:raise ValueError('A64 word mismatch')
        kind,to=flow(w,pc)
        if kind in ('b','bl','conditional') and direct_target(op,args)!=to:raise ValueError('A64 branch mismatch')
    if a64[0x18018][1:]!=('str','wzr, [x0]'):raise ValueError('clear instruction mismatch')
    if wide64(data,(0x18010,0x18014),0)!=0x15900104:raise ValueError('AP clear address mismatch')
    word=lambda a:struct.unpack_from('<I',data,a)[0]
    anchors={0x3b4a4:2,0x3b4b0:0xa5900100,0x3b4c8:0xa5900108,0x3b4cc:1,0x3b4d0:16,
        0x3b9a8:7,0x3b974:0x5965,0x3b978:0x6005,0x3b968:0x5c35,
        0x56e74:0x2e828,0x5c028:0x29699,0x56eac:0xa590010c,0x56eb0:0xabcd1234,
        0x56e88:0x1234abcd,0x56e8c:0xa590010c,0x5a9a4:0xa590010c}
    if any(word(a)!=v for a,v in anchors.items()):raise ValueError('anchor mismatch')
    if (thumb_wide(data,0x39d3c),thumb_wide(data,0x39d42,True))!=((2,0x799c),(2,0)):
        raise ValueError('plugin mapping base mismatch')
    for lo,hi,expected in ((0x397a4,0x397ac,0xa5910104),(0x39ca4,0x39cac,0xa5910104),
                           (0x545d2,0x545d6,0xa5960104)):
        low,high=thumb_wide(data,lo),thumb_wide(data,hi,True)
        if (low[0],high[0],low[1]|high[1]<<16)!=(3,3,expected):raise ValueError('neighbor address mismatch')
    channel=struct.unpack_from('<18I',data,0x3b498)
    return dict(source_base='a3610ff0da8f1d2318f70be66b6f52728e96f57c',sboot_sha256=IMAGES['sboot'][1],
        scope='selected direct event path; no exhaustive reader census or live register values',
        channel=dict(index=channel[0],core_descriptor='0x7498',file_descriptor='0x3b498',stride=72,
            file_words=list(channel),type=channel[3],request=hex(channel[6]),response=hex(channel[12]),
            count=channel[13],packet_stride=channel[14],allocator_skips=True,
            ap_clear='0x18018 clears AP0x15900104 after return of0x18000',
            candidate_word='word1 of local request buffer0xa5900100, under AP/local alias',
            packet_word1_read_on_selected_path=False),
        route=dict(event=128,mask=8,decoder='0x39c34; exact mask8 uses priority fallback',
            channel_output=3,plugin_output=7,plugin_map='core0x799c[3] =7',
            plugin_map_words=list(struct.unpack_from('<15I',data,0x3b99c)),
            direct_dispatcher='0x3933c',queue_dispatcher='0x39164 (different path)',
            request_pointer_load='0x393a0',slot='frame+16',callback_call='0x39416',
            callback_interface='core0x2e828+0 =0x29699',callback_file='0x56e98'),
        callback=dict(argument_packet_read=False,local_register='0xa590010c',load='0x56e9c',
            compare='0xabcd1234',initialization_magic='0x1234abcd',magic_values_differ=True,
            mismatch='skip call, return0',match='call0x5a938, then return0 regardless of callee result if it returns',
            poll=False,selected_tail='0x5a994..0x5a99e clears0xa590010c; earlier body not modeled here'),
        distinctions=['file channel configuration is conditional, not observed RAM',
            'clear104 is not proven to release DMC mask consumption',
            'selected callback reads10c once; neither104 nor mask cells are its local gate',
            '0x1234abcd from init7 does not satisfy callback equality0xabcd1234',
            'return0 does not prove helper invoked or physical completion',
            'no order added between late mask stores and init9'],
        conditions=['preserved descriptor roots, channel type/request and plugin mapping',
            'event128/mask8 reaches direct dispatcher; status/hooks are explicit host fixtures',
            'DVFS method interface installed/preserved and selected callback returns',
            'physical aliases, event delivery, fresh MMIO values and memory visibility unverified'],
        not_proven=['all readers of104','producer of callback magic0xabcd1234',
            'full effects or transitive reads of0x5a938','release of all DMC calls','slot47/X0'],
        anchors={hex(a):v for a,v in anchors.items()},literals={hex(a):v for a,v in sorted(literals.items())},
        witnesses=[dict(pc=hex(p),bytes=raw.hex(),op=op,args=args) for p,(raw,op,args) in sorted(rows.items())],
        a64_witnesses=[dict(pc=hex(p),word=f'{w:08x}',op=op,args=args) for p,(w,op,args) in sorted(a64.items())],
        gnu=dict(thumb_instructions=len(rows),relative_targets=relative,literals=len(literals),
            a64_words=len(a64),selected_operands=len(SELECTED)),firmware_executed=False,slot47_resolved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');p.add_argument('--json',required=True);a=p.parse_args()
    try:r=inspect(a.sboot)
    except (OSError,ValueError,subprocess.CalledProcessError) as e:p.exit(2,str(e)+'\n')
    Path(a.json).write_text(json.dumps(r,indent=1)+'\n');print(json.dumps(r['gnu']))

if __name__=='__main__':main()
