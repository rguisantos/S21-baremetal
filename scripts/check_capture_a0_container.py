#!/usr/bin/env python3
"""Check fixed-geometry repack, hash-only refusal and laboratory AVB signatures.

Creates only local analysis images. Does not assemble a runnable kernel/module
package or authorize flashing. A0 remains open even when every control passes.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from capture_a0_container import rehash, result, seal_lab, stage, template
from capture_a0_formats import MAX_IMAGE, digest, layout, require
from check_capture_a0 import PINS

TOOL_PINS = PINS.parent/'capture-a0-container-pins-hzc2.json'


def pinned_bytes(path, pin):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size == pin['bytes'] <= MAX_IMAGE,
        'pinned input type/size differs: '+path.name)
    with path.open('rb') as source:
        data = source.read(pin['bytes']+1)
    require(len(data) == pin['bytes'] and digest(data) == pin['sha256'], 'pinned input hash differs: '+path.name)
    return data


def native(args, cwd, label, data=None, success=True):
    r = subprocess.run(list(map(str, args)), cwd=cwd, input=data, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env={'PATH': os.defpath, 'LC_ALL': 'C'}, timeout=60)
    (cwd/(label+'.stdout')).write_bytes(r.stdout)
    (cwd/(label+'.stderr')).write_bytes(r.stderr)
    require((r.returncode == 0) == success, 'unexpected native result: '+label)
    return r


def inspect(stock_dir, avbtool, test_key, output):
    pins = json.loads(PINS.read_text()); tools = json.loads(TOOL_PINS.read_text())
    require(not output.exists(), 'output directory must be new')
    tool_bytes = pinned_bytes(avbtool, tools['avbtool'])
    key_bytes = pinned_bytes(test_key, tools['public_test_key'])
    originals = {}
    for name in ('boot.img', 'vendor_boot.img', 'dtbo.img'):
        path = stock_dir/name; originals[name] = pinned_bytes(path, pins['stock_raw'][name])
        require(layout(originals[name])['avb']['all_hashes_match'], 'stock AVB hashes differ')
        if name != 'dtbo.img': template(originals[name])
    openssl = shutil.which('openssl', path=os.defpath)
    require(openssl is not None, 'openssl is required')
    output = output.resolve(); output.mkdir(parents=True, exist_ok=False)
    tool = output/'avbtool.py'; tool.write_bytes(tool_bytes)
    key = output/'public-testkey-rsa4096.pem'; key.write_bytes(key_bytes)
    version = native([openssl, 'version'], output, 'openssl-version').stdout.decode().strip()
    public = output/'lab-public.avbpubkey'
    native([sys.executable, tool, 'extract_public_key', '--key', key, '--output', public], output, 'extract-key')
    public_bytes = public.read_bytes()
    controls = {}; trials = {}

    def verify(directory, name, label, expected, with_lab_key=False):
        args = [sys.executable, tool, 'verify_image', '--image', directory/name]
        if with_lab_key: args += ['--key', key]
        run = native(args, directory, label, success=expected)
        text = (run.stdout+run.stderr).decode('utf-8', errors='replace')
        return dict(returncode=run.returncode, expected_success=expected,
            hash_mismatch='does not match digest in descriptor' in text,
            signature_failure='Signature check failed' in text,
            lab_key_explicitly_supplied=with_lab_key,
            log_hash_depends_on_output_path=True,
            output_sha256=digest(run.stdout+run.stderr))

    control = output/'no-change'; control.mkdir()
    for name, original in originals.items():
        rebuilt = stage(original, {}) if name != 'dtbo.img' else original
        # dtbo is a read-only reference, not a modified-payload packer target.
        (control/name).write_bytes(rebuilt)
        verified = verify(control, name, name+'.verify', True)
        controls[name] = dict(bytes=len(rebuilt), sha256=digest(rebuilt),
            byte_identical=rebuilt == original, aosp_verification=verified,
            packer_exercised=name != 'dtbo.img')

    for name, component in [('boot.img', 'kernel'), ('vendor_boot.img', 'ramdisk')]:
        original = originals[name]; p = template(original); inv = p['inventory']
        row = next(r for r in inv['parts'] if r['name'] == component)
        replacement = bytearray(original[row['start']:row['end']]); replacement[-1] ^= 1
        staged = stage(original, {component: bytes(replacement)})
        hashed = rehash(original, staged)
        signing_trial = 0
        def sign(data):
            nonlocal signing_trial
            signing_trial += 1
            return native([openssl, 'dgst', '-sha256', '-sign', key], output,
                name+'.sign-'+str(signing_trial), data=data).stdout
        signed = seal_lab(original, staged, public_bytes, sign)
        # RSA PKCS#1 v1.5 is deterministic for the same key and bytes.
        repeated = seal_lab(original, staged, public_bytes, sign)
        require(signed == repeated, 'same-input laboratory repack was not deterministic')
        variants = {}
        tampered = bytearray(signed); tampered[row['start']] ^= 1
        for label, data, expected, lab in [('stale', staged, False, False),
                ('hash-only', hashed, False, False), ('lab-signed', signed, True, True),
                ('tampered', bytes(tampered), False, True)]:
            directory = output/(name+'.'+label); directory.mkdir()
            (directory/name).write_bytes(data)
            variants[label] = dict(result=result(original, data),
                aosp_verification=verify(directory, name, 'verify', expected, lab))
        require(variants['stale']['aosp_verification']['hash_mismatch']
            and variants['hash-only']['aosp_verification']['signature_failure']
            and variants['tampered']['aosp_verification']['hash_mismatch'],
            'negative controls did not reach the expected verification layers')
        expected_local = {'stale': (False, True), 'hash-only': (True, False),
            'lab-signed': (True, True), 'tampered': (False, True)}
        for label, (hash_ok, rsa_ok) in expected_local.items():
            local = variants[label]['result']
            require((local['hash_descriptors_match'], local['rsa_signature_matches_embedded_key']) == (hash_ok, rsa_ok)
                and local['android_header_and_non_vbmeta_non_payload_bytes_preserved']
                and local['avb_header_preserved'] and local['footer_preserved']
                and local['original_hash_extent'] == local['output_hash_extent'],
                'local crypto/geometry control differs: '+label)
        trials[name] = dict(component=component, mutation_offset=row['end']-1,
            mutation_xor=1, synthetic_mutation_not_a_runnable_payload=True,
            same_key_repack_byte_identical=signed == repeated, variants=variants)
    require(all(c['byte_identical'] for c in controls.values()), 'no-change identity failed')
    return dict(schema='S21-CAPTURE-A0-CONTAINER-v1', source_base='ed262c44b8762a9b8e3f2e7ad464a5fcbeae34bc',
        tools=tools, implementation_sha256={name: digest(Path(__file__).with_name(name).read_bytes())
            for name in ('capture_a0_container.py', 'check_capture_a0_container.py')},
        openssl=dict(version=version, executable_sha256=digest(Path(openssl).read_bytes())),
        public_lab_key_sha256=digest(public_bytes), no_change_controls=controls, trials=trials,
        fixed_geometry_lab_repack_checks_passed=True, runnable_payload_package_built=False,
        samsung_signerver03_regenerated=False, samsung_signerver03_validated=False,
        key_trust_established=False, parent_vbmeta_updated=False,
        signature_policy_verified=False, physical_acceptance_established=False,
        module_abi_established=False, a0_complete=False, a1_implemented=False, physical_action=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('stock-dir', 'avbtool', 'test-key', 'output-dir'):
        p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args()
    try:
        r = inspect(a.stock_dir.resolve(), a.avbtool.resolve(), a.test_key.resolve(), a.output_dir)
        (a.output_dir/'report.json').write_text(json.dumps(r, indent=2)+'\n')
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        p.exit(1, 'OFFLINE CONTAINER REFUSED: '+str(exc)+'\n')
    print('Offline laboratory repack controls PASS; Samsung acceptance and A0 remain open')
    return 2


if __name__ == '__main__': raise SystemExit(main())
