#!/usr/bin/env python3
"""Verify preserved bytes, copy-prefix evidence and the ARM64/PE size delta.

No new kernel build, padding, package policy or physical operation. A header
layout explanation is distinct from identifying a compiler/configuration cause.
"""
import argparse
import hashlib
import io
import json
import mmap
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import time

from capture_a0_copy import MAX_COPY, copy_checked
from capture_a0_formats import digest, layout, require
from capture_a0_layout import explain_delta, prefix_evidence
from capture_a0_sizes import flat_image
from check_capture_a0 import PINS, source_members
from check_capture_a0_sizes import IMAGE_FLAGS, extract_selected, file_hash, module_input, verify

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('arch/arm64/kernel/head.S','arch/arm64/kernel/efi-header.S',
    'arch/arm64/kernel/vmlinux.lds.S','arch/arm64/kernel/image.h')


def unique_object(pairs):
    result = {}
    for key,value in pairs:
        require(key not in result,'duplicate manifest JSON key'); result[key] = value
    return result


def archive_inventory(path, pin):
    verify(path,pin); seen = set(); computed = {}; manifest = None; total = 0
    with tarfile.open(path,'r|gz') as archive:
        for member in archive:
            p = PurePosixPath(member.name)
            require(member.name not in seen and p.parts and not p.is_absolute() and '..' not in p.parts
                and str(p) == member.name and '\\' not in member.name and member.isfile()
                and 0 <= member.size <= MAX_COPY and len(seen) < 10000,'archive path/type/budget')
            seen.add(member.name)
            if member.name == 'manifest.json':
                require(member.size <= 2*1024*1024,'manifest size bound')
                raw = archive.extractfile(member).read(); manifest = json.loads(raw,object_pairs_hook=unique_object)
                manifest_hash = digest(raw); continue
            h = hashlib.sha256(); count = 0
            with archive.extractfile(member) as file:
                while chunk := file.read(1024*1024): count += len(chunk); h.update(chunk)
            total += count; require(count == member.size and total <= 2*1024**3,'archive extent/budget')
            computed[member.name] = dict(bytes=count,sha256=h.hexdigest())
    require(manifest and manifest.get('schema') == 'S21-CANDIDATE-ARTIFACTS-v1'
        and computed == manifest.get('files') and len(computed) == pin['files_verified'],'archive manifest contents differ')
    return dict(archive_bytes=pin['bytes'],archive_sha256=pin['sha256'],manifest_sha256=manifest_hash,
        payloads_verified=len(computed),members=len(seen),payload_bytes=total,failures=0,
        inventory_sha256=digest(json.dumps(computed,sort_keys=True,separators=(',',':')).encode()))


def inspect(stock_boot, archive, source, tools, output):
    require(not output.exists(),'output directory must be new')
    pins = json.loads(PINS.read_text()); old = json.loads((PINS.parent/'capture-a0-aligned-full-validation-20261102.json').read_text())
    archive_check = archive_inventory(archive,old['reference_artifacts'])
    verify(source,pins['samsung_source_archive']); verify(stock_boot,pins['stock_raw']['boot.img'])
    members = source_members(source,SOURCES)
    require('__initdata_begin - efi_header_end' in members[SOURCES[1]].decode()
        and '_end - _head' in members[SOURCES[1]].decode()
        and '_kernel_size_le' in members[SOURCES[0]].decode(), 'source header expressions differ')
    audit_path = PINS.parent/'capture-a0-aligned-full-audit-hzc2.json'
    require(file_hash(audit_path) == old['report_sha256'],'reference audit differs')
    audit = json.loads(audit_path.read_text()); by_name = {r['name']:r for r in audit['modules']}
    selected = [{**r,'bytes':by_name[r['name']]['bytes']} for r in audit['candidate_module_set']['files']]
    require(len(selected) == 274,'selected set differs')
    output = output.resolve(); output.mkdir(parents=True)
    candidate = output/'candidate'; candidate.mkdir()
    vpin = dict(bytes=437269784,sha256=old['native_build']['vmlinux_sha256'])
    copies = extract_selected(archive,selected,candidate,vpin)
    incident = json.loads((PINS.parent/'capture-a0-payload-sizes-validation-20261102.json').read_text())['refused_attempt']
    mali = next(r for r in selected if r['name'] == 'mali_kbase')
    module_path = candidate/'mali_kbase.ko'; data = module_input(module_path,mali)
    evidence = prefix_evidence(data,incident['observed_copy_bytes'],incident['observed_sha256'])
    require(evidence['recorded_hash_matches_prefix'] and not evidence['section_table_fits_prefix'],'incident prefix evidence differs')
    trials = []
    for name in ('copy-a.ko','copy-b.bin','copy-c.copy'):
        with module_path.open('rb') as file:
            trials.append(dict(name=name,copy=copy_checked(file,output/name,mali)))
    # A declared synthetic control recreates the recorded prefix, not a new
    # spontaneous occurrence or a kernel build. Never truncate the original.
    cut = output/'controlled-prefix.ko'
    copy_checked(io.BytesIO(data[:evidence['prefix_bytes']]),cut,
        dict(bytes=evidence['prefix_bytes'],sha256=evidence['prefix_sha256']))
    def native(name,args,label,success=True):
        binary = tools/'usr/bin'/('aarch64-linux-gnu-'+name)
        run = subprocess.run(['bash',str(ROOT/'scripts/cross-run.sh'),str(tools),str(binary),*map(str,args)],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env={**os.environ,'LC_ALL':'C'},timeout=60)
        (output/(label+'.log')).write_bytes(run.stdout)
        require((run.returncode == 0) == success,'unexpected native result: '+label)
        return run
    refused = native('strip',['--strip-debug','-o',output/'controlled-stripped.ko',cut],'controlled-prefix-strip',False)
    require(b'file format not recognized' in refused.stdout,'prefix control failed for another reason')
    verify(candidate/'vmlinux',vpin)
    native('objcopy',IMAGE_FLAGS+[candidate/'vmlinux',output/'Image'],'image-objcopy')
    verify(candidate/'vmlinux',vpin)
    image = (output/'Image').read_bytes()
    with (candidate/'vmlinux').open('rb') as file,mmap.mmap(file.fileno(),0,access=mmap.ACCESS_READ) as mapped:
        independent,_ = flat_image(mapped)
    require(image == independent,'independent Image mapping differs')
    stock = stock_boot.read_bytes(); inv = layout(stock)
    kernel = next(p for p in inv['parts'] if p['name'] == 'kernel')
    delta = explain_delta(stock[kernel['start']:kernel['end']],image)
    names = {'_head','_text','efi_header_end','__initdata_begin','_edata','_end','stext','__efistub_entry'}
    symbols = {}
    for line in native('nm',['--defined-only',candidate/'vmlinux'],'candidate-symbols').stdout.decode().splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[-1] in names:
            require(fields[-1] not in symbols,'ambiguous symbol'); symbols[fields[-1]] = int(fields[0],16)
    require(symbols.keys() == names,'linker boundary symbols missing'); base = symbols['_head']; pe = delta['candidate']
    require(symbols['_text'] == base and symbols['efi_header_end']-base == pe['headers_bytes']
        and symbols['__initdata_begin']-base == pe['sections']['.data']['file_offset']
        and symbols['_edata']-base == pe['mapped_file_end'] and symbols['_end']-base == pe['pe_runtime_bytes']
        and symbols['stext']-base == pe['primary_branch_target']
        and symbols['__efistub_entry']-base == pe['efi_entry_rva'],'ELF symbols and Image fields differ')
    time.sleep(2)
    for trial in trials:
        module_input(output/trial['name'],mali); trial['later_hash_check_passed'] = True
    versions = {n:dict(version=native(n,['--version'],n+'-version').stdout.decode().splitlines()[0],
        sha256=file_hash(tools/'usr/bin'/('aarch64-linux-gnu-'+n))) for n in ('objcopy','strip','nm')}
    return dict(schema='S21-CAPTURE-A0-LAYOUT-COPY-v1',source_base='0a5c9ec91821cb0949f858ded38ae829a3a78568',
        implementation_sha256={n:digest(Path(__file__).with_name(n).read_bytes()) for n in
            ('capture_a0_copy.py','capture_a0_layout.py','check_capture_a0_layout.py','check_capture_a0_sizes.py')},
        archive=archive_check,source_archive_sha256=pins['samsung_source_archive']['sha256'],
        stock_boot_sha256=pins['stock_raw']['boot.img']['sha256'],
        source_members={n:dict(bytes=len(b),sha256=digest(b)) for n,b in members.items()},
        selected_copy_readbacks_verified=len(copies),module_readback=copies[mali['source']],
        incident=evidence,copy_trials=trials,controlled_prefix=dict(synthetic=True,native_returncode=refused.returncode,
            original_unchanged=file_hash(module_path) == mali['sha256'],same_error_class_as_incident=True),
        historical_copy_available=(ROOT/'build/capture-a0-sizes-final/candidate/mali_kbase.ko').exists(),
        historical_log_available=(ROOT/'build/capture-a0-sizes-final/strip-103.log').exists(),
        historical_mutation_origin_identified=False,copy_trials_do_not_prove_historical_cause=True,
        layout=delta,candidate_symbols={n:hex(v) for n,v in sorted(symbols.items())},candidate_elf_symbol_binding_verified=True,
        tools=versions,producer_build_cause_identified=False,padding_applied=False,geometry_changed=False,
        signature_policy_verified=False,user_independent_verification_completed=False,
        a0_complete=False,a1_implemented=False,physical_action=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('stock-boot','candidate-artifacts','source','tools-root','output-dir'): p.add_argument('--'+name,required=True,type=Path)
    args = p.parse_args()
    try:
        r = inspect(*[x.resolve() for x in (args.stock_boot,args.candidate_artifacts,args.source,args.tools_root,args.output_dir)])
        (args.output_dir/'report.json').write_text(json.dumps(r,indent=2)+'\n')
    except (OSError,ValueError,KeyError,tarfile.TarError,subprocess.SubprocessError) as error: p.exit(1,'LAYOUT/COPY REFUSED: '+str(error)+'\n')
    print('Archive/prefix/copy/layout checks PASS; historical mutator and producer build cause remain open')
    return 2


if __name__ == '__main__': raise SystemExit(main())
