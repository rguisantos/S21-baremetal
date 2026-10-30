#!/usr/bin/env python3
"""Validate selected pinned Flop sources and compile only a host RPMB layout probe."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from inspect_rpmb_frame import LOCAL_FIELDS, wire_interval


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT/'docs/references/flop-kernel-source-4553117.json'
COMMIT = '4553117a5014928dff55595f46627e0d77bcf133'
REPOSITORY = 'FlopKernel-Series/flop_exynos2100_kernel'


def numeric_define(text, name):
    """Read literal integer defines only; duplicate identical values are allowed."""
    definitions = re.findall(r'^#define\s+'+re.escape(name)+r'\s+([^\n]+)$', text, re.M)
    if not definitions:
        raise ValueError(f'missing integer define: {name}')
    values = []
    for value in definitions:
        value = value.strip()
        if value.startswith('(') and value.endswith(')'):
            value = value[1:-1].strip()
        if not re.fullmatch(r'0[xX][0-9a-fA-F]+|0|[1-9][0-9]*', value):
            raise ValueError(f'nonliteral integer define: {name}')
        values.append(int(value, 16 if value.lower().startswith('0x') else 10))
    if len(set(values)) != 1:
        raise ValueError(f'conflicting integer defines: {name}')
    return values[0]


def packet_declaration(text):
    """Accept the audited fixed-width struct grammar, never arbitrary C text."""
    matches = list(re.finditer(r'struct\s+rpmb_packet\s*\{([^{}]*)\}\s*;', text))
    if len(matches) != 1:
        raise ValueError('one RPMB packet declaration required')
    fields = []
    for declaration in matches[0][1].split(';'):
        if not declaration.strip():
            continue
        match = re.fullmatch(r'\s*(u8|u16|u32)\s+([A-Za-z_]\w*)(?:\[([1-9][0-9]*)\])?\s*', declaration)
        if not match:
            raise ValueError('unsupported RPMB packet field')
        fields.append((match[2], match[1], int(match[3] or 1)))
    if len({f[0] for f in fields}) != len(fields) or not fields:
        raise ValueError('empty or duplicate RPMB packet fields')
    return matches[0][0], fields


def host_layout(declaration, fields, *, cc='cc'):
    # declaration has passed the narrow grammar and source hashes are checked
    # before this function is used by inspect(). This is a host ABI probe only.
    rows = ','.join('"'+name+'":{"offset":%zu,"bytes":%zu}' for name, _, _ in fields)
    args = ','.join(f'offsetof(struct rpmb_packet,{name}), sizeof(p.{name})' for name, _, _ in fields)
    code = ('#include <stdint.h>\n#include <stddef.h>\n#include <stdio.h>\n'
            'typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;\n'
            +declaration+'\nint main(void) { struct rpmb_packet p;\n'
            +'printf("{\\"bytes\\":%zu,\\"fields\\":{'+rows.replace('"', '\\"')
            +'}}\\n",sizeof(p),'+args+'); return 0; }\n')
    with tempfile.TemporaryDirectory(prefix='rpmb-layout-') as directory:
        source = Path(directory)/'layout.c'; binary = Path(directory)/'layout'
        source.write_text(code)
        subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)],
                       capture_output=True, text=True, check=True)
        result = json.loads(subprocess.check_output([str(binary)], text=True))
    expected = {name: dict(offset=offset, bytes=size) for name, offset, size in LOCAL_FIELDS}
    if result != dict(bytes=512, fields=expected):
        raise ValueError('host C layout differs from offline decoder')
    return result


def inspect(source_root, *, cc='cc'):
    manifest = json.loads(MANIFEST.read_text())
    if (manifest['commit'], manifest['repository']) != (COMMIT, REPOSITORY):
        raise ValueError('unexpected source manifest identity')
    texts = {}; metadata = []
    for row in manifest['files']:
        raw = (Path(source_root)/row['path']).read_bytes()
        blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if (len(raw), blob, hashlib.sha256(raw).hexdigest()) != (row['bytes'], row['blob_sha1'], row['sha256']):
            raise ValueError(f'source bytes differ: {row["path"]}')
        texts[row['path']] = raw.decode('utf-8')
        metadata.append(row)
    header = texts['drivers/scsi/scsi_srpmb.h']
    declaration, fields = packet_declaration(header)
    layout = host_layout(declaration, fields, cc=cc)
    constants = {name: numeric_define(header, name) for name in (
        'GET_WRITE_COUNTER', 'WRITE_DATA', 'READ_DATA', 'RESULT_READ_REQ',
        'RPMB_PACKET_SIZE', 'RPMB_REQRES', 'RPMB_RESULT', 'RPMB_IN_PROGRESS',
        'RPMB_PASSED', 'SCSI_IOCTL_SECURITY_PROTOCOL_IN', 'SCSI_IOCTL_SECURITY_PROTOCOL_OUT',
        'SECU_PROT_UFS', 'SECU_PROT_SPEC_CERT_DATA')}
    smc = texts['include/soc/samsung/exynos-smc.h']
    constants.update({name: numeric_define(smc, name) for name in ('SMC_SRPMB_WSM', 'SMC_CMD_RANDOM')})
    config = texts['arch/arm64/configs/exynos2100-unified_defconfig']
    symbols = ('ARCH_EXYNOS', 'UFS_SRPMB', 'SCSI_UFS_EXYNOS', 'SCSI_UFS_EXYNOS_SRPMB',
               'SERIAL_SAMSUNG', 'SERIAL_SAMSUNG_CONSOLE', 'ARM_PSCI_FW')
    selected_config = {}
    for name in symbols:
        matches = re.findall(r'^CONFIG_'+name+r'=(\w+)$', config, re.M)
        if len(matches) != 1:
            raise ValueError(f'one config assignment required: {name}')
        selected_config[name] = matches[0]
    version = []
    for name in ('VERSION', 'PATCHLEVEL', 'SUBLEVEL'):
        match = re.findall(r'^'+name+r'\s*=\s*([0-9]+)$', texts['Makefile'], re.M)
        if len(match) != 1:
            raise ValueError('kernel version assignment differs')
        version.append(match[0])
    return dict(mode='pinned_flop_source_and_host_rpmb_layout', repository=REPOSITORY,
        commit=COMMIT, kernel_version='.'.join(version), files=metadata,
        source_files_verified=len(metadata), host_c_layout=layout,
        wire_fields={name: dict(offset=wire_interval(offset, size)[0], bytes=size)
                     for name, offset, size in LOCAL_FIELDS},
        constants=constants, selected_config=selected_config,
        kernel_built=False, kernel_executed=False, firmware_executed=False,
        phone_modified=False, lk_callback_identity_established=False,
        limits=[
            'a host compiler checked only the fixed-width packet declaration, not the kernel',
            'matching layout is a source comparison; it does not identify LK callback targets or prove HZC2 source equivalence',
            'kernel request type IDs1/2/3, frame commands, ioctl selectors7/8 and LK dispatcher IDs are distinct namespaces',
            'kernel WSM/RNG service IDs differ from the LK MAC/nonce requests; no secure handler implementation was acquired',
            'defconfig and board source presence do not prove the running configuration, final FDT, image acceptance or bootability'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root', type=Path)
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.source_root, cc=args.cc), indent=2))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(2, f'inspect_flop_reference: {error}\n')


if __name__ == '__main__':
    main()
