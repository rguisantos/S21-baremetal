#!/usr/bin/env python3
"""Replay a guarded userland contract from preserved read-only memory bytes."""
import argparse
import json
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.xnu import boot_contract as c,efi_memory as memory,resident,userland_profile as profile
from scripts import run_xnu_lab as lab


def verify(run,kernel):
    path=run/'report.json'
    if not path.exists():path=run/'status.json'
    data=json.loads(path.read_text());capture=data['contract']
    if not capture or not capture.get('verified'):raise c.ContractError('completed boot capture required')
    reference=json.loads(lab.REFERENCE.read_text());expected=next(x['sha256'] for x in reference['kernel_prebuilt_integrity']['checks'] if x['path']=='prebuilt/mach.development.bcm2837')
    lab.verified(kernel,expected)
    pinned=json.loads((ROOT/'docs/references/hackios-userland-inputs-20261023.json').read_text())['images']
    for name in ('root','system'):
        if any(data['inputs'][name][key]!=pinned[name][key] for key in ('bytes','sha256')):raise c.ContractError('unpinned image metadata')
    physical=capture['physical_reads'];values={}
    for name,info in physical.items():
        raw=(run/(name+'.bin')).read_bytes()
        if len(raw)!=info['bytes'] or lab.sha256(run/(name+'.bin'))!=info['sha256']:raise c.ContractError('changed physical capture: '+name)
        address=data['build']['symbols'][name]+capture['loader_relocation']
        if hex(address)!=info['physical']:raise c.ContractError('capture symbol address mismatch')
        values[name]=raw
    maps=profile.snapshots(values['s21_maps'])
    u64=lambda name:struct.unpack('<Q',values[name])[0]
    claims={'payload':{'base':memory.PAYLOAD.base,'size':memory.PAYLOAD.size,'status':u64('s21_payload_status'),'returned':u64('s21_payload_claim')},
            'window':{'base':u64('win_base'),'size':u64('win_size'),'status':u64('s21_window_status'),'returned':u64('s21_window_claim')}}
    rd=dict(zip(('base','size'),struct.unpack('<2Q',values['s21_resident_cfg'])));declared=resident.decode(bytes.fromhex(data['resident_descriptor_hex']))
    if rd!=declared or rd['size']!=data['inputs']['system']['bytes']:raise c.ContractError('resident capture mismatch')
    frame={'base':u64('s21_frame_base'),'size':u64('s21_frame_size'),'after_stage':u64('s21_frame_after_stage')}
    typed=profile.decode(bytes.fromhex(data['raw_profile_hex']));ident,epoch=struct.unpack('<I4xQ',values['s21_profile_cfg'])
    if (ident,epoch)!=(typed['id'],typed['epoch']):raise c.ContractError('profile capture mismatch')
    for name,key in (('boot-args.bin','boot_args_sha256'),('apple-tree.bin','tree_sha256'),('resident-header.bin','header_sha256')):
        if lab.sha256(run/name)!=capture[key]:raise c.ContractError('changed ABI capture: '+name)
    boot=c.BootArgs.decode((run/'boot-args.bin').read_bytes());tree=c.decode_tree((run/'apple-tree.bin').read_bytes())
    resident.verify_header((run/'resident-header.bin').read_bytes(),rd['size'])
    checked,audit=memory.verify(maps,claims,boot,tree,boot.physical(int(capture['x0'],16),c.BOOT_SIZE).base,kernel.read_bytes(),resident_claim=rd,video_claim=frame)
    limits=profile.verify(boot,tree,typed,data['inputs']['root']['bytes'])
    if checked!=capture['profile'] or limits!=capture['userland_limits'] or audit!=capture['memory_audit']:
        raise c.ContractError('replayed contract differs from recorded result')
    return {'verified':True,'profile':limits,'window':audit['window'],'root':checked['placements']['RAMDisk'],'small_disk':checked['placements']['RAMDisk1'],
            'framebuffer':checked['video'],'scope':'Consistency of preserved boot and UEFI captures, not Samsung execution or automatic GUI proof'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--kernel',type=Path,required=True);args=p.parse_args()
    try:print(json.dumps(verify(args.run,args.kernel),indent=2))
    except (OSError,ValueError,KeyError,struct.error) as exc:p.exit(2,'Verification failed: '+str(exc)+'\n')
