#!/usr/bin/env python3
"""Inventory tracked files >=5MiB and match local Debian payloads or a pinned asset.

Local .deb matches prove byte identity to those archives, not Debian signature
or remote download verification. The official Magisk digest was read from
GitHub release asset metadata; no binaries are downloaded by this script.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent.parent
MAGISK = dict(repository='topjohnwu/Magisk', tag='v30.7', asset_id=360657865,
    asset_name='app-debug.apk', bytes=25278536,
    sha256='40729525e298a11dad6e13586a29efa48a48e97cbf00203798e8047d1c710cb2',
    metadata_url='https://api.github.com/repos/topjohnwu/Magisk/releases/tags/v30.7',
    download_url='https://github.com/topjohnwu/Magisk/releases/download/v30.7/app-debug.apk')
PACKAGE_PREFIXES = ('gcc-14-aarch64-linux-gnu_', 'cpp-14-aarch64-linux-gnu_',
    'qemu-system-arm_', 'libcapstone5_', 'libssl3t64_', 'libasan8-arm64-cross_',
    'libtsan2-arm64-cross_', 'libgcc-14-dev-arm64-cross_')


def digest(stream):
    value = hashlib.sha256()
    while block := stream.read(1024*1024):
        value.update(block)
    return value.hexdigest()


def file_digest(path):
    with path.open('rb') as stream:
        return digest(stream)


def audit(root=ROOT):
    tracked = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=root).split(b'\0')
    files = []
    for raw in tracked:
        if not raw:
            continue
        metadata, relative = raw.decode().split('\t', 1)
        mode, blob, stage = metadata.split()
        path = root/relative
        if mode in ('100644', '100755') and path.is_file() and path.stat().st_size >= 5*1024*1024:
            actual = subprocess.check_output(['git', 'hash-object', str(path)], cwd=root, text=True).strip()
            if stage != '0' or actual != blob:
                raise ValueError('large working file differs from indexed blob')
            files.append(dict(path=relative, git_blob=blob, git_mode=mode,
                bytes=path.stat().st_size, sha256=file_digest(path)))
    wanted = {f['sha256'] for f in files}
    packages, payloads = {}, {}
    for archive in sorted((root/'tools/debs').glob('*.deb')):
        if not archive.name.startswith(PACKAGE_PREFIXES):
            continue
        fields = subprocess.check_output(['dpkg-deb', '-f', str(archive),
            'Package', 'Version', 'Architecture', 'Source'], text=True)
        metadata = dict(line.split(': ', 1) for line in fields.splitlines() if ': ' in line)
        relative = str(archive.relative_to(root))
        packages[relative] = dict(path=relative, sha256=file_digest(archive), control=metadata)
        process = subprocess.Popen(['dpkg-deb', '--fsys-tarfile', str(archive)], stdout=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=process.stdout, mode='r|') as tar:
                for member in tar:
                    if member.isfile() and member.size >= 5*1024*1024:
                        stream = tar.extractfile(member)
                        value = digest(stream)
                        stream.close()
                        if value in wanted:
                            payloads.setdefault(value, []).append(dict(package=relative,
                                member=member.name, bytes=member.size))
            if process.wait(timeout=10):
                raise ValueError('Debian payload extraction failed')
        finally:
            if process.stdout:
                process.stdout.close()
            if process.poll() is None:
                process.kill(); process.wait()
    for item in files:
        path = item['path']
        if path in packages:
            item['provenance'] = dict(kind='local_deb_archive', package=path,
                independently_authenticated=False)
        elif item['sha256'] in payloads:
            item['provenance'] = dict(kind='byte_match_to_local_deb_payload',
                matches=payloads[item['sha256']], independently_authenticated=False)
        elif path == 'scripts/magiskboot/magisk.apk' and item['sha256'] == MAGISK['sha256']:
            item['provenance'] = dict(kind='official_release_asset_digest_match', asset=MAGISK)
        else:
            item['provenance'] = dict(kind='source_not_recovered')
    files.sort(key=lambda item:item['path'])
    groups = {}
    for item in files:
        groups.setdefault(item['sha256'], []).append(item['path'])
    return dict(mode='tracked_large_binary_inventory', threshold_bytes=5*1024*1024,
        count=len(files), total_versioned_bytes=sum(f['bytes'] for f in files), files=files,
        source_not_recovered=[f['path'] for f in files if f['provenance']['kind']=='source_not_recovered'],
        local_archives=list(packages.values()), duplicate_content_groups=[v for v in groups.values() if len(v)>1],
        downloaded_or_removed_binaries=False, debian_signature_or_remote_archives_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path, help='require identical saved inventory')
    args = parser.parse_args()
    result = audit()
    output = json.dumps(result, indent=2)+'\n'
    if args.check and args.check.read_text() != output:
        parser.exit(2, 'audit_large_binaries: inventory differs\n')
    print(output, end='')
