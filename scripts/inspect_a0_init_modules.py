#!/usr/bin/env python3
"""Read the pinned boot ramdisk init and bind its static module-loading calls.

The init ELF and modules are never executed. Native readers receive sealed
snapshots. This is selected static evidence, not an Android boot simulation.
"""
import argparse
import json
import lzma
from pathlib import Path
import re
import stat
import struct
import subprocess

from capture_a0_formats import digest, layout, require
from capture_a0_inputs import checked_buffer, read_checked, sealed_input
from capture_a0_modules import cpio, gunzip
from check_capture_a0_parent import lz4_frame

ROOT = Path(__file__).resolve().parents[1]
INIT_PIN = dict(bytes=1502328, sha256='389d314c35d4d058da8845213191ff1058275fd403809ea2c8b244983825775b')
FUNCTIONS = {
    0x25d304:'android::init::GetModuleLoadList(',
    0x25d4cc:'android::init::LoadKernelModules(',
    0x25ddec:'android::init::FirstStageMain(',
    0x2f3e88:'Modprobe::Modprobe(',
    0x2f4684:'Modprobe::GetDependencies(',
    0x2f4744:'Modprobe::InsmodWithDeps(',
    0x2f4d30:'Modprobe::LoadWithAliases(',
    0x2f5084:'Modprobe::LoadListedModules(',
    0x2f6344:'Modprobe::Insmod(',
    0x32c820:'syscall',
}
CALLS = {0x25ec18:0x25d4cc, 0x25d798:0x25d304, 0x25d7a8:0x2f3e88,
    0x25d824:0x2f5084, 0x25d9d0:0x2f5084, 0x2f50dc:0x2f4d30,
    0x2f4f84:0x2f4744, 0x2f47a4:0x2f4684, 0x2f4804:0x2f4d30,
    0x2f4ab8:0x2f6344, 0x2f65ac:0x32c820}
# These words support the selected dependency loop and syscall argument, not
# an automatic proof of all the C++ container/alias/blocklist semantics.
WORDS = {0x2f47e8:0xd10062d6, 0x2f4824:0x91006028, 0x2f482c:0x54fffd61,
    0x2f659c:0x52802220, 0x2f65a8:0x2a1f03e3}
STRINGS = {0x35d8:b'/lib/modules', 0x6907:b'/modules.dep',
    0xc844:b'modules.load', 0x61c1:b'modules.load.recovery',
    0xcba3:b'system/core/libmodprobe/libmodprobe.cpp'}


def pin(data): return dict(bytes=len(data), sha256=digest(data))


def section(data, wanted):
    require(type(data) is bytes and len(data)>=64 and data[:7]==b'\x7fELF\x02\x01\x01', 'ELF64 LE header')
    require(struct.unpack_from('<HHI',data,16)==(2,183,1), 'AArch64 executable required')
    at = struct.unpack_from('<Q',data,40)[0]
    size,count,names = struct.unpack_from('<HHH',data,58)
    require(size==64 and 0<names<count<=4096 and at>=64 and at+count*64<=len(data), 'ELF section table bounds')
    rows = [struct.unpack_from('<IIQQQQIIQQ',data,at+64*i) for i in range(count)]
    r=rows[names];require(r[1]==3 and r[4]+r[5]<=len(data), 'section names extent/type')
    strings=data[r[4]:r[4]+r[5]];found=[]
    for r in rows[1:]:
        require(r[0]<len(strings), 'section name offset')
        end=strings.find(b'\0',r[0]);require(end>=0, 'section name terminator')
        if strings[r[0]:end]==wanted.encode(): found.append(r)
    require(len(found)==1, 'missing/duplicate requested section')
    r=found[0];require(r[1]==1 and not r[2]&0x800 and r[4]+r[5]<=len(data), 'section data extent/type')
    return r[3],r[4],data[r[4]:r[4]+r[5]]


def mini_debug(packed):
    require(type(packed) is bytes and 0<len(packed)<=1024*1024, 'mini debug input bound')
    dec=lzma.LZMADecompressor(memlimit=64*1024*1024)
    raw=dec.decompress(packed,max_length=4*1024*1024+1)
    require(len(raw)<=4*1024*1024 and dec.eof and not dec.unused_data, 'mini debug incomplete/concatenated/oversized')
    return raw


def branch(word, pc):
    require(word&0xfc000000==0x94000000, 'expected direct BL')
    delta=word&0x3ffffff
    if delta&(1<<25):delta-=1<<26
    return pc+4*delta


def inspect_init(raw):
    checked_buffer(raw,INIT_PIN)
    address,offset,text=section(raw,'.text')
    _,_,packed=section(raw,'.gnu_debugdata');debug=mini_debug(packed)
    with sealed_input(debug,pin(debug)) as (fd,path):
        symbols=subprocess.check_output(['nm','-C',path],pass_fds=(fd,),text=True,timeout=30)
    selected={}
    for pc,prefix in FUNCTIONS.items():
        names=[m.group(2) for line in symbols.splitlines()
            if (m:=re.fullmatch(r'([0-9a-fA-F]+) [Tt] (.+)',line))
            and int(m.group(1),16)==pc and (m.group(2)==prefix or m.group(2).startswith(prefix))]
        require(names and address<=pc<address+len(text), 'debug symbol binding differs')
        selected[hex(pc)]=sorted(set(names))
    def word(pc):
        require(pc%4==0 and address<=pc<=address+len(text)-4, 'instruction outside text')
        return struct.unpack_from('<I',text,pc-address)[0]
    for pc,target in CALLS.items():require(branch(word(pc),pc)==target, 'selected call target differs')
    for pc,expected in WORDS.items():require(word(pc)==expected, 'selected instruction differs')
    for at,value in STRINGS.items():require(raw[at:at+len(value)+1]==value+b'\0', 'selected literal differs')
    with sealed_input(raw,INIT_PIN) as (fd,path):
        listing=subprocess.check_output(['bash',str(ROOT/'scripts/cross-run.sh'),str(ROOT/'tools/root'),
            str(ROOT/'tools/root/usr/bin/aarch64-linux-gnu-objdump'),'-d',path],pass_fds=(fd,),text=True,timeout=30)
    decoded={}
    for line in listing.splitlines():
        m=re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)',line)
        if m and int(m[1],16) in (CALLS.keys()|WORDS.keys()):
            pc=int(m[1],16);require(int(m[2],16)==word(pc), 'GNU word differs')
            decoded[hex(pc)]=dict(word=m[2],instruction=m[3].strip())
    require(len(decoded)==len(CALLS)+len(WORDS), 'GNU selected coverage incomplete')
    return dict(init=INIT_PIN,mini_debug=pin(debug),mini_debug_compressed=pin(packed),
        text_section=dict(address=hex(address),file_offset=offset,**pin(text)),
        symbols=selected,calls={hex(pc):hex(target) for pc,target in CALLS.items()},
        selected_instructions=decoded,literals={hex(at):value.decode() for at,value in STRINGS.items()},
        native_readers_use_sealed_snapshots=True,init_executed=False,modules_loaded=False,
        actual_device_boot_observed=False,exact_runtime_order_established=False,a0_complete=False,
        interpretation='Selected static path: first-stage init calls LoadKernelModules; LoadListedModules calls LoadWithAliases; InsmodWithDeps resolves dependencies recursively before Insmod. The selected loop walks dependency strings backwards. Insmod calls syscall with number 273 and flags 0.',
        limits=['Selected calls and operands, not complete symbolic execution of C++ containers',
            'Alias, blocklist, softdep, recovery selection and live cmdline require separate semantics',
            'This identifies the stock file implementation, not execution or successful module initialization',
            'No claim that the earlier generic DFS order equals the Samsung loader order'])


def inspect(boot):
    pins=json.loads((ROOT/'docs/references/capture-a0-pins-hzc2.json').read_text())
    packed=read_checked(boot,pins['stock_lz4']['boot.img.lz4'])
    raw=checked_buffer(lz4_frame(packed,pins['stock_raw']['boot.img']['bytes']),pins['stock_raw']['boot.img'])
    part=next(p for p in layout(raw)['parts'] if p['name']=='ramdisk')
    compressed=raw[part['start']:part['end']];archive=gunzip(compressed);entries=cpio(archive)
    require('init' in entries and entries['init']['kind']==stat.S_IFREG, 'regular init missing')
    return dict(schema='S21-A0-INIT-MODULE-LOADER-v1',boot_lz4=pins['stock_lz4']['boot.img.lz4'],
        boot_raw=pins['stock_raw']['boot.img'],ramdisk_gzip=pin(compressed),ramdisk_cpio=pin(archive),
        cpio_entries={n:dict(kind=e['kind'],**pin(e['data'])) for n,e in entries.items()},
        analysis=inspect_init(entries['init']['data']))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('boot_lz4',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        result=inspect(a.boot_lz4)
        with a.output.open('x') as file:file.write(json.dumps(result,indent=2)+'\n')
    except (OSError,ValueError,KeyError,struct.error,lzma.LZMAError,subprocess.SubprocessError) as exc:
        p.exit(1,'INIT MODULE LOADER REFUSED: '+str(exc)+'\n')
    print('Pinned stock init: selected module-loading call chain PASS; runtime not executed')


if __name__=='__main__':main()
