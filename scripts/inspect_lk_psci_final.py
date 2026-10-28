#!/usr/bin/env python3
"""Static HZC2 final PSCI property edit; optional allowlisted boot message."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import zipfile
from check_epbl_protocol_gnu import direct_target, parse_lines
from inspect_el2_hzc2 import IMAGES, read_exact
from inspect_lk_final_edges import flow
from inspect_lk_payload_return import summarize_local

BLOCKS = {
    'psci_rewriter': (0xf9470, 0xf9618),
    'post_banks_tail_fragment': (0xfb4dc, 0xfb548),
    'boot_wrapper_fragment': (0xfbcb0, 0xfbd1c),
    'handoff_args_fragment': (0xfbdf4, 0xfbe18),
    'temperature_gate': (0x148a30, 0x148a7c),
    'header_size_helper': (0xf1240, 0xf12c4),
    'harx_flag_store_fragment': (0xf90a0, 0xf90e4),
}


def inspect(path):
    data = read_exact(path, *IMAGES['sboot'])
    root = Path(__file__).resolve().parent.parent
    command = ['bash', str(root/'scripts/cross-run.sh'), str(root/'tools/root'),
               str(root/'tools/root/usr/bin/aarch64-linux-gnu-objdump')]
    lines = {}
    for a,b in BLOCKS.values():
        lines.update(parse_lines(subprocess.check_output(command + [
            '-D','-b','binary','-m','aarch64',f'--start-address={a}',
            f'--stop-address={b}',str(Path(path).resolve())], text=True)))
    expected = {pc for a,b in BLOCKS.values() for pc in range(a,b,4)}
    if set(lines) != expected:
        raise ValueError('GNU coverage differs')
    branches = {}
    for pc,(raw,op,args) in lines.items():
        if raw != struct.unpack_from('<I',data,pc)[0] or op in ('.inst','udf'):
            raise ValueError(f'GNU instruction differs at {pc:#x}')
        kind,target = flow(raw,pc)
        if kind in ('b','bl','conditional'):
            if target != direct_target(op,args):
                raise ValueError(f'GNU target differs at {pc:#x}')
            branches[hex(pc)] = dict(kind=kind,target=hex(target))
    graphs = {name:summarize_local(data,a,a,b) for name,(a,b) in BLOCKS.items()}
    strings = {hex(p):data[p:data.index(0,p)].decode('ascii') for p in
               (0x214c18,0x26d230,0x214c70,0x214c78,0x214ca8,0x214cf8,0x23c5d0)}
    packed = b''.join(struct.pack('<II',pc,lines[pc][0]) for pc in sorted(lines))
    return dict(mode='static_lk_psci_final_edit',sboot_sha256=IMAGES['sboot'][1],
        firmware_executed=False,live_registers_observed=False,
        gnu_version=subprocess.check_output(command+['--version'],text=True).splitlines()[0],
        gnu_words=len(lines),gnu_relative_targets=len(branches),
        instruction_index_sha256=hashlib.sha256(packed).hexdigest(),
        instructions={hex(pc):dict(word=f'{raw:08x}',op=op,args=args)
                      for pc,(raw,op,args) in sorted(lines.items())},
        branches=branches,strings=strings,local_graphs=graphs,
        interpretation=dict(
            flag='byte at LK-relative 0x487c90; zero returns -1',
            node='/psci', property='method', compare_length='property length, not fixed literal length',
            replacement='hvc plus NUL, length 4',
            preexisting_hvc='returns zero without editing',
            caller='0xfb52c; prints warning on nonzero and continues',
            size_helper='0xfb544 -> 0xf1240(0): header totalsize round-up to 4, not fdt_pack',
            handoff='0xfbe0c W0=0x8b080000; x1=x2=x3=0 before BLR x4'),
        limits=['Call graph includes opaque callees; not a proof of all later FDT effects',
                'Harx flag is written before crash-registration HVC, not a certificate of that HVC',
                'A successful log message witnesses local setprop return, not a dump of the final FDT',
                'No PSCI service, EL state, or physical payload execution established'])





def boot_observation(path):
    from inspect_bugreport_boot import ARCHIVE_SHA256, MAX_ARCHIVE, MAX_MEMBER, MAX_LINE, HEADING
    with open(path, 'rb') as stream:
        data = stream.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE or hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('requires exact received bugreport SHA-256')
    member = 'dumpstate-2026-10-27-18-23-28.txt'
    message = b'Change PSCI method to HVC'
    matches, body = [], bytearray()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.namelist().count(member) != 1 or archive.getinfo(member).file_size > MAX_MEMBER:
            raise ValueError('unexpected main member')
        active = False
        with archive.open(member) as stream:
            for number in range(1, 2_000_001):
                raw = stream.readline(MAX_LINE + 1)
                if not raw:
                    raise ValueError('missing complete LAST KMSG')
                if len(raw) > MAX_LINE:
                    raise ValueError('report line exceeds host bound')
                if raw.rstrip(b'\r\n') == HEADING:
                    active = True
                    continue
                if active and raw.startswith(b'------ '):
                    break
                if active:
                    body.extend(raw)
                    if len(body) > 2 << 20:
                        raise ValueError('boot section exceeds host bound')
                    match = re.fullmatch(rb'\[0:\s+([0-9]+\.[0-9]+) \] ' + message + rb'\s*', raw)
                    if match:
                        matches.append(dict(kind='psci_method_changed_to_hvc_message',
                            source_line=number, boot_seconds=match[1].decode('ascii')))
            else:
                raise ValueError('main report exceeds line bound')
    if len(matches) != 1:
        raise ValueError('expected exactly one allowlisted PSCI message')
    return dict(archive_sha256=ARCHIVE_SHA256, main_member=member,
                last_kmsg_sha256=hashlib.sha256(body).hexdigest(), events=matches,
                raw_lines_published=False, final_fdt_captured=False)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    parser.add_argument('--bugreport')
    args=parser.parse_args()
    try:
        result = inspect(args.sboot)
        if args.bugreport:
            result['boot_observation'] = boot_observation(args.bugreport)
        print(json.dumps(result,indent=2))
    except (OSError,ValueError,UnicodeError,struct.error,subprocess.CalledProcessError,
            KeyError,zipfile.BadZipFile,RuntimeError) as error:
        parser.exit(2,f'inspect_lk_psci_final: {error}\n')
