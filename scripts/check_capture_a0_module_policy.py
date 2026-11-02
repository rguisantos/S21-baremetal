#!/usr/bin/env python3
"""Compare pinned stock/candidate module sets without changing either package."""
import argparse
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile

from capture_a0_formats import digest,layout,require,config_values
from capture_a0_modules import cpio,gunzip
from capture_a0_module_policy import module,symvers,evaluate,GPL
from check_capture_a0 import PINS,verify_file,source_members

ROOT=Path(__file__).resolve().parents[1]
VALIDATION=ROOT/'docs/references/capture-a0-crc-trace-validation-20261102.json'
SOURCE_NAMES=('kernel/module.c','include/linux/license.h','include/linux/vermagic.h',
              'include/linux/export.h','scripts/genksyms/genksyms.c','scripts/mod/modpost.c')


def candidate_inputs(path,pin):
    verify_file(path,pin);manifest=None
    with tarfile.open(path,'r|gz') as t:
        for m in t:
            if m.name=='manifest.json':
                require(manifest is None and m.isfile() and m.size<=2*1024*1024,'manifest format')
                manifest=json.load(t.extractfile(m))
    require(manifest and manifest['schema']=='S21-CANDIDATE-ARTIFACTS-v1','artifact manifest missing')
    modules={};paths={};texts={};seen=set()
    with tarfile.open(path,'r|gz') as t:
        for m in t:
            p=PurePosixPath(m.name)
            require(p.parts and not p.is_absolute() and '..' not in p.parts and str(p)==m.name
                    and m.name not in seen,'artifact member path/duplicate');seen.add(m.name)
            if not (m.name.endswith('.ko') or m.name in ('Module.symvers','.config','build-report.json')):continue
            require(m.isfile() and m.name in manifest['files'] and m.size<=128*1024*1024,'artifact member type/bound')
            data=t.extractfile(m).read();entry=manifest['files'][m.name]
            require(len(data)==entry['bytes'] and digest(data)==entry['sha256'],'artifact member hash')
            if m.name.endswith('.ko'):
                parsed=module(data);name=parsed['name'];require(name not in modules,'candidate module duplicate')
                modules[name]=parsed;paths[name]=m.name
            else:texts[m.name]=data.decode()
    require(set(texts)=={'Module.symvers','.config','build-report.json'},'candidate metadata missing')
    report=json.loads(texts['build-report.json'])
    require(report['full_build_completed'] and report['final_profile']['critical_profile_preserved']
            and report['final_config_unchanged'],'candidate build profile not demonstrated')
    require(digest(texts['.config'].encode())==report['final_profile']['generated_config_sha256']
            and digest(texts['Module.symvers'].encode())==report['candidate_comparison']['sha256'],
            'candidate metadata/build report mismatch')
    return modules,paths,texts,manifest


def stock_inputs(path,pins):
    verify_file(path,pins['stock_raw']['vendor_boot.img']);data=path.read_bytes();inv=layout(data)
    require(inv['kind']=='vendor_boot_v3' and inv['avb'] and inv['avb']['all_hashes_match'],'stock container integrity')
    part=next(p for p in inv['parts'] if p['name']=='ramdisk');entries=cpio(gunzip(data[part['start']:part['end']]))
    def regular(name):
        require(name in entries and entries[name]['kind']==stat.S_IFREG,'stock entry type')
        return entries[name]['data']
    stock={};paths={};filenames={}
    for path in sorted(entries):
        if not path.endswith('.ko'):continue
        require(path.startswith('lib/modules/') and path.count('/')==2,'stock module path')
        row=module(regular(path));name=row['name'];require(name not in stock,'stock module duplicate')
        stock[name]=row;paths[name]=path;filenames[path.split('/')[-1]]=name
    load=regular('lib/modules/modules.load');listed=load.decode().splitlines()
    require(listed and len(listed)==len(set(listed)) and set(listed)==set(filenames),'stock requested set')
    dep=regular('lib/modules/modules.dep');deps={};known_paths=set(paths.values())
    for line in dep.decode().splitlines():
        name,sep,rest=line.partition(':')
        require(sep and name.startswith('/') and name[1:] in known_paths and name not in deps,
                'stock modules.dep format')
        deps[name]=rest.split()
        require(all(x.startswith('/') and x[1:] in known_paths for x in deps[name]),'stock modules.dep reference')
    require(len(deps)==len(stock),'stock modules.dep incomplete')
    return stock,paths,[filenames[n] for n in listed],listed,digest(load),digest(dep)


def inspect(vendor,archive,source):
    pins=json.loads(PINS.read_text());verify_file(source,pins['samsung_source_archive'])
    members=source_members(source,SOURCE_NAMES)
    import re
    require(set(re.findall(r'strcmp\(license, "([^"]+)"\) == 0',members['include/linux/license.h'].decode()))==GPL,
            'source GPL rules differ')
    require('amagic += strcspn(amagic, " ");' in members['kernel/module.c'].decode()
            and 'return strcmp(amagic, bmagic) == 0;' in members['kernel/module.c'].decode(),
            'source vermagic rule differs')
    ref=json.loads(VALIDATION.read_text());cand,cpaths,texts,manifest=candidate_inputs(archive,ref['reference_artifacts'])
    require(manifest['source_archive_sha256']==pins['samsung_source_archive']['sha256'],'candidate source differs')
    stock,spaths,requested,load,loadhash,dephash=stock_inputs(vendor,pins)
    allrows=symvers(texts['Module.symvers']);kernel={n:{k:r[k] for k in ('crc','export','namespace')} for n,r in allrows.items() if r['provider']=='vmlinux'}
    magic=sorted({m['vermagic'] for m in cand.values()});require(len(magic)==1,'candidate vermagic ambiguity')
    require(set(requested)<=cand.keys(),'candidate lacks requested module')
    mismatches=[]
    for name,m in cand.items():
        provider=cpaths[name][:-3]
        expected={n:{k:r[k] for k in ('crc','export','namespace')} for n,r in allrows.items() if r['provider']==provider}
        if expected!=m['exports']:mismatches.append(name)
    require(not mismatches,'candidate exports differ from final Module.symvers: '+','.join(mismatches))
    evaluated={label:evaluate(mods,kernel,requested,magic[0],texts['.config']) for label,mods in [('stock',stock),('candidate',cand)]}
    parity={key:sorted(n for n in requested if stock[n][key]!=cand[n][key])
            for key in ('imports','exports','versions','depends','licenses','import_namespaces')}
    summaries={}
    for label,m in [('stock',stock),('candidate',cand)]:
        full=evaluated[label];summaries[label]={k:v for k,v in full.items() if k not in ('selected_names','dependencies','dependency_order')}
        summaries[label].update(imports=sum(len(m[n]['imports']) for n in requested),
            weak_imports=sum(sum(v=='weak' for v in m[n]['imports'].values()) for n in requested),
            exports=sum(len(m[n]['exports']) for n in requested),
            version_records=sum(len(m[n]['versions']) for n in requested),
            dependency_edges=sum(map(len,full['dependencies'].values())),
            dependency_graph_sha256=digest(json.dumps(full['dependencies'],sort_keys=True).encode()),
            module_metadata=[dict(name=n,path=(spaths if label=='stock' else cpaths)[n],sha256=m[n]['sha256'],
                licenses=sorted(set(m[n]['licenses'])),import_namespaces=m[n]['import_namespaces']) for n in requested])
    reference=evaluated['stock'];valid=reference['modeled_source_checks_passed'] and all(
        b[1]=='crc_coverage_not_established' for b in reference['plan_blocks'])
    plan=dict(status='proposed_with_version_gaps' if valid else 'blocked',
        reference_set='stock_vendor_ramdisk',kernel='candidate_from_PR80',
        requested_names=requested,modules_load_original=load,modules_load_sha256=loadhash,
        modules_dep_sha256=dephash,dependency_order_for_audit=reference['dependency_order'],
        dependency_order_is_boot_validation=False,package_modified=False,
        additional_candidate_modules=sorted(cand.keys()-set(requested)),
        alternative_candidate_set_names=requested)
    return dict(schema='S21-CAPTURE-A0-MODULE-POLICY-v1',source_archive_sha256=pins['samsung_source_archive']['sha256'],
        source_members={n:dict(bytes=len(data),sha256=digest(data)) for n,data in members.items()},
        candidate_archive_sha256=ref['reference_artifacts']['sha256'],vendor_boot_sha256=pins['stock_raw']['vendor_boot.img']['sha256'],
        kernel_vermagic_reference_from_same_build_modules=magic[0],
        kernel_modversions=config_values(texts['.config'])['CONFIG_MODVERSIONS'],
        kernel_build_settings={k:config_values(texts['.config']).get(k) for k in ('CONFIG_MODULE_SIG',
            'CONFIG_MODULE_ALLOW_MISSING_NAMESPACE_IMPORTS','CONFIG_CFI_CLANG','CONFIG_UH','CONFIG_RKP')},
        stock_vermagic_values=sorted({m['vermagic'] for m in stock.values()}),
        candidate_exports_verified_against_symvers=True,selected_metadata_differences=parity,
        sets=summaries,proposed_plan=plan,
        module_abi_established=False,signature_policy_verified=False,cfi_runtime_verified=False,
        physical_action=False,a0_complete=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('vendor-boot','candidate-artifacts','source','output'):p.add_argument('--'+n,required=True,type=Path)
    a=p.parse_args()
    try:
        require(not a.output.exists(),'output must be new')
        r=inspect(a.vendor_boot,a.candidate_artifacts,a.source)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    except (OSError,ValueError,KeyError,tarfile.TarError) as exc:p.exit(1,'MODULE PLAN REFUSED: '+str(exc)+'\n')
    print('Reference plan:',r['proposed_plan']['status'],'; A0 remains open')
    return 2


if __name__=='__main__':raise SystemExit(main())
