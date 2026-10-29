#!/usr/bin/env python3
"""Static FVP command6/domain0 arbitration before the nominal DVFS relay."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

from check_acpm_handshake_gnu import parse_thumb
from inspect_acpm_handshake_hzc2 import thumb_target, thumb_pair, thumb_wide
from inspect_el2_hzc2 import IMAGES, read_exact

U32 = (1 << 32)-1
STATE = 0x120f0
CAP_ENABLE = 0x120a0
RAW_MAX = 0x12208
DIRECTION = 0x12210
POLICY_ENABLE = 0x12214
RANGES = ((0x3f000,0x3f086), (0x3f0d0,0x3f46c), (0x3f470,0x3f784),
          (0x5bb6c,0x5bbe4))
SELECTED = {
    0x3f014:('str','r0, [r3, #0]'),
    0x3f028:('str','r2, [r3, r1]'), 0x3f02a:('str','r2, [r3, #16]'),
    0x3f0da:('str','r2, [sp, #20]'), 0x3f0e4:('ldr','r5, [r2, r3]'),
    0x3f0e8:('bls.n','0x3f14a'), 0x3f0f8:('str','r1, [sp, #16]'),
    0x3f10e:('ldr','r0, [r3, #0]'), 0x3f114:('str','r2, [sp, #0]'),
    0x3f116:('ldr','r4, [r3, #28]'), 0x3f118:('movs','r1, #7'),
    0x3f11a:('add','r3, sp, #16'), 0x3f11c:('add','r2, sp, #12'),
    0x3f11e:('blx','r4'), 0x3f130:('cbnz','r4, 0x3f15c'),
    0x3f132:('cmp','r5, #0'), 0x3f134:('blt.n','0x3f144'),
    0x3f13a:('ldr','r2, [sp, #16]'), 0x3f142:('str','r2, [r5, r3]'),
    0x3f14a:('movs','r2, #140'), 0x3f156:('ldr','r1, [r0, r3]'),
    0x3f158:('str','r1, [sp, #16]'),
    0x3f262:('movw','r3, #8724'), 0x3f26c:('cbz','r3, 0x3f2ca'),
    0x3f27a:('cmp','r1, r2'), 0x3f27c:('bls.n','0x3f2ca'),
    0x3f28c:('cmp','r0, #1'), 0x3f28e:('bne.n','0x3f2ca'),
    0x3f2cc:('bl','0x3f0d0'),
    0x3f39e:('cmp','r3, #1'), 0x3f3a2:('b.n','0x3f6a4'),
    0x3f3b4:('beq.n','0x3f3b8'), 0x3f3c4:('ldr','r1, [r1, #16]'),
    0x3f3c8:('bls.n','0x3f3da'), 0x3f3d4:('cmp','r2, #0'),
    0x3f3de:('cmp','r5, #0'), 0x3f3e2:('b.n','0x3f262'),
    0x3f4b0:('str','r6, [r2, #4]'), 0x3f4be:('str','r2, [r1, #0]'),
    0x3f4d2:('ldr','r2, [r1, #4]'), 0x3f4da:('ldr','r2, [r1, #8]'),
    0x3f4e4:('ldr','r2, [r1, #12]'),
    0x3f4f6:('cmp','r2, r1'), 0x3f4f8:('bcc.n','0x3f4fc'),
    0x3f506:('str','r5, [r1, #0]'), 0x3f518:('str','r2, [r3, r1]'),
    0x3f51c:('ldr','r1, [r1, #16]'), 0x3f520:('bhi.n','0x3f524'),
    0x3f53a:('str','r1, [r3, r2]'),
    0x3f5aa:('str','r2, [r6, #16]'), 0x3f64a:('bhi.n','0x3f676'),
    0x3f64e:('cmp','r1, r2'), 0x3f650:('bls.n','0x3f654'),
    0x3f656:('str','r2, [r1, #0]'), 0x3f664:('bcc.n','0x3f668'),
    0x3f672:('str','r5, [r1, #0]'),
    0x3f68c:('bcc.n','0x3f654'), 0x3f69c:('str','r1, [r2, #0]'),
    0x3f6ac:('movs','r0, #0'), 0x3f6ae:('movs','r5, #1'),
    0x3f6b0:('movw','ip, #0'), 0x5bbc0:('ldr','r0, [r0, #0]'),
    0x5bbc2:('ldr','r1, [r1, #0]'), 0x5bbc4:('blx','r3'),
}


def u32(value):
    if type(value) is not int or not 0 <= value <= U32:
        raise ValueError('expected host u32')
    return value


def arbitrate(request, competing8, competing12, old, cap, cap_enabled, direction):
    """Bounded host formula, selected command6/domain0 with stable RAM roots."""
    for value in (request,competing8,competing12,old,cap,cap_enabled,direction):u32(value)
    candidate=max(request,competing8,competing12)
    after_direction=direction if candidate==old else int(candidate<old)
    effective=min(candidate,cap) if cap_enabled else candidate
    return dict(request=request,uncapped=candidate,effective=effective,
                direction_before=direction,direction_after=after_direction,
                direction_written=candidate!=old,cap_applied=effective!=candidate,
                raw_max_cell=candidate,relay_domain=0,relay_mode=0,
                helper_call_selected=True)


def returned_cache(index,relay_result,effective_after_call):
    """3f130/3f134: signed table index; value is reloaded from private frame."""
    for value in (index,relay_result,effective_after_call):u32(value)
    if relay_result or index & (1 << 31):return None
    return dict(core=(0x12700+((index<<2)&U32))&U32,value=effective_after_call)


def inspect(path):
    data=read_exact(path,*IMAGES['sboot'])
    root=Path(__file__).resolve().parent.parent
    cmd=['bash',str(root/'scripts/cross-run.sh'),str(root/'tools/root'),
         str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines={}
    for lo,hi in RANGES:
        output=subprocess.check_output(cmd+['-D','-z','-b','binary','-m','arm','-M','force-thumb',
            f'--start-address={lo}',f'--stop-address={hi}',str(Path(path).resolve())],text=True)
        decoded=parse_thumb(output)
        if lines.keys() & decoded.keys():raise ValueError('overlapping GNU windows')
        lines.update(decoded)
    covered=set();relative=0
    for pc,(raw,op,args) in sorted(lines.items()):
        if raw!=data[pc:pc+len(raw)] or op in ('.short','.word','.inst','udf'):
            raise ValueError(f'GNU word differs at {pc:#x}')
        covered.update(range(pc,pc+len(raw),2))
        target=thumb_target(data,pc)
        if target is not None:
            if int(args.split('@')[0].split(',')[-1].strip(),0)!=target:
                raise ValueError(f'GNU branch differs at {pc:#x}')
            relative+=1
        elif op in ('bl','b.n','b.w','beq.n','bne.n','blt.n','bgt.n','bhi.n','bls.n','bcc.n','bcs.n','cbz','cbnz'):
            raise ValueError(f'unhandled relative instruction at {pc:#x}')
    if covered!={pc for lo,hi in RANGES for pc in range(lo,hi,2)}:
        raise ValueError('GNU halfword coverage differs')
    for pc,expected in SELECTED.items():
        _,op,args=lines[pc]
        if (op,args.split('@')[0].strip())!=expected:
            raise ValueError(f'GNU operand differs at {pc:#x}')
    word=lambda core:struct.unpack_from('<I',data,core+0x2d800)[0]
    lo,hi=thumb_wide(data,0x3f018),thumb_wide(data,0x3f022,True)
    if (lo[0],hi[0],lo[1]|hi[1]<<16)!=(3,3,STATE) or thumb_pair(data,0x3f3ca,2)!=CAP_ENABLE:
        raise ValueError('state or cap-enable address differs')
    command_table=struct.unpack_from('<7I',data,0x3f784)
    if command_table[6]+0x2d800!=0x3f38c:raise ValueError('command6 target differs')
    index=word(0x1200c)
    cases=[('raw_request',(3172000,0,0,0,U32,1,9)),
           ('competing_floor',(100,200,50,100,U32,1,9)),
           ('cap_after_rise',(300,0,0,200,100,1,9)),
           ('cap_disabled',(300,0,0,200,100,0,9)),
           ('equal_candidate_still_clamped',(300,0,0,300,100,1,9)),
           ('all_zero',(0,0,0,0,0,1,9)),
           ('unsigned_high_bit',(0x80000000,1,0,0,U32,1,9))]
    return dict(mode='static_FVP_command6_domain0_effective_hzc2',
        source_base='4d36dd13de75eb118f78cd322e1867b16f920a75',sboot_sha256=IMAGES['sboot'][1],
        scope='file PCs; core data addresses; selected Thumb ACPM mapping file=core+0x2d800',
        entry=dict(command6='0x3f38c',domain0='0x3f6a4',channel=1,
            setup='R8=0, R0=0, R5=1, IP=0; frame+20=request, frame+24=6',
            dispatch_initial_core_pointers=[hex(v) for v in command_table]),
        fields=dict(state_core=hex(STATE),effective='+0',request='+4',competing=['+8','+12'],cap='+16',
            cap_enable_core=hex(CAP_ENABLE),uncapped_mirror_core=hex(RAW_MAX),
            direction_core=hex(DIRECTION),other_policy_core=hex(POLICY_ENABLE),
            initial_file_words=[word(STATE+i*4) for i in range(5)],
            initial_cap_enable=word(CAP_ENABLE),initial_domain0_cache_index=index,
            initializer='0x3f028/0x3f02a set both domain caps to 0xffffffff if initializer executes',
            selected_cap_writer='command4/channel1: 0x3f5aa',
            selected_enable_writer='command5/subselector2: 0x3f69c; value from packet word1',
            file_initial_is_runtime_observation=False),
        arbitration=dict(formula='M=max_u32(request,S+8,S+12); E=cap_enabled ? min_u32(M,cap) : M',
            requested_store='0x3f4b0 -> core0x120f4',raw_mirror='0x3f4be=0; 0x3f656=M on nonzero branch',
            direction='M<old ->1; M>old ->0; M==old ->no write; evaluated BEFORE cap',
            effective_stores=['0x3f518: uncapped M when changed','0x3f53a: cap when enabled and M>cap'],
            unchanged_still_calls_helper=True,
            auxiliary_policy='0x3f262..0x3f2ca: even if 12214!=0 and S+8>request, R0=0 rejects R0==1 arm',
            policies_not_recomputed_after_cap=True,
            meanings_of_competing_words_and_direction='structural only; hardware units/policy names not established'),
        relay=dict(call='0x3f2cc ->0x3f0d0',selected_domain=0,
            reload='0x3f156 reloads effective from core120f0 into private frame+16',
            mode='private frame+20 initialized0 at0x3f0da',
            api_call='0x3f11e: R0=M32[core1220c] descriptor; R1=7; R2=&domain; R3=&effective; stack0=&mode',
            private_argument_mutation_excluded=False,
            post_return='relay result nonzero skips cache; zero and signed index>=0 stores reloaded frame effective',
            initial_cache_candidate=returned_cache(index,0,3172000),
            rollback_in_selected_error_path=False,
            error_path='0x3f130 ->0x3f15c log ->0x3f144; pre-call stores are not undone here',
            next_nominal_target='0x5bb6c ->mode0 ->0x59be4; body delegated to separate analysis'),
        scenarios=[dict(name=name,inputs=list(args),result=arbitrate(*args)) for name,args in cases],
        conditions=['normal selected code and copy mapping; channel1, command6, domain0',
            'logging calls return and preserve carried registers/private frames/selected state and roots',
            'no concurrent or aliased writes to selected words between load/compare/store/reload',
            'no physical data values, clock unit, MMIO effect or success inferred from local arithmetic',
            'helper call is selected even unchanged, but relay gates may reject and callbacks may not return',
            'effective/mode pointers passed to relay may be mutated; post-return cache reload is explicit'],
        gnu=dict(version=subprocess.check_output(cmd+['--version'],text=True).splitlines()[0],
            instructions=len(lines),halfwords=len(covered),relative_targets=relative,selected_operands=len(SELECTED)),
        witnesses=[dict(pc=hex(pc),bytes=raw.hex(),op=op,args=args) for pc,(raw,op,args) in sorted(lines.items())],
        firmware_executed=False,qemu_scope_extended=False,physical_device_tested=False,
        slot47_caller_resolved=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('sboot');args=parser.parse_args()
    try:report=inspect(args.sboot)
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as exc:
        parser.exit(2,f'inspect_newtime_fvp_effective_hzc2: {exc}\n')
    print(json.dumps(report,indent=2))
