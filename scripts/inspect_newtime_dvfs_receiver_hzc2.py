#!/usr/bin/env python3
"""Independent static audit of DVFS mode0, callback, initialization and returns."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal, thumb_target
from inspect_el2_hzc2 import IMAGES, read_exact

U32=(1<<32)-1
DOM=0x2f44c
RANGES=((0x56ee0,0x56fd8),(0x582a4,0x582cc),(0x587a4,0x587cc),
        (0x5944c,0x59788),(0x597b8,0x598c4),(0x598dc,0x5991c),
        (0x59a90,0x59bc8),(0x59be4,0x59c5c),(0x5acec,0x5ad28),(0x5bb6c,0x5bbe4))
SELECTED={
    0x56ef2:('str','r2, [r3, #0]'),0x56ef6:('ldr','r3, [r2, #0]'),
    0x56efa:('bne.n','0x56ef6'),0x56f16:('str','r4, [r1, #12]'),
    0x56f20:('ldr','r0, [r4, #24]'),0x56f2a:('str','r0, [r3, #32]'),
    0x56f42:('adds','r4, #52'),0x56f44:('adds','r1, #48'),
    0x56f46:('cmp','r2, #29'),0x56fc6:('cmp','r2, #37'),
    0x582b4:('cmp','r1, r3'),0x582b6:('beq.n','0x582c8'),
    0x582bc:('bge.n','0x582c8'),0x582c6:('beq.n','0x582c2'),
    0x587ba:('str','r3, [r0, #0]'),0x587c4:('cmp','r0, r1'),
    0x587c6:('bne.n','0x587b4'),
    0x5948e:('bl','0x5acec'),0x5949a:('bl','0x5acec'),
    0x594a8:('b.n','0x59896'),0x594ae:('b.n','0x5989c'),
    0x594ba:('bl','0x587a4'),0x5954a:('bl','0x581fc'),
    0x5954e:('cmp','r0, #0'),0x59550:('ble.n','0x59564'),
    0x59572:('bl','0x581fc'),0x5957a:('bl','0x58214'),
    0x59614:('cmp','r2, r3'),0x59616:('bhi.n','0x59692'),
    0x5961a:('bls.n','0x5961e'),0x5961c:('b.n','0x598a2'),
    0x59692:('movs','r6, #1'),0x59694:('negs','r6, r6'),
    0x59698:('ldr','r7, [r3, #0]'),0x5969a:('mvns','r7, r7'),
    0x5969c:('lsrs','r7, r7, #31'),0x596a0:('subs','r7, r3, r7'),
    0x596aa:('movs','r7, #1'),0x596b2:('movs','r7, #2'),
    0x5974c:('str','r4, [r3, #0]'),0x59778:('bne.n','0x59774'),
    0x597c8:('bne.n','0x597c4'),0x5980c:('bl','0x58214'),
    0x59810:('cmp','r0, #0'),0x59812:('ble.n','0x59826'),
    0x59828:('bl','0x581fc'),0x5982e:('ble.n','0x59842'),
    0x59870:('movs','r2, #240'),0x59872:('movs','r1, #241'),
    0x59886:('lsls','r4, r4, #8'),0x59890:('str','r4, [r2, #32]'),
    0x59892:('movs','r0, #0'),0x59898:('negs','r0, r0'),
    0x5989e:('negs','r0, r0'),0x598a8:('blt.n','0x598ac'),
    0x598aa:('b.n','0x596ae'),0x598b0:('movs','r7, #3'),
    0x598b2:('b.n','0x596b4'),
    0x598ee:('beq.n','0x59910'),0x59906:('bl','0x5944c'),
    0x5990a:('ldr','r3, [pc, #20]'),0x5990c:('ldr','r0, [r3, #0]'),
    0x59916:('bl','0x5944c'),0x5991a:('pop','{r4, r5, r6, pc}'),
    0x59bba:('blx','r5'),0x59bbe:('cmp','r1, #0'),
    0x59c00:('bhi.n','0x59c06'),0x59c02:('bl','0x59a90'),
    0x59c10:('ldr','r3, [r3, #40]'),0x59c18:('blx','r3'),
    0x59c1a:('movs','r4, r0'),0x59c48:('bls.n','0x59c52'),
    0x59c4e:('bl','0x59a90'),0x59c52:('movs','r0, r4'),
    0x5acf0:('ldrb','r4, [r3, #1]'),0x5acf6:('ldrh','r3, [r3, #20]'),
    0x5acf8:('cbz','r4, 0x5ad22'),0x5ad22:('subs','r2, r4, #1'),
    0x5bbc0:('ldr','r0, [r0, #0]'),0x5bbc2:('ldr','r1, [r1, #0]'),
    0x5bbc4:('blx','r3'),0x5bbd2:('str','r0, [r6, #0]'),
}


def uint(v):
    if type(v) is not int or not 0<=v<=U32:raise ValueError('expected host u32')
    return v


def pack(old,value):
    uint(old);uint(value)
    return ((value<<8)&U32)|(old&255)


def init_first29(base,current_words,old_packed):
    uint(base)
    if len(current_words)!=29 or len(old_packed)!=29:raise ValueError('host fixture requires first29')
    return [dict(sub=(base+52*i)&U32,packed=pack(old_packed[i],uint(v)))
            for i,v in enumerate(current_words)]


def callback(a,b,value,first_result=0,final_result=0,b_after_first=None):
    for v in (a,b,value,first_result,final_result):uint(v)
    if b_after_first is not None:uint(b_after_first)
    double=min(a,value)<b<max(a,value)
    calls=[(a,b),(b if b_after_first is None else b_after_first,value)] if double else [(a,value)]
    return dict(calls=calls,first_return_ignored=double,return_value=final_result,
                boundary_reloaded=double,requires_normal_first_return=double)


def minlock_position(cur,value):
    uint(cur);uint(value)
    return 'pre' if cur<=value else 'post'


def lookup(value,levels):
    uint(value)
    if len(levels)>255:raise ValueError('host level count exceeds u8')
    for v in levels:uint(v)
    for i,v in enumerate(levels):
        if (v&0xffffff)<=value:return i
    return len(levels)-1


def regime(from_value,value,threshold,status):
    for v in (from_value,value,threshold,status):uint(v)
    return dict(selector=1 if value<=threshold else 2+(status>>31),
                threshold_is_rejection=False,
                ordinary_presequence=from_value<=threshold and value<=threshold)


def rmw(old,value,status):
    for v in (old,value,status):uint(v)
    return dict(written=(old&0xcffffffc)|(value&0x30000003),
                poll_entered=value!=0x10000001 and bool(status&(1<<31)),
                poll_mask=1<<29,poll_exit_bit_set=True)


def broadcast_field(old,mask,value):
    for v in (old,mask,value):uint(v)
    return (old&~((mask<<24)&U32))|(((value&mask)<<24)&U32)


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for lo,hi in RANGES:
        out=subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',
            f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True)
        part=parse_thumb(out)
        if lines.keys()&part.keys():raise ValueError('overlapping code windows')
        lines.update(part)
    covered=set();relative=0;literals={}
    for pc,(raw,op,args) in sorted(lines.items()):
        if raw!=data[pc:pc+len(raw)] or op in ('.short','.word','.inst','udf'):raise ValueError(f'GNU word differs {pc:#x}')
        covered.update(range(pc,pc+len(raw),2));target=thumb_target(data,pc)
        if target is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=target:raise ValueError('GNU branch differs')
            relative+=1
        elif op in ('bl','b.n','b.w','beq.n','bne.n','bhi.n','bls.n','blt.n','bge.n','bgt.n','ble.n','bcc.n','bcs.n','cbz','cbnz'):
            raise ValueError('unhandled relative branch')
        if op=='ldr' and '[pc,' in args:
            register=int(args.split(',')[0][1:]);at,value=thumb_literal(data,pc,register)
            if f'(0x{at:x})' not in args:raise ValueError('GNU literal differs')
            literals[at]=value
    if covered!={p for lo,hi in RANGES for p in range(lo,hi,2)}:raise ValueError('GNU coverage differs')
    for pc,expected in SELECTED.items():
        _,op,args=lines[pc]
        if (op,args.split('@')[0].strip())!=expected:raise ValueError(f'GNU selected operand differs {pc:#x}')
    word=lambda file:struct.unpack_from('<I',data,file)[0]
    anchors={0x5bbe8:0x2f400,0x5cc00:0x2c3e5,0x5c034:0x2e36d,
        0x59c5c:DOM,0x5cc74:0x2c0dd,0x5991c:DOM,0x59920:0x2f248,
        0x59798:0x2f230,0x597b0:0xa5900100,0x598cc:DOM,
        0x56fdc:0x38e00,0x56fe0:0x2fbf4,0x56fe8:DOM,0x59be0:0x2eccc,
        0x587cc:0xac000800,0x587d0:0xac400800,
        0x582cc:0xcffffffc,0x582d0:0x30000003,0x582d4:0x10000001}
    if any(word(at)!=value for at,value in anchors.items()):raise ValueError('selected data anchor differs')
    return dict(mode='static_DVFS_receiver_audit_hzc2',source_base='ed48cbaf99a4405bbcdc9750017fe62b0fbd2e3b',
        sboot_sha256=IMAGES['sboot'][1],scope='file PCs; nominal Thumb core+0x2d800 mapping',
        entry=dict(method='0x5bb6c',mode=0,domain=0,handler='0x59be4',initial_callback='0x598dc',
            target_value='effective FVP E, desreferenced at5bbc2; not the raw packet request in general',
            no_mode0_argument_writeback_in_selected_method=True),
        init=dict(handshake='write core38e00 to MMIOa5900108; poll until register zero BEFORE reading live data',
            first_loop=dict(rows=29,sub='u32(core38e00+52*i)',packed='u32(current_i<<8)|(old_i&255)',current_i='M32[sub_i+24]'),
            second_loop='indices29..36 derive extra records; not modeled as more identical first-loop records',
            file_current0=word(0x66618),file_current0_is_runtime_observation=False,
            post_handshake_data_producer_or_preservation_proved=False),
        handler=dict(snapshot='cur=M32[entry+32]>>8 before dispatch',
            minlock='pre call if captured cur<=E, post call if captured cur>E; normal-return/preservation conditions',
            result='saved R4 from dispatch, restored after optional post-minlock; no aggregation of minlock return'),
        callback=dict(intermediate_condition='min(A,E)<B<max(A,E), all u32',
            first_call='0x59906 ->5944c(A,B,entry)',first_return_tested=False,
            after_first='0x5990c reloads B from core2f248; not a reload of packed current',
            final_call='0x59916 ->5944c(B_after,E,entry), or (A,E,entry) for one step',
            result='only final call result; failure of first call does not abort second if it returns normally'),
        transition=dict(lookup='5acec: count u8 atsub+1, offset u16 atsub+20, compares low24(level) to full u32 value',
            count_zero_return=-1,lookup_fail_edges=['594a8->59896','594ae->5989c'],
            threshold_core='0x2f230',initial_threshold=word(0x5ca30),threshold_rejects=False,
            selectors='1 if E<=threshold; else2 if status31 clear,3 if set; current>threshold changes presequence',
            effect_before_threshold_tests='594b0 RPC;594ba broadcast clear; other RPC/notification calls before59614',
            selected_MMIO_store='5974c: M32[0xa5900100]=E, if reached',
            broadcast='587a4: core MMIO [ac000800,ac400800) step100000, four registers; upper bound exclusive',
            final_broadcast='59870..59876 passes (24,0xf1,0xf0): clears bit24 as well as setting bits28..31',
            final_packed_store='59890: M32[core2f44c+32]=u32(E<<8)|(old&255)',
            final_packed_is_passed_entry_relative=False,
            return0='59892: constant0 on local terminal path, not aggregate acceptance of callbacks/RPCs/polls',
            positive_RPC_returns='selected signed>0 branches notify and continue; negative/zero are not uniformly propagated'),
        notification=dict(minlock_table_cell='M32[core2eccc+16], not M32[M32[core2eccc]+16]',
            initial_pointer=hex(word(0x5c4dc)),target_file=hex((word(0x5c4dc)&~1)+0x2d800),
            runtime_table_preservation_proved=False),
        RMW=dict(write_mask='0x30000003',preserve_mask='0xcffffffc',
            skip_poll_exact_value='0x10000001; other values with same masked write may still poll',
            status_sample='addr+8 bit31 gates entry; bit29 on repeated reads gates exit; no selected timeout'),
        external_corrections=['from>threshold and target>threshold are routing conditions, not error exits',
            'first29 sub pointers advance52; live current comes after MMIO handshake, not file-zero inference',
            'first transition return is ignored; B is reloaded independently before final call',
            'external fvp_projection test keeps low16, contradicting the actual published-word projection',
            'broadcast end is exclusive (four registers); final mask argument is f1, not f0',
            '2341 external instruction records include overlapping windows and literal-pool disassembly',
            'curated MMIO table is not individually validated in full by40 regex claims and80 literal checks'],
        conditions=['normal calls and memory accesses; preserved transported registers, frames, roots and selected code/data',
            'intermediate call may mutate B, current, MMIO or other RAM; do not infer preservation from its return',
            'if a poll or first call does not return, no subsequent call/state store is guaranteed',
            'runtime callback/mode tables, framework cells, plugin interfaces and aliases remain conditional',
            'FVP E arithmetic already audited separately; physical units, device effects and slot47 origin remain open'],
        anchors={hex(k):hex(v) for k,v in anchors.items()},literals={hex(k):v for k,v in sorted(literals.items())},
        gnu=dict(version=subprocess.check_output(cmd+['--version'],text=True).splitlines()[0],instructions=len(lines),
            halfwords=len(covered),relative_targets=relative,literal_xrefs=sum(1 for _,op,args in lines.values() if op=='ldr' and '[pc,' in args),selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(pc),bytes=raw.hex(),op=op,args=args) for pc,(raw,op,args) in sorted(lines.items())],
        firmware_executed=False,physical_device_tested=False,qemu_scope_extended=False,slot47_resolved=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('sboot');args=p.parse_args()
    try:r=inspect(args.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:p.exit(2,f'inspect_newtime_dvfs_receiver_hzc2: {exc}\n')
    print(json.dumps(r,indent=2))
