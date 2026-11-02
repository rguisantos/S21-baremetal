#!/usr/bin/env python3
"""Audit every rebuilt module and compare stock/rebuilt sets against the new kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import struct
import tarfile

from capture_a0_aligned_build import completed_build, metadata_changes, phase_metadata
from capture_a0_build import patch_tui
from capture_a0_formats import digest, require, config_values
from capture_a0_module_policy import module, symvers, evaluate, MAX_MODULE
from capture_a0_module_stages import patch_modpost
from check_capture_a0 import PINS, verify_file, source_members
from check_capture_a0_module_policy import candidate_inputs, stock_inputs

SOURCES=('kernel/module.c','include/linux/license.h','include/linux/export.h',
    'scripts/mod/modpost.c','scripts/genksyms/genksyms.c','scripts/Makefile.modpost','drivers/misc/tui/Makefile')


def inspect(build, vendor, source, reference_artifacts, preserved_layout=False):
    pins=json.loads(PINS.read_text());verify_file(source,pins['samsung_source_archive'])
    members=source_members(source,SOURCES);source_identity={}
    for name,data in members.items():
        expected=patch_modpost(data) if name=='scripts/Makefile.modpost' else patch_tui(data) if name=='drivers/misc/tui/Makefile' else data
        actual=(build/'source'/name).read_bytes();require(actual==expected,'build source differs: '+name)
        source_identity[name]=dict(archive_sha256=digest(data),build_sha256=digest(actual))
    refpin=json.loads((PINS.parent/'capture-a0-crc-trace-validation-20261102.json').read_text())['reference_artifacts']
    old,_,oldtexts,_=candidate_inputs(reference_artifacts,refpin)
    report_bytes=(build/('build-report.json' if preserved_layout else 'report.json')).read_bytes();report=json.loads(report_bytes)
    require(report['source_archive_sha256']==pins['samsung_source_archive']['sha256'],'build source identity differs')
    obj=build if preserved_layout else build/'complete'
    config=(obj/'.config').read_bytes();export_bytes=(obj/'Module.symvers').read_bytes()
    p=completed_build(report,config,export_bytes,(build/'source/scripts/Makefile.modpost').read_bytes(),oldtexts['.config'].encode())
    with (obj/'vmlinux').open('rb') as f:vmlinux_hash=hashlib.file_digest(f,'sha256').hexdigest()
    require(vmlinux_hash==report['vmlinux_sha256'],'vmlinux changed after build')
    with (obj/'vmlinux').open('rb') as f:header=f.read(64)
    require(len(header)==64 and header[:7]==b'\x7fELF\x02\x01\x01'
            and struct.unpack_from('<HHI',header,16)==(3,183,1),'vmlinux ELF header differs')
    allrows=symvers(export_bytes.decode());kernel={n:{k:r[k] for k in ('crc','export','namespace')}
        for n,r in allrows.items() if r['provider']=='vmlinux'}
    modules={};inventory=[];phases={}
    for path in sorted(obj.rglob('*.ko')):
        size=path.lstat();require(stat.S_ISREG(size.st_mode) and size.st_size<=MAX_MODULE,'module type/size')
        raw=path.read_bytes();m=module(raw);name=m['name'];relative=str(path.relative_to(obj))
        require(name not in modules,'duplicate rebuilt module name');modules[name]=m
        expected={n:{k:r[k] for k in ('crc','export','namespace')} for n,r in allrows.items()
                  if r['provider']==relative[:-3]}
        require(expected==m['exports'],'module exports differ from final symvers: '+name)
        pre=path.with_suffix('.lto.o');generated=path.with_suffix('.mod.c')
        require(pre.is_file() and not pre.is_symlink() and pre.stat().st_size<=MAX_MODULE
                and generated.is_file() and not generated.is_symlink() and generated.stat().st_size<=128*1024,
                'module phase missing/unsupported: '+name)
        phases[name]=phase_metadata(pre.read_bytes(),generated.read_text(),m)
        inventory.append(dict(name=name,path=relative,bytes=m['bytes'],sha256=m['sha256'],
            imports=len(m['imports']),exports=len(m['exports']),version_records=len(m['versions'])))
    require(len(modules)==report['built_module_count'] and modules,'module count differs')
    stock,stock_paths,requested,load,loadhash,dephash=stock_inputs(vendor,pins)
    require(set(requested)<=modules.keys(),'rebuilt set lacks stock requested names')
    magic=sorted({m['vermagic'] for m in modules.values()});require(len(magic)==1,'rebuilt vermagic ambiguity')
    results={}
    for label,selected,names in [('stock274',stock,requested),('rebuilt274',modules,requested),('all_rebuilt',modules,sorted(modules))]:
        result=evaluate(selected,kernel,names,magic[0],config.decode())
        result.update(imports=sum(len(selected[n]['imports']) for n in names),
            exports=sum(len(selected[n]['exports']) for n in names),
            version_records=sum(len(selected[n]['versions']) for n in names),
            weak_imports=sum(sum(b=='weak' for b in selected[n]['imports'].values()) for n in names))
        results[label]={k:v for k,v in result.items() if k not in ('selected_names','dependencies')}
    phase_totals={k:sum(len(v[k]) for v in phases.values()) for k in ('imports_added_after_modpost',
        'prelink_imports_without_generated_version','final_imports_without_version','unused_version_records')}
    by_name={m['name']:m for m in inventory}
    return dict(schema='S21-CAPTURE-A0-ALIGNED-FULL-AUDIT-v1',build_report_sha256=digest(report_bytes),
        source_archive_sha256=pins['samsung_source_archive']['sha256'],source_identity=source_identity,
        reference_archive_sha256=refpin['sha256'],vendor_boot_sha256=pins['stock_raw']['vendor_boot.img']['sha256'],
        profile=p,export_sha256=digest(export_bytes),vmlinux_sha256=report['vmlinux_sha256'],
        vmlinux_header=dict(type='ET_DYN',machine='AArch64',entry=hex(struct.unpack_from('<Q',header,24)[0])),
        candidate_exports_verified_against_symvers=True,modules=inventory,module_phases=phases,
        phase_totals=phase_totals,changes_from_PR80=metadata_changes(old,modules),sets=results,
        kernel_build_settings={k:config_values(config.decode()).get(k) for k in (
            'CONFIG_MODULE_SIG','CONFIG_MODULE_ALLOW_MISSING_NAMESPACE_IMPORTS','CONFIG_CFI_CLANG','CONFIG_UH','CONFIG_RKP')},
        candidate_module_set=dict(status='proposed' if results['rebuilt274']['strict_plan_checks_passed'] else 'blocked',
            reference_set='rebuilt274',names=requested,modules_load_original=load,modules_load_sha256=loadhash,
            modules_dep_original_sha256=dephash,additional_names=sorted(modules.keys()-set(requested)),
            files=[dict(name=n,source=by_name[n]['path'],package_path=stock_paths[n],sha256=modules[n]['sha256']) for n in requested],
            package_modified=False,stock_module_set_modified=False),
        source_checks_are_runtime_loading=False,module_abi_established=False,signature_policy_verified=False,
        cfi_runtime_verified=False,physical_action=False,a0_complete=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('build-dir','vendor-boot','source','reference-artifacts','output'):
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--preserved-layout',action='store_true',help='read the unpacked artifact layout without rebuilding')
    a=p.parse_args()
    try:
        require(not a.output.exists(),'output must be new')
        r=inspect(*[x.resolve() for x in (a.build_dir,a.vendor_boot,a.source,a.reference_artifacts)],a.preserved_layout)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    except (OSError,ValueError,KeyError,tarfile.TarError) as exc:p.exit(1,'ALIGNED BUILD AUDIT REFUSED: '+str(exc)+'\n')
    print('Rebuilt selected plan:',r['sets']['rebuilt274']['strict_plan_checks_passed'],'; A0 remains open')
    return 2


if __name__=='__main__':raise SystemExit(main())
