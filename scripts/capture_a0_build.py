#!/usr/bin/env python3
"""Content identities and critical profile checks for the offline p3s build."""
import hashlib
from pathlib import PurePosixPath
import re
import stat
import struct
import tarfile

from capture_a0_formats import require, config_values, config_diff, digest

CRITICAL = dict(CONFIG_CC_IS_CLANG='y', CONFIG_CLANG_VERSION='110001',
    CONFIG_LD_IS_LLD='y', CONFIG_LTO='y', CONFIG_LTO_CLANG='y',
    CONFIG_CFI_CLANG='y', CONFIG_CFI_CLANG_SHADOW='y', CONFIG_CFI_PERMISSIVE='n',
    CONFIG_COMPAT_VDSO='y', CONFIG_MODVERSIONS='y', CONFIG_TRIM_UNUSED_KSYMS='y',
    CONFIG_MALI_DDK_VALHALL_R38P0='y')
TUI_BEFORE = '42c5595348f0670cf18f1e48f8f4fc532e000f9714d8bf75678763c3d45eb067'
TUI_AFTER = 'eedc69cb4c0b8e82561925badb1cd765ce266a99dd91ad2aa224a878320084d7'


def profile(source, generated):
    values = config_values(generated)
    mismatches = {k:dict(expected=v, actual=values.get(k)) for k,v in CRITICAL.items()
                  if values.get(k) != v}
    differences = [dict(key=row['key'],source_value_sha256=row['source_value_sha256'],
                        generated_value_sha256=row['stock_value_sha256'])
                   for row in config_diff(source, generated)]
    return dict(critical_profile_preserved=not mismatches, critical_mismatches=mismatches,
        selected_config={k:values.get(k) for k in CRITICAL},
        source_defconfig_equal=not differences, config_differences=differences,
        generated_config_sha256=digest(generated.encode()), module_abi_established=False)


def vdso(data, elfclass, machine):
    require(len(data) >= 64 and data[:4] == b'\x7fELF' and data[4] == elfclass
            and data[5:7] == b'\x01\x01', 'VDSO ELF class/encoding differs')
    require(struct.unpack_from('<HHI',data,16) == (3,machine,1), 'VDSO ELF type/machine differs')
    return dict(bytes=len(data),sha256=digest(data),elf_class=elfclass,machine=machine,
                elf_header_only=True,runtime_execution_tested=False)


def partial_versions(data, stock):
    """Read genksyms linker assignments; do not fabricate a Module.symvers."""
    require(len(data) <= 1024*1024, 'symversions bound')
    values = {}
    for line in data.decode().splitlines():
        match = re.fullmatch(r'__crc_([A-Za-z_][A-Za-z0-9_]*) = (0x[0-9a-fA-F]{1,8});',line)
        require(match and match[1] not in values, 'invalid/duplicate genksyms assignment')
        values[match[1]] = f'0x{int(match[2],16):08x}'
    require(values, 'empty genksyms assignments')
    comparisons = {n:dict(candidate_crc=crc,stock_crcs=stock[n]['crcs'],
                    matches_stock=stock[n]['crcs'] == [crc])
                   for n,crc in sorted(values.items()) if n in stock}
    return dict(sha256=digest(data),assignments=len(values),compared=comparisons,
                full_module_symvers=False,module_abi_established=False)


def blob(stream, size):
    require(0 <= size <= 1024**3, 'toolchain file exceeds bound')
    h = hashlib.sha1(b'blob '+str(size).encode()+b'\0')
    remaining = size
    while remaining:
        chunk = stream.read(min(remaining,1024*1024))
        require(chunk, 'truncated file'); h.update(chunk); remaining -= len(chunk)
    return h.digest()


def tree_identity(entries):
    """Recreate Git trees from bounded (name, mode, blob-hash, size) entries."""
    root = {}; total = count = 0
    for name,mode,sha,size in entries:
        p = PurePosixPath(name)
        require(p.parts and not p.is_absolute() and '..' not in p.parts and str(p) == name,
                'unsafe tree path')
        node = root
        for part in p.parts[:-1]:
            node = node.setdefault(part,{})
            require(isinstance(node,dict), 'path traverses file/link')
        require(p.name not in node, 'duplicate/file-directory collision')
        node[p.name] = (mode,sha)
        count += 1; total += size
        require(count <= 100000 and total <= 4*1024**3, 'toolchain census bound')
    def tree(node):
        rows=[]
        for name,v in sorted(node.items(),key=lambda item:(item[0]+('/' if isinstance(item[1],dict) else '')).encode()):
            mode,sha = ('40000',tree(v)) if isinstance(v,dict) else v
            rows.append(mode.encode()+b' '+name.encode()+b'\0'+sha)
        raw=b''.join(rows)
        return hashlib.sha1(b'tree '+str(len(raw)).encode()+b'\0'+raw).digest()
    return dict(tree=tree(root).hex(),members=count,content_bytes=total)


def archive_tree(path):
    """Gitiles transport identity without extraction or execution."""
    import io
    def entries():
        seen=set(); directories=set()
        with tarfile.open(path,'r|gz') as t:
            for m in t:
                name=m.name.removeprefix('./').rstrip('/'); p=PurePosixPath(name)
                require(p.parts and not p.is_absolute() and '..' not in p.parts and str(p)==name,
                        'unsafe archive path')
                require(name not in seen and len(seen)<100000,'duplicate/member bound');seen.add(name)
                if m.isdir():directories.add(name);continue
                require(not any(str(parent) in seen and str(parent) not in directories
                                for parent in p.parents if str(parent)!='.'),'archive parent is not a directory')
                if m.issym():
                    data=m.linkname.encode();yield name,'120000',blob(io.BytesIO(data),len(data)),len(data)
                else:
                    require(m.isfile(),'unsupported archive member')
                    yield name,'100755' if m.mode&0o111 else '100644',blob(t.extractfile(m),m.size),m.size
    return tree_identity(entries())


def directory_tree(path):
    """Verify toolchain files/modes/links; ignore only root .git metadata."""
    import io
    def entries(directory):
        for p in directory.iterdir():
            if directory==path and p.name=='.git':continue
            mode=p.lstat().st_mode
            if stat.S_ISDIR(mode):yield from entries(p)
            elif stat.S_ISLNK(mode):
                data=str(p.readlink()).encode();yield str(p.relative_to(path)),'120000',blob(io.BytesIO(data),len(data)),len(data)
            else:
                require(stat.S_ISREG(mode),'special toolchain file')
                size=p.stat().st_size
                with p.open('rb') as f:sha=blob(f,size)
                yield str(p.relative_to(path)),'100755' if mode&0o111 else '100644',sha,size
    return tree_identity(entries(path))


def patch_tui(data):
    require(digest(data)==TUI_BEFORE,'requires original pinned TUI Makefile')
    for path in (b'drivers/video/fbdev/exynos/dpu30',b'drivers/video/fbdev/exynos/panel',b'drivers/misc/tzdev/include/tzdev'):
        old=b'ccflags-y += -I'+path+b'\n'
        require(data.count(old)==1,'TUI include anchor differs')
        data=data.replace(old,b'ccflags-y += -I$(srctree)/'+path+b'\n')
    require(digest(data)==TUI_AFTER,'patched TUI identity differs')
    return data
