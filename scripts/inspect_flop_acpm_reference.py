#!/usr/bin/env python3
"""Hash-check eight pinned ACPM/ECT sources and probe only fixed SRAM structs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from inspect_el2_hzc2 import IMAGES,read_exact
from inspect_flop_reference import numeric_define
from inspect_newtime_hzc2 import embedded
from inspect_newtime_dmc_magic_hzc2 import MAGIC,SIGNAL,LOCAL_SIGNAL

ROOT=Path(__file__).resolve().parent.parent
MANIFEST=ROOT/'docs/references/flop-acpm-source-reference.json'
PREFIX='drivers/soc/samsung/acpm/'
FILES={PREFIX+x for x in ('acpm.h','acpm_ipc.h','acpm_ipc.c','fw_header/common.h','fw_header/framework.h')}|{
 'include/soc/samsung/acpm_ipc_ctrl.h','include/soc/samsung/ect_parser.h','drivers/soc/samsung/ect_parser.c'}
COMMIT='4553117a5014928dff55595f46627e0d77bcf133'


def struct_fields(text,name):
    if not re.fullmatch(r'[A-Za-z_]\w*',name):raise ValueError('invalid struct name')
    text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
    found=re.findall(r'\bstruct\s+'+re.escape(name)+r'\s*\{([^{}]*)\}\s*;',text)
    if len(found)!=1:raise ValueError('one fixed SRAM struct required')
    body=re.sub(r'#if\s+!\(defined\(CONFIG_EXYNOS_ACPM\)\s*\|\|\s*defined\(CONFIG_EXYNOS_ACPM_MODULE\)\)\s*\n.*?#else\s*\n(.*?)#endif',r'\1',found[0],flags=re.S)
    fields=[]
    for line in body.split(';'):
        if not line.strip():continue
        match=re.fullmatch(r'\s*(u8|u32|s32|struct\s+timer_desc|struct\s+channel_info)\s+([A-Za-z_]\w*)\s*',line)
        if not match:raise ValueError('unsupported SRAM field or preprocessing')
        fields.append((' '.join(match[1].split()),match[2]))
    if not fields or len({n for t,n in fields})!=len(fields):raise ValueError('empty or duplicate SRAM field')
    return fields


def host_layout(definitions,*,cc='cc'):
    code='#include <stdint.h>\n#include <stddef.h>\n#include <stdio.h>\ntypedef uint8_t u8; typedef uint32_t u32; typedef int32_t s32;\n'
    rows=[];args=[]
    for name,fields in definitions:
        # Revalidate, then recompose declaration-only C. Never execute source macros.
        safe='struct '+name+' {'+''.join(t+' '+n+';' for t,n in fields)+'};'
        if struct_fields(safe,name)!=fields:raise ValueError('invalid probe grammar')
        code+=safe+'\n';rows.append('"'+name+'.bytes":%zu');args.append('sizeof(struct '+name+')')
        for _,n in fields:rows.append('"'+name+'.'+n+'":%zu');args.append('offsetof(struct '+name+','+n+')')
    fmt='{'+','.join(rows)+'}\\n'
    code+='int main(void){printf("'+fmt.replace('"','\\"')+'",'+','.join(args)+');return 0;}\n'
    with tempfile.TemporaryDirectory(prefix='acpm-abi-') as d:
        p=Path(d);(p/'probe.c').write_text(code)
        subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror',str(p/'probe.c'),'-o',str(p/'probe')],capture_output=True,text=True,check=True)
        return json.loads(subprocess.check_output([str(p/'probe')],text=True))


def verify_sources(root):
    manifest=json.loads(MANIFEST.read_text())
    if manifest['repository']!='FlopKernel-Series/flop_exynos2100_kernel' or manifest['commit']!=COMMIT or {r['path'] for r in manifest['files']}!=FILES or len(manifest['files'])!=len(FILES):
        raise ValueError('unexpected ACPM source manifest identity/files')
    texts={}
    for row in manifest['files']:
        if type(row['bytes']) is not int or not 0<row['bytes']<=1024*1024:raise ValueError('source size bound differs')
        with (Path(root)/row['path']).open('rb') as f:raw=f.read(row['bytes']+1)
        if (len(raw),hashlib.sha256(raw).hexdigest(),hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())!=(row['bytes'],row['sha256'],row['blob_sha1']):
            raise ValueError('ACPM source bytes differ: '+row['path'])
        texts[row['path']]=raw.decode('utf-8')
    return texts,manifest


def inspect(root,sboot,*,cc='cc'):
    data=read_exact(sboot,*IMAGES['sboot'])
    texts,manifest=verify_sources(root)
    common=texts[PREFIX+'fw_header/common.h'];framework=texts[PREFIX+'fw_header/framework.h']
    definitions=[(n,struct_fields(src,n)) for src,n in ((common,'timer_desc'),(common,'plugin'),(framework,'channel_info'),(framework,'ipc_channel'))]
    layout=host_layout(definitions,cc=cc)
    if [layout[n+'.bytes'] for n in ('plugin','channel_info','ipc_channel')]!=[48,52,72]:raise ValueError('SRAM host ABI sizes differ')
    constants={n:numeric_define(texts[PREFIX+'acpm_ipc.h'],n) for n in ('INTGR0','INTSR1','INTCR1')}
    if constants!={'INTGR0':8,'INTSR1':40,'INTCR1':32}:raise ValueError('mailbox register offsets differ')
    off=lambda member:layout['ipc_channel.ch']+layout['channel_info.'+member]
    channel=0x3b3c0+3*layout['ipc_channel.bytes']
    word=lambda a:struct.unpack_from('<I',data,a)[0]
    fields={n:word(channel+layout['ipc_channel.'+n]) for n in ('id','field','type')}
    fields.update({n:word(channel+off(n)) for n in ('rx_base','tx_base','q_len','q_elem_size','mbox_addr')})
    if fields!={'id':3,'field':8,'type':2,'rx_base':0xa5900100,'tx_base':0xa5900108,'q_len':1,'q_elem_size':16,'mbox_addr':0xa5900000}:
        raise ValueError('channel3 source-to-binary binding differs')
    plugin_ids=[word(0x3b2a0),word(0x3b2a0+2*layout['plugin.bytes'])]
    if plugin_ids!=[7,9]:raise ValueError('plugin stride/id binding differs')
    if fields['rx_base']+12!=LOCAL_SIGNAL or (1 << fields['id']) << 16!=0x80000:raise ValueError('magic/doorbell binding differs')
    driver=texts[PREFIX+'acpm_ipc.c']
    orientation={n:bool(re.search(r'\.\s*'+n+r'_ch\.base\s*=\s*[^;]+\.ch\.'+other+r'_base',driver)) for n,other in (('tx','rx'),('rx','tx'))}
    if not all(orientation.values()):raise ValueError('kernel/AP buffer orientation differs')
    ect=texts['include/soc/samsung/ect_parser.h']
    names={k:v for k,v in re.findall(r'^#define\s+(BLOCK_\w+)\s+"([A-Z0-9_]+)"\s*$',ect,re.M)}
    binary=embedded(data)
    directory=[name for name,_ in binary['directory']]
    if not set(directory)<=set(names.values()) or names.get('BLOCK_NEW_TIMING_PARAM')!='NEWTIME':raise ValueError('ECT namespace differs')
    if not re.search(r'ect_signature\[\]\s*=\s*"PARA"',texts['drivers/soc/samsung/ect_parser.c']):raise ValueError('ECT signature differs')
    return dict(mode='pinned_flop_acpm_sram_abi_reference',repository=manifest['repository'],commit=COMMIT,
        sboot_sha256=IMAGES['sboot'][1],source_files=len(texts),source_manifest_sha256=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        host_probe_only=True,kernel_or_firmware_executed=False,layout=layout,mailbox_constants=constants,
        channel3=dict(file_offset=hex(channel),fields={k:hex(v) for k,v in fields.items()},
            offsets={k:off(k) for k in ('rx_base','tx_base','q_len','q_elem_size','mbox_addr')},
            local_magic=hex(LOCAL_SIGNAL),candidate_ap_magic=hex(SIGNAL),magic=hex(MAGIC),physical_alias_verified=False),
        plugins=dict(stride=layout['plugin.bytes'],selected_ids=plugin_ids),
        kernel_buffer_orientation=dict(ap_tx_uses_firmware_rx=orientation['tx'],ap_rx_uses_firmware_tx=orientation['rx']),
        ect=dict(signature='PARA',binary_directory_names=directory,source_namespace=names,
            namespace_agrees=True,same_runtime_parser_or_data_version_proven=False),
        bounded_magic_text_search=dict(files=len(texts),matching_files=[p for p,t in texts.items() if 'abcd1234' in t.lower()],
            absence_across_repository_proven=False),
        limits=['Eight fixed source files, distinct from the unavailable sixteen-file external round.',
                'Fixed-width SRAM declarations only; host compiler probe does not build or run kernel/ACPM.',
                'Struct/offset/mailbox/namespace agreement is reference context, not proof of identical firmware implementation.',
                'Plugin ids, channel data, alias, clocks, interrupt delivery and service results are not live device observations.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source_root');parser.add_argument('sboot');parser.add_argument('--cc',default='cc');args=parser.parse_args()
    try:print(json.dumps(inspect(args.source_root,args.sboot,cc=args.cc),indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError) as exc:parser.exit(2,f'inspect_flop_acpm_reference: {exc}\n')
