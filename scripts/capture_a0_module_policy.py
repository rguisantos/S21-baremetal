#!/usr/bin/env python3
"""Bounded offline module metadata and necessary loader-policy checks.

Supports the pinned ELF64 LE/AArch64, absolute-CRC, 24-byte kernel_symbol ABI.
Does not load modules, apply relocations to code, or approve runtime ABI.
"""
from collections import defaultdict
import re
import struct

from capture_a0_formats import require, digest, config_values
from capture_a0_modules import SYMBOL, cstring

MAX_MODULE=128*1024*1024
MAX_METADATA=16*1024*1024
EXPORTS={'__ksymtab':'EXPORT_SYMBOL','__ksymtab_gpl':'EXPORT_SYMBOL_GPL',
         '__ksymtab_gpl_future':'EXPORT_SYMBOL_GPL_FUTURE',
         '__ksymtab_unused':'EXPORT_UNUSED_SYMBOL','__ksymtab_unused_gpl':'EXPORT_UNUSED_SYMBOL_GPL'}
GPL={'GPL','GPL v2','GPL and additional rights','Dual BSD/GPL','Dual MIT/GPL','Dual MPL/GPL'}
MODNAME=re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*')


class Elf:
    def __init__(self,data,require_module_metadata=True,max_sections=4096):
        require(isinstance(max_sections,int) and 1<=max_sections<=16384,'section count budget')
        require(64<=len(data)<=MAX_MODULE,'module size bound')
        require(data[:7]==b'\x7fELF\x02\x01\x01','requires ELF64 little endian')
        require(struct.unpack_from('<HHI',data,16)==(1,183,1),'requires AArch64 ET_REL')
        off=struct.unpack_from('<Q',data,40)[0]
        eh,_,ph,sz,count,names=struct.unpack_from('<6H',data,52)
        require(eh==64 and ph==0 and sz==64 and 0<names<count<=max_sections and off>=64
                and off+64*count<=len(data),'section table bounds')
        self.data=data;self.rows=[struct.unpack_from('<IIQQQQIIQQ',data,off+64*i) for i in range(count)]
        self.cache={};self.used=0
        require(self.rows[names][1]==3,'section names type')
        strings=self.read(names);self.sections={}
        for i,row in enumerate(self.rows[1:],1):
            require(row[1]==8 or row[4]+row[5]<=len(data),'section exceeds file')
            name=cstring(strings,row[0]);require(name and name not in self.sections,'section name duplicate/empty')
            self.sections[name]=i
        require('.symtab' in self.sections and (not require_module_metadata or
                ('.modinfo' in self.sections and '__versions' in self.sections)),
                'required metadata missing')
        self.symindex=self.sections['.symtab'];s=self.rows[self.symindex]
        require(s[1]==2 and s[9]==24 and s[5]%24==0 and s[5]//24<=200000 and
                0<s[6]<count and self.rows[s[6]][1]==3,'symbol table ABI/bounds')
        raw=self.read(self.symindex);strings=self.read(s[6]);self.symbols=[]
        for pos in range(0,len(raw),24):
            name,info,other,section,value,size=struct.unpack_from('<IBBHQQ',raw,pos)
            self.symbols.append(dict(name=cstring(strings,name),binding=info>>4,
                type=info&15,section=section,value=value,size=size))

    def read(self,index):
        require(0<index<len(self.rows),'section index bound')
        if index not in self.cache:
            row=self.rows[index]
            require(row[1]!=8 and not row[2]&0x800 and row[4]+row[5]<=len(self.data),
                    'unsupported metadata section')
            self.used+=row[5];require(self.used<=MAX_METADATA,'metadata read bound')
            self.cache[index]=self.data[row[4]:row[4]+row[5]]
        return self.cache[index]

    def relocations(self,target):
        result={}
        for i,row in enumerate(self.rows[1:],1):
            if row[1]!=4 or row[7]!=target:continue
            require(row[6]==self.symindex and row[9]==24 and row[5]%24==0,'relocation table ABI')
            raw=self.read(i)
            for pos in range(0,len(raw),24):
                offset,info,addend=struct.unpack_from('<QQq',raw,pos);symbol=info>>32;kind=info&0xffffffff
                width={257:8,258:4}.get(kind)
                require(width and offset+width<=self.rows[target][5] and symbol<len(self.symbols)
                        and offset not in result,'relocation bounds/type/symbol/duplicate')
                result[offset]=(kind,self.symbols[symbol],addend)
        return result

    def export_table(self):
        found={}
        for sec,kind in EXPORTS.items():
            if sec not in self.sections:continue
            index=self.sections[sec];raw=self.read(index)
            require(len(raw)%24==0,'kernel_symbol ABI differs')
            reloc=self.relocations(index);n=len(raw)//24
            require(all(off%24 in (0,8,16) and row[0]==257 for off,row in reloc.items()),
                    'unexpected export pointer relocation')
            require(all(i*24 in reloc and (0<reloc[i*24][1]['section']<len(self.rows)
                    or reloc[i*24][1]['section']==0xfff1) for i in range(n)),
                    'export value relocation missing/undefined')
            crcname=sec.replace('__ksymtab','__kcrctab',1)
            require(crcname in self.sections or n==0,'export CRC table missing')
            crcs=self.read(self.sections[crcname]) if n else b''
            require(len(crcs)==4*n,'export CRC table size differs')
            crcreloc=self.relocations(self.sections[crcname]) if n else {}
            require(set(crcreloc)==set(range(0,4*n,4)),'unexpected export CRC relocation offsets')
            def string_at(offset):
                require(offset in reloc,'export string relocation missing')
                typ,sym,addend=reloc[offset]
                require(typ==257 and 0<sym['section']<len(self.rows),'export string ABS64 ABI')
                return cstring(self.read(sym['section']),sym['value']+addend)
            for i in range(n):
                name=string_at(i*24+8);require(SYMBOL.fullmatch(name) and name not in found,'export identity')
                namespace=string_at(i*24+16) if i*24+16 in reloc else None
                if namespace is None:require(raw[i*24+16:i*24+24]==bytes(8),'export namespace pointer')
                require(i*4 in crcreloc,'export CRC relocation missing')
                typ,sym,addend=crcreloc[i*4]
                require(typ==258 and sym['section']==0xfff1 and sym['name']=='__crc_'+name
                        and addend==0 and sym['value']<=0xffffffff,'export CRC ABS32 ABI differs')
                found[name]=dict(crc=f"0x{sym['value']:08x}",export=kind,namespace=namespace)
        return found


def module(data):
    elf=Elf(data);raw=elf.read(elf.sections['.modinfo']);require(raw.endswith(b'\0'),'modinfo termination')
    fields=defaultdict(list)
    for item in raw.split(b'\0'):
        if not item:continue
        key,sep,value=item.partition(b'=');require(sep and key,'modinfo format')
        if key in (b'name',b'vermagic',b'depends',b'license',b'import_ns'):
            fields[key.decode()].append(value.decode('utf-8'))
    require(all(len(fields[k])==1 for k in ('name','vermagic','depends')),'module identity ambiguity')
    name=fields['name'][0];require(MODNAME.fullmatch(name),'module name')
    depends=fields['depends'][0].split(',') if fields['depends'][0] else []
    require(all(MODNAME.fullmatch(x) for x in depends) and len(set(depends))==len(depends),'depends names')
    versions={};raw=elf.read(elf.sections['__versions'])
    require(raw and len(raw)%64==0,'versions ABI')
    for off in range(0,len(raw),64):
        crc=struct.unpack_from('<Q',raw,off)[0];symbol=cstring(raw[off+8:off+64],0)
        require(crc<=0xffffffff and SYMBOL.fullmatch(symbol) and symbol not in versions,'version record')
        versions[symbol]=f'0x{crc:08x}'
    require('module_layout' in versions,'module_layout missing')
    imports={}
    for sym in elf.symbols[1:]:
        require(sym['section']!=0xfff2 or sym['name'].startswith('__gnu_lto'),
                'unsupported common symbol')
        if sym['section']!=0:continue
        require(SYMBOL.fullmatch(sym['name']) and sym['binding'] in (1,2),'undefined symbol ABI')
        require(sym['name'] not in imports,'duplicate undefined symbol')
        imports[sym['name']]='weak' if sym['binding']==2 else 'strong'
    return dict(name=name,sha256=digest(data),bytes=len(data),vermagic=fields['vermagic'][0],
        depends=depends,licenses=fields['license'],import_namespaces=sorted(set(fields['import_ns'])),
        versions=versions,imports=imports,exports=elf.export_table())


def symvers(text):
    require(len(text)<=16*1024*1024,'symvers bound');result={}
    for line in text.splitlines():
        row=line.split();require(len(row) in (4,5),'symvers format')
        crc,name,provider,kind=row[:4]
        require(re.fullmatch('0x[0-9a-fA-F]{8}',crc) and SYMBOL.fullmatch(name) and
                kind in EXPORTS.values() and name not in result,'symvers identity/duplicate')
        result[name]=dict(crc=crc.lower(),provider=provider,export=kind,namespace=row[4] if len(row)==5 else None)
    require(result,'empty symvers');return result


def same_magic(module_magic,kernel_magic,has_crcs,modversions=True):
    require(' ' in module_magic and ' ' in kernel_magic,'vermagic format')
    if modversions and has_crcs:
        module_magic=module_magic[module_magic.index(' '):]
        kernel_magic=kernel_magic[kernel_magic.index(' '):]
    return module_magic==kernel_magic


def evaluate(modules,kernel_exports,requested,kernel_magic,config):
    """Source-derived checks and explicit conservative gaps; no ABI/load approval."""
    require(len(requested)==len(set(requested)) and set(requested)<=modules.keys(),'requested set')
    settings=config_values(config);require(settings.get('CONFIG_MODVERSIONS')=='y','requires MODVERSIONS profile')
    require(settings.get('CONFIG_MODULE_REL_CRCS') in (None,'n') and
            settings.get('CONFIG_HAVE_ARCH_PREL32_RELOCATIONS') in (None,'n'),'unsupported relative ABI')
    selected={n:modules[n] for n in requested};exports={k:dict(v,owner='vmlinux') for k,v in kernel_exports.items()}
    canonical={n.replace('-','_'):n for n in selected}
    require(len(canonical)==len(selected),'ambiguous canonical module names')
    duplicates=[]
    for owner,m in selected.items():
        for name,row in m['exports'].items():
            if name in exports:duplicates.append(name)
            else:exports[name]=dict(row,owner=owner)
    errors=[];warnings=[];blocks=[];unversioned=[];edges={n:set() for n in requested};optional={};gplonly={n:False for n in requested}
    symbol_edges={n:set() for n in requested};future=defaultdict(list)
    initial_taint={n:not m['licenses'] or any(x not in GPL for x in m['licenses']) for n,m in selected.items()}
    for name,m in selected.items():
        if not same_magic(m['vermagic'],kernel_magic,bool(m['versions'])):errors.append([name,'vermagic'])
        declared={canonical.get(n.replace('-','_'),n) for n in m['depends']}
        missing_dep=sorted(declared-selected.keys())
        if missing_dep:blocks.append([name,'declared_dependencies_missing',missing_dep])
        edges[name].update(declared&selected.keys())
        optional[name]=[]
        for symbol,binding in m['imports'].items():
            row=exports.get(symbol)
            if row is None:
                if binding=='weak':optional[name].append(symbol)
                else:errors.append([name,'strong_import_missing',symbol])
                continue
            if binding=='weak':
                blocks.append([name,'available_weak_resolution_order_not_modeled',symbol])
                continue
            if row['owner']!='vmlinux':
                edges[name].add(row['owner']);symbol_edges[name].add(row['owner'])
            if row['export'] in ('EXPORT_SYMBOL_GPL','EXPORT_UNUSED_SYMBOL_GPL'):gplonly[name]=True
            if row['export']=='EXPORT_SYMBOL_GPL_FUTURE':future[name].append(symbol)
            if row['namespace'] is not None and row['namespace'] not in m['import_namespaces']:
                issue=[name,'namespace_not_imported',symbol,row['namespace']]
                (warnings if settings.get('CONFIG_MODULE_ALLOW_MISSING_NAMESPACE_IMPORTS')=='y' else errors).append(issue)
            if symbol not in m['versions']:
                warnings.append([name,'import_version_missing_source_permits',symbol])
                blocks.append([name,'crc_coverage_not_established',symbol])
                unversioned.append(dict(module=name,symbol=symbol,provider=row['owner'],
                    provider_crc=row['crc'],consumer_version_record_present=False))
            elif m['versions'][symbol]!=row['crc']:errors.append([name,'crc_mismatch',symbol])
        layout=exports.get('module_layout')
        if layout is None or layout['crc']!=m['versions']['module_layout']:errors.append([name,'module_layout_mismatch'])
    taint=dict(initial_taint)
    for _ in range(len(selected)+1):
        next_taint={n:taint[n] or any(taint[d] for d in deps) for n,deps in symbol_edges.items()}
        if next_taint==taint:break
        taint=next_taint
    for name in selected:
        if taint[name] and gplonly[name]:errors.append([name,'gpl_only_with_proprietary_taint'])
        if taint[name] and future[name]:warnings.append([name,'gpl_future_warning',sorted(future[name])])
    order=[];pending={n:set(d) for n,d in edges.items()};rank={n:i for i,n in enumerate(requested)}
    while pending:
        ready=sorted((n for n,d in pending.items() if not d),key=rank.get)
        if not ready:blocks.append(['dependency_cycle',sorted(pending)]);break
        for n in ready:
            order.append(n);pending.pop(n)
        for d in pending.values():d.difference_update(ready)
    return dict(strict_plan_checks_passed=not (errors or duplicates or blocks),errors=errors,warnings=warnings,plan_blocks=blocks,
        modeled_source_checks_passed=not (errors or duplicates),
        unversioned_imports=unversioned,
        duplicate_exports=sorted(duplicates),selected_count=len(selected),selected_names=sorted(selected),
        dependency_order=order,dependencies={n:sorted(d) for n,d in sorted(edges.items())},
        weak_unresolved={n:v for n,v in optional.items() if v},
        proprietary_taint_closure=sorted(n for n,v in taint.items() if v),
        module_abi_established=False,runtime_loading_tested=False,a0_complete=False)
