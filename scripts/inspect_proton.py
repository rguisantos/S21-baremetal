#!/usr/bin/env python3
"""Read-only Proton ZIP inspection; no installation or execution of its files."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zipfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('mkpayload', ROOT/'tools/mkpayload.py')
wire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wire)
MAX_INPUT = 128 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fdt_nodes(data):
    wire.validate_dtb(data)
    _, _, pos, strings, _, _, _, _, _, size = struct.unpack_from('>10I', data)
    end = pos + size
    stack, nodes = [], {}
    while pos < end:
        token, = struct.unpack_from('>I', data, pos)
        pos += 4
        if token == 1:
            stop = data.index(0, pos)
            stack.append(data[pos:stop].decode('ascii'))
            pos = wire.align(stop+1, 4)
            path = '/'+'/'.join(filter(None, stack))
            wire.require(path not in nodes, 'duplicate FDT node path')
            nodes[path] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, name = struct.unpack_from('>II', data, pos)
            pos += 8
            stop = data.index(0, strings+name)
            key = data[strings+name:stop].decode('ascii')
            props = nodes['/'+'/'.join(filter(None, stack))]
            wire.require(key not in props, 'duplicate FDT property')
            props[key] = data[pos:pos+length]
            pos = wire.align(pos+length, 4)
        elif token == 9:
            break
    return nodes


def inspect(path):
    wire.require(path.stat().st_size <= MAX_INPUT, 'archive too large')
    archive = path.read_bytes()
    result = {'archive_size': len(archive), 'archive_sha256': digest(archive)}
    with zipfile.ZipFile(path) as z:
        def read(name):
            entries = [i for i in z.infolist() if i.filename == name]
            wire.require(len(entries) == 1 and entries[0].file_size <= MAX_INPUT, 'missing/duplicate/large '+name)
            return z.read(entries[0])
        image, vendor, installer = read('Image'), read('vendor_boot.img'), read('anykernel.sh')
    wire.require(len(image) >= 64 and image[56:60] == b'ARMd', 'missing ARM64 Image header')
    text, size, flags = struct.unpack_from('<QQQ', image, 8)
    version = re.search(rb'Linux version ([^\x00\n ]+)', image)
    pe = struct.unpack_from('<I', image, 60)[0]
    pe_fields = None
    if image[:2] == b'MZ' and pe+94 <= len(image) and image[pe:pe+4] == b'PE\0\0':
        pe_fields = {'machine': hex(struct.unpack_from('<H', image, pe+4)[0]),
                     'subsystem': struct.unpack_from('<H', image, pe+24+68)[0]}
    result['Image'] = {'size': len(image), 'sha256': digest(image), 'text_offset': hex(text),
                       'image_size': hex(size), 'flags': hex(flags),
                       'linux_version': version.group(1).decode() if version else None, 'pe': pe_fields}
    wire.require(len(vendor) >= 2112 and vendor[:8] == b'VNDRBOOT', 'invalid vendor_boot')
    v, page, kernel, ramdisk, rd_size = struct.unpack_from('<5I', vendor, 8)
    hs, dt_size, dt_addr = struct.unpack_from('<IIQ', vendor, 2096)
    wire.require(v == 3 and hs == 2112 and page in (2048,4096,8192,16384), 'only vendor_boot v3 supported')
    rd_off = wire.align(hs, page)
    dt_off = rd_off + wire.align(rd_size, page)
    wire.require(dt_off+dt_size <= len(vendor), 'truncated vendor_boot components')
    region = vendor[dt_off:dt_off+dt_size]
    wire.require(len(region) >= 32, 'short Android DT table')
    magic, total, header, entry, count, entries, _, table_ver = struct.unpack_from('>8I', region)
    wire.require(magic == 0xd7b7ab1e and total <= len(region) and header >= 32
                 and header <= entries and entry >= 32 and 0 < count <= 16
                 and entries+entry*count <= total, 'invalid Android DT table')
    trees = []
    for i in range(count):
        n, off = struct.unpack_from('>II', region, entries+i*entry)
        wire.require(off >= entries+entry*count and off+n <= total, 'invalid DT table entry')
        data = region[off:off+n]
        nodes = fdt_nodes(data)
        chosen = nodes.get('/chosen', {})
        uart = nodes.get('/uart@10840000', {})
        trees.append({'size': n, 'sha256': digest(data), 'offset_in_region': off,
                      'memory_nodes': [p for p,v in nodes.items() if v.get('device_type') == b'memory\0'],
                      'bootargs': chosen.get('bootargs', b'').rstrip(b'\0').decode(errors='replace'),
                      'initrd_properties': {k:hex(int.from_bytes(chosen[k], 'big')) for k in
                                           ('linux,initrd-start','linux,initrd-end') if k in chosen},
                      'uart1_status': uart.get('status', b'').rstrip(b'\0').decode()})
    result['vendor_boot'] = {'size': len(vendor), 'sha256': digest(vendor), 'version': v,
                             'page_size': page, 'kernel_addr': hex(kernel), 'ramdisk_addr': hex(ramdisk),
                             'dtb_addr': hex(dt_addr), 'vendor_ramdisk_size': rd_size,
                             'dtb_region_size': dt_size, 'dt_table_version': table_ver, 'trees': trees}
    result['anykernel.sh'] = {'sha256': digest(installer), 'size': len(installer)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.archive)
    except (OSError, ValueError, zipfile.BadZipFile, KeyError, struct.error) as exc:
        parser.exit(2, f'inspect_proton: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
