#!/usr/bin/env python3
"""Measure the preserved build against stock payload slots without rebuilding.

Image follows the pinned source's objcopy recipe, independently mapped from
ELF sections. Two ramdisk measurement profiles retain stock non-module data:
as-built .ko files and copies processed with INSTALL_MOD_STRIP=1 semantics.
Neither profile is a bootable-package or runtime compatibility approval.
"""
import argparse
from contextlib import ExitStack
import hashlib
import io
import json
import mmap
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess
import sys
import tarfile
import zlib

from capture_a0_formats import digest, layout, require
from capture_a0_copy import copy_checked
from capture_a0_inputs import checked_buffer, read_checked, read_sealed, sealed_input, select_members
from capture_a0_module_policy import MODNAME
from capture_a0_module_policy import MAX_MODULE
from capture_a0_modules import gunzip
from capture_a0_sizes import arm64_header, comparison, flat_image, ramdisk, strip_equivalence
from check_capture_a0 import PINS

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('arch/arm64/boot/Makefile', 'Makefile', 'scripts/Makefile.modinst')
IMAGE_FLAGS = ['-O','binary','-R','.note','-R','.note.gnu.build-id','-R','.comment','-S']


def file_hash(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def verify(path, pin):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size == pin['bytes'], 'input type/size differs: '+path.name)
    require(file_hash(path) == pin['sha256'], 'input SHA differs: '+path.name)


def module_input(path, pin):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size == pin['bytes'] <= MAX_MODULE,
        'as-built module copy size/type drifted: '+path.name)
    with path.open('rb') as file: data = file.read(pin['bytes']+1)
    require(len(data) == pin['bytes'] and digest(data) == pin['sha256'], 'as-built module copy hash drifted: '+path.name)
    return data


def extract_selected(archive, selected, output, vmlinux_pin, snapshot_stack=None, snapshots=None):
    require((snapshot_stack is None) == (snapshots is None),'snapshot arguments must be paired')
    wanted = {r['source']:dict(bytes=r['bytes'],sha256=r['sha256'],target=output/(r['name']+'.ko')) for r in selected}
    require(len(wanted) == len(selected), 'duplicate source path')
    wanted['vmlinux'] = dict(**vmlinux_pin, target=output/'vmlinux')
    seen = set(); found = set(); readbacks = {}
    opened = tarfile.open(fileobj=io.BytesIO(archive),mode='r|gz') if type(archive) is bytes else tarfile.open(archive,'r|gz')
    with opened as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            require(path.parts and not path.is_absolute() and '..' not in path.parts
                and str(path) == member.name and member.name not in seen, 'artifact path/duplicate')
            seen.add(member.name)
            if member.name not in wanted: continue
            row = wanted[member.name]
            require(member.isfile() and member.size == row['bytes'], 'artifact selected member type/size')
            with tar.extractfile(member) as source:
                if snapshots is None:
                    readbacks[member.name] = copy_checked(source,row['target'],row)
                else:
                    data = checked_buffer(source.read(row['bytes']+1),row)
                    readbacks[member.name] = copy_checked(io.BytesIO(data),row['target'],row)
                    snapshots[member.name] = snapshot_stack.enter_context(sealed_input(data,row))
            found.add(member.name)
    require(found == wanted.keys(), 'selected build member missing')
    return readbacks


def inspect(stock, archive, source, tools_root, output):
    require(not output.exists(), 'output directory must be new')
    pins = json.loads(PINS.read_text())
    previous = json.loads((PINS.parent/'capture-a0-aligned-full-validation-20261102.json').read_text())
    audit_path = PINS.parent/'capture-a0-aligned-full-audit-hzc2.json'
    audit_data = read_checked(audit_path,dict(bytes=audit_path.stat().st_size,sha256=previous['report_sha256']))
    audit = json.loads(audit_data); inventory = {r['name']:r for r in audit['modules']}
    selection = audit['candidate_module_set']['files']; selected = []
    for row in selection:
        require(MODNAME.fullmatch(row['name']) and row['name'] in inventory
            and inventory[row['name']]['path'] == row['source']
            and inventory[row['name']]['sha256'] == row['sha256'], 'selection identity')
        selected.append(dict(**row, bytes=inventory[row['name']]['bytes']))
    require(len(selected) == len({r['name'] for r in selected})
        == len({r['package_path'] for r in selected}) == 274, 'selected module set')
    archive_bytes = read_checked(archive,previous['reference_artifacts'])
    source_bytes = read_checked(source,pins['samsung_source_archive'])
    members,_ = select_members(source_bytes,SOURCES,source_tree=True); del source_bytes
    line = next(x for x in members[SOURCES[0]].decode().splitlines() if x.startswith('OBJCOPYFLAGS_Image :='))
    require(line.partition(':=')[2].split() == IMAGE_FLAGS, 'source Image recipe differs')
    require('mod_strip_cmd = $(STRIP) --strip-debug' in members['Makefile'].decode()
        and 'ifeq ($(INSTALL_MOD_STRIP),1)' in members['Makefile'].decode()
        and '$(mod_strip_cmd) $(2)/$(notdir $@)' in members['scripts/Makefile.modinst'].decode(), 'source install strip recipe differs')
    raw = {}
    for name in ('boot.img','vendor_boot.img'):
        raw[name] = read_checked(stock/name,pins['stock_raw'][name])
        require(layout(raw[name])['avb']['all_hashes_match'], 'stock descriptor hashes differ')
    output = output.resolve(); output.mkdir(parents=True)
    candidate = output/'candidate'; candidate.mkdir()
    vmlinux_pin = dict(bytes=437269784,sha256=previous['native_build']['vmlinux_sha256'])
    snapshot_stack = ExitStack(); native_sources = {}
    try:
        readbacks = extract_selected(archive_bytes, selected, candidate,vmlinux_pin,snapshot_stack,native_sources); del archive_bytes
        tools = {}
        def native(tool, args, label, pass_fds=()):
            binary = tools_root/'usr/bin'/('aarch64-linux-gnu-'+tool)
            require(binary.is_file(), 'cross binutils missing')
            prefix = ['bash',str(ROOT/'scripts/cross-run.sh'),str(tools_root),str(binary)]
            run = subprocess.run(prefix+list(map(str,args)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env={**os.environ,'LC_ALL':'C'}, timeout=60,pass_fds=pass_fds)
            (output/(label+'.log')).write_bytes(run.stdout); require(run.returncode == 0, 'binutils failed: '+label)
            return run.stdout.decode(errors='replace')
        for name in ('objcopy','strip'):
            version = native(name,['--version'],name+'-version').splitlines()[0]
            tools[name] = dict(version=version,sha256=file_hash(tools_root/'usr/bin'/('aarch64-linux-gnu-'+name)))
        fd,path = native_sources['vmlinux']; image = output/'Image'
        native('objcopy',IMAGE_FLAGS+[path,image],'image-objcopy',pass_fds=(fd,))
        with mmap.mmap(fd,0,access=mmap.ACCESS_READ) as vmlinux:
            independent, mapped = flat_image(vmlinux)
        actual = read_checked(image,dict(bytes=len(independent),sha256=digest(independent)))
        require(actual == independent, 'objcopy Image differs from independent ELF mapping')
        boot_layout = layout(raw['boot.img']); kernel = next(r for r in boot_layout['parts'] if r['name'] == 'kernel')
        stock_header = arm64_header(raw['boot.img'][kernel['start']:kernel['end']])
        vendor_layout = layout(raw['vendor_boot.img']); vr = next(r for r in vendor_layout['parts'] if r['name'] == 'ramdisk')
        cpio = gunzip(raw['vendor_boot.img'][vr['start']:vr['end']])
        stock_control = ramdisk(cpio,{},output/'stock-control.cpio.gz')
        stripped = output/'stripped'; stripped.mkdir(); rows = []; replacements = {'as_built':{},'strip_debug':{}}
        for index, row in enumerate(selected):
            before = candidate/(row['name']+'.ko'); after = stripped/before.name
            fd,path = native_sources[row['source']]; old_bytes = read_sealed(fd,row)
            native('strip',['--strip-debug','-o',after,path],'strip-%03d'%index,pass_fds=(fd,))
            new_bytes = after.read_bytes()
            equality = strip_equivalence(old_bytes,new_bytes)
            new_pin = dict(bytes=len(new_bytes),sha256=digest(new_bytes))
            new_fd,_ = snapshot_stack.enter_context(sealed_input(new_bytes,new_pin))
            for mode, source_fd, data in [('as_built',fd,old_bytes),('strip_debug',new_fd,new_bytes)]:
                replacements[mode][row['package_path']] = dict(fd=source_fd,bytes=len(data),sha256=digest(data))
            rows.append(dict(name=row['name'],package_path=row['package_path'],as_built_bytes=len(old_bytes),
                as_built_sha256=digest(old_bytes),strip_debug_bytes=len(new_bytes),strip_debug_sha256=digest(new_bytes),**equality))
            if (index+1) % 50 == 0: print('Measured module copies:',index+1,flush=True)
        profiles = {}
        for mode, inputs in replacements.items():
            print('Compressing measurement profile:',mode,flush=True)
            profiles[mode] = ramdisk(cpio,inputs,output/(mode+'.cpio.gz'))
            profiles[mode]['comparison'] = comparison(vr['bytes'], profiles[mode]['gzip_bytes'])
            profiles[mode]['delta_from_stock_recompressed_with_same_gzip_profile'] = profiles[mode]['gzip_bytes']-stock_control['gzip_bytes']
            profiles[mode]['compressed_ramdisk_alone_exceeds_stock_image'] = profiles[mode]['gzip_bytes'] > len(raw['vendor_boot.img'])
            profiles[mode]['module_bytes'] = sum(x['bytes'] for x in inputs.values())
            require(profiles[mode]['modules_replaced'] == 274, 'ramdisk replacement count differs')
        return dict(schema='S21-CAPTURE-A0-PAYLOAD-SIZES-v1',source_base='a7733812fe10d99e1ae465715615a76550ac190e',
            implementation_sha256={n:digest(Path(__file__).with_name(n).read_bytes())
                for n in ('capture_a0_sizes.py','check_capture_a0_sizes.py')},
            source_archive_sha256=pins['samsung_source_archive']['sha256'],candidate_archive_sha256=previous['reference_artifacts']['sha256'],
            selected_build_payloads_verified=275,selected_copy_readbacks_verified=len(readbacks),
            consumption=dict(archive_source_and_stock_same_checked_buffers=True,
                native_objcopy_and_strip_inputs_sealed=True,native_inputs_verified=275,
                snapshots_sealed_during_extraction=True,working_copy_paths_reconsumed=False,
                ramdisk_replacements_checked_before_emit=True,gzip_replay_same_checked_buffer=True,
                other_runners_certified=False),
            source_members={n:dict(bytes=len(b),sha256=digest(b)) for n,b in members.items()},
            tools=tools,python=sys.version,zlib_version=zlib.ZLIB_VERSION,
            image=dict(recipe=IMAGE_FLAGS,sha256=digest(actual),mapping=mapped,independent_mapping_byte_identical=True,
                comparison=comparison(kernel['bytes'],len(actual)),stock_header=stock_header,
                zero_padding_to_stock_bytes=max(0,kernel['bytes']-len(actual)),zero_padding_applied=False),
            stock_vendor_ramdisk=dict(gzip_bytes=vr['bytes'],cpio_bytes=len(cpio),measurement_recompression=stock_control),
            profiles=profiles,modules=rows,strip_profile='Source INSTALL_MOD_STRIP=1 / --strip-debug on copies only; not an adopted package policy',
            stock_non_module_data_and_load_dep_files_changed=False,modules_dep_regenerated=False,
            boot_container_built=False,payload_semantics_validated=False,module_abi_established=False,
            signature_policy_verified=False,key_trust_established=False,a0_complete=False,a1_implemented=False,physical_action=False)
    finally: snapshot_stack.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('stock-dir','candidate-artifacts','source','tools-root','output-dir'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    try:
        r = inspect(*[p.resolve() for p in (args.stock_dir,args.candidate_artifacts,args.source,args.tools_root,args.output_dir)])
        (args.output_dir/'report.json').write_text(json.dumps(r,indent=2)+'\n')
    except (OSError,ValueError,KeyError,struct.error,tarfile.TarError,subprocess.SubprocessError) as exc:
        parser.exit(1,'PAYLOAD SIZING REFUSED: '+str(exc)+'\n')
    print('Image comparison:',r['image']['comparison'])
    for mode,p in r['profiles'].items(): print('Ramdisk comparison:',mode,p['comparison'])
    return 2  # A0 is open; this is not a bootable-package gate.


if __name__ == '__main__': raise SystemExit(main())
