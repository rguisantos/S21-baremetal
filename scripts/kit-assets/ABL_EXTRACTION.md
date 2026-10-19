# ABL_EXTRACTION.md — como obter e triar o ABL do firmware stock (sem hardware)

O objetivo: extrair do firmware oficial, por análise estática, os três dados
que o payload da Fase 2 precisa para o primeiro flash na cobaia:

1. **UART_BASE** — endereço do console (nó serial@/uart do DTB embutido no ABL)
2. **RAM base + tamanho** — nó memory@ (valida o ladder 0x80000000/0x40000000)
3. **formato das linhas de log do ABL** — para reconhecer na serial o momento
   exato do handoff (o banner "Fase 2" tem que aparecer DEPOIS delas)

Tudo offline, sem executar nada do firmware.

## 1. Baixar o firmware stock

Ferramentas que baixam diretamente dos servidores da Samsung (fuso de
marshaling KDZ/tar): **Frija** (Windows/Linux, GUI) ou **samfirm.js** /
**Bifrost** (CLI). Modelo do S21 (Exynos 2100): G981B/G981N; S21 Ultra: G998B.

- CSC/país: o de origem do aparelho (ou KOO/XEZ para não trigar Knox-telas)
- saída: `AP_G981BXXXX_....tar.md5` + BL/CP/CSC

⚠️ Não confundir com "home CSC" flash de atualização — aqui queremos só o
arquivo AP, que contém TODAS as imagens de bootloader.

## 2. Localizar o ABL dentro do AP

```bash
tar tvf AP_G981BXXXX_....tar.md5 | grep -E 'abl|boot'
#   abl.img         <- o Android Bootloader (alvo da triagem)
#   boot.img        <- o kernel stock (para o repack_day2.sh)
```

## 3. Triagem automática (abl_triage.py)

```bash
python3 abl_triage.py AP_G981BXXXX_....tar.md5 --dump-dtb
# ou direto na imagem extraída:
python3 abl_triage.py abl.img --dump-dtb
```

O script (Python puro, offline) faz:

- parse do header de boot image (v0-v4) e extração do binário ABL
- varredura por DTBs embutidos (magic d00dfeed em qualquer offset) com dump
  dos nós de interesse em qualquer profundidade:
  - `serial@/uart@/pl011/ns16550` → **reg = UART_BASE** (anotar também
    `reg-shift`, tipicamente 2 no DW 8250 Samsung)
  - `memory@` → **reg = base+tamanho da RAM**
  - `watchdog/reboot/gic/timer/pmu/chipid` → registros uteis para debug
- strings de interesse (mensagens de log do ABL: "ABLoad", console, ecc,
  exynos...) e endereços hex citados (pistas de base de carga)
- saída legível em stdout (+ `--json` para máquina; `--dump-dtb` grava os
  DTBs em arquivos `.dtb` para inspeção com `dtc -I dtb -O dts`)

**Passo crítico que só a triagem não faz:** confirmar o `compatible` do UART.
Se for `samsung,exynos4210-uart` (IP legacy Samsung): offsets UTRSTAT/UTXH
(status +0x10 bit 1, TX +0x20 — polaridade e offsets DIFERENTES do DW 8250).
Se for `ns16550a`/`dw8250`: THR/LSR (o esqueleto `#else` do main.c/start.S
da Fase 2 já implementa DW 8250; falta preencher UART_BASE).

## 4. Engenharia reversa assistida (Ghidra) — opcional, mas acelera

1. Extrair o binário ABL (o "kernel" da abl.img):
   `python3 abl_triage.py abl.img` já mostra o offset/tamanho.
2. Ghidra → importar como **raw AArch64 little-endian** (ou ELF, se o ABL
   for `\x7fELF` — comum: o Samsung ABL é um ELF carregado pelo BL1).
   ELF: o Ghidra resolve base e símbolos sozinho. Raw: usar como base um
   dos endereços citados nas strings (o triage lista).
3. Procurar xrefs para o UART_BASE achado no passo 3 → as funções de
   console do ABL (printf/boot_log) → copiar o formato de linha.
4. Procurar a constante do magic "ARM\x64" (bytes 41 52 4d 64) → o código
   que VALIDA o kernel Image — confirma que o header do payload é aceito e
   revela o endereço de carga do kernel (o número que o delta do payload
   vai confirmar no metal).

## 5. Fechando o circuito com o payload Fase 2 (PIC)

Nada disso bloqueia o flash: o payload Fase 2 roda em qualquer base e
reporta na serial o delta e o FDT inteiro (memory@/compatible). A triagem
prévia do ABL serve para:

- preencher UART_BASE no `ALVO_QEMU=0` (senão o payload Fase 2 imprime os
  canários 'S'/'K' em endereço errado e fica mudo)
- saber o que esperar ANTES do silêncio (linhas do ABL) → distinguir
  "ABL rodou e me entregou" de "ABL nem chegou lá"
