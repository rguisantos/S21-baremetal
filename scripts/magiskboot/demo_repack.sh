#!/bin/bash
# demo_repack.sh — valida o fluxo magiskboot (passos 2-5 do Caminho A)
# boot.img v3 sintetico (kernel lz4 = payload real) → unpack → troca de
# kernel → repack → verificacao de integridade → tar ustar p/ Odin
set -u
cd /home/z/my-project/scripts/magiskboot
PY=/home/z/.venv/bin/python3
PAYLOAD=${1:-/home/z/my-project/download/exynos-baremetal-qemu/payload.bin}

echo '== 0. sintese do boot.img v3 (kernel = payload lz4) =='
$PY make_boot_v3.py "$PAYLOAD" boot.img

echo; echo '== 0b. transporte lz4 (equivale ao boot.img.lz4 dentro do AP tar) =='
$PY -c "import lz4.frame as f; open('boot.img.lz4','wb').write(f.compress(open('boot.img','rb').read()))"
$PY -c "import lz4.frame as f; assert f.decompress(open('boot.img.lz4','rb').read())==open('boot.img','rb').read(); print('lz4 transporte: roundtrip OK')"
$PY -c "d=open('boot.img.lz4','rb').read(); print('magic lz4 frame:', d[:4].hex(), '(04224d18 = frame padrao; 02214c18 = legacy)')"

echo; echo '== 1. magiskboot unpack: deteccao automatica =='
./magiskboot unpack boot.img
ls -la kernel header 2>/dev/null
$PY -c "d=open('kernel','rb').read(); print('kernel descomprimido: %d bytes, primeiros 8: %s' % (len(d), d[:8].hex()))"
cmp -s kernel "$PAYLOAD" && echo 'kernel descomprimido == payload.bin (esperado)' || echo 'ATENCAO: kernel != payload'

echo; echo '== 2. troca de kernel: payload cru no lugar =='
cp "$PAYLOAD" kernel

echo; echo '== 3. magiskboot repack =='
./magiskboot repack boot.img custom_boot.img
ls -la custom_boot.img
$PY -c "d=open('custom_boot.img','rb').read(); print('magic:', d[:8]); print('kernel @4096:', d[4096:4106].hex(), '<- lz4? (04224d18)')"

echo; echo '== 4. verificacao: unpack do repack e comparacoes =='
./magiskboot unpack custom_boot.img
cmp -s kernel "$PAYLOAD" && echo 'ROUNDTRIP OK: kernel do repack == payload.bin' || echo 'FALHA: kernel divergiu'
$PY -c "
import struct
for f in ('boot.img','custom_boot.img'):
    d = open(f,'rb').read()
    ks, rs = struct.unpack('<II', d[8:16])
    hs = struct.unpack('<I', d[20:24])[0]
    hv = struct.unpack('<I', d[40:44])[0]
    print('%-17s kernel_size=%-5d ramdisk=%d hdr_size=%d ver=%d' % (f, ks, rs, hs, hv))
print('-> header v3 preservado; kernel_size = novo tamanho comprimido (lz4 do magiskboot)')
"

echo; echo '== 5. tar ustar p/ Odin =='
tar -H ustar -c custom_boot.img > BOOT_CUSTOM.tar
tar -tvf BOOT_CUSTOM.tar
ls -la BOOT_CUSTOM.tar
