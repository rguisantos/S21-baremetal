#!/usr/bin/env python3
"""Build offline B prototypes from pinned real payloads; never flash images."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from capture_a0_container import describe, template
from capture_a0_formats import digest, reassemble, require
from capture_a0_inputs import read_checked, sealed_input
from capture_a0_modules import cpio, gunzip
from capture_a0_module_policy import module
from capture_a0_natural import evidence, rehash, seal_lab, stage
from capture_a0_sizes import arm64_header
from check_capture_a0 import PINS

ROOT = Path(__file__).resolve().parents[1]

# Only pathname resolution and descriptor inheritance are adapted. Upstream
# parsers, hash/RSA checks and the --key equivalent are left unchanged.
SNAPSHOT_VERIFY = r'''
import os, subprocess, sys
tool_fd, image_fd, key_fd = map(int,sys.argv[1:4])
name, explicit = sys.argv[4:6]
scope = {'__name__':'a0_pinned_avbtool'}
exec(compile(os.pread(tool_fd,204714,0),'<pinned-avbtool>','exec'),scope)
base = scope['ImageHandler']
logical = '/sealed/'+name
class SnapshotImage(base):
    def __init__(self, filename, read_only=False):
        if filename != logical or not read_only:
            raise ValueError('unmapped or writable image requested')
        super().__init__('/proc/self/fd/'+str(image_fd),read_only=True)
        self.filename = logical
scope['ImageHandler'] = SnapshotImage
previous_popen = subprocess.Popen
def inherit_key(*args,**kwargs):
    kwargs['pass_fds'] = tuple(set(kwargs.get('pass_fds',())) | {key_fd})
    return previous_popen(*args,**kwargs)
subprocess.Popen = inherit_key
try:
    scope['Avb']().verify_image(logical,'/proc/self/fd/'+str(key_fd) if explicit=='yes' else None,None,False,False)
except (scope['AvbError'],ValueError) as exc:
    print(str(exc),file=sys.stderr);sys.exit(1)
'''


def pin(data): return dict(bytes=len(data), sha256=digest(data))


def native_verify(tool, key, image, name, explicit_key=True):
    with ExitStack() as stack:
        descriptors = [stack.enter_context(sealed_input(data,pin(data)))[0] for data in (tool,image,key)]
        r = subprocess.run([sys.executable,'-c',SNAPSHOT_VERIFY,*map(str,descriptors),name,
            'yes' if explicit_key else 'no'],pass_fds=tuple(descriptors),stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,timeout=60,env={'PATH':os.defpath,'LC_ALL':'C'})
    return dict(returncode=r.returncode,stdout=r.stdout.decode(errors='replace'),stderr=r.stderr.decode(errors='replace'),
        image_and_tool_read_from_sealed_snapshots=True,explicit_expected_key=explicit_key,
        upstream_verify_image_api=True,unmodified_cli=False)


def payload_checks(stock, image, zipped, measured):
    arm = arm64_header(image)
    old_inv = template(stock)['inventory']; ram = next(r for r in old_inv['parts'] if r['name']=='ramdisk')
    before = cpio(gunzip(stock[ram['start']:ram['end']]))
    after = cpio(gunzip(zipped)); require(before.keys() == after.keys(),'ramdisk entry set differs')
    expected = {r['package_path']:r for r in measured['modules']}
    actual = {n for n in after if n.endswith('.ko')}
    require(actual == expected.keys() and len(actual)==274,'natural module set differs')
    names = {}; dependencies = {}
    for name, entry in after.items():
        require(entry['kind'] == before[name]['kind'],'ramdisk entry kind differs')
        if name not in expected:
            require(entry['data']==before[name]['data'],'non-module ramdisk entry changed')
            continue
        row = expected[name]
        require(pin(entry['data']) == dict(bytes=row['strip_debug_bytes'],sha256=row['strip_debug_sha256']),
            'selected stripped module identity differs')
        m = module(entry['data']); require(m['name'] not in names,'duplicate module name')
        names[m['name']]=name;dependencies[m['name']]=m['depends']
    canonical = {name.replace('-','_'):name for name in names}
    missing = {name:sorted(d for d in deps if d.replace('-','_') not in canonical)
        for name,deps in dependencies.items()}
    missing = {n:d for n,d in missing.items() if d}
    require(not missing,'declared module dependency absent from selected package')
    return dict(arm64_header=arm,modules_verified=len(actual),module_names=sorted(names),
        declared_dependency_names_present=True,non_module_entries_byte_identical=True,
        modules_dep_and_load_files_preserved=True,modules_dep_regenerated=False,
        dependency_load_order_validated=False,runtime_loading_validated=False)


def inspect(stock_dir,image_path,ramdisk_path,avbtool,test_key,output):
    require(not output.exists(),'natural output directory must be new')
    pins=json.loads(PINS.read_text());tools=json.loads((PINS.parent/'capture-a0-container-pins-hzc2.json').read_text())
    measured=json.loads((PINS.parent/'capture-a0-payload-sizes-hzc2.json').read_text())
    raw={name:read_checked(stock_dir/name,pins['stock_raw'][name]) for name in ('boot.img','vendor_boot.img')}
    image=read_checked(image_path,dict(bytes=measured['image']['comparison']['candidate_bytes'],sha256=measured['image']['sha256']))
    zipped=read_checked(ramdisk_path,dict(bytes=measured['profiles']['strip_debug']['gzip_bytes'],sha256=measured['profiles']['strip_debug']['gzip_sha256']))
    tool=read_checked(avbtool,tools['avbtool']);key=read_checked(test_key,tools['public_test_key'])
    checks=payload_checks(raw['vendor_boot.img'],image,zipped,measured)
    openssl=shutil.which('openssl',path=os.defpath);require(openssl is not None,'openssl missing')
    with sealed_input(key,pin(key)) as (fd,path):
        r=subprocess.run([openssl,'rsa','-in',path,'-modulus','-noout'],pass_fds=(fd,),
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=True)
    n=int(r.stdout.decode().strip().split('=')[1],16)
    public=struct.pack('>II',4096,(-pow(n,-1,2**32))%2**32)+n.to_bytes(512,'big')+pow(2,8192,n).to_bytes(512,'big')
    expected_public=json.loads((PINS.parent/'capture-a0-container-hzc2.json').read_text())['public_lab_key_sha256']
    require(digest(public)==expected_public,'lab public key identity differs')
    output=output.resolve();output.mkdir(parents=True,exist_ok=False);reports={}
    def sign(data):
        with sealed_input(key,pin(key)) as (fd,path):
            return subprocess.run([openssl,'dgst','-sha256','-sign',path],input=data,pass_fds=(fd,),
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=True).stdout
    for name,replacements in [('boot.img',{'kernel':image}),('vendor_boot.img',{'ramdisk':zipped})]:
        original=raw[name];inv=template(original)['inventory']
        independent=reassemble(inv['parts'],[original[r['start']:r['end']] for r in inv['parts']],len(original))
        require(independent==original and stage(original,{})==original,'stock no-change reconstruction differs')
        draft=stage(original,replacements);hashed=rehash(draft);signed=seal_lab(original,replacements,public,sign)
        require(signed==seal_lab(original,replacements,public,sign),'natural same-input signing differs')
        local=evidence(original,signed)
        require(local['opaque_bytes_preserved'] and local['vbmeta_header_preserved'],'natural preservation differs')
        rows={r['name']:r for r in local['output_layout']['parts']}
        for component,data in replacements.items():
            r=rows[component];require(signed[r['start']:r['end']]==data,'natural extraction differs')
        old_rows={r['name']:r for r in inv['parts']}
        for component in ({'kernel','ramdisk'} if name=='boot.img' else {'ramdisk','dtb'})-replacements.keys():
            a,b=old_rows[component],rows[component]
            require(original[a['start']:a['end']]==signed[b['start']:b['end']],'unchanged payload differs')
        corrupted=bytearray(signed);corrupted[rows[next(iter(replacements))]['start']]^=1
        controls={}
        for label,data,expected,explicit in [('stock-no-change',independent,True,False),
                ('stale',draft,False,False),('hash-only',hashed,False,False),
                ('lab-signed',signed,True,True),('tampered',bytes(corrupted),False,True)]:
            run=native_verify(tool,key,data,name,explicit)
            require((run['returncode']==0)==expected,'unexpected upstream natural result: '+label)
            controls[label]=run
        require('Signature check failed' in controls['hash-only']['stderr']
            and 'does not match digest' in controls['tampered']['stderr'],'negative controls reached wrong layer')
        (output/name).write_bytes(signed)
        read_checked(output/name,pin(signed))
        reports[name]=dict(**local,no_change_byte_identical=True,same_input_repeated_signature_byte_identical=True,
            independent_controls=controls)
    return dict(schema='S21-CAPTURE-A0-NATURAL-B-v1',source_base='0261215cfe48f25fed68ef2d818afee523843573',
        decision=dict(option='B',payload_lengths='natural',module_profile='strip-debug',file_bytes=67108864,
            authorization='User: Faca do jeito que for melhor prossiga; offline prototype only'),
        input_pins=dict(image=pin(image),vendor_ramdisk=pin(zipped)),payload_checks=checks,images=reports,
        tools=tools,upstream_io_adapter_sha256=digest(SNAPSHOT_VERIFY.encode()),
        implementation_sha256={n:digest(Path(__file__).with_name(n).read_bytes()) for n in
            ('capture_a0_natural.py','check_capture_a0_natural.py')},
        parent_vbmeta_status='not_supplied_not_assumed_unaffected',parent_vbmeta_updated=False,
        samsung_signerver03_validated=False,samsung_acceptance_established=False,
        module_abi_established=False,a0_complete=False,a1_started=False,physical_action=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('stock-dir','image','vendor-ramdisk','avbtool','test-key','output-dir'):
        p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    try:
        report=inspect(a.stock_dir,a.image,a.vendor_ramdisk,a.avbtool,a.test_key,a.output_dir)
        (a.output_dir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    except (OSError,ValueError,KeyError,struct.error,subprocess.SubprocessError) as exc:
        p.exit(1,'NATURAL LAB CONTAINER REFUSED: '+str(exc)+'\n')
    print('Natural B laboratory geometry/AVB controls PASS; Samsung acceptance and A0 remain open')
    return 2


if __name__=='__main__':raise SystemExit(main())
