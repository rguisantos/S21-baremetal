#!/usr/bin/env python3
"""Static audit of DMC plugin 9 method+12 and subcommands 8/9 (HZC2 sboot).

Chain audited: DVFS core 0x5944c -> wrappers 0x581fc/0x58214 -> relay 0x58170
(cell core 0x2fbf0) -> framework relay 0x38b04 -> DMC method+12 0x5f758 ->
handlers 0x5fadc (subcmd 8) / 0x5fbbc (subcmd 9) -> callees/polls -> returns.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys

from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_literal, thumb_target
from inspect_el2_hzc2 import IMAGES, read_exact

U32=(1<<32)-1
NEG1=U32
DELTA1=0x34000   # first copy:  file = core + 0x34000
DELTA2=0x2d800   # second copy: file = core + 0x2d800
DMC_PLUGIN=9
DVFS_PLUGIN=7
HANDLER_TABLE_CORE=0x37cd0
METHODS_CORE=0x37c40
DMC_OBJ_CORE=0x37c84

RANGES=((0x3840c,0x3842c),(0x38ad4,0x38b04),(0x38b04,0x38bd4),(0x38e2a,0x38ec0),
        (0x3998c,0x39a3e),(0x39b48,0x39b90),(0x3a3c8,0x3a3d4),(0x3a40c,0x3a43c),
        (0x56e00,0x56e10),(0x58170,0x5822c),(0x5944c,0x5959a),(0x597f0,0x59846),
        (0x5f600,0x5f64c),(0x5f758,0x5f7a0),(0x5f9cc,0x5f9f4),(0x5fadc,0x5fcc0),
        (0x615ec,0x61648),(0x616cc,0x6176c),(0x6176c,0x61844),(0x6366c,0x63694),
        (0x643d0,0x64400),(0x64400,0x64440),(0x6449c,0x644b0),(0x64500,0x64698),
        (0x646d0,0x6470c),(0x649b0,0x649c8),(0x65170,0x651b0),(0x651b0,0x651d0))

SELECTED={
    0x58174:('movs','r5, r0'),0x5817e:('ldr','r0, [r3, #0]'),
    0x58180:('ldr','r3, [r0, #8]'),0x58184:('str','r2, [sp, #0]'),
    0x58186:('ldr','r4, [r3, #28]'),0x5818e:('blx','r4'),
    0x58202:('movs','r3, #8'),0x58206:('add','r1, sp, #4'),
    0x58208:('movs','r0, #9'),0x5820a:('bl','0x58170'),
    0x5821a:('movs','r2, r1'),0x5821c:('movs','r3, #9'),0x58222:('bl','0x58170'),
    0x38b22:('cmp','r3, r1'),0x38b24:('bls.n','0x38b36'),
    0x38b32:('ldrb','r2, [r3, r2]'),0x38b34:('cbnz','r2, 0x38b58'),
    0x38b58:('ldr','r2, [r3, #12]'),0x38b5a:('ldr','r2, [r2, #12]'),
    0x38b5e:('beq.n','0x38b36'),0x38b62:('ldr','r0, [r0, #0]'),
    0x38b64:('ldr','r3, [r3, #20]'),0x38b66:('lsls','r2, r0'),
    0x38b68:('tst','r3, r2'),0x38b6a:('bne.n','0x38b74'),
    0x38b8e:('ldr','r3, [r3, #40]'),0x38ba0:('mov','r0, r8'),
    0x38ba2:('blx','r3'),
    0x38e46:('str','r2, [r1, #0]'),0x38e7c:('ldrb','r2, [r3, r2]'),
    0x38e7e:('cbz','r2, 0x38eb6'),0x38e90:('blx','r8'),
    0x38eb0:('ldr','r3, [r3, #36]'),
    0x39a30:('str','r2, [r3, #4]'),0x39a34:('str','r2, [r3, #36]'),
    0x39a3c:('str','r2, [r0, r3]'),
    0x39b52:('str','r3, [r0, #0]'),0x39b5e:('str','r3, [r0, #8]'),
    0x39b66:('str','r2, [r0, #20]'),
    0x3a3d0:('ldr','r0, [r3, #0]'),
    0x3a430:('ldr','r3, [r2, #0]'),0x3a436:('bhi.n','0x3a430'),
    0x56e04:('str','r3, [r0, #12]'),0x56e08:('str','r0, [r3, #0]'),
    0x5948e:('bl','0x5acec'),0x5949a:('bl','0x5acec'),
    0x5953a:('lsls','r3, r3, #8'),0x59544:('orrs','r0, r3'),
    0x5954a:('bl','0x581fc'),0x5954e:('cmp','r0, #0'),
    0x59550:('ble.n','0x59564'),0x59560:('movs','r0, #5'),
    0x5956a:('orrs','r7, r3'),0x59572:('bl','0x581fc'),
    0x59576:('ldr','r1, [sp, #28]'),0x59578:('movs','r0, r7'),
    0x5957a:('bl','0x58214'),0x5957e:('cmp','r0, #0'),
    0x59580:('ble.n','0x59594'),0x59590:('movs','r0, #4'),
    0x5980c:('bl','0x58214'),0x59810:('cmp','r0, #0'),
    0x59812:('ble.n','0x59826'),0x59828:('bl','0x581fc'),
    0x5982c:('cmp','r0, #0'),0x5982e:('ble.n','0x59842'),
    0x5f610:('str','r2, [r3, #12]'),0x5f616:('str','r2, [r3, #0]'),
    0x5f766:('ldr','r3, [r3, #0]'),0x5f774:('lsls','r2, r2, #2'),
    0x5f776:('ldr','r3, [r2, r3]'),0x5f778:('cbz','r3, 0x5f792'),
    0x5f784:('ldr','r0, [r3, #0]'),0x5f788:('ldr','r3, [r3, #0]'),
    0x5f78c:('blx','r2'),
    0x5f9de:('ldr','r3, [r3, #44]'),0x5f9e4:('blx','r3'),
    0x5faea:('lsrs','r3, r3, #16'),0x5faee:('ands','r3, r2'),
    0x5fb0c:('bl','0x64620'),0x5fb18:('bl','0x64620'),
    0x5fb2c:('ldr','r2, [r3, #56]'),0x5fb30:('str','r2, [r3, #68]'),
    0x5fb40:('cbnz','r3, 0x5fb64'),0x5fb46:('bge.n','0x5fbaa'),
    0x5fb4c:('ble.n','0x5fbaa'),0x5fb52:('bl','0x64618'),
    0x5fb5a:('bl','0x64658'),0x5fb6e:('ble.n','0x5fbaa'),
    0x5fb74:('bge.n','0x5fbaa'),0x5fb7a:('bl','0x645bc'),
    0x5fb82:('bl','0x64510'),0x5fb92:('ble.n','0x5fbaa'),
    0x5fb98:('bge.n','0x5fbaa'),0x5fb9a:('bl','0x64530'),
    0x5fba2:('bl','0x64658'),
    0x5fbca:('lsrs','r3, r3, #16'),0x5fbe8:('ldr','r3, [r7, #0]'),
    0x5fbea:('str','r3, [r7, #20]'),0x5fbf0:('bl','0x6463c'),
    0x5fbfc:('bl','0x6463c'),0x5fc0c:('cbnz','r3, 0x5fc60'),
    0x5fc12:('blt.n','0x5fc3e'),0x5fc18:('blt.n','0x5fc3e'),
    0x5fc1e:('bl','0x6467c'),0x5fc28:('bl','0x6467c'),
    0x5fc30:('ble.n','0x5fc3e'),0x5fc36:('bl','0x6467c'),
    0x5fc3e:('bl','0x651b0'),0x5fc46:('bne.n','0x5fc58'),
    0x5fc48:('bl','0x651c0'),0x5fc50:('movs','r0, #0'),
    0x5fc52:('bl','0x64554'),0x5fc58:('movs','r0, #1'),
    0x5fc5a:('bl','0x64554'),0x5fc64:('bne.n','0x5fcb6'),
    0x5fc76:('bl','0x6467c'),0x5fc80:('bl','0x6467c'),
    0x5fc88:('ble.n','0x5fc96'),0x5fc8e:('bl','0x6467c'),
    0x5fcaa:('bl','0x64554'),
    0x61602:('ldr','r4, [r4, #0]'),0x61628:('str','r4, [r2, #0]'),
    0x6162a:('str','r1, [r2, #56]'),0x6162c:('str','r3, [r2, #8]'),
    0x61630:('str','r3, [r2, #4]'),
    0x616f2:('ldr','r6, [r3, r2]'),0x6171a:('str','r4, [r3, #0]'),
    0x6178c:('ldr','r2, [r3, r2]'),0x6178e:('ldr','r6, [r3, r1]'),
    0x61796:('bne.n','0x61830'),0x617ce:('blx','r3'),
    0x63678:('ldr','r3, [r3, #24]'),0x6368e:('str','r3, [r2, #24]'),
    0x643de:('blx','r4'),0x643f6:('blx','r4'),
    0x64406:('blx','r3'),0x64408:('cmp','r0, #1'),
    0x6440a:('bne.n','0x64422'),0x64410:('str','r2, [r3, #0]'),
    0x644a6:('ldr','r3, [r3, #52]'),0x644a8:('blx','r3'),
    0x64578:('str','r4, [r3, #0]'),0x6457a:('str','r5, [r3, #4]'),
    0x64594:('str','r0, [r2, r3]'),0x645d4:('str','r4, [r3, #0]'),
    0x64622:('ldr','r2, [r3, #0]'),0x64624:('cbz','r2, 0x64630'),
    0x64628:('lsls','r3, r0'),0x6462c:('cmp','r3, #0'),
    0x6462e:('bgt.n','0x64634'),0x64630:('movs','r0, #1'),
    0x64632:('negs','r0, r0'),0x6466a:('adds','r0, #18'),
    0x6466c:('lsls','r0, r0, #3'),0x64670:('ldr','r0, [r0, #4]'),
    0x6468e:('adds','r0, #31'),0x64694:('ldr','r0, [r0, #4]'),
    0x646d8:('str','r1, [r3, r2]'),0x649b6:('str','r2, [r3, #0]'),
    0x65182:('ldr','r0, [r4, #0]'),0x65186:('tst','r0, r2'),
    0x65188:('bne.n','0x65182'),0x65196:('ldr','r3, [r1, #0]'),
    0x65198:('lsrs','r3, r3, #9'),0x6519a:('ands','r3, r2'),
    0x6519c:('cmp','r3, #15'),0x6519e:('bne.n','0x65196'),
    0x651b2:('ldr','r0, [r3, #0]'),0x651b6:('lsrs','r0, r0, #28'),
    0x651c4:('lsls','r0, r0, #12'),0x651c6:('lsrs','r0, r0, #28'),
}

ANCHORS={
    0x58194:0x2fbf0,0x56e74:0x2e828,0x56e78:0x2fbf0,
    0x59788:0x2fbf4,0x59790:0x2eccc,0x598c8:0x2eccc,0x598cc:0x2f44c,
    0x5f63c:0x37c40,0x5f640:0x384d4,0x5f644:0x37a28,0x5f648:0x37a30,
    0x5f79c:0x37cd0,0x5f9f0:0x384d4,0x5fbb4:0x384d4,0x5fbb8:0x37c84,
    0x645ac:0x3a600,0x645b0:0x381c8,0x645b4:0x37fb4,0x645b8:0x38038,
    0x64528:0x381c8,0x6452c:0x37d40,0x6454c:0x381c8,0x64550:0x37d40,
    0x64564:0x37e20,0x64608:0x3a600,0x6460c:0x381c8,
    0x64610:0x37fb4,0x64614:0x38038,
    0x64638:0x3a660,0x64654:0x3a668,0x64674:0x381c8,0x64678:0x3a664,
    0x64698:0x381c8,0x6469c:0x3a664,
    0x646f4:0x381c8,0x646f8:0x3ca00,0x646fc:0x3d9b0,0x64700:0x3e960,
    0x64704:0x3f910,0x64708:0x408c0,
    0x6495c:0x3a600,0x64958:0x3a610,0x64960:0x3c9ff,
    0x649c0:0x3a64c,0x649c4:0xc0c0baba,
    0x651a4:0xa5863a20,0x651a8:0xffffe1ff,0x651ac:0xa5863a30,
    0x651bc:0xa0000010,0x651cc:0xa0000010,
    0x6163c:0x37df8,0x61640:0xcfffffff,0x61644:0xf80fffff,
    0x61754:0x37df8,0x61758:0x37e20,
    0x61840:0x37df8,0x61844:0xefffffff,0x61848:0x381c8,
    0x6184c:0x38038,0x61850:0x37e20,
    0x63694:0x37e0c,0x63698:0xffffbfff,
    0x64424:0x38038,0x64428:0x37df8,
    0x6442c:0xac03f000,0x64430:0xac13f000,0x64434:0xac23f000,
    0x64438:0xac33f000,0x6443c:0xaa34f000,
    0x644ac:0x381c8,
    0x39a40:0xf800,0x39a44:0x2000,0x39a48:0x29600,0x39a4c:0x6800,
    0x39a50:0x11800,0x39a54:0x1000,0x39a58:0x26800,0x39a5c:0x1000,
    0x39a60:0x14800,0x39a64:0x6000,0x39a68:0x1a800,0x39a6c:0x1000,
    0x39a70:0x1b800,0x39a74:0xb000,0x39a78:0x12800,0x39a7c:0x2000,
    0x39a80:0x2fe00,0x39a84:0x2000,0x39a88:0x27800,0x39a8c:0x1e00,
    0x39a90:0x31e00,0x39a94:0x7000,
}


def uint(v):
    if type(v) is not int or not 0<=v<=U32: raise ValueError('expected host u32')
    return v


def signed(v):
    uint(v)
    return v-(1<<32) if v&(1<<31) else v


def core_to_file(core):
    """Programmatic core->file conversion over the two mapped ACPM copies."""
    uint(core)
    if 0x4000<=core<0x9000: return core+DELTA1
    if 0xf800<=core<0x39800: return core+DELTA2
    raise ValueError(f'core address {core:#x} outside the mapped image copies')


def file_to_core(off):
    uint(off)
    if 0x38000<=off<0x3d000: return off-DELTA1
    if 0x3d000<=off<0x67000: return off-DELTA2
    raise ValueError(f'file offset {off:#x} outside the mapped image copies')


def thumb_file(core):
    """Thumb core pointer (bit0 set) -> file PC of the instruction."""
    return core_to_file(core & ~1)


def fmask(byte, mask):
    """f_64620/f2_6463c: byte when the mask bit is set, else -1 (0xffffffff).

    cbz mask -> -1; lsls by register uses the low 8 bits, >=32 zeroes the
    shift; the bgt exit is a signed compare, so bit31 of the and-product
    (byte==31 with mask bit31 set) also returns -1. r0 keeps the raw byte.
    """
    uint(byte); uint(mask)
    if mask==0: return NEG1
    shift=byte & 255
    shifted=(1<<shift) if shift<32 else 0
    product=mask & shifted
    if product==0 or product&(1<<31): return NEG1
    return byte


def fields(v):
    uint(v)
    return dict(sel=(v>>16)&3, byte1=(v>>8)&0xff, byte0=v&0xff)


def handler8(v, mask, h_value=None):
    """Subcommand 8 handler 0x5fadc: path selection and return value."""
    f=fields(v)
    va=fmask(f['byte0'],mask)
    vb=fmask(f['byte1'],mask)
    result=NEG1
    path=f'sel{f["sel"]}'
    if f['sel']==0:
        if signed(vb)<0 and signed(va)>0:
            path+='+g64618+h64658'
            result=uint(h_value) if h_value is not None else None
    elif f['sel']==1:
        if signed(vb)>0 and signed(va)<0:
            path+='+p645bc+q64510'
    elif f['sel']==2:
        if signed(vb)>0 and signed(va)<0:
            path+='+r64530+h64658'
            result=uint(h_value) if h_value is not None else None
    return dict(path=path, va=va, vb=vb, result=result,
                arg2_ignored=True, publishes_critical_pair=True)


def handler9(v, mask, g2_byte0, g2_byte1, t_field, u_field):
    """Subcommand 9 handler 0x5fbbc: comparisons, w() tail, return value."""
    f=fields(v)
    va=fmask(f['byte0'],mask)
    vb=fmask(f['byte1'],mask)
    result=NEG1
    w_arg=None
    if f['sel'] in (0,1):
        if signed(vb)>=0 and signed(va)>=0:
            if f['sel']==0 and signed(g2_byte1)>signed(g2_byte0):
                result=g2_byte0
            elif f['sel']==1 and signed(g2_byte0)>signed(g2_byte1):
                result=g2_byte0
        w_arg=0 if (t_field==1 and u_field==0) else 1
    return dict(path=f'sel{f["sel"]}', va=va, vb=vb, result=result,
                w_arg=w_arg, arg2_stored_but_never_read=True)


def dispatch(cmd, handlers):
    """0x5f758: handler = M32[0x37cd0 + W32(cmd*4)]; null -> -1, no bounds check."""
    uint(cmd)
    idx=(cmd*4)&U32
    address=(HANDLER_TABLE_CORE+idx)&U32
    slot=idx//4
    in_table = slot in handlers
    if in_table and handlers[slot]!=0:
        return dict(cmd=cmd, index=idx, address=f'core {address:#x}',
                    handler=handlers[slot], handler_file=thumb_file(handlers[slot]),
                    out_of_table=cmd not in handlers, memory_known=True,
                    return_value='handler(*slot_a1,*slot_a2)')
    return dict(cmd=cmd, index=idx, address=f'core {address:#x}',
                handler=None, out_of_table=cmd not in handlers, memory_known=in_table,
                return_value=NEG1 if in_table else None)


def relay_gates(count, enabled, method_ptr, allow_mask, caller_id, target=DMC_PLUGIN):
    for v in (count,enabled,method_ptr,allow_mask,caller_id,target): uint(v)
    shift=caller_id & 255
    bit=(1<<shift) if shift<32 else 0
    allowed_bit=bool(allow_mask & bit)
    return dict(count_ok=count>target, enabled_ok=enabled!=0,
                method_ok=method_ptr!=0, caller_allowed=allowed_bit,
                allowed=count>target and enabled!=0 and method_ptr!=0 and allowed_bit,
                fail_return_10=count<=target or enabled==0 or method_ptr==0,
                fail_return_neg11=(count>target and enabled!=0 and method_ptr!=0) and not allowed_bit)


def dvfs_pair(ret8, ret9):
    """0x59572/0x5957a: the subcmd 8 return is overwritten before the subcmd 9 call."""
    uint(ret8); uint(ret9)
    return dict(subcmd8_return=ret8, subcmd8_used='ignored; r0 overwritten at 0x59578',
                subcmd9_return=ret9,
                notify9=dict(cmd=4, issued=signed(ret9)>0, value=ret9),
                subcmd9_gated_by_subcmd8=False)


def dvfs_first8(ret):
    uint(ret)
    return dict(notify=dict(cmd=5, issued=signed(ret)>0, value=ret),
                continues_to_pair=True, rollback=False)


def dvfs_terminal(ret9, ret8):
    uint(ret9); uint(ret8)
    return dict(order='9 at 0x5980c then 8 at 0x59828', sel=0,
                notify9=dict(cmd=4, issued=signed(ret9)>0),
                notify8=dict(cmd=5, issued=signed(ret8)>0),
                subcmd8_gated_by_subcmd9=False, rollback=False)


POLLS=(
    dict(site='0x65182', address='0xa5863a30', mask=0x1e00,
         exit_condition='(M32[0xa5863a30] & 0x1e00) == 0', timeout='none in the analyzed path',
         reached_from='handler8 sel1 -> q64510 -> 0x6176c -> 0x65170'),
    dict(site='0x65196', address='0xa5863a30', mask=0x1e00,
         exit_condition='((M32[0xa5863a30] >> 9) & 0xf) == 15', timeout='none in the analyzed path',
         reached_from='handler8 sel1 -> q64510 -> 0x6176c -> 0x65170 (after M32[0xa5863a20] |= 0x1e00)'),
    dict(site='0x3a430', address='0xe000e018 (SysTick CVR)', mask=None,
         exit_condition='u32(fresh + u32(51*arg)) <=u original snapshot; modulo arithmetic, not a general elapsed-time guarantee',
         timeout='no explicit counter; termination requires SysTick to keep running',
         reached_from='handler8 sel1/sel0 tail: 0x6449c -> 0x5f9cc -> API+0x2c (0x38ad4) -> 0x3a40c'),
)


def inspect(path):
    data=read_exact(path,*IMAGES['sboot'])
    root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
         str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    version=subprocess.check_output(cmd+['--version'],text=True).splitlines()[0]
    lines={}
    for lo,hi in RANGES:
        out=subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',
            f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True)
        part=parse_thumb(out)
        if lines.keys()&part.keys(): raise ValueError('overlapping code windows')
        lines.update(part)
    covered=set(); relative=0; literals={}
    for pc,(raw,op,args) in sorted(lines.items()):
        if raw!=data[pc:pc+len(raw)] or op in ('.short','.word','.inst','udf'):
            raise ValueError(f'GNU word differs {pc:#x}')
        covered.update(range(pc,pc+len(raw),2))
        target=thumb_target(data,pc)
        if target is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=target:
                raise ValueError('GNU branch differs')
            relative+=1
        elif op in ('bl','b.n','b.w','beq.n','bne.n','bhi.n','bls.n','blt.n','bge.n',
                    'bgt.n','ble.n','bcc.n','bcs.n','cbz','cbnz'):
            raise ValueError(f'unhandled relative branch at {pc:#x}')
        if op=='ldr' and '[pc,' in args:
            register=int(args.split(',')[0][1:])
            at,value=thumb_literal(data,pc,register)
            if f'(0x{at:x})' not in args: raise ValueError('GNU literal differs')
            literals[at]=value
    if covered!={p for lo,hi in RANGES for p in range(lo,hi,2)}:
        raise ValueError('GNU coverage differs')
    for pc,expected in SELECTED.items():
        _,op,args=lines[pc]
        if (op,args.split('@')[0].strip())!=expected:
            raise ValueError(f'GNU selected operand differs {pc:#x}: {(op,args)}')
    word=lambda off: struct.unpack_from('<I',data,off)[0]
    if any(word(at)!=value for at,value in ANCHORS.items()):
        raise ValueError('selected literal anchor differs')

    # structural anchors: descriptors, API table, methods/handler tables, MMIO arrays
    desc=lambda i:0x3b150+48*i
    if [word(desc(9)+o) for o in (0,20,44)]!=[9,0x8b4,0x6fd4]:
        raise ValueError('plugin 9 descriptor differs')
    if data[core_to_file(0x6fd4):core_to_file(0x6fd4)+20].split(b'\0')[0]!=b'plugin_DMC_0_0_0.fw':
        raise ValueError('plugin 9 name differs')
    if [word(desc(7)+o) for o in (0,20)]!=[7,0xb34]:
        raise ValueError('plugin 7 descriptor differs')
    api={off:word(0x3b10c+off) for off in (0x08,0x0c,0x10,0x1c,0x2c,0x38,0x3c)}
    if [thumb_file(api[o]) for o in (0x1c,0x2c,0x38,0x3c)]!=[0x38b04,0x38ad4,0x3840c,0x3841c]:
        raise ValueError('framework API pointers differ')
    methods={off:word(core_to_file(METHODS_CORE)+off) for off in (0,4,8,12)}
    if thumb_file(methods[12])!=0x5f758: raise ValueError('DMC method+12 pointer differs')
    handlers={i:word(core_to_file(HANDLER_TABLE_CORE)+4*i) for i in range(20)}
    if thumb_file(handlers[8])!=0x5fadc or thumb_file(handlers[9])!=0x5fbbc:
        raise ValueError('DMC handler table entries 8/9 differ')
    if handlers[3]!=0 or any(handlers[i]!=handlers[10] for i in range(11,17)):
        raise ValueError('DMC handler table shape differs')
    mmio_first=[word(core_to_file(0x37df8)+4*i) for i in range(5)]
    mmio_t=[word(0x6442c+4*i) for i in range(5)]
    mmio_second=[word(core_to_file(0x37e0c)+4*i) for i in range(5)]
    if mmio_first!=[0xac036000,0xac136000,0xac236000,0xac336000,0xaa346000]:
        raise ValueError('default MMIO pointer array differs')
    if mmio_t!=[0xac03f000,0xac13f000,0xac23f000,0xac33f000,0xaa34f000]:
        raise ValueError('t()-gated MMIO pointer array differs')
    if mmio_second!=[0xac040000,0xac140000,0xac240000,0xac340000,0xaa350000]:
        raise ValueError('second MMIO pointer array differs')
    service={ 'core0x7d48':word(0x3bd48),'core0x7d8c':word(0x3bd8c),
              'core0x7994':word(0x3b994),'core0x7998':word(0x3b998)}
    if [thumb_file(service[k]) for k in service]!=[0x3a3c8,0x3a40c,0x39b10,0x39b04]:
        raise ValueError('framework service pointers differ')
    dmc_cells={'core0x38000':word(0x65800),'core0x38004':word(0x65804),
               'core0x380c0':word(0x658c0),'core0x37d94':word(0x65594),
               'core0x37d98':word(0x65598),'core0x37ebc':word(0x656bc),
               'core0x37eb8':word(0x656b8),'core0x37cb8':word(0x654b8)}
    if [thumb_file(v) for v in dmc_cells.values()]!=[0x643d0,0x643e8,0x6449c,0x6176c,
            0x616cc,0x6366c,0x63acc,0x5f9cc]:
        raise ValueError('DMC indirect service pointers differ')
    init_lit={1:(0x39a40,0x39a44),2:(0x39a50,0x39a54),3:(0x39a58,0x39a5c),
              5:(0x39a78,0x39a7c),6:(0x39a80,0x39a84),7:(0x39a48,0x39a4c),
              8:(0x39a88,0x39a8c),9:(0x39a90,0x39a94),10:(0x39a70,0x39a74),
              11:(0x39a60,0x39a64),12:(0x39a68,0x39a6c)}
    if (word(0x39a90)|1)!=0x31e01 or thumb_file(word(0x39a90))!=0x5f600:
        raise ValueError('plugin 9 initializer pointer differs')
    if thumb_file(word(0x39a48))!=0x56e00 or thumb_file(word(0x39a50))!=0x3f000:
        raise ValueError('plugin 7/2 initializer pointers differ')

    witnesses=[dict(pc=f'{pc:#x}',bytes=raw.hex(),op=op,args=args)
               for pc,(raw,op,args) in sorted(lines.items())]
    init_and_size={str(i):dict(initializer=f'core {word(a)|1:#x}',
                     init_file=f'{thumb_file(word(a)):#x}',size=word(s))
        for i,(a,s) in init_lit.items()}
    return dict(mode='static_DMC_method12_subcommands_hzc2',
        audit_revision=2,
        provenance=dict(external_extractor_sha256='68b022eb1b1ade3004a4a9c3086d59012c4aea92fb0d9109c736729f3a473b09',
            external_tests_sha256='45d49303e37d3e4de080d4eb3a519b74b875115bfdb521551a7377635cd9928a',
            external_json_sha256='e289db60c323419ab7f95770da1a9848be76d85f99b43fc95c3a82a5786f1b9a',
            baseline='65 external tests reproduced; original JSON byte-identical with GNU 2.44',
            corrections=['relay error precedence and low8 shift','dispatch wrapped slot and unknown-memory result','unknown h result preserved','writer-absence claim withdrawn','test memory requires explicit bytes']),
        source_base='5ec3ea2a2a8a0e72975bb97ee09b3d3e5f6b2079',
        sboot_sha256=IMAGES['sboot'][1],
        scope='file PCs; first copy core=file-0x34000, second copy core=file-0x2d800',
        mapping=dict(first=dict(file=['0x38000','0x3d000'],core=['0x4000','0x9000']),
            second=dict(file=['0x3d000','0x67000'],core=['0xf800','0x39800']),
            thumb='pointers keep bit0; cleared only to locate the instruction',
            out_of_image='core >=0x39800 is outside the second copy; no initial value inferred'),
        registration=dict(
            manager='0x39b48/0x39b52: M32[core0x8000]=0x7150; 0x39b66: M32[core0x8014]=13 (runtime cells; file zero)',
            dataset='0x3998c called at 0x38e5a with core0x8000: writes desc_i+4 (initializer|1) and desc_i+36 (data size)',
            api_install='0x38e46 loop: M32[desc+8]=core0x710c for every descriptor before initializers run',
            initializer_call='0x38e90: blx M32[desc+4] with R0=&desc_i; enabled byte +32 gates the call',
            plugin9=dict(descriptor='core 0x7300 (file 0x3b300)',id=9,allow_mask='0x8b4 (bit7 set: DVFS may call)',
                enabled=1,name='plugin_DMC_0_0_0.fw',initializer='core 0x31e01 -> file 0x5f600',data_size='0x7000'),
            plugin7=dict(descriptor='core 0x72a0',id=7,allow_mask='0xb34',
                initializer='core 0x29601 -> file 0x56e00'),
            initializers=init_and_size),
        dvfs_side=dict(
            descriptor_cell='core0x2fbf0 written by DVFS init 0x56e06/0x56e08 (entry 0x56e00); read by relay 0x5817c',
            relay_58170='r0=M32[core0x2fbf0] (DVFS desc); r3=M32[desc+8] (API); r4=M32[API+28]=0x4b05 -> file 0x38b04; blx r4(desc,9,&frame20,&frame16,&frame12)',
            wrapper_581fc='subcmd 8: r0=9, r1=&value(wrapper sp+4), r2=0, r3=8',
            wrapper_58214='subcmd 9: r0=9, r1=&value(wrapper sp+4), r2=arg2, r3=9',
            call_sites=[
                dict(pc='0x5954a',wrapper='0x581fc',cmd=8,packed='0x20000|idxB|(idxA<<8)',sel=2,
                     return_tested='ble 0x59564 skips only notify cmd5; flow continues'),
                dict(pc='0x59572',wrapper='0x581fc',cmd=8,packed='0x10000|idxB|(idxA<<8)',sel=1,
                     return_tested=False,note='r0 overwritten at 0x59578 before the subcmd 9 call'),
                dict(pc='0x5957a',wrapper='0x58214',cmd=9,packed='0x10000|idxB|(idxA<<8)',sel=1,
                     arg2='M32[DVFS frame+28] = return of 0x5adb0(entry,B,&frame+80)',
                     return_tested='ble 0x59594 skips only notify cmd4'),
                dict(pc='0x5980c',wrapper='0x58214',cmd=9,packed='(idxA<<8)|idxB',sel=0,
                     arg2='same 0x5adb0 result',return_tested='ble 0x59826 skips only notify cmd4'),
                dict(pc='0x59828',wrapper='0x581fc',cmd=8,packed='(idxA<<8)|idxB',sel=0,
                     return_tested='ble 0x59842 skips only notify cmd5')],
            level_indices='idxA=0x5acec(A,entry), idxB=0x5acec(B,entry); count0 returns-1 and reaches 0x59896/0x5989c before any DMC call; nonempty lookup selects first low24(level)<=value, or last index if none'),
        generic_relay=dict(
            file='0x38b04',plugin_table='core0x8000: +0 descriptor array (0x7150), +20 count (13)',
            gates=dict(count='M32[core0x8014] > target (unsigned bls)',enabled='u8[desc+32] != 0',
                       method='M32[M32[desc+12]+12] != 0',
                       caller='(M32[desc+20] >> M32[caller_desc+0]) & 1; register shift uses low8(caller_id); effective shift >=32 zeroes'),
            fail_returns=dict(count_enabled_method=10,caller_mask=-11,
                              logged='via 0x38684 with M32[core0x8010] and fmt literals 0x6cfc/0x6cdc'),
            timing='SysTick reads via M32[core0x7d48]=0x63c9 -> 0x3a3c8 (M32[0xe000e018]) before/after the method call; difference logged; not a lock',
            method_call='blx M32[M32[desc+12]+12] with r0=&a1slot, r1=&a2slot, r2=&a3slot',
            retval='propagates the method return; wrapper 0x581fc/0x58214 return it unchanged'),
        dmc_interface=dict(
            initializer='0x5f600: M32[desc9+12]=core0x37c40; M32[core0x384d4]=&desc9; then 0x5f6ec (log), 0x60c70 (parses "db9f4b2" -> M32[core0x3a62c]), 0x60108->0x646d0 (installs table pointers 0x3ca00/0x3d9b0/0x3e960/0x3f910/0x408c0 at core0x381c8+0x1f0..0x200), 0x64400 (re-points the MMIO array only when t()==1)',
            methods_table=dict(core=hex(METHODS_CORE),file=f'{core_to_file(METHODS_CORE):#x}',
                entries={f'+{o}':f'core {v:#x} -> file {thumb_file(v):#x}' for o,v in methods.items()}),
            method12=dict(core=f'{methods[12]:#x}',file='0x5f758',
                behavior='cmd=*r2; handler=M32[0x37cd0+W32(cmd*4)]; null->-1; else handler(*r0slot,*r1slot) with r2 retaining the loaded handler pointer',
                bounds='no cmd bounds check; W32(cmd*4) wraps and may read outside the table'),
            handler_words={str(i):v for i,v in handlers.items()},
            handler_table={str(i):(f'core {v:#x} -> file {thumb_file(v):#x}' if v else 'null')
                for i,v in handlers.items()},
            state_object=dict(core=hex(DMC_OBJ_CORE),file=f'{core_to_file(DMC_OBJ_CORE):#x}',
                critical_slots='+68/+72 (core 0x37cc8/0x37ccc) start zero in file; handler8 stores API+0x38/API+0x3c there')),
        arguments=dict(
            subcmd8=dict(registers='wrapper R1=&value, R2=0, R3=8, R0=9',
                dereferences=['0x58170 stores R1/R2/R3 at its frame+20/+16/+12',
                              '0x38b04 passes &frame20/&frame16/&frame12 to the method',
                              'method+12: cmd=M32[&frame12]=8; a1=M32[&frame20]=&value; a2=M32[&frame16]=0',
                              'handler r0=&value (one more deref yields the packed u32), r1=0'],
                recipient_mutation='handler r0 points at the wrapper stack slot; neither analyzed handler writes through it; the wrapper never reads the slot back'),
            subcmd9=dict(registers='wrapper R1=&value, R2=arg2, R3=9, R0=9',
                dereferences=['same three-level chain; a2=M32[&frame16]=arg2 by value',
                              'handler r0=&value, r1=arg2'],
                arg2='saved at frame+0 by 0x5fbc4, copied via 0x5fbe8 to frame+20 at 0x5fbea; neither slot is read later in the selected handler body: the 0x5adb0 helper result is discarded by the DMC',
                recipient_mutation='none in the analyzed handlers; arg2 is a copy, not a pointer')),
        handlers=dict(
            subcmd8=dict(file='0x5fadc',fields='sel=(v>>16)&3, byte1=(v>>8)&0xff, byte0=v&0xff',
                va='f64620(byte0)=byte0 or -1 using bitmask M32[core0x3a660]',
                vb='f64620(byte1) with the same mask',
                publish='0x5fb26..0x5fb3c: M32[obj+68]=M32[API+0x38] (0x440d->0x3840c enter critical), M32[obj+72]=M32[API+0x3c] (0x441d->0x3841c exit critical); both are PRIMASK save/restore at 0x39b10/0x39b04',
                sel0='vb<0 and va>0: g64618(obj)->0x645c4 (copies M32[core0x3a600]/M32[core0x3a604] into core0x381c8+0x240/0x244, extracts bits8..11 into +0x209, stores obj at +0x260, calls 0x643d0(4,bits,28,6)->0x615ec MMIO RMW and 0x6449c(1)->obj+0x34); result=h64658(byte0)',
                sel1='vb>0 and va<0: p645bc(obj)->0x64568 (same copies; 0x643e8(4,bits,28,4)->0x615ec; 0x6449c(6)) then q64510(obj)->M32[core0x37d94]=0x33f6d->0x6176c(4) with enter/exit critical and the two polls; result stays -1',
                sel2='vb>0 and va<0: r64530() gated by bits16..19 of M32[core0x381c8+0x244]==1 -> 0x616cc(4) MMIO sequence; result=h64658(byte0)',
                sel3='result -1; unmatched sign pairs also return -1',
                h_table='h64658(b)=M32[base+(b+18)*8+4], base lazily M32[core0x381c8+0x23c] from M32[core0x3a664]',
                mmio='0x615ec reads M32[entry0] (entry0=M32[core0x37df8]) and writes entry4+0/+4/+8/+0x38; 0x6176c/0x616cc read entry0+0x364/+0x23c/+0xcc/+0x1bc and write entry4+0x23c/+0xcc/+0x1bc/+0x48c/+0',
                mmio_arrays=dict(default=[hex(v) for v in mmio_first],
                    when_t1=[hex(v) for v in mmio_t],second=[hex(v) for v in mmio_second])),
            subcmd9=dict(file='0x5fbbc',fields='same extraction',
                va='f6463c(byte0) using bitmask M32[core0x3a668]',
                vb='f6463c(byte1) with the same mask',
                sel0='vb>=0, va>=0 and g2(byte1)>g2(byte0): result=g2(byte0)',
                sel1='vb>=0, va>=0 and g2(byte0)>g2(byte1): result=g2(byte0)',
                sel23='result -1; no w() tail',
                tail='for sel0/1 always: t()=bits20..23 of M32[0xa0000010] (0x651b0), u()=bits16..19 (0x651c0); t()==1 and u()==0 -> w(0) else w(1)',
                w='w(arg)=M32[core0x37ebc]=0x35e6d->0x6366c(arg): RMW M32[second_array[arg]+0x18] bit14=arg&1 (entries 0xac040000/0xac140000 for arg 0/1)',
                g2_table='g6467c(b)=M32[base+(b+31)*8+4] with the same lazily filled base')),
        polls=[dict(p) for p in POLLS],
        returns=dict(
            relay='wrapper returns the method return unchanged (0x58170/0x38b04 do not transform it)',
            first8='0x5954a: positive signed return notifies cmd5 via M32[core0x2eccc+16] (0x2a321->0x57b20); non-positive is silent; both continue',
            pair='0x59572 return ignored; 0x5957a return notifies cmd4 when positive; subcmd8 cannot gate subcmd9 by its return value',
            terminal='0x5980c (cmd9) then 0x59828 (cmd8), both sel=0, each with its own notify (4 then 5) on positive returns',
            hangs='a non-returning call (unbounded polls 0x65182/0x65196) prevents later calls; that is a hang frontier, not a return-propagated failure',
            no_rollback='no local return-conditioned rollback identified in the selected DVFS call sites; callee effects are not globally excluded; handler8 publishes the critical pair'),
        frontiers=[
            'M32[core0x3a660]/M32[core0x3a668] (level bitmasks) and M32[core0x3a664] (h/g2 table base) lie beyond the second copied image (core>=0x39800). Readers at 0x64620/0x6463c/0x64662/0x64686 are identified; absence of writers or aliases is not proven',
            'external config-loader lead: 0x647ac..0x65170 is not fully covered here. Computed store aliases must be traced before excluding writes to 0x3a660/0x3a664/0x3a668',
            'plugin count M32[core0x8014], array base M32[core0x8000], desc+8 API and desc+12 methods are runtime-installed (0x39b48/0x38e46/0x5f610); file content only proves the initializers and masks',
            'MMIO pointer arrays are re-pointed by 0x64400 only when t()==1 at DMC init; both variants are in-image literals but the live selection depends on MMIO 0xa0000010',
            'the caller of BL2 table slot 47 remains open; the 0x5adb0 helper feeding subcmd9 arg2 was not reconstructed here (its result is discarded by the DMC anyway)',
            'no hardware semantics or physical units were attributed to sel/byte0/byte1/g2/h values'],
        conditions=['DVFS->DMC passes only after the selected initializers install count, roots, API and methods, and those roots/masks remain preserved across logging/timing hooks; file descriptor bytes alone do not establish that state',
            'handlers only see the packed word and arg2; the level table contents are runtime state',
            'poll loops have no firmware timeout; host test budgets are not firmware timeouts'],
        anchors={f'{at:#x}':value for at,value in ANCHORS.items()},
        literals={f'{at:#x}':value for at,value in sorted(literals.items())},
        witnesses=witnesses,
        gnu=dict(version=version,instructions=len(lines),relative_branches=relative,
            literal_loads=len(literals),selected=len(SELECTED),
            ranges=[[hex(lo),hex(hi)] for lo,hi in RANGES]),
        firmware_executed=False,physical_device_tested=False,
        qemu_scope_extended=False,slot47_resolved=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot',nargs='?',default='download/firmware_jhzc2/sboot.bin')
    parser.add_argument('--json',default='docs/references/newtime-dmc-method12-hzc2.json')
    args=parser.parse_args()
    try:
        report=inspect(args.sboot)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    Path(args.json).parent.mkdir(parents=True,exist_ok=True)
    Path(args.json).write_text(json.dumps(report,indent=1)+'\n')
    print(json.dumps({k:report[k] for k in
        ('mode','source_base','sboot_sha256','scope')},indent=1))
    print('witness instructions:',len(report['witnesses']))
    print('wrote',args.json)


if __name__=='__main__':
    raise SystemExit(main())
