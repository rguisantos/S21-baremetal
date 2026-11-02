#!/usr/bin/env python3
"""Isolated p3s module build with snapshots around modpost and final linking."""
import argparse
import difflib
import json
import os
from pathlib import Path
import re
import tarfile

from capture_a0_build import directory_tree, profile
from capture_a0_formats import digest, require
from capture_a0_module_policy import module, symvers
from capture_a0_module_stages import analyze, imports, link_commands, patch_modpost, snapshot
from check_capture_a0 import PINS, verify_file
from check_capture_a0_build_profile import TREES, run

TARGET='drivers/mfd/s2mpb02_mfd'


def inspect(archive, artifacts, tools, host, work):
    require(not work.exists(), 'work directory must be new')
    for p in (archive,artifacts,tools,host,work):
        require(re.fullmatch(r'/[A-Za-z0-9_./-]+',str(p)), 'unsupported build path')
    pins=json.loads(PINS.read_text())
    apin=json.loads((PINS.parent/'capture-a0-crc-trace-validation-20261102.json').read_text())['reference_artifacts']
    verify_file(archive,pins['samsung_source_archive']);verify_file(artifacts,apin)
    trees={n:directory_tree(tools/n) for n in TREES}
    require(all(trees[n]['tree']==v for n,v in TREES.items()), 'toolchain tree differs')
    for n,pin in pins['toolchain']['executables'].items():verify_file(tools/'clang-r383902/bin'/n,pin)
    selected={}
    with tarfile.open(artifacts,'r|gz') as t:
        for m in t:
            if m.name not in ('.config','Module.symvers',TARGET+'.ko','build-report.json'):continue
            require(m.isfile() and m.size<=16*1024*1024 and m.name not in selected, 'reference member type/bound/duplicate')
            selected[m.name]=t.extractfile(m).read()
    require(len(selected)==4, 'reference artifacts missing')
    reference_report=json.loads(selected['build-report.json'])
    require(reference_report['full_build_completed'] and reference_report['final_config_unchanged'], 'reference build incomplete')
    require(digest(selected['.config'])==reference_report['final_profile']['generated_config_sha256']
            and digest(selected['Module.symvers'])==reference_report['candidate_comparison']['sha256'],
            'reference metadata differs')
    providers=symvers(selected['Module.symvers'].decode());reference=module(selected[TARGET+'.ko'])
    work.mkdir(parents=True);source=work/'source';source.mkdir();obj=work/'objects';obj.mkdir()
    logs=work/'logs';logs.mkdir();evidence=work/'evidence';evidence.mkdir()
    with tarfile.open(archive,'r:gz') as t:t.extractall(source,filter='data')
    (obj/'.config').write_bytes(selected['.config']);(work/'reference.symvers').write_bytes(selected['Module.symvers'])
    (evidence/'reference.config').write_bytes(selected['.config'])
    (evidence/'reference.symvers').write_bytes(selected['Module.symvers'])
    (evidence/'reference.ko').write_bytes(selected[TARGET+'.ko'])
    original=(source/'scripts/Makefile.modpost').read_bytes();patched=patch_modpost(original)
    patch=''.join(difflib.unified_diff(original.decode().splitlines(True),patched.decode().splitlines(True),
        fromfile='a/scripts/Makefile.modpost',tofile='b/scripts/Makefile.modpost'))
    (work/'modpost-flags.patch').write_text(patch)
    baseline=(source/'arch/arm64/configs/exynos2100-p3sxxx_defconfig').read_text()
    env=dict(PATH=':'.join([str(host/'usr/bin'),str(tools/'clang-r383902/bin'),
        str(tools/'aarch64-android49/bin'),str(tools/'arm-android49/bin'),os.defpath]),
        LC_ALL='C',ARCH='arm64',PLATFORM_VERSION='11',ANDROID_MAJOR_VERSION='r',
        SEC_BUILD_CONF_VENDOR_BUILD_OS='15',BISON_PKGDATADIR=str(host/'usr/share/bison'),
        M4=str(host/'usr/bin/m4'),LD_LIBRARY_PATH=':'.join([str(host/'usr/lib/x86_64-linux-gnu'),
        str(tools/'clang-r383902/lib64')]),KBUILD_BUILD_USER='s21-a0',KBUILD_BUILD_HOST='offline',
        KBUILD_BUILD_VERSION='1',KBUILD_BUILD_TIMESTAMP='Sun Nov 1 00:00:00 UTC 2026')
    common=['make','-C',str(source),'ARCH=arm64','LLVM=1','HOSTCC=gcc','HOSTCXX=g++',
        'CROSS_COMPILE='+str(tools/'aarch64-android49/bin/aarch64-linux-android-'),
        'CROSS_COMPILE_COMPAT='+str(tools/'arm-android49/bin/arm-linux-androideabi-'),
        'CLANG_TRIPLE=aarch64-linux-gnu-','HOSTCFLAGS=-I'+str(host/'usr/include'),
        'HOSTLDFLAGS=-L'+str(host/'usr/lib/x86_64-linux-gnu'),'O='+str(obj),'-j4','V=1']
    stages={};snapshots={};analyses={};finals={};prelinks={}
    def execute(name,args,cwd=None):
        result=run(args,env,logs/(name+'.log'),180,cwd=cwd)
        result['log_sha256']=digest((logs/(name+'.log')).read_bytes());stages[name]=result
        print(name,result['returncode'],flush=True)
        require(result['returncode']==0 and not result['timed_out'], 'native stage failed: '+name)
    def check_config():
        require((obj/'.config').read_bytes()==selected['.config'], 'candidate configuration changed')
        p=profile(baseline,(obj/'.config').read_text());require(p['critical_profile_preserved'], 'critical profile changed')
        return p
    for target in ('olddefconfig','prepare','scripts'):execute(target,common+[target])
    current_profile=check_config()
    # Use a fixed export table because this isolated build does not rebuild vmlinux.
    # Keep normal version generation; no -w, force, or synthetic CRC assignments.
    modpost=str(obj/'scripts/mod/modpost')+' -m -i '+str(work/'reference.symvers')+' -s -T -'
    for label in ('original','aligned'):
        if label=='aligned':
            (source/'scripts/Makefile.modpost').write_bytes(patched)
            for name in (TARGET+'.ko',TARGET+'.mod.o',TARGET+'.mod.c',
                         'drivers/mfd/.s2mpb02_mfd.ko.cmd','drivers/mfd/.s2mpb02_mfd.mod.o.cmd'):
                (obj/name).unlink(missing_ok=True)
        execute(label+'-pre',common+['MODPOST='+modpost,'KBUILD_MODPOST_NOFINAL=1',TARGET+'.ko'])
        snapshots[label+'-pre']=snapshot(obj,evidence/(label+'-pre'))
        pre=(obj/(TARGET+'.lto.o')).read_bytes();generated=(obj/(TARGET+'.mod.c')).read_text()
        prelinks[label]=imports(pre)
        execute(label+'-final',common+['MODPOST='+modpost,TARGET+'.ko'])
        snapshots[label+'-final']=snapshot(obj,evidence/(label+'-final'))
        require((obj/(TARGET+'.lto.o')).read_bytes()==pre and (obj/(TARGET+'.mod.c')).read_text()==generated,
                'prelink/version source changed during final phase')
        final=(obj/(TARGET+'.ko')).read_bytes();analyses[label]=analyze(pre,generated,final,providers)
        finals[label]=module(final);check_config()
    for name in ('s2mpb02-core.o','s2mpb02-irq.o','s2mpb02_mfd.o','s2mpb02_mfd.o.symversions'):
        path='drivers/mfd/'+name
        require(snapshots['original-pre'][path]==snapshots['aligned-pre'][path], 'input object changed between controls')
    # Independent control: same original archive and CRC script, only the ThinLTO limit added.
    control=work/'limit5.o'
    execute('limit5-control',[str(tools/'clang-r383902/bin/ld.lld'),'-r','-mllvm','-import-instr-limit=5',
        '-o',str(control),'-T',str(obj/(TARGET+'.o.symversions')),'--whole-archive',str(obj/(TARGET+'.o'))],cwd=obj)
    control_imports=imports(control.read_bytes());(evidence/'limit5.o').write_bytes(control.read_bytes())
    reference_parity={label:{key:finals[label][key]==reference[key] for key in ('imports','exports','depends','licenses','import_namespaces','vermagic')}
                      for label in finals}
    return dict(schema='S21-CAPTURE-A0-MODULE-STAGES-v1',source_archive_sha256=pins['samsung_source_archive']['sha256'],
        reference_archive_sha256=apin['sha256'],reference_module_sha256=digest(selected[TARGET+'.ko']),
        toolchain_trees=trees,profile=current_profile,stages=stages,snapshots=snapshots,analyses=analyses,
        source_patch=dict(before_sha256=digest(original),after_sha256=digest(patched),sha256=digest(patch.encode())),
        source_ir_objects_unchanged_between_controls=True,control_limit5_imports=control_imports,
        resolved_link_commands=link_commands(evidence,work),
        control_limit5_matches_aligned_prelink=control_imports==prelinks['aligned'],
        metadata_parity_with_PR80=reference_parity,
        final_text_equal_between_controls=analyses['original']['final_text_sha256']==analyses['aligned']['final_text_sha256'],
        original_isolated_gap_reproduced=analyses['original']['final_imports_without_versions']==['__stack_chk_fail','__stack_chk_guard'],
        aligned_isolated_crc_coverage_complete=analyses['aligned']['strict_final_crc_coverage'],
        original_full_kernel_build_reexecuted=False,stock_build_history_established=False,
        fixed_full_kernel_built=False,reference_module_set_modified=False,
        module_abi_established=False,physical_action=False,a0_complete=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','candidate-artifacts','toolchains','host-root','work-dir'):p.add_argument('--'+n,required=True,type=Path)
    a=p.parse_args()
    try:
        r=inspect(*[x.resolve() for x in (a.source,a.candidate_artifacts,a.toolchains,a.host_root,a.work_dir)])
        (a.work_dir/'report.json').write_text(json.dumps(r,indent=2)+'\n')
    except (OSError,ValueError,KeyError,tarfile.TarError) as exc:p.exit(1,'MODULE STAGES REFUSED: '+str(exc)+'\n')
    print('Original gap:',r['original_isolated_gap_reproduced'],'; aligned coverage:',r['aligned_isolated_crc_coverage_complete'],'; A0 open')
    return 2


if __name__=='__main__':raise SystemExit(main())
