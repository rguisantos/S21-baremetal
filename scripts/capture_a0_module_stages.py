#!/usr/bin/env python3
"""Stable intermediate copies and comparison of pre/post-modpost imports."""
import os
import stat

from capture_a0_crc_trace import identity
from capture_a0_formats import digest, require
from capture_a0_module_policy import Elf, module, SYMBOL
from capture_a0_stack_versions import version_rows

MODPOST_SHA = '083ce8e6dc233be0cb4d347bd7e2de850639d7b9a05c3cdc707f6c1fe8dbac98'
NAMES = ('s2mpb02-core.o','s2mpb02-irq.o','s2mpb02_mfd.o','s2mpb02_mfd.lto.o',
         's2mpb02_mfd.mod','s2mpb02_mfd.mod.c','s2mpb02_mfd.mod.o','s2mpb02_mfd.ko')
FILES = tuple('drivers/mfd/'+n for n in NAMES) + tuple(
    'drivers/mfd/.'+n+'.cmd' for n in NAMES if n.endswith(('.o','.ko','.mod'))) + tuple(
    'drivers/mfd/'+n+'.symversions' for n in NAMES[:3])
MAX_COPY = 8*1024*1024


def patch_modpost(data):
    require(digest(data)==MODPOST_SHA, 'requires original pinned modpost Makefile')
    old=b'$(LD) $(ld_flags) -r -o $(@)'
    require(data.count(old)==1, 'prelink command ambiguity')
    return data.replace(old,b'$(LD) $(ld_flags) $(KBUILD_LDFLAGS_MODULE) -r -o $(@)')


def snapshot(root, destination):
    """Call only after make exits; reject unstable/non-regular intermediate files."""
    require(not destination.exists(), 'snapshot destination must be new')
    destination.mkdir(parents=True); result={}; total=0
    for name in FILES:
        p=root/name
        try:before=p.lstat()
        except FileNotFoundError:
            result[name]=dict(state='missing');continue
        require(stat.S_ISREG(before.st_mode) and before.st_size<=MAX_COPY, 'intermediate type/size')
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as f:
            opened=os.fstat(f.fileno());require(identity(before)==identity(opened), 'intermediate replaced')
            data=f.read(MAX_COPY+1);after=os.fstat(f.fileno())
        require(identity(opened)==identity(after)==identity(p.lstat()) and len(data)<=MAX_COPY,
                'intermediate changed during read')
        total+=len(data);require(total<=64*1024*1024, 'snapshot total bound')
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        result[name]=dict(state='regular',bytes=len(data),sha256=digest(data))
    return result


def imports(data):
    elf=Elf(data,require_module_metadata=False,max_sections=16384); result={}
    for s in elf.symbols[1:]:
        if s['section']!=0:continue
        require(SYMBOL.fullmatch(s['name']) and s['binding'] in (1,2) and s['name'] not in result,
                'intermediate undefined symbol ABI')
        result[s['name']]='weak' if s['binding']==2 else 'strong'
    return result


def link_commands(evidence, work):
    result={}
    for label in ('original','aligned'):
        for phase, suffix in (('pre','.lto.o'),('final','.ko')):
            text=(evidence/(label+'-'+phase)/('drivers/mfd/.s2mpb02_mfd'+suffix+'.cmd')).read_text()
            require(len(text)<=256*1024, 'link command bound')
            first=text.splitlines()[0];key,sep,command=first.partition(' := ')
            require(sep and key.startswith('cmd_') and command.strip(), 'link command record')
            result[label+'-'+phase]=command.replace(str(work),'<WORK>')
    return result


def analyze(pre, generated_source, final, providers):
    before=imports(pre); generated=version_rows(generated_source); after=module(final)
    relevant=before.keys()-{'__this_module','_GLOBAL_OFFSET_TABLE_'}
    require(set(generated)==relevant|{'module_layout'}, 'generated versions differ from prelink imports/layout')
    require(generated==after['versions'], 'version payload changed after modpost')
    names=set(after['imports'])|set(generated)
    require(names<=providers.keys(), 'reference provider missing')
    mismatches=sorted(n for n,v in generated.items() if providers[n]['crc']!=v)
    e=Elf(final); text=e.read(e.sections['.text'])
    return dict(prelink_imports=before,prelink_effective_imports=len(relevant),
        generated_records=len(generated),final_imports=after['imports'],
        final_version_records=len(after['versions']),
        imports_added_after_modpost=sorted(after['imports'].keys()-relevant),
        imports_removed_after_modpost=sorted(relevant-after['imports'].keys()),
        final_imports_without_versions=sorted(after['imports'].keys()-generated.keys()),
        crc_mismatches=mismatches,version_payload_unchanged=True,
        strict_final_crc_coverage=not mismatches and set(after['imports'])<=generated.keys(),
        final_text_sha256=digest(text),module_abi_established=False)
