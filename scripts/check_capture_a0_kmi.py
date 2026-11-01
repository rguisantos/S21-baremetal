#!/usr/bin/env python3
"""Audit the two stock KMI config differences in the pinned Samsung source.

Runs isolated host fixtures, never a kernel/module build or phone operation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile

from capture_a0_formats import config_values, digest, require

ARCHIVE_SHA = 'c5ad9994240e67ebdc40878c191be040bf30db398bc8513ea1f156eaebd86bf2'
CONFIG_SHA = '55dde3bb7c52e99eccdb82b925a4b831c03fd32a19a2b64bdf7bda993e92a2e1'
RAW = 'gki/abi_symbollist.raw'
CORE = ('init/Kconfig', 'Makefile', 'scripts/gen_autoksyms.sh',
        'scripts/adjust_autoksyms.sh', 'include/linux/export.h',
        'include/linux/kconfig.h', 'scripts/Makefile.build',
        'scripts/Makefile.modpost', 'scripts/mod/modpost.c',
        'kernel/module.c', 'build.config.universal2100_r', RAW)
TOKENS = ('KMI_SYMBOL_LISTS', 'UNUSED_KSYMS_WHITELIST')
PATTERNS = {key: re.compile(rb'(?<![A-Za-z0-9_])(?:CONFIG_)?'+key.encode()+
                          rb'(?![A-Za-z0-9_])') for key in TOKENS}


def list_paths(value):
    decoded = json.loads(value)
    require(isinstance(decoded, str), 'KMI list setting must be a string')
    paths = decoded.split()
    require(0 < len(paths) <= 64 and len(paths) == len(set(paths)), 'KMI list count/duplicates')
    for name in paths:
        require(bool(re.fullmatch(r'[A-Za-z0-9_./-]{1,256}', name)), 'unsafe KMI list name')
        path = PurePosixPath(name)
        require(bool(path.parts) and not path.is_absolute() and '..' not in path.parts and str(path) == name,
                'KMI list path is not canonical and relative')
    return paths


def symbols(data, sections=False):
    result = set()
    for line in data.decode('utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or sections and line == '[abi_symbol_list]':
            continue
        require(bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', line)), 'unsupported symbol-list syntax')
        result.add(line)
    return result


def scan_stream(archive, wanted):
    """No filesystem extraction or link following; fail on an incomplete census."""
    found = {}; hits = {k: [] for k in TOKENS}; links = {}; seen = set()
    regular = total = directories = symlinks = 0
    for member in archive:
        name = member.name.removeprefix('./')
        require(name not in seen, 'duplicate archive path')
        seen.add(name)
        require(len(seen) <= 100000, 'archive member budget exceeded')
        if not member.isfile():
            if member.isdir(): directories += 1
            elif member.issym(): symlinks += 1
            else: raise ValueError('unsupported non-regular archive member')
            if name in wanted: links[name] = member.linkname
            continue
        require(0 <= member.size <= 32*1024*1024, 'member exceeds complete-census bound')
        regular += 1; total += member.size
        require(total <= 2*1024**3, 'archive byte budget exceeded')
        data = archive.extractfile(member).read()
        require(len(data) == member.size, 'short source member')
        for key, pattern in PATTERNS.items():
            if pattern.search(data):
                hits[key].extend(dict(file=name, line=i) for i, line in
                                 enumerate(data.splitlines(), 1) if pattern.search(line))
                require(len(hits[key]) <= 1000, 'identifier hit budget exceeded')
        if name in wanted: found[name] = data
    return found, dict(regular_members=regular, regular_bytes=total,
                      directories=directories, symlinks_not_followed=symlinks,
                      skipped_regular_members=0, wanted_nonregular=links,
                      identifier_hits=hits)


def read_archive(path, wanted):
    with path.open('rb') as source:
        require(hashlib.file_digest(source, 'sha256').hexdigest() == ARCHIVE_SHA,
                'requires the exact Samsung source archive')
        source.seek(0)
        with tarfile.open(fileobj=source, mode='r|gz') as archive:
            return scan_stream(archive, wanted)


PROBE = '''#include <stddef.h>
#include <stdio.h>
#include <linux/kconfig.h>
#define __aligned(x) __attribute__((aligned(x)))
#define __section(x) __attribute__((section(x)))
#define __used __attribute__((used))
#include <linux/export.h>
struct observed { char tag; PAYLOAD_TYPE payload; };
int keep_symbol(struct observed *v) { return v->payload; }
int optional_symbol(struct observed *v) { return v->tag; }
EXPORT_SYMBOL(keep_symbol);
EXPORT_SYMBOL(optional_symbol);
int main(void) { printf("%zu %zu\\n", sizeof(struct observed), offsetof(struct observed, payload)); }
'''


def command(args, cwd, extra_env=None):
    env = dict(PATH=os.defpath, LC_ALL='C', **(extra_env or {}))
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=env,
                            capture_output=True, timeout=30)
    require(result.returncode == 0, 'isolated host probe failed: '+str(args[0]))
    return result.stdout


def probe_case(root, source, cc, nm, absolute=False, metadata='', trim=False,
               missing=False, changed_type=False):
    # The original generator evaluates a shell-sourced string. Refuse shell
    # metacharacters even in our scratch path, before writing any fixture.
    require(bool(re.fullmatch(r'/[A-Za-z0-9_./-]+', str(root))), 'unsafe host fixture path')
    require(bool(re.fullmatch(r'[A-Za-z0-9_./ -]*', metadata)), 'unsafe fixture metadata')
    for directory in ('include/config', 'include/generated', 'include/linux', 'gki'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for name in ('export.h', 'kconfig.h'):
        shutil.copyfile(source / 'include/linux' / name, root / 'include/linux' / name)
    (root / 'gki/list').write_text('keep_symbol\n'+('' if trim else 'optional_symbol\n'))
    (root / 'modules.order').write_text('fixture.ko\n')
    (root / 'fixture.mod').write_text('fixture.o\nmodule_required\n')
    whitelist = str(root / 'gki/list') if absolute else 'gki/list'
    if missing: whitelist = 'gki/missing'
    values = dict(UNUSED_KSYMS_WHITELIST=whitelist, KMI_SYMBOL_LISTS=metadata)
    # Only our own inert fixture values enter the shell-sourced auto.conf.
    (root / 'include/config/auto.conf').write_text('CONFIG_MODVERSIONS=y\n'+''.join(
        'CONFIG_'+key+'='+json.dumps(value)+'\n' for key, value in values.items()))
    (root / 'include/generated/autoconf.h').write_text(
        '#define CONFIG_MODULES 1\n#define CONFIG_TRIM_UNUSED_KSYMS 1\n#define CONFIG_MODVERSIONS 1\n'+
        ''.join('#define CONFIG_'+key+' '+json.dumps(value)+'\n' for key, value in values.items()))
    target = root / 'include/generated/autoksyms.h'
    invocation = ['/bin/sh', str(source / 'scripts/gen_autoksyms.sh'), str(target)]
    env = dict(PATH=os.defpath, LC_ALL='C', abs_srctree=str(root))
    generated = subprocess.run(invocation, cwd=root, env=env, capture_output=True, timeout=30)
    if missing:
        require(generated.returncode == 1 and not target.exists(), 'missing whitelist was not refused')
        return dict(missing_whitelist_refused=True)
    require(generated.returncode == 0, 'autoksyms generation failed')
    code = PROBE.replace('PAYLOAD_TYPE', 'unsigned int' if changed_type else 'unsigned long')
    (root / 'probe.c').write_text(code)
    command([cc, '-std=gnu11', '-O0', '-fno-pie', '-no-pie', '-I'+str(root / 'include'),
             root / 'probe.c', '-o', root / 'probe'], root)
    measurements = [int(n) for n in command([root / 'probe'], root).split()]
    require(len(measurements) == 2, 'fixture layout output differs')
    names = command([nm, '--defined-only', root / 'probe'], root).decode().splitlines()
    exports = sorted(line.split()[-1] for line in names
                     if line.strip() and line.split()[-1].startswith('__ksymtab_'))
    header = target.read_bytes()
    return dict(autoksyms_sha256=digest(header), fixture_size=measurements[0],
        fixture_payload_offset=measurements[1], exports=exports,
        module_layout_kept=b'#define __KSYM_module_layout 1\n' in header,
        module_import_kept=b'#define __KSYM_module_required 1\n' in header)


def probes(members, output, cc, nm):
    source = output / 'source'
    for name in ('scripts/gen_autoksyms.sh', 'include/linux/export.h', 'include/linux/kconfig.h'):
        target = source / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(members[name])
    cases = dict(relative={}, absolute=dict(absolute=True),
        metadata_only=dict(metadata='different-kmi-input'), trimmed=dict(trim=True),
        missing=dict(missing=True), type_change=dict(changed_type=True))
    rows = {name: probe_case(output / name, source, cc, nm, **options)
            for name, options in cases.items()}
    base = rows['relative']
    require(base == rows['absolute'] == rows['metadata_only'], 'equivalent-input probe changed')
    require(base['exports'] == ['__ksymtab_keep_symbol', '__ksymtab_optional_symbol'], 'base exports differ')
    require(rows['trimmed']['exports'] == ['__ksymtab_keep_symbol'], 'trim did not remove export')
    require((base['fixture_size'], base['fixture_payload_offset']) ==
            (rows['trimmed']['fixture_size'], rows['trimmed']['fixture_payload_offset']), 'trim changed fixture layout')
    require(rows['type_change']['fixture_size'] != base['fixture_size'], 'type-change positive control failed')
    require(all(row.get('module_layout_kept') and row.get('module_import_kept')
                for name, row in rows.items() if name != 'missing'), 'required symbols lost')
    return dict(cases=rows, compiler_version=command([cc, '--version'], output).decode().splitlines()[0],
        compiler_target=command([cc, '-dumpmachine'], output).decode().strip(),
        scope='isolated host fixture; non-PREL32 export branch; no p3s kernel build',
        crc_values_computed=False, real_kernel_struct_layouts_compared=False)


def inspect(archive, config_path, output, cc='cc', nm='nm'):
    config = config_path.read_bytes()
    require(digest(config) == CONFIG_SHA, 'requires the exact stock IKCONFIG')
    values = config_values(config.decode())
    paths = list_paths(values['CONFIG_KMI_SYMBOL_LISTS'])
    found, census = read_archive(archive, set(CORE) | set(paths))
    require(all(name in found for name in CORE), 'required build sources missing')
    require(not census['wanted_nonregular'], 'selected input is not a regular file')
    available = {name: symbols(found[name], sections=True) for name in paths if name in found}
    raw = symbols(found[RAW]); union = set().union(*available.values())
    missing = sorted(set(paths) - available.keys())
    output = output.resolve()
    require(bool(re.fullmatch(r'/[A-Za-z0-9_./-]+', str(output))), 'unsafe host fixture path')
    output.mkdir(parents=True, exist_ok=False)
    controls = probes(found, output, cc, nm)
    return dict(schema='S21-CAPTURE-A0-KMI-v1', source_archive_sha256=ARCHIVE_SHA,
        stock_ikconfig_sha256=CONFIG_SHA, stock_kmi_value_sha256=digest(values['CONFIG_KMI_SYMBOL_LISTS'].encode()),
        source_members={name: dict(bytes=len(data), sha256=digest(data)) for name, data in sorted(found.items())},
        census=census, stock_list_paths=paths, missing_list_inputs=missing,
        available_list_symbols={name: len(names) for name, names in available.items()},
        available_union_symbols=len(union), raw_whitelist_symbols=len(raw),
        raw_not_in_available_union=sorted(raw-union), available_union_not_in_raw=sorted(union-raw),
        kmi_inputs_accounted_for=not missing and raw == union,
        controls=controls, module_abi_established=False, a0_complete=False,
        final_elf_checked=False, physical_action=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--stock-config', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.source, args.stock_config, args.output_dir)
        (args.output_dir / 'report.json').write_text(json.dumps(result, indent=2)+'\n')
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        parser.exit(1, 'KMI ANALYSIS REFUSED: '+str(exc)+'\n')
    print('KMI analysis complete; missing list inputs:', len(result['missing_list_inputs']),
          '; module ABI not established; A0 open')
    return 0 if result['kmi_inputs_accounted_for'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
