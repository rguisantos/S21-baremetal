#!/usr/bin/env python3
"""
S21R10 Payload Packer

Packs R10 payload ELF + DTB + boot args into the format expected by the shim's loader.
Format matches the shim's loader.c expectations (S21R10 magic).

Usage:
    python3 mkpayload.py --kernel r8/build/r10_payload.elf --dtb extracted.dtb --output payload.bin
"""

import argparse
import struct
import sys
import os
import subprocess

PAGE_SIZE = 4096

def align_up(x, align):
    return (x + align - 1) & ~(align - 1)

def read_elf_entry(elf_path):
    """Extract entry point from ELF."""
    result = subprocess.run(
        ["aarch64-linux-gnu-readelf", "-h", elf_path],
        capture_output=True, text=True, check=True
    )
    for line in result.stdout.split('\n'):
        if "Entry point" in line:
            parts = line.split()
            if len(parts) >= 3 and parts[2].startswith('0x'):
                return int(parts[2], 16)
    # Fallback: _start_r10 symbol
    result = subprocess.run(
        ["aarch64-linux-gnu-nm", elf_path],
        capture_output=True, text=True
    )
    for line in result.stdout.split('\n'):
        if "_start_r10" in line:
            return int(line.split()[0], 16)
    return 0x80080000

def pack_payload(kernel_path, dtb_path, output_path):
    # Read files ONCE
    with open(kernel_path, 'rb') as f:
        kernel = f.read()
    with open(dtb_path, 'rb') as f:
        dtb = f.read()
    
    kernel_size = len(kernel)
    dtb_size = len(dtb)
    
    # Layout calculations
    HDR_SIZE = 680
    SEG_SIZE = 32
    KERN_OFF = 680 + 32  # After header + segment array
    KERN_END = align_up(KERN_OFF + kernel_size, PAGE_SIZE)
    DTB_OFF = KERN_END
    DTB_END = align_up(DTB_OFF + dtb_size, PAGE_SIZE)
    TOTAL_SIZE = DTB_OFF + dtb_size + 4096  # + boot args page
    
    print(f"Kernel: {kernel_size} bytes (0x{kernel_size:x})")
    print(f"DTB: {dtb_size} bytes (0x{dtb_size:x})")
    print(f"Kernel off: 0x{KERN_OFF:x}, end: 0x{KERN_OFF + kernel_size:x} -> aligned 0x{KERN_END:x}")
    print(f"DTB off: 0x{DTB_OFF:x}, end: 0x{DTB_END:x}")
    print(f"Total size: {TOTAL_SIZE} bytes")
    
    # Create payload buffer
    payload = bytearray()
    
    # 1. Header (680 bytes)
    payload.extend(b"S21R10  ")
    payload.extend(b'\x00' * (680 - 8))
    
    # 2. Segment entry at offset 680 (32 bytes)
    payload[680:712] = struct.pack('<QQQQ', 
        0x80080000,           # vmaddr
        align_up(kernel_size, PAGE_SIZE),  # vmsize
        680 + 32,             # file_off (after header + seg array)
        len(kernel)           # file_size
    )
    
    # 3. Kernel data at KERN_OFF (712)
    if len(payload) < 680 + 32:
        payload.extend(b'\x00' * (680 + 32 - len(payload)))
    payload[680+32:680+32+len(kernel)] = kernel
    
    # 4. Align to page boundary after kernel
    while len(payload) & (PAGE_SIZE - 1):
        payload.append(0)
    
    # Verify kernel end alignment
    assert len(payload) == (680 + 32 + len(kernel) + 4095) & ~4095
    
    # 5. DTB at DTB_OFF
    dtb_off = len(payload)
    payload.extend(dtb)
    
    # Align DTB to page
    while len(payload) & (PAGE_SIZE - 1):
        payload.append(0)
    
    # 4KB boot args (zeroed)
    payload.extend(b'\x00' * 4096)
    
    # Now fix up header fields
    # Header layout:
    # 0-7: magic (8 bytes)
    # 8-11: version (uint32)
    # 12-15: nsegs (uint32)
    # 16-23: virt_base (uint64)
    # 24-31: entry_va (uint64)
    # 32-39: dtb_off (uint64)
    # 40-47: dtb_size (uint64)
    # 48-55: kernel_end (uint64)
    # 56-63: phys_base (uint64)
    # 64-71: mem_size (uint64)
    # 72-679: cmdline (608 bytes)
    
    payload[0:8] = b"S21R10  "
    struct.pack_into('<II', payload, 8, 1, 1)  # version=1, nsegs=1
    struct.pack_into('<Q', payload, 16, 0x80080000)   # virt_base
    struct.pack_into('<Q', payload, 24, 0x80080000)   # entry_va
    struct.pack_into('<Q', payload, 32, DTB_OFF)      # dtb_off
    struct.pack_into('<Q', payload, 40, len(dtb))     # dtb_size
    struct.pack_into('<Q', payload, 48, align_up(len(kernel), PAGE_SIZE))  # kernel_end
    struct.pack_into('<Q', payload, 56, 0x80080000)   # phys_base
    struct.pack_into('<Q', payload, 64, 0x80000000)   # mem_size
    
    cmdline = b"clocksource=arch_sys_counter nr_cpus=8 androidboot.hardware=exynos2100"
    cmdline = cmdline.ljust(608, b'\x00')
    payload[72:72+608] = cmdline
    
    # Fix segment entry at offset 680
    payload[680:712] = struct.pack('<QQQQ',
        0x80080000,           # vmaddr
        align_up(kernel_size, PAGE_SIZE),  # vmsize
        680 + 32,             # file_off
        len(kernel)           # file_size
    )
    
    # Verify header
    payload_bytes = bytes(payload)
    assert payload_bytes[0:8] == b"S21R10  ", "Magic mismatch"
    assert struct.unpack('<I', payload[8:12])[0] == 1, "Version mismatch"
    assert struct.unpack('<I', payload[12:16])[0] == 1, "Nsegs mismatch"
    assert struct.unpack('<Q', payload[32:40])[0] == DTB_OFF, "DTB offset mismatch"
    assert struct.unpack('<Q', payload[40:48])[0] == len(dtb), "DTB size mismatch"
    
    # Verify DTB at correct offset
    dtb_magic = int.from_bytes(payload[DTB_OFF:DTB_OFF+4], 'big')
    assert dtb_magic == 0xd00dfeed, f"DTB magic mismatch at offset {hex(DTB_OFF)}"
    
    # Write output
    with open(output_path, 'wb') as f:
        f.write(payload)
    
    print(f"Payload written to {output_path}")
    print(f"  Total size: {len(payload)} bytes ({len(payload)/1024:.1f} KB)")
    print(f"  Kernel: {kernel_size} bytes at offset 0x{KERN_OFF:x}")
    print(f"  DTB: {dtb_size} bytes at offset 0x{DTB_OFF:x}")

def main():
    parser = argparse.ArgumentParser(description="S21R10 Payload Packer")
    parser.add_argument("--kernel", required=True, help="R10 payload ELF")
    parser.add_argument("--dtb", required=True, help="DTB file")
    parser.add_argument("--output", required=True, help="Output payload.bin")
    args = parser.parse_args()
    
    if not os.path.exists(args.kernel):
        print(f"Error: kernel not found: {args.kernel}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.dtb):
        print(f"Error: DTB not found: {args.dtb}", file=sys.stderr)
        sys.exit(1)
    
    pack_payload(args.kernel, args.dtb, args.output)

if __name__ == "__main__":
    main()