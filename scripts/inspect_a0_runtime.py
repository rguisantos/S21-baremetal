#!/usr/bin/env python3
"""Compare the main Samsung dumpstate header and LSMOD with pinned references."""
import argparse
import hashlib
import json
from itertools import chain
import os
import re
import zipfile

from inspect_bugreport_boot import MAX_ARCHIVE, MAX_LINE, MAX_MEMBER

BANNERS = {
    '021b80430696d9d788ba9e339f36783fe7def993ab8b89a326c74c88f0cafe2e': 'samsung_hzc2',
    '7959587b8848e40ea2cf4b5168a198981b749ac4ee7a4c5e44093075e74a4835': 'aligned_a0',
}
STOCK_NAMES = 'e914f326b924ddc338fc34649c990e69414f001b5c357278b0fd4d4de82f0df7'
FOCUS = ('gpu_cooling', 'pdic_notifier_module', 'input_booster_lkm', 'sec_debug_sched_info')
TITLE = b'------ LSMOD (lsmod) ------'
END = re.compile(rb"------ [0-9]+(?:\.[0-9]+)?s was the duration of 'LSMOD' ------")
ROW = re.compile(rb'([A-Za-z0-9_]+)\s+[0-9]+\s+[0-9]+(?:\s+[A-Za-z0-9_,\[\]-]+)?')


def main_lines(stream):
    size = 0
    for number in range(1, 2_000_001):
        raw = stream.readline(MAX_LINE + 1)
        if not raw:
            return
        size += len(raw)
        if size > MAX_MEMBER or len(raw) > MAX_LINE:
            raise ValueError('main report exceeds size limit')
        yield number, raw
    raise ValueError('main report exceeds line limit')


def compare(stream):
    lines = iter(main_lines(stream))
    banner = None
    names = set()
    found_section = False
    for number, raw in lines:
        if number == 2 and not raw.startswith(b'== dumpstate: '):
            raise ValueError('unexpected dumpstate header')
        if raw.startswith(b'------ '):
            first_section = (number, raw)
            break
        if number > 128:
            raise ValueError('unexpected dumpstate header length')
        if raw.startswith(b'Kernel: '):
            if banner is not None or not raw.startswith(b'Kernel: Linux version '):
                raise ValueError('ambiguous or malformed kernel header')
            banner = hashlib.sha256(raw[8:].removesuffix(b'\n').removesuffix(b'\r') + b'\n').hexdigest()
    else:
        raise ValueError('missing dumpstate sections')
    if banner is None:
        raise ValueError('missing kernel header')

    for _, raw in chain((first_section,), lines):
        if raw.rstrip(b'\r\n') != TITLE:
            continue
        if found_section:
            raise ValueError('duplicate LSMOD')
        found_section = True
        _, columns = next(lines, (0, b''))
        if columns.split() != [b'Module', b'Size', b'Used', b'by']:
            raise ValueError('missing LSMOD columns')
        for _, raw in lines:
            row = raw.strip()
            if END.fullmatch(row):
                break
            match = ROW.fullmatch(row)
            if not match:
                raise ValueError('malformed or interrupted LSMOD')
            name = match[1]
            if name in names or len(names) >= 4096 or len(name) > 64:
                raise ValueError('duplicate or unsupported module name inventory')
            names.add(name)
        else:
            raise ValueError('unterminated LSMOD')
    if not found_section:
        raise ValueError('missing LSMOD')
    digest = hashlib.sha256(b''.join(n + b'\n' for n in sorted(names))).hexdigest()
    return dict(banner_match=BANNERS.get(banner, 'unknown'), banner_sha256=banner,
                module_count=len(names), module_names_sha256=digest,
                matches_stock_names=digest == STOCK_NAMES,
                listed={name: name.encode() in names for name in FOCUS})


def inspect(path):
    with open(path, 'rb') as source:
        if os.fstat(source.fileno()).st_size > MAX_ARCHIVE:
            raise ValueError('ZIP exceeds size limit')
        with zipfile.ZipFile(source) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or 'main_entry.txt' not in names:
                raise ValueError('ambiguous ZIP or missing main_entry')
            if archive.getinfo('main_entry.txt').file_size > 256:
                raise ValueError('oversized main_entry')
            name = archive.read('main_entry.txt').decode('ascii').strip()
            if not re.fullmatch(r'(?:dumpstate|bugreport)-[A-Za-z0-9._-]+\.txt', name) or name not in names:
                raise ValueError('invalid main_entry')
            if archive.getinfo(name).file_size > MAX_MEMBER:
                raise ValueError('main report exceeds size limit')
            with archive.open(name) as stream:
                return compare(stream)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bugreport')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.bugreport), indent=2))
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        parser.exit(1, f'Unsupported report: {exc}\n')
