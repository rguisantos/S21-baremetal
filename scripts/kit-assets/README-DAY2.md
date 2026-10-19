# Kit Dia 2 — Exynos 2100 bare-metal (sem hardware)

Este kit é o Dia 2 do projeto: TODO o trabalho que podia ser feito sem o
aparelho físico, para que o primeiro flash na cobaia (quando ela chegar à
bancada) seja uma leitura, não uma aventura.

## O que foi provado hoje (resumo executivo)

1. **O kit Dia 1 tinha um bug silencioso e grave** (armadilha 11): o make
   não re-linkava entre os degraus do ladder — os 4 payloads do kit Dia 1
   eram IDÊNTICOS, todos linkados em 0x40200000. Corrigido: re-link forçado
   + `check_payload_base.sh` (verifica o literal do pool contra a base do
   rótulo). O kit Dia 1 regenerado agora tem ladder de verdade (3 bases
   distintas, hashes diferentes).
2. **Zona de morte da Fase 1 mapeada empiricamente** (QEMU como simulador
   de ABL deslocado): delta carga-link entre +9 e +0xAC0 = o clear da BSS
   apaga a própria imagem → strings truncadas ou silêncio. Base linkada
   fora da RAM → Data Abort FAR=base+0xAC0, ELR = instrução do clear
   (assinatura: silêncio total no UART do aparelho).
3. **Fase 2 PIC validada**: o mesmo binário roda em QUALQUER base (deltas
   múltiplos de página — a classe que bootloaders reais produzem), SP/BSS
   rebaseados em runtime para junto da imagem, zona de morte eliminada,
   base não-RAM indiferente. Provado até com RAM suja (0xAA): o radar lê
   o lixo pré-clear e o clear limpa a BSS real.
4. **Instrumentação de silêncio**: canários 'S' (payload vivo) e 'K' (BSS
   gravável) antes de qualquer C — no aparelho, silêncio deixa de ser
   indistinguível de abort.
5. **abl_triage.py**: triagem estática do firmware stock (boot image
   header, DTBs embutidos, serial@/memory@/watchdog, strings, endereços) —
   o caminho para fechar UART_BASE SEM soldar fio (ver analysis/).

## Estrutura

```
code/         Fase 2: start.S (PIC+canários), main.c (reporte completo),
              link.ld, Makefile (ALVO_QEMU=0 compila para o aparelho)
payloads/     payload_fase2.bin — o binário para o flash (PIC, 3448 B)
experiments/  os dois sweeps + logs crus + exceções (o "porquê" de tudo)
analysis/     abl_triage.py + ABL_EXTRACTION.md (firmware → UART_BASE/RAM)
magiskboot/   magiskboot v30.7 + make_boot_v3.py + demo_repack.sh +
              verify_repack.py + repack_day2.sh (pipeline BLINDADO) +
              BOOT_CUSTOM_F2.tar(.md5) pronto para Odin (AP)
toolchain/    SETUP.md + fetch_qemu.sh (reconstituição do ambiente)
worklog.md    histórico completo R1-R6 (armadilhas 1-12)
```

## Como reproduzir os experimentos (QEMU)

```bash
# zona de morte da Fase 1 (payload com literais absolutos)
bash experiments/test_delta_sweep.sh          # logs: test_delta_*.log

# prova do PIC da Fase 2 (mesmos assassinos, todos sobrevivem)
bash experiments/test_delta_sweep_fase2.sh    # logs: test_delta2_*.log
```

## O passo-a-passo quando a cobaia chegar à bancada

0. **Antes de qualquer flash**: backup EFS/nvdata/omr/persistent (partições
   que não voltam de brick). Cabo UART 1,8 V lógico nos test points,
   minicom 115200 8N1. Odin com Auto Reboot DESMARCADO.
1. **Fechar UART_BASE** (se ainda não fechou via abl_triage.py):
   extrair abl.img do firmware AP → `python3 analysis/abl_triage.py
   abl.img --dump-dtb` → nó serial@ → preencher `UART_BASE` em
   `code/main.c` (bloco `#else`, DW 8250) e `code/start.S` (canary_tx).
   Recompilar: `make -C code ALVO_QEMU=0 flash`.
   (Se não achar: o payload Fase 2 com UART do QEMU ainda reporta via
   canários? Não — endereço errado fica mudo. Fechar UART é pré-requisito.)
2. **Repack blindado**: `cd magiskboot && ./repack_day2.sh <boot_stock.img>
   payloads/payload_fase2.bin` (ou --dry-run primeiro). Confere sha256 do
   payload, magic ARM\x64, roundtrip byte a byte, tamanho, md5 do tar.
3. **Flash no Odin** (slot AP, Auto Reboot OFF). Se não bootar:
   Vol- + Power 7s para voltar ao Download Mode (jig 523k se preciso).
4. **Ler a serial** — o dicionário do Dia 2:
   - linhas do ABL (formato conhecido da triagem) → bootloader vivo
   - `S` → payload executando (o ABL carregou e pulou pro nosso código)
   - `K` → BSS gravável
   - banner `Fase 2 (PIC)` + `rodando em 0x…` + `delta carga-link: 0x…` →
     a base REAL de carga (fecha a incógnita número 1 do projeto)
   - `sp herdado`, `bss pre-clear` (radar de lixo), `bss_probe pos-clear`
   - `DTB Magic d00dfeed` + `memory@ reg: base 0x… tamanho 0x…` → a
     geometria da RAM (fecha a incógnita número 2 — o ladder vira fato)
   - `S` sem `K` → BSS em região não gravável (colisão MMIO) — trocar
     base de referência do link não resolve (PIC!); investigar com o delta
   - nada de `S` → o ABL não entregou o controle: validar magic/assinar
     (avb), conferir se o ABL exige kernel maior que 3448 B (padding)
5. **Com a base real confirmada**, o Fase 2 já é o payload final desta
   fase; a Fase 3 (framebuffer/GIC) parte dele com endereços reais.

## Limites conhecidos (honestidade técnica)

- PIC válido para deltas múltiplos de 4096 (ADRP do small model). Deltas
  sub-página corrompem rodata (sintoma: SK + strings lixo). Bootloaders
  conformes ao header (bit3 = placement 2 MB) carregam alinhados — o limite
  é teórico para o nosso caso (ar­madilha 12).
- O QEMU não simula: assinatura AVB, MMU/caches herdadas do ABL, watchdog
  ativo, timing do UART real. O kit Dia 2 reduz, não elimina, o risco —
  por isso a cobaia de bancada, nunca o aparelho principal.
- abl_triage.py não substitui Ghidra: ele dá o mapa; a engenharia reversa
  fina do ABL continua manual (seção 4 do ABL_EXTRACTION.md).
