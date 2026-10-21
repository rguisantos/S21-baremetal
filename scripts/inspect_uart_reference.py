#!/usr/bin/env python3
"""Read-only UART evidence from the exact received Samsung Kernel.tar.gz.
No extraction, kernel build or hardware access. Emits source excerpts and hashes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

ARCHIVE_SHA = 'c5ad9994240e67ebdc40878c191be040bf30db398bc8513ea1f156eaebd86bf2'
FILES = {
    'arch/arm64/boot/dts/exynos/exynos2100.dts': '586ca56987bbaacce0a38ddaee8a852721caaaeb9096ada6bfde8bc8c0d88ca8',
    'drivers/tty/serial/exynos_tty.c': 'f8e0f52ca9cd2a29e65096749f3498eeef19856fd250c3a272bcf0fb6182b267',
    'include/linux/serial_s3c.h': 'e5c60b29c65ba77a469aa562a5fc4c5b6d64d0abbf48c295967885f6ebdc1aaa',
}


def inspect(path):
    with Path(path).open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != ARCHIVE_SHA:
            raise ValueError('requires the exact received Kernel.tar.gz')
        source.seek(0)
        found = {}
        with tarfile.open(fileobj=source, mode='r|gz') as archive:
            for member in archive:
                if member.name not in FILES:
                    continue
                if member.name in found or not member.isfile() or member.size > 2*1024*1024:
                    raise ValueError('unexpected source member')
                data = archive.extractfile(member).read()
                sha = hashlib.sha256(data).hexdigest()
                if sha != FILES[member.name]:
                    raise ValueError('source hash mismatch: '+member.name)
                found[member.name] = data.decode('utf-8')
        if set(found) != set(FILES):
            raise ValueError('required source files missing')
    dts = found['arch/arm64/boot/dts/exynos/exynos2100.dts']
    excerpts = {}
    # Exact strings from this hash-bound source, not a general DTS parser.
    for marker in ('uart@10540000 {', 'uart@10840000 {', 'uart0-bus {', 'syscon@10421000 {'):
        start = dts.index(marker)
        end = dts.index('};', start)+2
        excerpts[marker] = {'line': dts.count('\n', 0, start)+1, 'text': dts[start:end]}
    return {'archive_sha256': digest, 'source_sha256': FILES, 'excerpts': excerpts,
            'limits': ['Source configuration, not live DTB or pin measurement',
                       'No proof of physical connector or runtime console enable',
                       'No firmware writes or UART initialization performed']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel_tar', type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.kernel_tar)
    except (OSError, ValueError, tarfile.TarError) as exc:
        parser.exit(1, f'inspect_uart_reference: {exc}\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
