"""Explicit QEMU resident-image descriptor; no Samsung memory assumptions."""
import re
import struct
from . import boot_contract as c
BASE=0xfc000000
OFFSET=0x8000000
LIMIT=3<<30
MAGIC=b'S21RDSK\0'


def encode(size,base=BASE):
    raw=struct.pack('<8sIIQQ',MAGIC,1,0,base,size)
    decode(raw)
    return raw


def decode(raw):
    if len(raw)!=32:raise c.ContractError('resident descriptor length')
    magic,version,flags,base,size=struct.unpack('<8sIIQQ',raw)
    if magic!=MAGIC or version!=1 or flags or base!=BASE or not 0<size<=LIMIT or size%4096:
        raise c.ContractError('unsupported resident descriptor')
    return {'base':base,'size':size}


def allocation(claim):
    decode(struct.pack('<8sIIQQ',MAGIC,1,0,claim['base'],claim['size']))
    return c.Span(claim['base'],(claim['size']+0x3fff)&~0x3fff)


def parse_serial(serial):
    matches=re.findall(rb'^S21 RESIDENT DECLARATION ([0-9a-f]{1,16}) ([0-9a-f]{1,16})\r?$',serial,re.M)
    if len(matches)!=1:raise c.ContractError('missing/duplicate resident declaration')
    claim=dict(zip(('base','size'),(int(x,16) for x in matches[0])))
    allocation(claim)
    return claim


def verify_header(raw,size):
    if len(raw)<48 or size%4096 or struct.unpack_from('<IIQ',raw,32)!=(0x4253584e,4096,size//4096):
        raise c.ContractError('resident APFS header mismatch')
