"""One fixed static arm64 Mach-O for the lab init, not a general linker.

The position-independent .text has no external symbols or relocations. It
occupies part of one 16 KiB RX segment and enters via ARM_THREAD_STATE64.
No source or SDK headers from XNU are embedded here.
"""
import struct

BASE = 0x100000000
PAGE = 0x4000
CODE_OFFSET = 0x1000


def build_init(text):
    if not text or len(text) > PAGE - CODE_OFFSET:
        raise ValueError("init .text must fit the fixed 16 KiB segment")
    pagezero = struct.pack("<II16sQQQQIIII", 0x19, 72, b"__PAGEZERO",
                           0, BASE, 0, 0, 0, 0, 0, 0)
    textseg = struct.pack("<II16sQQQQIIII", 0x19, 152, b"__TEXT",
                          BASE, PAGE, 0, PAGE, 5, 5, 1, 0)
    section = struct.pack("<16s16sQQIIIIIIII", b"__text", b"__TEXT",
                          BASE + CODE_OFFSET, len(text), CODE_OFFSET,
                          2, 0, 0, 0x80000400, 0, 0, 0)
    state = bytearray(272)       # 29 GPRs, FP, LR, SP, PC, CPSR + pad
    struct.pack_into("<Q", state, 256, BASE + CODE_OFFSET)
    thread = struct.pack("<IIII", 5, 288, 6, 68) + state
    commands = pagezero + textseg + section + thread
    header = struct.pack("<8I", 0xFEEDFACF, 0x100000C, 0, 2, 3,
                         len(commands), 1, 0)
    if len(header + commands) > CODE_OFFSET:
        raise ValueError("load commands overlap code")
    image = bytearray(PAGE)
    image[:len(header + commands)] = header + commands
    image[CODE_OFFSET:CODE_OFFSET + len(text)] = text
    return bytes(image)
