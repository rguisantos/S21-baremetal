#!/usr/bin/env python3
"""Two offline investigations: copy-limit hypotheses and pre-init alignment.

All binary parsers consume the very immutable buffers checked by SHA-256.
No padding, new package, build, device operation or OEM decision is performed.
"""
import argparse
import ast
import fcntl
import io
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import tarfile

from capture_a0_copy import copy_checked
from capture_a0_formats import digest, ikconfig, layout, require
from capture_a0_inputs import checked_buffer, read_checked, select_members
from capture_a0_kallsyms import alignment_delta, compare_map, decode
from capture_a0_sizes import flat_image

ROOT = Path(__file__).resolve().parents[1]
BASE = 'b090537371f8d1d245e865c5b924f4ec3833a19b'
SIZES_BASE = '0a5c9ec91821cb0949f858ded38ae829a3a78568'
CUT = 25*1024*1024
MALI = 'drivers/gpu/arm/bv_r38p0/mali_kbase.ko'
SOURCES = ('scripts/kallsyms.c', 'kernel/kallsyms.c', 'arch/arm64/kernel/vmlinux.lds.S',
    'arch/arm64/include/asm/memory.h', 'arch/arm64/include/asm/kernel-pgtable.h',
    'arch/arm64/boot/Makefile', 'arch/arm64/kernel/image.h', 'arch/arm64/kernel/efi-header.S')


def integer_expression(node):
    """Recognize bounded integer arithmetic, without eval or executing code."""
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value if 0 <= node.value <= 2**40 else None
    if not isinstance(node, ast.BinOp): return None
    a, b = integer_expression(node.left), integer_expression(node.right)
    if a is None or b is None: return None
    if isinstance(node.op, ast.Mult): value = a*b
    elif isinstance(node.op, ast.Add): value = a+b
    elif isinstance(node.op, ast.Pow) and b <= 32: value = a**b
    elif isinstance(node.op, ast.LShift) and b <= 40: value = a<<b
    else: return None
    return value if value <= 2**40 else None


def boundary_hits(raw, python=False):
    text = raw.decode('utf-8'); result = set()
    pattern = r'26214400|26[,.]214[,.]400|0x0?1900000\b|25\s*MiB|25\s*\*\s*1024|25\s*<<\s*20'
    for n, line in enumerate(text.splitlines(), 1):
        if re.search(pattern, line, re.I): result.add(n)
    if python:
        for node in ast.walk(ast.parse(text)):
            if integer_expression(node) == CUT: result.add(node.lineno)
    return sorted(result)


def repository_scan(ref):
    names = subprocess.check_output(['git','ls-tree','-r','--name-only',ref,'scripts','.github','docs','worklog.md'], cwd=ROOT).decode().splitlines()
    rows = []; hits = []; records = []; record_hits = []; logs = []
    for name in names:
        if name.endswith('.log'): logs.append(name)
        if name == 'worklog.md' or (name.startswith('docs/') and 'capture-a0' in name and name.endswith(('.md','.json'))):
            raw = subprocess.check_output(['git','show',ref+':'+name], cwd=ROOT)
            records.append(dict(path=name,bytes=len(raw),sha256=digest(raw)))
            record_hits += [dict(path=name,line=n) for n in boundary_hits(raw)]
        if Path(name).suffix not in ('.py','.sh','.yml','.yaml'): continue
        raw = subprocess.check_output(['git','show',ref+':'+name], cwd=ROOT)
        require(len(raw) <= 4*1024*1024, 'script scan bound')
        rows.append(dict(path=name, bytes=len(raw), sha256=digest(raw)))
        for line in boundary_hits(raw, name.endswith('.py')): hits.append(dict(path=name,line=line))
    source = subprocess.check_output(['git','show',ref+':scripts/check_capture_a0_sizes.py'], cwd=ROOT)
    text = source.decode(); start = text.index('def extract_selected('); end = text.index('\n\ndef inspect(', start)
    return dict(commit=ref, files_scanned=len(rows), matches=hits,
        inventory_sha256=digest(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()),
        record_files_scanned=len(records),record_matches=record_hits,tracked_log_paths=logs,
        record_inventory_sha256=digest(json.dumps(records,sort_keys=True,separators=(',',':')).encode()),
        extractor_sha256=digest(source), extractor_function=text[start:end],
        negative_search_is_not_a_proof_about_unrecorded_tools=True)


def copy_probes(data, output):
    """Native copy from a sealed, verified input; a declared RLIMIT control.

    The full-size copies exclude an active 25 MiB limit for these operations,
    not limits or quotas on a different filesystem/process at the incident.
    """
    cp = shutil.which('cp'); require(cp is not None, 'GNU cp required')
    version = subprocess.check_output([cp,'--version'], env={**os.environ,'LC_ALL':'C'}).decode().splitlines()[0]
    require('GNU coreutils' in version, 'unsupported cp implementation')
    fd = os.memfd_create('a0-verified-input', os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(os.dup(fd), 'wb') as file:
            require(file.write(data) == len(data), 'memfd short write'); file.flush()
        # Linux UAPI: F_ADD_SEALS=1024+9, SEAL_SEAL/SHRINK/GROW/WRITE=1/2/4/8.
        # Some Python builds omit these names despite exposing memfd_create.
        fcntl.fcntl(fd, getattr(fcntl,'F_ADD_SEALS',1033), 1 | 2 | 4 | 8)
        require(os.pread(fd, len(data)+1, 0) == data, 'sealed source bytes differ')
        rows = []
        for restricted in (False, True):
            dest = output/('limited-copy' if restricted else 'native-copy')
            def limit_child():
                resource.setrlimit(resource.RLIMIT_FSIZE, (CUT,CUT))
                signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            run = subprocess.run([cp,'--reflink=never','--sparse=never','--','/proc/self/fd/'+str(fd),str(dest)],
                pass_fds=(fd,), preexec_fn=limit_child if restricted else None,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,env={**os.environ,'LC_ALL':'C'})
            expected = data[:CUT] if restricted else data
            pin = dict(bytes=len(expected),sha256=digest(expected)); consumed = read_checked(dest,pin)
            require((run.returncode != 0) if restricted else (run.returncode == 0), 'unexpected cp status')
            require(not restricted or b'File too large' in run.stdout, 'limit control failed for another reason')
            rows.append(dict(synthetic_limit=restricted, returncode=run.returncode, **pin,
                exceeds_25mib=len(consumed) > CUT, diagnostic=run.stdout.decode().strip()))
        dest = output/'python-stream-copy'
        with io.BytesIO(data) as source, dest.open('xb') as target: shutil.copyfileobj(source,target)
        pin = dict(bytes=len(data),sha256=digest(data)); read_checked(dest,pin)
        copied = copy_checked(io.BytesIO(data),output/'repository-copy',pin)
        # Consume the destination in this same checked buffer, rather than
        # claiming copy_checked by itself protects any future path reopening.
        read_checked(output/'repository-copy',pin)
        fs = os.statvfs(output)
        return dict(cp_version=version, native_trials=rows,
            python_stream_copy=pin, repository_copy_readback=copied['destination_readback_verified'],
            current_rlimit_fsize=list(resource.getrlimit(resource.RLIMIT_FSIZE)),
            current_free_bytes=fs.f_bavail*fs.f_frsize,
            current_filesystem_supports_full_module=True,
            historical_process_environment_known=False, quota_history_available=False,
            historical_writer_identified=False,
            injected_limit_is_not_a_reproduction_of_the_historical_process=True)
    finally: os.close(fd)


def inspect(stock_path, archive_path, source_path, output):
    require(not output.exists(), 'output directory must be new')
    pins = json.loads((ROOT/'docs/references/capture-a0-pins-hzc2.json').read_text())
    old = json.loads((ROOT/'docs/references/capture-a0-aligned-full-validation-20261102.json').read_text())
    archive = read_checked(archive_path,old['reference_artifacts'])
    selected, manifest = select_members(archive,('vmlinux','System.map','.config',MALI),manifest=True)
    require(digest(manifest) == 'dc9fa0410b3dc211f47e2c94cae4af0d6607041b5443b657bf2b32172a7ebcbf', 'manifest identity differs')
    del archive
    source = read_checked(source_path,pins['samsung_source_archive'])
    members, _ = select_members(source,SOURCES,source_tree=True); del source
    stock = read_checked(stock_path,pins['stock_raw']['boot.img']); parts = layout(stock)['parts']
    kernel = next(p for p in parts if p['name'] == 'kernel'); stock_image = stock[kernel['start']:kernel['end']]; del stock
    image, mapping = flat_image(selected['vmlinux'])
    require(digest(image) == '9614f9a0ec8e83177ccb2010a585a128fd11f028cb46c417f2c1dbed2c2fd571', 'candidate Image differs')
    configs = (ikconfig(stock_image),selected['.config'])
    for config in configs:
        require(b'CONFIG_KALLSYMS_BASE_RELATIVE=y\n' in config and b'CONFIG_ARM64_4K_PAGES=y\n' in config
            and b'# CONFIG_DEBUG_ALIGN_RODATA is not set\n' in config
            and b'CONFIG_KALLSYMS_ABSOLUTE_PERCPU=y' not in config, 'unsupported config profile')
    require(b'. = ALIGN(SEGMENT_ALIGN);\n\t__init_begin' in members['arch/arm64/kernel/vmlinux.lds.S']
        and b'#define SEGMENT_ALIGN\t\tSZ_64K' in members['arch/arm64/include/asm/memory.h']
        and next(line.partition(b':=')[2].split() for line in members['arch/arm64/boot/Makefile'].splitlines()
            if line.startswith(b'OBJCOPYFLAGS_Image')) == b'-O binary -R .note -R .note.gnu.build-id -R .comment -S'.split(),
        'source alignment/Image recipe differs')
    result = alignment_delta(stock_image,image); rows, _ = decode(image)
    result['candidate_system_map_check'] = compare_map(rows,selected['System.map'])
    result['candidate_file_backed_sections'] = mapping['sections']
    result['candidate_image'] = dict(bytes=len(image),sha256=digest(image))
    result['stock_image'] = dict(bytes=len(stock_image),sha256=digest(stock_image))
    result['config_sha256'] = dict(stock=digest(configs[0]),candidate=digest(configs[1]))
    result['source_members'] = {n:dict(bytes=len(b),sha256=digest(b)) for n,b in members.items()}
    result['stock_build_recipe_available'] = False
    output.mkdir(parents=True); probes = copy_probes(selected[MALI],output)
    copy = dict(schema='S21-A0-COPY-ORIGIN-INVESTIGATION-v1',base=BASE,
        scans=[repository_scan(SIZES_BASE),repository_scan(BASE)],probes=probes,
        historical_bad_copy_available=(ROOT/'build/capture-a0-sizes-final/candidate/mali_kbase.ko').exists(),
        historical_log_available=(ROOT/'build/capture-a0-sizes-final/strip-103.log').exists(),
        historical_writer_audit_available=False,
        conclusion='not identified; current copy limits tested, historical conditions unknown')
    common = dict(archive=dict(bytes=old['reference_artifacts']['bytes'],sha256=old['reference_artifacts']['sha256'],
        manifest_sha256=digest(manifest), selected_members_verified=len(selected),
        per_payload_2133_verification_repeated=False),
        inputs_checked_and_processed_in_same_immutable_buffers=True,
        implementation_sha256={n:digest(Path(__file__).with_name(n).read_bytes()) for n in
            ('capture_a0_inputs.py','capture_a0_kallsyms.py','check_capture_a0_handoff.py')},
        new_pipeline_does_not_certify_other_consumers=True,source_archive_sha256=pins['samsung_source_archive']['sha256'],
        a0_complete=False,a1_implemented=False,physical_action=False,padding_applied=False,geometry_changed=False,
        user_independent_verification_completed=False)
    result.update(schema='S21-A0-IMAGE-PRODUCER-INVESTIGATION-v1',base=BASE,
        conclusion='alignment mechanism accounted; upstream option/object/function not identified')
    return {name:{**report,**common} for name,report in (('copy-origin',copy),('image-producer',result))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('stock-boot','candidate-artifacts','source','output-dir'): p.add_argument('--'+n,required=True,type=Path)
    a = p.parse_args()
    try:
        reports = inspect(a.stock_boot,a.candidate_artifacts,a.source,a.output_dir)
        for name,report in reports.items(): (a.output_dir/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    except (OSError,ValueError,KeyError,StopIteration,tarfile.TarError,subprocess.SubprocessError) as error:
        p.exit(1,'A0 HANDOFF REFUSED: '+str(error)+'\n')
    print('Investigations complete: alignment mechanism accounted; historical copy writer and upstream build cause unknown; A0 open')
    return 2


if __name__ == '__main__': raise SystemExit(main())
