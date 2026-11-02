#!/usr/bin/env python3
"""Re-run pinned modpost on final modules; never repair or load a module."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile

from capture_a0_formats import digest, layout, require
from capture_a0_modules import cpio, gunzip
from capture_a0_module_policy import module, symvers
from capture_a0_stack_versions import HELPERS, coverage_delta, offsets, stack_sites, version_rows
from check_capture_a0 import PINS, source_members, verify_file

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('scripts/mod/modpost.c','scripts/mod/modpost.h','scripts/mod/file2alias.c',
    'scripts/mod/sumversion.c','scripts/mod/mk_elfconfig.c','scripts/mod/devicetable-offsets.c',
    'include/linux/license.h','include/linux/mod_devicetable.h','include/linux/kbuild.h',
    'scripts/Makefile.modpost','scripts/Makefile.modfinal','scripts/module-lto.lds',
    'drivers/mfd/s2mpb02-irq.c')
TYPES = '''typedef unsigned long kernel_ulong_t;
typedef unsigned int __u32;
typedef unsigned short __u16;
typedef unsigned char __u8;
typedef struct {__u8 b[16];} guid_t;
typedef struct {__u8 b[16];} uuid_le;
typedef struct {__u8 b[16];} uuid_t;
#define UUID_STRING_LEN 36
#define BITS_PER_LONG 64
#define offsetof(t,f) __builtin_offsetof(t,f)
'''
LIBCPP = dict(bytes=1233936, sha256='b0157c4eccf705a00528728b4dc4797b56ac10d43829114cd3002dde763e7ccc')


def inspect(source, vendor, artifacts, clang_dir, out):
    pins = json.loads(PINS.read_text())
    build_pins = json.loads((PINS.parent/'capture-a0-build-pins-hzc2.json').read_text())
    artifact_pin = json.loads((PINS.parent/'capture-a0-crc-trace-validation-20261102.json').read_text())['reference_artifacts']
    reference = json.loads((PINS.parent/'capture-a0-module-policy-hzc2.json').read_text())
    require(not out.exists(), 'output directory must be new')
    require(platform.machine() == 'x86_64', 'native modpost probe requires x86_64 host')
    for path, pin in ((source,pins['samsung_source_archive']),
                      (vendor,pins['stock_raw']['vendor_boot.img']),(artifacts,artifact_pin),
                      (clang_dir/'bin/clang.real',build_pins['clang']['executables']['clang.real']),
                      (clang_dir/'lib64/libc++.so.1',LIBCPP)):
        verify_file(path, pin)
    members = source_members(source, SOURCES)
    source_text = members['scripts/Makefile.modpost'].decode()
    require('modpost-ext = $(if $(CONFIG_LTO_CLANG),.lto,)' in source_text
            and "sed 's/\\.ko$$/$(modpost-ext)\\.o/'" in source_text
            and '$(MAKE) -f $(srctree)/scripts/Makefile.modfinal' in source_text,
            'source stage order differs')
    rows = {label:next(m for m in reference['sets'][label]['module_metadata']
                      if m['name']=='s2mpb02_mfd') for label in ('stock','candidate')}
    image = vendor.read_bytes(); inv = layout(image)
    require(inv['avb'] and inv['avb']['all_hashes_match'], 'stock image hashes differ')
    part = next(p for p in inv['parts'] if p['name']=='ramdisk')
    entries = cpio(gunzip(image[part['start']:part['end']]))
    data = {'stock':entries[rows['stock']['path']]['data']}; symtext = None
    with tarfile.open(artifacts,'r|gz') as archive:
        for m in archive:
            if m.name not in (rows['candidate']['path'],'Module.symvers'):
                continue
            require(m.isfile() and m.size <= 16*1024*1024, 'selected artifact type/bound')
            if m.name == 'Module.symvers':
                require(symtext is None, 'duplicate symvers'); symtext = archive.extractfile(m).read().decode()
            else:
                require('candidate' not in data, 'duplicate candidate'); data['candidate']=archive.extractfile(m).read()
    require(set(data)=={'stock','candidate'} and symtext, 'selected artifacts missing')
    require(all(digest(d)==rows[label]['sha256'] for label,d in data.items()), 'module hash differs')
    exports = symvers(symtext)
    # Only the verified copies below are passed to modpost, which writes .mod.c.
    out.mkdir(parents=True); src = out/'source'; work = out/'probe'; work.mkdir()
    for name, content in members.items():
        p = src/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(content)
    mod = src/'scripts/mod'; (mod/'probe-types.h').write_text(TYPES)
    env = dict(PATH=os.defpath, LC_ALL='C')
    clang_env = dict(env, LD_LIBRARY_PATH=str(clang_dir/'lib64'))
    stages = {}
    def run(name,args,custom_env=None,stdin=None):
        result = subprocess.run(list(map(str,args)),env=custom_env or env,input=stdin,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        require(len(result.stdout)+len(result.stderr)<=2*1024*1024, 'native output bound')
        (out/(name+'.stdout')).write_bytes(result.stdout)
        (out/(name+'.stderr')).write_bytes(result.stderr)
        diagnostics = result.stderr.decode().replace(str(out), '<WORK>')
        stages[name] = dict(returncode=result.returncode,stdout_sha256=digest(result.stdout),
            normalized_stderr_sha256=digest(diagnostics.encode()),
            warning_count=diagnostics.count('WARNING:'),normalized_diagnostics=diagnostics)
        require(result.returncode==0, 'native stage failed: '+name)
        return result.stdout
    clang = clang_dir/'bin/clang.real'
    version = run('clang-version',[clang,'--version'],clang_env).decode().splitlines()[0]
    host_version = run('host-version',['cc','--version']).decode().splitlines()[0]
    run('target-offsets',[clang,'--target=aarch64-linux-gnu','-ffreestanding','-nostdinc',
        '-I',src/'include','-include',mod/'probe-types.h','-S',mod/'devicetable-offsets.c',
        '-o',mod/'devicetable-offsets.s'],clang_env)
    header = offsets((mod/'devicetable-offsets.s').read_text())
    (mod/'devicetable-offsets.h').write_text(header)
    run('build-elfconfig',['cc','-O2',mod/'mk_elfconfig.c','-o',mod/'mk_elfconfig'])
    elfconfig = run('elfconfig',[mod/'mk_elfconfig'],stdin=data['candidate'])
    (mod/'elfconfig.h').write_bytes(elfconfig)
    run('build-modpost',['cc','-O2',*[mod/n for n in ('modpost.c','file2alias.c','sumversion.c')],
                         '-o',mod/'modpost'])
    (work/'Module.symvers').write_text(symtext); results = {}
    for label, content in data.items():
        path = work/(label+'.o'); path.write_bytes(content)
        original = module(content)
        run('modpost-'+label,[mod/'modpost','-m','-i',work/'Module.symvers',path])
        generated_source = path.with_suffix('.mod.c').read_text()
        generated = version_rows(generated_source); added = coverage_delta(original, generated)
        require(set(added)==HELPERS and all(added[n]==exports[n]['crc'] for n in HELPERS),
                'unexpected regeneration difference')
        require(path.read_bytes()==content, 'modpost modified its ELF input')
        results[label] = dict(module_sha256=digest(content),original_version_records=len(original['versions']),
            final_imports=len(original['imports']),generated_version_records=len(generated),
            generated_source_sha256=digest(generated_source.encode()),
            generated_version_rows=generated,added_rows=added,existing_rows_unchanged=True,
            elf_input_unchanged=True,stack_relocation_sites=stack_sites(content))
    return dict(schema='S21-CAPTURE-A0-STACK-VERSIONS-v1',source_archive_sha256=pins['samsung_source_archive']['sha256'],
        candidate_archive_sha256=artifact_pin['sha256'],vendor_boot_sha256=pins['stock_raw']['vendor_boot.img']['sha256'],
        source_members={n:dict(bytes=len(d),sha256=digest(d)) for n,d in members.items()},
        native_versions=dict(clang=version,host_cc=host_version),native_stages=stages,
        target_device_table_offset_definitions=len(header.splitlines()),
        auxiliary_type_prelude_sha256=digest(TYPES.encode()),
        clang_sha256=build_pins['clang']['executables']['clang.real']['sha256'],libcpp=LIBCPP,
        symvers_sha256=digest(symtext.encode()),sets=results,
        deliberate_modpost_helper_exemption_observed=False,
        preserved_pre_modpost_lto_objects_supplied=False,
        original_build_transition_reproduced=False,stock_build_cause_established=False,
        regenerated_source_compiled_into_modules=False,package_modified=False,
        module_abi_established=False,physical_action=False,a0_complete=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vendor-boot','candidate-artifacts','clang-dir','output-dir'):
        p.add_argument('--'+n,required=True,type=Path)
    a=p.parse_args()
    try:
        report=inspect(*[x.resolve() for x in (a.source,a.vendor_boot,a.candidate_artifacts,a.clang_dir,a.output_dir)])
        (a.output_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    except (OSError,ValueError,KeyError,tarfile.TarError,subprocess.TimeoutExpired) as exc:
        p.exit(1,'STACK VERSIONS REFUSED: '+str(exc)+'\n')
    print('MODPOST FINAL: both sets 35 -> 37 records; original transition unproven; A0 open')
    return 2


if __name__=='__main__': raise SystemExit(main())
