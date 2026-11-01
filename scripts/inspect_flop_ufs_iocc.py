#!/usr/bin/env python3
"""Cross-check pinned flattened DTS/driver reference against selected LK writes."""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from inspect_lk_ufs_iocc import inspect as inspect_lk

ROOT=Path(__file__).resolve().parent.parent
MANIFEST=ROOT/'docs/references/flop-ufs-iocc-source-reference.json'
COMMIT='4553117a5014928dff55595f46627e0d77bcf133'
DTS='arch/arm64/boot/dts/exynos/exynos2100.dts'
DRIVER='drivers/scsi/ufs/ufs-exynos.c'
TOKEN=re.compile(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*|[{};=<>]|[^\s{};=<>]+',re.S)


def dts_nodes(text):
    """Parse the pinned flattened syntax, retaining opaque property tokens.

    No cpp, include, incbin, overlays, expressions or label resolution.
    Numeric cell interpretation is separate and rejects expressions.
    """
    nodes={};stack=[];pending=[];newlines=[m.start() for m in re.finditer('\n',text)]
    for match in TOKEN.finditer(text):
        token=match[0]
        if token.startswith(('/*','//')):continue
        line=bisect.bisect_left(newlines,match.start())+1
        if token=='{':
            if len(pending)==2 and re.fullmatch(r'[A-Za-z_]\w*:',pending[0][0]):
                pending=pending[1:]  # Declaration label only; never resolve &references.
            if len(pending)!=1:raise ValueError('unsupported DTS node header')
            name=pending[0][0]
            if not stack:
                if name!='/':raise ValueError('one DTS root required')
                path='/'
            else:
                if not re.fullmatch(r'[A-Za-z0-9_,.@+\-]+',name):raise ValueError('unsupported DTS node name')
                path=stack[-1].rstrip('/')+'/'+name
            if path in nodes:raise ValueError('duplicate DTS node')
            nodes[path]=dict(line=pending[0][1],properties={});stack.append(path);pending=[]
        elif token=='}':
            if pending or not stack:raise ValueError('unbalanced DTS node')
            stack.pop()
        elif token==';':
            if not pending:continue  # semicolon after a node
            if not stack:
                if [t for t,_ in pending]!=['/dts-v1/'] or nodes:raise ValueError('unsupported DTS directive')
            else:
                key=pending[0][0]
                if not re.fullmatch(r'[A-Za-z0-9_,.#@+\-]+',key):raise ValueError('unsupported DTS property')
                values=[t for t,_ in pending[1:]]
                if values and values[0]!='=':raise ValueError('DTS assignment required')
                props=nodes[stack[-1]]['properties']
                if key in props:raise ValueError('duplicate DTS property')
                props[key]=dict(tokens=values[1:] if values else [],line=pending[0][1])
            pending=[]
        else:pending.append((token,line))
    if stack or pending or '/' not in nodes:raise ValueError('truncated DTS')
    return nodes


def cells(node,name):
    tokens=node['properties'][name]['tokens']
    if len(tokens)<3 or tokens[0]!='<' or tokens[-1]!='>' or any(not re.fullmatch(r'0[xX][0-9a-fA-F]+|[0-9]+',t) for t in tokens[1:-1]):
        raise ValueError('literal DTS cells required')
    values=[int(t,16 if t.lower().startswith('0x') else 10) for t in tokens[1:-1]]
    if any(v>=1 << 32 for v in values):raise ValueError('DTS cell exceeds u32')
    return values


def dts_reference(text):
    nodes=dts_nodes(text);root=nodes['/']
    if cells(root,'#address-cells')!=[2] or cells(root,'#size-cells')!=[1]:raise ValueError('root DTS cell counts differ')
    phandles={}
    for path,node in nodes.items():
        if 'phandle' not in node['properties']:continue
        value=cells(node,'phandle')
        if len(value)!=1 or value[0] in (0,0xffffffff) or value[0] in phandles:raise ValueError('invalid or duplicate phandle')
        phandles[value[0]]=path
    path='/ufs@0x13100000';ufs=nodes[path]
    def region(node):
        value=cells(node,'reg')
        if len(value)!=3:raise ValueError('one root region required')
        return (value[0] << 32)|value[1],value[2]
    def control(name,property_name):
        handle=cells(ufs,property_name)
        if len(handle)!=1 or handle[0] not in phandles:raise ValueError('unresolved control phandle')
        parent=phandles[handle[0]];base,size=region(nodes[parent]);child=nodes[path+'/'+name]
        fields={n:cells(child,n) for n in ('offset','mask','val')}
        if any(len(v)!=1 for v in fields.values()):raise ValueError('scalar control cells required')
        offset,mask,val=(fields[n][0] for n in ('offset','mask','val'))
        if offset%4 or offset+4>size or val & ~mask:raise ValueError('control offset/value outside declared region/mask')
        return dict(node=path+'/'+name,syscon_node=parent,base=hex(base),offset=hex(offset),
            address=hex(base+offset),mask=hex(mask),value=hex(val),line=child['line'])
    dma='dma-coherent' in ufs['properties']
    if dma and ufs['properties']['dma-coherent']['tokens']:raise ValueError('dma-coherent must be a flag')
    return dict(ufs_node=path,ufs_line=ufs['line'],ufs_reg_cells=[hex(v) for v in cells(ufs,'reg')],dma_coherent=dma,
        phy_isolation=control('ufs-phy-iso','samsung,pmu-phandle'),
        iocc=control('ufs-iocc','samsung,sysreg-phandle'))


C_WITNESSES={
    'phy_context':'struct ext_cxt *cxt = &ufs->cxt_phy_iso;',
    'phy_update':'exynos_pmu_update(cxt->offset, cxt->mask, (en ? 1 : 0) ? cxt->val : 0);',
    'phy_before_iocc':'exynos_ufs_ctrl_phy_pwr(ufs, true);',
    'iocc_context':'for (i = EXT_SYSREG, p = &ufs->regmap_sys, q = &ufs->cxt_iocc;',
    'iocc_update':'regmap_update_bits(*p, q->offset, q->mask, q->val);',
    'syscon_lookup':'syscon_regmap_lookup_by_phandle(np, ufs_ext_blks[i][0]);',
    'dma_flag':'bool is_dma_coherent = !!of_find_property(dev->of_node, "dma-coherent", NULL);',
    'disable_without_flag':'if (!is_dma_coherent) { ufs->cxt_iocc.val = 0;',
    'context_tokens':'{"samsung,sysreg-phandle", "ufs-iocc"}',
}


def driver_witnesses(text):
    rows={}
    for key,snippet in C_WITNESSES.items():
        pattern=r'\s*'.join(re.escape(c) for c in re.sub(r'\s+','',snippet))
        matches=list(re.finditer(pattern,text))
        if len(matches)!=1:raise ValueError('one driver witness required: '+key)
        rows[key]=dict(line=text.count('\n',0,matches[0].start())+1,snippet=snippet)
    return rows


def verify_sources(root):
    manifest=json.loads(MANIFEST.read_text())
    if manifest['repository']!='FlopKernel-Series/flop_exynos2100_kernel' or manifest['commit']!=COMMIT or len(manifest['files'])!=2 or {r['path'] for r in manifest['files']}!={DTS,DRIVER}:raise ValueError('source manifest identity/files differ')
    texts={}
    for row in manifest['files']:
        if type(row['bytes']) is not int or not 0<row['bytes']<=1024*1024:raise ValueError('source size bound differs')
        with (Path(root)/row['path']).open('rb') as f:raw=f.read(row['bytes']+1)
        blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if (len(raw),hashlib.sha256(raw).hexdigest(),blob)!=(row['bytes'],row['sha256'],row['blob_sha1']):raise ValueError('source bytes differ: '+row['path'])
        texts[row['path']]=raw.decode('utf-8')
    return texts


def inspect(root,sboot):
    texts=verify_sources(root);lk=inspect_lk(sboot)
    ref=dts_reference(texts[DTS]);witnesses=driver_witnesses(texts[DRIVER])
    phy,iocc=ref['phy_isolation'],ref['iocc'];alt=lk['configuration_tables'][1]
    if (phy['address'],phy['mask'],phy['value'])!=('0x15860728','0x1','0x1') or phy['address']!=alt['phy']:raise ValueError('PHY isolation cross-check differs')
    if (iocc['address'],iocc['mask'],iocc['value'])!=('0x11020700','0x300000','0x300000') or iocc['address']!=alt['iocc_candidate'] or not ref['dma_coherent']:raise ValueError('IOCC alternate cross-check differs')
    return dict(mode='pinned_flop_ufs_phy_iocc_reference',commit=COMMIT,source_files=2,
        source_manifest_sha256=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        sboot_sha256=lk['sboot_sha256'],lk_instruction_index_sha256=lk['instruction_index_sha256'],
        dts=ref,driver_witnesses=witnesses,
        match=dict(phy_bypass='LK OR1 at15860728 agrees with reference PHY isolation bypass control',
            alternate_iocc='alternate table11020700 with independent query=1 OR300000 agrees with reference enabled IOCC bits',
            primary_iocc_meaning_established=False,
            disable='driver clears its IOCC mask when dma-coherent is absent; the selected LK fragment has OR/skip paths, no equivalent clear',
            query_stability_established=False),
        kernel_or_firmware_executed=False,live_iocc_acquired=False,dma_coherence_established=False,
        limits=['Pinned custom-kernel source declaration/driver intent, not the stock HZC2 DTB or device register state.',
            'DTS parser supports flattened nodes and literal u32 cells only; opaque unrelated property values are not interpreted.',
            'Source witnesses do not build or execute kernel code; regmap/exynos_pmu_update implementations and error effects are outside this cross-check.',
            'Only the alternate address with query=1 is matched; unknown producer/stability can yield other table/mask combinations.',
            'No proof of CPU/device ownership, snooping, cache freshness, SMMU/bus translation, preserved configuration or successful storage I/O.'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source_root');p.add_argument('sboot');a=p.parse_args()
    try:print(json.dumps(inspect(a.source_root,a.sboot),indent=2))
    except (OSError,ValueError,KeyError,UnicodeError,struct.error,subprocess.CalledProcessError) as exc:p.exit(2,f'inspect_flop_ufs_iocc: {exc}\n')
