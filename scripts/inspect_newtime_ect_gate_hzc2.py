#!/usr/bin/env python3
"""Independent static ECT gate audit; opaque SMC values and scoped effects."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_newtime_asv_gen_hzc2 import parser_reservation
from inspect_newtime_hzc2 import embedded

U32, U64 = (1 << 32)-1, (1 << 64)-1
RANGES = ((0x16050,0x162f0),(0x163c0,0x163fc),(0x16420,0x165cc),
          (0x1b3a4,0x1b43c),(0x1c50c,0x1c540),(0x1c87c,0x1cb80))
SELECTED = {
    0x16068:('cmp','w1, w2'),0x16084:('b.eq','0x16124'),0x160a0:('bl','0x1ca44'),
    0x160a4:('bl','0x161d8'),0x160a8:('bl','0x19a28'),0x160bc:('bl','0x17e14'),
    0x16114:('bl','0x16278'),0x16118:('bl','0x161b0'),0x16120:('b','0x1cb04'),
    0x163f8:('ret',''),0x16420:('smc','#0x0'),0x16430:('smc','#0x0'),
    0x16434:('mov','x0, x2'),0x16454:('stp','w1, w3, [x2]'),
    0x1645c:('str','wzr, [x2, #12]'),0x16464:('str','w3, [x2, #8]'),
    0x164b8:('mov','x0, #0xffffffffffffff1a'),0x164bc:('bl','0x16420'),
    0x16524:('mov','x0, #0xffffffffffffff19'),0x16550:('mov','x1, #0x0'),
    0x16554:('mov','x0, #0xffffffffffffff17'),0x1655c:('bl','0x16428'),
    0x16590:('mov','w1, w0'),0x16598:('mov','x2, #0x0'),
    0x1659c:('mov','x0, #0xffffffffffffff0c'),0x165ac:('mov','x2, #0x2'),
    0x165c0:('mov','x2, #0x1'),0x1b408:('add','x0, x3, w0, uxtw'),
    0x1c520:('ldr','w2, [x1]'),0x1c524:('orr','w0, w0, w2'),
    0x1c528:('str','w0, [x1]'),0x1c8ac:('mov','w0, #0x10'),
    0x1c8b0:('bl','0x1b3f8'),0x1c8b4:('str','x0, [x4, #16]'),
    0x1c8fc:('ldr','w0, [x0, #8]'),0x1c900:('add','x0, x0, #0x4'),
    0x1c904:('add','x0, x1, x0'),0x1c908:('str','x0, [x20, #3080]'),
    0x1c920:('bl','0x1b3a4'),0x1c9c4:('blr','x2'),
    0x1ca08:('mov','w2, #0x4'),0x1ca14:('bl','0x1b3a4'),
    0x1ca1c:('mov','w2, #0x3'),0x1ca20:('add','x1, x8, #0x4'),
    0x1ca24:('add','x0, x7, #0x4'),0x1ca28:('bl','0x1b3a4'),
    0x1ca50:('ubfiz','w1, w0, #2, #4'),0x1ca54:('lsr','w0, w0, w1'),
    0x1ca5c:('sub','w0, w0, #0x4'),0x1ca64:('b.hi','0x1ca88'),
    0x1ca78:('str','x1, [x0, #3080]'),0x1ca7c:('str','x1, [x2, #8]'),
    0x1ca84:('b','0x1c87c'),0x1ca94:('tbnz','w0, #0, 0x1cad8'),
    0x1cae0:('cbnz','x0, 0x1caec'),0x1cae4:('bl','0x165b8'),
    0x1cae8:('cbz','x0, 0x1ca68'),0x1cafc:('str','wzr, [x0]'),
    0x1cb58:('cbz','w0, 0x1cb60'),0x1cb5c:('b','0x1cb5c'),
    0x1cb60:('bl','0x1caf4'),0x1cb6c:('cbz','w0, 0x1cb74'),
    0x1cb70:('b','0x1cb70'),
}


def uint(value,bits):
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'expected host u{bits}')
    return value


def nibble(value):
    w=uint(value,64)&U32
    return (w >> (((w&15)*4)&31))&15


def signature(ect,sram):
    if not isinstance(ect,bytes) or not isinstance(sram,bytes) or min(len(ect),len(sram))<7:
        raise ValueError('host signature needs at least seven bytes from each source')
    return 0 if sram[:4]==b'PARA' and sram[4:7]==ect[4:7] else U32


def gate(ret233,mmio,ret0,ret1,ect=b'PARA007n',sram=b'PARA007',*,rmw_sample=None):
    """Code-level paths assuming normal SMC/memory returns, not hardware outcomes."""
    n=nibble(ret233);uint(mmio,32);uint(ret0,64);uint(ret1,64)
    if rmw_sample is not None:uint(rmw_sample,32)
    calls=[];write=None;read=False;parse=True
    if n not in (4,5):
        read=True;calls.append(dict(command=-244,X1=0,X2=0))
        if mmio&1:
            if ret0!=0:parse=False
            else:
                calls.append(dict(command=-244,X1=0,X2=1))
                parse=ret1==0
        else:
            matched=signature(ect,sram)==0
            if matched:write='reloaded_MMIO|1' if rmw_sample is None else rmw_sample|1
            calls.append(dict(command=-244,X1=0,X2=2 if matched else 1))
    return dict(selected_nibble=n,parser_edge=parse,return_without_parser=not parse,
        initial_SMC=dict(command=-233,result_register='X2',X1=0,X2=0,X3='inherited'),
        SMC244_calls=calls,gate_MMIO_read=read,direct_MMIO_store=write,
        direct_state_stores=['0x31c08','0x31c10'] if parse else [],
        opaque_SMC_memory_effects_excluded=False)


def finalize(ret233,ret230,ret231,table):
    uint(ret230,64);uint(ret231,64)
    if len(table)!=11:raise ValueError('host finalize table must have eleven bytes')
    n=nibble(ret233);mode=table[n-1] if 1<=n<=11 else 0
    writes={0:0xe8000000,4:0x280000,8:0x02024c00,12:0}
    if mode==0:writes.update({16:0x761,20:0x1400,24:0xe8000000})
    elif mode==0x14:writes.update({16:0x1400,20:0xe8000000})
    elif mode==0x20:writes.update({16:0xec,20:0x280,24:0xe8000000})
    return dict(nibble=n,mode=mode,SMC237_called=mode!=0x40,
        metadata_base='0xe7ffe000',metadata_u32_stores=writes,
        clears_entire_gate_MMIO_word=(ret230&U32)==0,
        terminal='spin_1cb5c' if ret230&U32 else 'spin_1cb70' if ret231&U32 else 'return')


def inspect(path):
    data=read_exact(path,*IMAGES['sboot']);root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
         str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for lo,hi in RANGES:
        lines.update(parse_lines(subprocess.check_output(cmd+['-D','-z','-b','binary','-m','aarch64',
            f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True)))
    if set(lines)!={p for lo,hi in RANGES for p in range(lo,hi,4)}:raise ValueError('GNU coverage differs')
    relative=0
    for pc,(w,op,args) in lines.items():
        if w!=struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):raise ValueError('GNU word differs')
        kind,target=flow(w,pc)
        if kind in ('b','bl','conditional'):
            if direct_target(op,args)!=target:raise ValueError('GNU relative target differs')
            relative+=1
    for pc,expected in SELECTED.items():
        if lines[pc][1:]!=expected:raise ValueError(f'GNU operand differs at {pc:#x}: {lines[pc][1:]}')
    table=list(data[0x2fdf8:0x2fe03]);ect=embedded(data)
    word=lambda p:struct.unpack_from('<I',data,p)[0]
    calls={hex(p):[] for p in (0x1ca44,0x1c87c,0x1caf4,0x1cb04,0x17e14,0x19a28)}
    for p in range(0x16000,0x2fd00,4):
        kind,target=flow(word(p),p)
        if kind in ('b','bl') and hex(target) in calls:calls[hex(target)].append(dict(pc=hex(p),kind=kind))
    cursor=parser_reservation(ect['source_file'],ect['header_total'])
    return dict(mode='independent_static_ECT_gate_audit_hzc2',source_base='45f316fa77a1431e90866cc92f5be76cfb52919c',
        sboot_sha256=IMAGES['sboot'][1],
        gate=dict(function='0x1ca44',nibble_formula='(u32(R) >> ((4*(u32(R)&15))&31))&15; R is SMC233 X2 result',
            bypass_MMIO_for_nibbles=[4,5],
            skip_condition='N not4/5 AND initial_MMIO_bit0 AND (SMC0_X0!=0 OR SMC1_X0!=0 after SMC0==0)',
            signature_clear_bit_branch='both signature outcomes take parser edge if all helpers return',
            signature_rule='SRAM[:4]==PARA and SRAM[4:7]==current_ECT[4:7]; 007 only under preserved ECT bytes',
            publication=['0x1ca78: M64[nominal(31c08)]=0x02153000','0x1ca7c: M64[nominal(31c10)]=0x02153000'],
            skip_direct_global_store_count=0,stack_save_restore_still_present=True,
            opaque_monitor_preserves_cells_or_MMIO_proved=False),
        main=dict(ordinary_call='0x160a0',bad_PMU_value='0xbad',bad_branch='0x16084 ->0x16124',
            gate_return_tested=False,next_instruction='0x160a4 BL0x161d8',
            later_copy='0x16114',later_finalize='0x16120',
            later_execution_guaranteed=False,note='program order only: intervening calls and polls may not return'),
        parser_reservation=dict(initial_file_equivalent=hex(ect['source_file']),header_total=ect['header_total'],
            after_header=hex(cursor['after_header']),after_total_plus4=hex(cursor['after_total_plus4']),end=hex(cursor['end']),
            order='allocate16/align8; read four header words; add total+4 to advanced cursor; align8; then validate PARA',
            raw_header_plus4_end=hex(ect['source_file']+ect['header_total']+4),
            read_guard_proved=False,callbacks_executed_just_from_gate_edge=False),
        finalize=dict(function='0x1cb04',nibble_resampled=True,table=table,
            map={str(i):table[i-1] if 1<=i<=11 else 0 for i in range(16)},
            helper230='0x1643c stores LK metadata at0xe7ffe000 before SMC230; mode64 leaves tail words unstored',
            result_tests='W32 at1cb58/1cb6c, whereas gate1cae0/1cae8 tests X64',
            clear='0x1cafc writes entire u32 zero, not merely clearing bit0',
            self_loops=['0x1cb5c before clear','0x1cb70 after clear']),
        direct_call_scan=dict(scope='aligned B/BL in BL2 [16000,2fd00), not indirect reachability proof',targets=calls),
        corrections=['no proof of RAM residue or preserved runtime state from file all-ones bytes',
            'skipping parser has no selected direct global stores, but monitor/transitive effects remain opaque',
            'signature tail compares current ECT bytes; main continuation/copies/finalize require normal later returns',
            'prior ASV audit misnamed header_total+4 as full reservation; header16 had already advanced cursor'],
        conditions=['selected nominal BL2 mapping, private frames/registers, memory reads/stores and helper returns',
            'SMC/MMIO/SRAM values supplied to host fixtures are not observations or proof of feasibility',
            'direct scans do not exclude alternate entries, indirect calls or other address constructions',
            'parser entry does not establish successful header validation, callback completion, bounds or physical state'],
        gnu=dict(version=subprocess.check_output(cmd+['--version'],text=True).splitlines()[0],
            words=len(lines),relative_targets=relative,selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(p),word=f'{w:08x}',op=op,args=args) for p,(w,op,args) in sorted(lines.items())],
        firmware_executed=False,qemu_scope_extended=False,physical_device_tested=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try: report=inspect(args.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'inspect_newtime_ect_gate_hzc2: {exc}\n')
    print(json.dumps(report,indent=2))
