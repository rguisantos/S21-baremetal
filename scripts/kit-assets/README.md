# Kit Dia 1 — Primeiro boot bare-metal no Samsung Galaxy S21 Ultra (Exynos 2100)

Kit completo e autossuficiente do projeto, empacotado à prova de perda de chat.
Estado: **Fase 1 concluída e validada no QEMU** (5 boots empíricos). O pipeline
de repack do boot.img foi validado em round-trip byte a byte. Os payloads
abaixo estão prontos para o primeiro flash via Odin.

> **v1.1 (Dia 2)**: correção crítica da armadilha 11 — o `make` não
> re-linkava entre os degraus do ladder, e os 3 payloads estavam
> IDÊNTICOS (linkados em 0x40200000). Regenerados com re-link forçado +
> verificação automática de base (`code/check_payload_base.sh`: confere o
> literal `__bss_start` do pool contra a base do rótulo). Antes de flashear,
> rode:
> `bash code/check_payload_base.sh 0x80000000 payloads/payload_80000000.bin`
> (e idem para as outras bases). Se você tem o kit v1.0, descarte-o — ou
> re- gere os payloads com `make -C code ladders`.
> Prefira o **Kit Dia 2** (payload PIC): roda em qualquer base e reporta
> o delta na serial — o ladder por re-link deixa de ser necessário.

```
exynos-baremetal-kit-DAY1/
├── README.md             ← este guia
├── worklog.md            ← histórico compactado de todo o projeto (R1..R5)
├── code/                 ← fontes: start.S (v3, header arm64 Image), link.ld
│                            (BOOT_BASE paramétrico), main.c (parser FDT +
│                            current_pc), Makefile (ladder-r1/r2/r3 com
│                            re-link forçado + verificação de base),
│                            check_payload_base.sh (prova do literal)
├── payloads/             ← binários prontos (2744 B, header "ARM\x64")
│   ├── payload_80000000.bin  ← TENTATIVA 1: base GKI/universal2100 (padrão)
│   ├── payload_40000000.bin  ← TENTATIVA 2: base tradicional
│   ├── payload_80080000.bin  ← TENTATIVA 3: offset histórico +2 MB
│   └── payload.bin           ← default QEMU (BOOT_BASE 0x40200000)
├── qemu/                 ← wrapper, suíte de testes e logs dos 5 boots
├── magiskboot/           ← binário v30.7 extraído do APK + scripts do
│                            pipeline + repack_day1.sh (fluxo p/ boot STOCK)
└── toolchain/            ← SETUP.md + fetch_qemu.sh (reconstituição host)
```

## Procedimento tático do Dia 1

### Passo 0 — Backup e desbloqueio (mandatório, ordem não negociável)

1. **Backup**: se você tiver acesso root prévio (ou backup da EFS/NVRAM),
   extraia as partições `EFS`, `nvdata`, `omr`, `persistent` — o IMEI e o
   calibramento de rádio vivem aí. Sem backup, qualquer acidente na tabela
   de partições custa o IMEI.
2. **Nunca** use arquivo `.pit` customizado no Odin durante estes testes.
3. Opções de desenvolvedor → habilitar **OEM Unlocking** (SIM conectado).
4. Boot em Download Mode: aparelho desligado → **Vol− + Vol+ + plug USB**.
5. Confirme o desbloqueio (Vol+ segurar). Consequências irreversíveis:
   **Knox 0x1** (e-fuse queimado, Samsung Pay/Knox nunca mais) e **wipe** dos
   dados do usuário. Isto é o ponto sem volta.

### Passo 1 — Extrair o boot.img stock do seu firmware

Do firmware oficial do SEU aparelho (mesma versão instalada — confira em
Configurações):

```bash
tar xf AP_G998B_*.tar.md5 boot.img.lz4   # dentro do AP tar da Samsung
lz4 -d boot.img.lz4 boot.img             # boot.img descomprimido
```

O S21 Ultra é GKI: o kernel genérico está no `boot.img` (comprimido, tipicamente
LZ4) e o DTB no `vendor_boot` — que **não mexemos**: o ABL lê o vendor_boot,
descomprime o kernel do boot.img e entrega o DTB em x0.

### Passo 2 — Repack com o payload (2 comandos)

```bash
cd magiskboot
./repack_day1.sh /caminho/do/boot.img  ../payloads/payload_80000000.bin
# → gera BOOT_CUSTOM.tar e BOOT_CUSTOM.tar.md5 (slot AP do Odin)
```

O `repack_day1.sh` faz o ciclo validado: `magiskboot unpack` → substitui o
kernel pelo payload (com header de Image arm64 oficial) → `magiskboot repack`
(re-comprime no MESMO formato do original — comportamento do magiskboot v30,
que re-lê a imagem original) → unpack de verificação (byte a byte) → tar ustar.

### Passo 3 — UART escutando antes de qualquer flash

```bash
minicom -D /dev/ttyUSB0 -b 115200 -8    # 115200 8N1
```

- Conversor USB-TTL configurado para **lógica de 1,8 V** (não 3,3 V!).
- Cabo jig: **523 kΩ entre CC e GND** (+ 619 kΩ conforme o layout do jig) —
  força o aparelho em modo serial/debug quando conectado.
- GND comum entre conversor, cabo e aparelho.
- Com o jig certo, os logs do **SBOOT/ABL da Samsung** aparecem no minicom
  IMEDIATAMENTE no power-on. Se não aparecerem, o problema é do cabo —
  resolva antes de continuar (o UART é seu único olho).

### Passo 4 — Flash via Odin

1. Aparelho em Download Mode, cabo UART conectado, minicom escutando.
2. Odin → slot **AP** ← `BOOT_CUSTOM.tar.md5` (ou o `.tar`).
3. Aba Options → **DESMARQUE "Auto Reboot"**.
4. Start → aguarde **PASS**. O aparelho permanece no Download Mode.

### Passo 5 — A hora da verdade

1. Reinício forçado: **Vol− + Power por 7 segundos**.
2. Olhos no minicom. Sequência esperada: logs SBOOT/ABL → aviso de bootloader
   desbloqueado (na tela do aparelho, tecla Vol+ para continuar) → o ABL
   valida o boot.img, descomprime, carrega o kernel e transfere o controle.

## Saída esperada no terminal

```
== payload bare-metal ==
Exynos Baremetal Ativo - Fase 1
rodando em 0x00000000800000XX | EL de entrada: X | x0 = 0x000000008XXXXXXX
[+] DTB Magic d00dfeed encontrado!
    tamanho: 0x... | revisao: 0x...
    compatible: "samsung,..."
    memory@ reg: base 0x0000000080000000 tamanho 0x...
bss_probe = 0x0000000000000000 (esperado 0)
```

Três linhas fecham o jogo de uma vez:
- **`rodando em`** → onde o ABL realmente carregou o payload (confirma/corrige o ladder);
- **`memory@ reg`** → base e tamanho reais da RAM do Exynos 2100 (do DTB do ABL);
- **`bss_probe`** → 0 = boot limpo; **valor ≠ 0 = payload rodando DESLOCADO do link**
  (o ADRP tolera deslocamento, mas a BSS limpa no endereço linkado).

## Ladder de BOOT_BASE (se não sair nada)

| Tentativa | Artefato | BOOT_BASE | Quando usar |
|---|---|---|---|
| 1 | `payload_80000000.bin` | 0x80000000 | GKI/universal2100 — SEMPRE primeiro |
| 2 | `payload_40000000.bin` | 0x40000000 | se a 1 não emitir nada no UART |
| 3 | `payload_80080000.bin` | 0x80080000 | se a 2 também falhar (offset histórico) |

Silêncio total = abort ANTES do primeiro fetch (endereço de carga em RAM não
mapeada → Data Abort) OU cabo UART. Repack a tentativa 2 com o mesmo
`repack_day1.sh` e refaça o flash. IMPORTANTE: o payload tolera deslocamentos
pequenos (código+rodata se reencontram via ADRP PC-relativo); colisão real
só ocorre se o delta entre link e carga for menor que ~128 KiB — improvável.

## Troubleshooting rápido

- **Nada no minicom desde o power-on** → problema de cabo/jig/1,8 V/baud, não do payload.
- **Logs SBOOT/ABL aparecem, mas nada do payload** → ladder: tentativa 2, depois 3.
- **Lixo/garbled** → baud rate errado do conversor.
- **`bss_probe` ≠ 0** → rodou deslocado: anote o `rodando em 0x…` (a base real!),
  recompile com `make BOOT_BASE=<base real>` e reflashe.
- **Odin FAIL** → verifique o checksum MD5 (use o `.tar.md5` gerado) e refaça o
  download mode (Português do Odin: FAIL vermelho vs PASS azul).

## As 10 armadilhas do projeto (arquivo completo no worklog.md)

1. Edit de Makefile converte tabs→espaços → `sed -i 's/^ \{8\}/\t/'`
2. GCC -O2 elimina leitura de BSS não-volatile → sempre `static volatile`
3. QEMU do sandbox pendura no shutdown → bg + `kill -9`
4. `-kernel` ELF → x0=0; raw → x0=DTB → teste fiel ao ABL = raw
5. `-bios none` inválido no ARM mainline; `-nic none` para evitar efi-virtio.rom
6. Header v3 ocupa a PRIMEIRA página do boot.img: kernel vai no offset 4096
7. magiskboot v30 sem estado: repack re-lê a imagem ORIGINAL (compressão = stock)
8. QEMU com magic "ARM\x64": carrega em RAMbase+2MB fixo (ignora text_offset)
9. DTB: version em hdr[5]; QEMU 10 gera DTB de 1 MiB com padding
10. Carga deslocada do link: ADRP tolera (código+rodata); SP/BSS absolutos não — bss_probe é o detector

## Reconstituição do ambiente de desenvolvimento

Ver `toolchain/SETUP.md` (cross-gcc conda user-space + QEMU via deb unpack +
`make run-raw` para regressão no emulador antes de qualquer novo flash).
