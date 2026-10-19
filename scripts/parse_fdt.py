#!/usr/bin/env python3
"""parse_fdt.py — parser FDT (flattened device tree) mínimo, sem dependências.

Uso: python3 parse_fdt.py <arquivo.dtb> [filtro_de_caminho]

Imprime os valores de `reg`, `compatible` e `interrupt-parent` de cada nó,
para conferência de endereços físicos: prova reprodutível do mapa de
memória que a placa emulada entrega ao software — nada de achismo.
"""
import struct
import sys

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_PROP = 2
FDT_END_NODE = 3
FDT_NOP = 4
FDT_END = 9


def parse(dtb_path, filtro=None):
    blob = open(dtb_path, "rb").read()
    magic, totalsize, off_struct, off_strings, version = struct.unpack_from(
        ">IIIII", blob, 0)
    if magic != FDT_MAGIC:
        sys.exit(f"não é um DTB: magic={magic:#x}")
    print(f"# FDT v{version}  total={totalsize} bytes  "
          f"struct@{off_struct} strings@{off_strings}")

    def string_at(off):
        end = blob.index(b"\0", off_strings + off)
        return blob[off_strings + off:end].decode()

    pos = off_struct
    path = []
    achados = []
    while True:
        (token,) = struct.unpack_from(">I", blob, pos)
        pos += 4
        if token == FDT_BEGIN_NODE:
            end = blob.index(b"\0", pos)
            path.append(blob[pos:end].decode())
            pos = (end + 1 + 3) & ~3
        elif token == FDT_PROP:
            lenp, nameoff = struct.unpack_from(">II", blob, pos)
            pos += 8
            data = blob[pos:pos + lenp]
            pos += (lenp + 3) & ~3
            full = "/" + "/".join(p for p in path if p)
            achados.append((full, string_at(nameoff), data))
        elif token == FDT_END_NODE:
            path.pop()
        elif token == FDT_END:
            break

    for full, name, data in achados:
        if filtro and filtro not in full:
            continue
        if name == "reg":
            n = len(data) // 4
            cells = struct.unpack(f">{n}I", data)
            # virt usa #address-cells=2 e #size-cells=2: grupos de 4 u32:
            # (addr_hi, addr_lo, size_hi, size_lo)
            for i in range(0, n, 4):
                addr = (cells[i] << 32) | cells[i + 1]
                size = (cells[i + 2] << 32) | cells[i + 3]
                fim = addr + size - 1 if size else addr
                print(f"    {full:<38} reg: 0x{addr:08x}..0x{fim:08x} "
                      f"(size 0x{size:x})")
        elif name == "compatible":
            comps = [c.decode() for c in data.rstrip(b"\0").split(b"\0")]
            print(f"    {full:<38} compatible: {comps}")
        elif name == "interrupt-parent":
            phandle, = struct.unpack(">I", data)
            print(f"    {full:<38} interrupt-parent: phandle {phandle}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    parse(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
