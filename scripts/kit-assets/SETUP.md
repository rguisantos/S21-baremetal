# SETUP.md — reconstituição do ambiente host (Linux, sem sudo)

## 1. Cross-compiler AArch64 (conda-forge, user-space)

```bash
# micromamba: https://micro.mamba.pm (binário único, sem root)
micromamba create -y -r toolchain/root -p toolchain/env \
        -c conda-forge gcc_linux-aarch64 sysroot_linux-aarch64
# resultado: toolchain/env/bin/aarch64-conda-linux-gnu-{gcc,as,ld,objcopy}
```

O Makefile do `code/` já aponta para esse prefixo por default; para outra
toolchain: `make CROSS=aarch64-linux-gnu-`.

## 2. QEMU system-aarch64 10.x (deb unpack user-space)

```bash
bash toolchain/fetch_qemu.sh
# baixa via apt-get download e extrai com dpkg-deb -x para toolchain/qemu-root/
# (qemu-system-arm, qemu-system-common, qemu-system-data + libs:
#  libndctl6 libdaxctl1 libnl-3-200 libnl-route-3-200 libkmod2)
```

Executar sempre com o `qemu/run_qemu.sh` (configura LD_LIBRARY_PATH):

```bash
bash qemu/run_qemu.sh -M virt -cpu cortex-a53 -smp 4 -m 128M \
        -nographic -nic none -kernel payloads/payload.bin
```

## 3. Regressão completa (5 cenários do header arm64)

```bash
bash qemu/test_header_qemu.sh     # logs em test_header_*.log
```

## 4. Recompilar payloads (o ladder é só re-link)

```bash
cd code
make clean && make                 # default QEMU (BOOT_BASE 0x40200000)
make ladder-r1                     # payload_80000000.bin (tentativa 1)
make ladder-r2                     # payload_40000000.bin (tentativa 2)
make ladder-r3                     # payload_80080000.bin (tentativa 3)
```

## 5. magiskboot

Binário estático x86_64 extraído do APK Magisk (lib/x86_64/libmagiskboot.so,
renomeado para `magiskboot/magiskboot`). O APK original está em
`magiskboot/magisk.apk` caso queira re-extrair ou verificar a procedência.

## 6. Dependências Python (apenas para o boot.img sintético de teste)

```bash
pip install lz4                    # make_boot_v3.py / verify_repack.py
```

## Notas de fidelidade

- Teste fiel ao handoff do ABL = **raw bin** (`-kernel payload.bin`), nunca o
  ELF (o QEMU entrega x0=DTB só no raw).
- Com o header "ARM\x64", o QEMU carrega em RAMbase+2MB fixo (ignora
  text_offset) — comportamento medido; ver worklog.md, armadilha 8.
- O sandbox de desenvolvimento pendura no shutdown do QEMU: rodar em
  background + `kill -9` (ver qemu/test_header_qemu.sh).
