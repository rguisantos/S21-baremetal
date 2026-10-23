# Worklog — projeto S21 Ultra bare-metal (Exynos 2100)
Compactado a cada round (a pedido do usuário) para preservar o trabalho acumulado.

## Estado atual
- Fase 1 (QEMU) 100%: payload com header de Image arm64 + parser FDT + current_pc
- **DIA 2 (sem hardware) completo**: zona de morte da Fase 1 mapeada empiricamente;
  Fase 2 PIC validada (zona eliminada p/ deltas múltiplos de página, base não-RAM
  indiferente, radar de lixo provado com RAM suja); canários S/K; abl_triage.py;
  repack_day2 blindado; kit DAY2 empacotado
- Kit DAY1 v1.1: armadilha 11 corrigida (ladder regenerado com re-link forçado +
  check_payload_base.sh — 3 bases distintas verificadas)
- Próximo: cobaia na bancada → repack_day2 + flash → serial fecha base real/delta/RAM

## Mapa de artefatos
- Código F1:   download/exynos-baremetal-qemu/ (start.S v3, main.c v3, Makefile c/ force-link+ladders+check, check_payload_base.sh)
- Código F2:   download/exynos-baremetal-qemu-fase2/ (start.S v5 PIC+canários, main.c v5 reporte completo, payload_fase2.bin 3448 B)
- Kits:        download/exynos-baremetal-kit-DAY1 (v1.1) e kit-DAY2 (+ .tar.gz/.sha256, 25 MB)
- Experimentos: scripts/test_delta_sweep.sh + test_delta_*.log/.exc/.txt (F1) e test_delta_sweep_fase2.sh + test_delta2_* (F2)
- Análise:     scripts/abl_triage.py (boot img header + DTB scan + serial@/memory@ + strings) + kit-assets/ABL_EXTRACTION.md
- Repack:      scripts/kit-assets/repack_day2.sh (blindado: sanity+dry-run+--force+verificação tripla) → BOOT_CUSTOM_F2.tar(.md5)
- Builds:      scripts/build_kit.sh (DAY1 v1.1) + build_kit_day2.sh (com smoke embutido)
- magiskboot:  scripts/magiskboot/ (v30.7, make_boot_v3.py, demo_repack.sh, verify_repack.py, boot.img, custom_boot.img, BOOT_CUSTOM.tar)
- Toolchain:   scripts/toolchain/env/bin/aarch64-conda-linux-gnu-* (conda-forge, user-space)
- QEMU:        scripts/toolchain/qemu-root/usr/bin/qemu-system-aarch64 (10.0.13) via scripts/run_qemu.sh (T=…s)
- Testes:      scripts/test_header_qemu.sh + test_header_*.log + boot*.log

## Armadilhas documentadas (NÃO reincidir)
 1. Makefile: Edit/MultiEdit converte tabs→espaços ("missing separator") — fix: sed -i 's/^ \{8\}/\t/'; sempre conferir grep -cP '^\t'
 2. GCC -O2 dobra leitura de BSS não-volatile em 0 (variável "some") — fix: static volatile
 3. QEMU do sandbox pendura no shutdown (SIGTERM ignorado, timeout externo ineficaz) — fix: bg + sleep + kill -9
 4. -kernel ELF → x0=0; -kernel raw → x0=DTB (0x44000000) — teste fiel ao handoff do ABL = SEMPRE raw
 5. -bios none não é keyword ARM mainline; NIC default exige efi-virtio.rom → -nic none
 6. boot.img v3: o header ocupa a PRIMEIRA página inteira — kernel em offset 4096 (não 1580!); desalinhado, o magiskboot lê "raw" em vez de LZ4
 7. magiskboot v30: sem estado entre unpack/repack — re-lê a imagem ORIGINAL p/ detectar o formato do kernel (com boot stock Samsung, recompressação idêntica à de fábrica)
 8. QEMU com header "ARM\x64": carrega em RAMbase+2MB FIXO (ignora text_offset); sem o magic: RAMbase+0 — o magic MUDA o comportamento de carga
 9. DTB: version está em hdr[5] (não pular off_rsvmap); QEMU 10 gera DTB de 1 MiB (totalsize com padding)
10. Payload tolera carga DESLOCADA do link: ADRP/ADD PC-relativo reencontra código+rodata; SP/BSS (literais absolutos) caem em RAM — bss_probe imprime lixo se a região linkada não foi zerada = detector de deslocamento no aparelho
11. **LADDER FALSO (Dia 2)**: `make BOOT_BASE=X payload.bin` NÃO re-linka (BOOT_BASE não é dep do .elf) → ladder-r2/r3 copiavam o .bin da base anterior; kit Dia 1 v1.0 saiu com 4 payloads IDÊNTICOS linkados em 0x40200000 (bug ASSINTOMÁTICO: tudo "passava" porque o payload tolera deslocamento) — fix: target PHONY `force-link` como pré-requisito do .elf (re-linka sempre) + `check_payload_base.sh` conferindo o literal `__bss_start` (offset 0x88 do pool) contra a base do rótulo
12. **ADRP só relocaliza em múltiplos de 4096** (small model): delta sub-página desalinha os acessos a rodata em ±1 página (sintoma: canários SK + strings/hex lixo — o d_p40 do sweep); a "tolerância ADRP" da armadilha 10 só vale para deltas múltiplos de página; loaders conformes ao header (bit3 = placement 2 MB) carregam alinhados → o limite é teórico para o caso real; solução sub-página (se um dia for necessária): .rela.dyn processada em runtime (estilo u-boot)
13. O QEMU -M virt chama o nó UART de "pl011@9000000" — NÃO confiar no NOME do nó para achar UART; casar pelo COMPATIBLE (arm,pl011/ns16550a/samsung,exynos-uart); e as props do DTB vêm em ordem arbitrária (reg ANTES do compatible) → acumular por nó e decidir no END_NODE (implementado no abl_triage.py)
14. `.tar.md5` = tar BINÁRIO + md5 appendado: `tail -n 1` engole nulls do tar (command substitution ignora nulls silenciosamente e corrompe o check) — ler com `tail -c 64 | tr -cd '0-9a-f'`

## Rounds
### R1 — Task 1: estratégia
UART-first (observabilidade antes de mutação); sem fastboot (Odin/Heimdall/Download Mode); magiskboot > mkbootimg; atalho Samsung OSR; UART 1,8V lógico; jig 523kΩ/619kΩ; backup EFS antes de tudo.

### R2 — Task 2: skeleton QEMU
start.S (holding pen por MPIDR, SP 16B alinhado, BSS clear 8B) + link.ld + main.c (banner/EL/DTB/bss_probe); toolchain conda user-space + QEMU via deb unpack; boot validado ELF e raw; armadilhas 2-5 documentadas.

### R3 — Task 3: Caminho A (magiskboot + FDT)
Round-trip magiskboot validado byte a byte (armadilhas 6-7); main.c v2 com parser FDT (magic d00dfeed BE, totalsize, compatible/model, #address/#size-cells, memory@ reg com 2 cells); DTB real do QEMU parseado (0x40000000/128M); lacuna mapeada: headers v3/v4 NÃO têm campo de endereço de carga → solução R4.

### R4 — Task 4: header arm64 Image + ladder empírico
- booting.rst confirmado via fetch: layout 64B; flags bit0=endian (0=LE, 1=BE — INVERSO do intuitivo), bits1-2=page size, bit3=physical placement; res5@0x3C = PE COFF offset (0 = não-EFI); magic "ARM\x64" em 0x38
- Correções ao draft do usuário: flags 0x8→0xA (bit "LE" estava no bit errado; 0xA = kernel real LE/4KB); comentários de campo corrigidos
- start.S v3: header de 64B no byte 0 (code0 = b stext PC-relativo); TEXT_OFFSET_BYTES/IMAGE_SIZE_BYTES chegam via ld --defsym (defaults PROVIDE no link.ld)
- link.ld: ORIGIN = BOOT_BASE (--defsym) → trocar BOOT_BASE = só re-link (.o intactos)
- main.c v3: current_pc() via ADR offset 0 — imprime endereço REAL de execução (instrumento que fecha o ladder no hardware)
- Makefile: ladder-r1/r2/r3 → payload_<base>.bin; default BOOT_BASE=0x40200000 (carga medida do QEMU com header); test-2g (ensaio r1 em RAM 2G)
- Empírico (hexdump conforme booting.rst + 4 boots QEMU): armadilhas 8 e 10 descobertas; zero warnings; tabs verificados (23)
- Artefatos: payload_80000000.bin / payload_40000000.bin / payload_80080000.bin (2744 B cada) prontos para o repack magiskboot → BOOT_CUSTOM.tar → Odin AP (Auto Reboot OFF)

### R5 — Task 5: kit Dia 1 à prova de perda de chat (round atual)
- Banner main.c v4: "Exynos Baremetal Ativo - Fase 1" (casa com a expectativa de saída do Dia 1); 4 payloads regenerados (2744 B) e revalidados no QEMU (test_header_fase1.log — zero regressão)
- demo_repack.sh: PAYLOAD parametrizável por argv; pipeline sintético regenerado com payload_80000000.bin (header incluso)
- Kit reproduzível: download/exynos-baremetal-kit-DAY1/ → README.md (procedimento tático Dia 1 completo: backup EFS/OEM unlock/Knox wipe → extrair boot stock → repack → minicom 115200 8N1 + jig 523kΩ/1,8V → Odin AP sem Auto Reboot → força reboot Vol-+Power 7s), worklog.md, code/, payloads/ (4 bin), qemu/ (run+suíte+logs), magiskboot/ (v30.7 + make_boot_v3.py + repack_day1.sh c/ verificação byte a byte + .tar/.tar.md5), toolchain/ (SETUP.md + fetch_qemu.sh)
- Empacotado: download/exynos-baremetal-kit-DAY1.tar.gz (+ .sha256) — tudo autocontido exceto toolchain conda (reconstituível via SETUP.md)
- Calcanhar de Aquiles quantificado: colisão BSS/imagem só se delta carga-link < ~128 KiB (payload 2744 B + BSS/stack ~64 KiB); "invadir ROM" = Data Abort/hang, não sobrescrita; PIC/rebase dinâmico ADIADO para Fase 2 por decisão tática (literais absolutos = instrumento forense do deslocamento)
- Tática Dia 1 endossada; correções incorporadas no README (.tar.md5 opcional p/ Odin, 1,8V lógico, EFS/nvdata/omr/persistent como alvos de backup, nunca .pit custom)
- Smoke test final: kit descompactado em dir limpo → ./repack_day1.sh boot.img → unpack/repack/ROUNDTRIP OK byte a byte + BOOT_CUSTOM.tar (10240 B, ustar) + .tar.md5 — kit autossuficiente com caminhos relativos; autorais mantidos em scripts/kit-assets/ (fonte permanente do build_kit.sh)

### R6 — Task 6: Dia 2 SEM hardware (decisão: celular principal fora dos testes)
Decisão do usuário: sem flash no aparelho principal; rotas = esgotar QEMU + Fase 2 PIC + análise estática. Snapshot R5 de proteção criado antes de qualquer mutação.

- **Descoberta 1 (crítica, armadilha 11)**: primeiro delta sweep "passava em tudo" — suspeita → hashes dos 4 payloads do kit DAY1 IDÊNTICOS (todos linkados 0x40200000; literais do pool em 0x88: c0 0a 20 40). Causa: `payload.elf: $(OBJS) link.ld` não declara BOOT_BASE → make pula o re-link → ladder falso. Fix: force-link PHONY + check_payload_base.sh (literal == base+ALIGN16(size)); ladders regenerados (3 hashes distintos); kit DAY1 v1.1 regenerado e verificado de forma independente
- **Zona de morte F1 (sweep v2, 12 cenários)**: carga QEMU fixa em 0x40200000 (armadilha 8) + BOOT_BASE variável = simulador de ABL deslocado. Resultado: d≤0 ou d>0xAC0 → boot completo; d∈[9,0xAC0] → o clear ABSOLUTO apaga a própria imagem (d=+0x40: rodata → banner corrompido "Exynos Bar1"; d≥+0x300: .text → silêncio; d=0xAC0: header). B=0x60000000 (não-RAM): Data Abort FAR=0x60000ac0, ELR=0x40200068 (= `str xzr,[x0],#8` do clear) → no hardware: silêncio puro
- **Insight arquitetural**: no F1 deslocado, clear usa literais ABSOLUTOS (limpa BSS linkada) mas main.c acessa bss_probe via ADRP (lê BSS deslocada NÃO limpa) → radar funciona no aparelho (lixo do ABL) e é invisível no QEMU (RAM nasce zerada) — por isso o sweep F1 sempre imprime bss_probe=0
- **Fase 2 PIC (dir -fase2)**: start.S v5 computa delta=execução−link (adr − literal do pool), rebaseia BSS/SP (+delta) para junto da imagem (dentro do image_size do header — contrato do protocolo), canários 'S'/'K' via UART em assembly pré-SP, captura forense (bss_raw pré-clear, sp herdado) passada ao main(dtb,bss_raw,sp_boot,delta); main.c v5 reporta tudo; payload 3448 B; Makefile: %.S via gcc (cpp p/ #if ALVO_QEMU), make ALVO_QEMU=0 → aparelho
- **Sweep F2 v2 (armadilha 12 no caminho)**: deltas múltiplos de página (0, ±4K, ±64K, +2M, −0x1FE00000/unmap) → 100% limpos com delta reportado (base não-RAM: F1 abortava, PIC nem se abala); d_p40 sub-página → SK+strings lixo (ADRP ±1 page) → limite conhecido documentado (loaders 2MB-aligned não produzem delta sub-página); d_dirt (0xAA em C+0xD78, sujando só a BSS runtime): radar lê 0xaaaaaaaaaaaaaaaa + bss_probe pós-clear=0 → clear PIC limpa a BSS REAL (as 2 propriedades que o QEMU escondia, provadas com sujeira)
- **abl_triage.py**: boot image v0-v4 + kernel ARM\x64 + ELF + DTB scan (magic d00dfeed no blob inteiro) + nós de interesse por compatible (armadilha 13: pl011@9000000 não tem "serial" no nome) em qualquer profundidade + strings/endereços hex + tar.md5/AP de firmware direto; validado no virt.dtb (pl011 reg 0x9000000+0x1000, memory 0x40000000+0x8000000) e boot.img sintético; ABL_EXTRACTION.md (Frija/samfirm → AP tar → abl.img → triagem → Ghidra)
- **repack_day2.sh (blindado)**: sanity (magic ANDROID!/ARM\x64, sha256), --dry-run, recusa overwrite sem --force, verificação tripla (kernel==payload byte a byte, repack≤stock, md5 re-lido — armadilha 14 no caminho), BOOT_CUSTOM_F2.tar(.md5); paths absolutos (readlink -f — bug do mktemp achado no smoke)
- **Kit DAY2 (25 MB)**: code/ + payloads/payload_fase2.bin + experiments/ (2 sweeps + logs + .exc) + analysis/ (abl_triage + ABL_EXTRACTION) + magiskboot/ (repack_day2 + BOOT_CUSTOM_F2 oficial) + README-DAY2 (dicionário de leitura da serial: linhas ABL → S → K → banner → delta → memory@; S sem K = BSS não gravável; sem S = ABL não entregou) — smoke de autossuficiência ok (dry-run + real + --force em dir limpo)
- Pipeline sintético revalidado com payload_fase2 (ROUNDTRIP OK, lz4 2486→2360 B comprimido)

## 2026-10-20 — FDT, memória e atualização da documentação

- O usuário confirmou que as imagens são originais do mesmo HZC2/Android 15 em uso e que não tem root. Registrados os resultados já recebidos: rish UID 2000, FDT root:0400 inacessível, TAR live sem propriedades úteis e MemTotal agregado sem mapa físico. Não repetir coleta bloqueada nem confundir Shizuku com root. Relato sem diagnósticos privados em `docs/runtime-collection.md`.
- Substituída a sanidade superficial do FDT por parser limitado e sem alocação: header/blocos/tokens, memória 32/64 bits, reservas, initrd, CPUs por MPIDR completo, GICv3 e timer. A política recusa payload fora da RAM ou em conflito e descrições incompletas. Sem endereço de fallback para GIC na main.
- Corrigido o linker: pilhas passam a integrar o segmento data PT_LOAD e seu p_memsz. A validação em C não desfaz escritas anteriores de BSS/pilha; reserva e coerência da imagem continuam sendo responsabilidades do carregador.
- Fixtures independentes exercitam o C real com ASan/UBSan. Integração QEMU recebe DTB real gerado, fora do payload, e usa parser/política antes de GIC/timer. Encontrado e corrigido um abort de alinhamento: GCC fundia leituras byte a byte em LDR de 64 bits sobre propriedade alinhada só a 4; parser compilado com `-mstrict-align`.
- O parser inspecionou base HZC2, oito árvores com overlays e DTB TWRP: recursos extraídos, nenhum nó memory, boot recusado por ausência de RAM. Reservas dinâmicas/aninhadas também impedem certificar RAM livre.
- Referência indicada `xfwdrev/android_device_samsung_exynos2100`, branch android-12.1, commit 0d8b294: configuração TWRP e DTB compilado. O DTB p3s tem tabela Android de 64 bytes e confirma GIC/MPIDRs/timer, mas não resolve RAM. Header v2/offsets daquele recovery não são contrato de boot do HZC2 v3. Detalhes e hash em `docs/twrp-reference.md`.
- README reescrito; mapa de hardware atual substitui afirmações contraditórias. Notas antigas preservadas com aviso em `docs/archive/`. Documentadas evidências, testes reproduzíveis, hipóteses e pendências; nenhuma operação de flash/execução no telefone.


## 2026-10-20 — Instalador Proton e contrato Samsung

- Seguido do_build.sh → build/ckbuild.sh na tag v6.1.0 (a0d7323): Image, DTB conforme variante, tabela Android, boot v3 e vendor_boot v3 com ramdisk/módulos. ZIP copia Image + vendor_boot para AnyKernel3 r9s; TAR usa boot/vendor_boot LZ4.
- Fixado o AnyKernel consultado em 59517ec. anykernel.sh aceita p3s, recompõe boot e grava vendor_boot. Branch flutuante/pasta local no build impedem atribuir automaticamente esse SHA ao ZIP publicado. Digest de release registrado, ainda sem comparação com upload.
- Conferidos mkbootimg, documentação ARM64 e head.S: offsets de contêiner/header não comprovam PC; Linux aceita EL1 ou EL2, enquanto R10 exige EL2. A imagem ELF R10 atual não é um substituto validado para uma Image ARM64 Samsung.
- Não há binário sboot/Harx/ABL na árvore pública para reanálise; notas/strings históricas não fecham handoff, RAM ou estado de caches. Ambiente de execução permaneceu indisponível; análise via fontes textuais GitHub, sem extração de ZIP nem execução de scripts.
- Corrigido ABL_EXTRACTION.md: modelo G998B, separação BL/AP e retirada de pressupostos ABL/U-Boot/flash. Matriz de evidências e critérios da próxima Image de diagnóstico em docs/loader-contract.md. README e referência Proton atualizados; payload e partições não alterados.


## 2026-10-20 — Contêiner S21R10 e conferência binária Proton

- Workspace reconstruído por clone da main. Comparado branch kilo/slim-fjord-u2q sem mesclar o estado anterior que remove correções/testes posteriores.
- ZIP publicado Proton baixado: SHA-256 confere com API release. Image possui magic ARM64, versão Linux 5.4.302 e PE/EFI stub; corrigida conclusão de que não seria Linux. DTB extraído passou no parser e foi recusado por NO_RAM. initrd-end estático 0x841fffff é exclusivo no binding, portanto não descreve exatamente 2 MiB. Hashes e procedimento em docs/proton-binary.md.
- tools/mkpayload.py gera S21R10 v1 a partir de ELF AArch64 identity-linked, FDT e cmdline; inclui extensão PT_LOAD/BSS/pilhas, sem reserva fictícia de 2 GB ou relocação implícita. Consumidor C inspeciona limites antes de devolver plano; não copia nem salta.
- Loader legado removido do caminho executável: passava boot_args XNU em x0 para um consumidor FDT e fazia cópias sem validação. loader_boot agora recusa; entrada shim padrão estaciona antes de BSS/pilha/MMIO. Código legado não validado continua explicitamente em quarentena.
- 59 casos de empacotador/consumidor/inspeção de headers passaram, com ASan/UBSan no consumidor C. Build de cinco ELFs R8-R10 e shim; integração R10 em uma CPU preservada. Não houve SMP do shim, chainload no telefone ou flash.


## 2026-10-20 — Revisão reproduzida do empacotador no branch kilo

- Conferido kilo/slim-fjord-u2q em 9dca396: produtor grava ELF bruto como segmento, usa kernel_end relativo, ignora função de leitura da entrada e presume 2 GiB. Na reprodução, os bytes que seriam executados começaram por 7f454c46, kernel_end=0x18000 e nsegs=1, omitindo a semântica dos dois PT_LOAD/BSS/pilhas do R10 atual.
- Validador antigo com ASan/UBSan retornou ALL CHECKS PASSED para esse artefato e heap-buffer-overflow para arquivo de quatro bytes. Consumidor main recusou o mesmo payload sem erro de sanitizer.
- Adicionado caso específico de kernel_end relativo: suíte atual 60 PASS. Conferido que run_r10 com QEMU_ARGS=-smp4 só imprime aviso e não executa QEMU; não há prova de SMP/fastboot por esse comando. Evidências completas em docs/branch-packer-review.md. Sem mesclar regressões do branch ou realizar operações no aparelho.


## 2026-10-20 — Carregador EL2 QEMU → main R10 de produção

- Criada etapa payload_stage separada: usa FDT confiável independente, reserva da janela completa e exclusões de fonte/FDT/firmware/pilha antes de zerar/copiar bytes exatos. FDT empacotado precisa coincidir com o fornecido pelo chamador. 17 casos host ASan/UBSan com buffers/canários e recusas sem escrita.
- Novo firmware QEMU em 0x44000000, com stack PT_LOAD de 16 KiB e container produzido do ELF R10 linkado em 0x40080000. A entrada exige EL2 e MMU/D-cache desligadas; manutenção de cache por VA/DSB/IC/ISB e x0=FDT/x1..x3=0 antes do salto. Não ligado ao shim Samsung.
- O harness compara a janela inteira contra os PT_LOAD/FDT antes do salto; depois confirma CurrentEL=EL1, g_fdt correto, boot_status=1 e pelo menos cinco IRQs do timer na main/dispatcher reais. Backend UART é o único dispositivo substituído por PL011 QEMU. Quatro recusas de contêiner/contexto preservam destino; uma quinta recusa entrada EL1 antes de BSS/pilha.
- Sockets locais foram bloqueados pelo ambiente; observação GDB adaptada para pipes, sem servidor de rede. Teste completo passou em uma CPU. Fixture QEMU descreve essa única CPU e inclui página reservada para injeção de falha. Sem SMP ou operação no telefone.

## 2026-10-21 UTC — revisão e organização

Conferida main b7185e4 e relidos README_Kernel/README_Platform anexados, com hashes em docs/samsung-reference.md. Criados índice de documentação, catálogo de scripts e aviso de escopo do recorte samsung_kernel. Preservados caminhos e toolchain offline; scripts DAY1/DAY2 e snapshot antigo identificados como históricos. Registrada a necessidade prioritária de BL HZC2, separada das evidências de execução ainda indisponíveis; não repetida a coleta Shizuku bloqueada. Resultados da nova execução e limites em docs/repository-review-2026-10-21.md. Nenhum flash ou upload de diagnóstico privado.

## 2026-10-21 UTC — BL recebido e PRs conferidos

BL HZC2 recebido: 12 membros LZ4, MD5 do TAR válido e hashes brutos registrados em docs/bootloader-hzc2.md. Encontradas referências de código a configure_dtb/Starting kernel e bloco BLR com x0=0x8b080000, x1..3=0 e destino 0x80080000 mais estado lido em memória. Inspecionada preparação condicional de SCTLR por EL; estado real, relocação e FDT final permanecem não provados. Nenhum firmware bruto publicado ou executado. API GitHub sem PR aberto; #2/#3 confirmados mergeados. Pedido anterior de BL atendido.

## 2026-10-21 UTC — continuação BL e resolução PR #4

Rastreado escritor do deslocamento do salto: serviço SMC 0xc200101c, seis bits do retorno w2 deslocados por 15; ramo de erro força zero. Localizado global do FDT inicializado com 0x8b080000 e construtor memory@/reg/device_type, com bancos dependentes de estado runtime. Encontrada chamada HVC para reservas, sem reinterpretar PSCI SMC como HVC. Evidência e limites detalhados em docs/bootloader-hzc2.md. PR #4 novo revisado e encerrado como substituído pela main; validador antigo reproduz overflow. Testes atuais: contêiner 60 PASS; QEMU um handoff/25 IRQs e cinco recusas PASS. Nenhum driver ou firmware modificado.

## 2026-10-21 — splits HZC2 e contraprova à premissa EL2

Detector fixado em 0c0acea reproduz BL1/EPBL/BL2/LK/monitor; limite de LK usa tamanho fixo, não footer independente. Primeiro BL de LK (sboot+0xec000) chama 0xf9b4c: retorno imediato se EL1; SPSR 0x3c5 e ERET nos caminhos superiores. Saltos/FDT anteriores pertencem a LK. Corrigidos offsets de strings e BL com extensão de sinal (0x1efcd0→0x1c4820, não chamada externa 0x1001c4820). Ferramenta standard library somente leitura inspect_sboot_hzc2.py aceita hash exato e rejeita três entradas inválidas. Relatório completo em docs/sboot-layout-hzc2.md; main mantém contrato EL2 sintético até adaptação fundamentada. Branch kilo f624360 traz apenas documentação nova, sem corrigir packer ou implementar SMP. Nenhum firmware bruto publicado.


## 2026-10-21 — diagnóstico independente de entrada

Preparado Image ARM64 pequeno que registra x0–x3, CurrentEL, DAIF, SCTLR do
EL atual, MPIDR, SPSel, SP e endereços efetivos em área interna de 128 bytes.
Sem pilha, periféricos, FDT dereference ou transição de EL; recusa gravação
com M/C ligado. R10 continua exigindo EL2.

`python3 scripts/test_entry_diag.py`: 6/6 PASS em QEMU, EL1/EL2 e offsets
0/0x8000/0x1f8000. Conferidos registro, código e sentinelas. O teste carrega
Image bruto e injeta as relocações via GDB; não executa o LK Samsung.
[Documentação](docs/entry-diagnostic.md) detalha campos, pré-condições e
recusas ainda não exercitadas. Nenhum novo arquivo necessário nesta etapa;
canal físico de observação e contrato de carregamento seguem pendentes.

## 2026-10-21 — console LK e chamadas finais

Rastreada a mensagem final por objeto/tabela/callback até 0xef4c0. Encontrado escritor da base 0x10540000 em 0xef3e0, distinto de UART1 no DTB. Documentadas dependências de estado, chamadas de dump após preparação de cache e ausência de prova do EL final. Inspector hash-bound ampliado; nenhum firmware ou driver alterado. Ver [evidências](docs/lk-console-handoff.md).

## 2026-10-21 — UART0 identificada na fonte

Kernel.tar.gz recuperado com o hash anterior. DTS identifica 0x10540000 como UART0, canal debug 115200/8, pinctrl gpg0-2/gpg0-3, status disabled. Driver/cabeçalho corroboram offsets USI e TX. LK tem ramo que bloqueia fallback serial e callback adicional ainda sem transporte identificado. Novo inspetor somente leitura reproduz a evidência da fonte; nenhum pacote completo ou firmware adicionado ao Git.

## 2026-10-21 — gate do console e roteamento MUIC

Identificada decisão ifconn_get_jig_status, tabela ADC MUIC e correspondência com JIG UART/USB na fonte. Consultado MAX77705 específico selecionado no defconfig p3s; documentados AP/CP e rustproof. Criado coletor read-only de atributos novos para rish, sem repetir FDT/iomem negados. Inspetor de sboot ampliado com tabela e destinos. Nenhuma observação física, alteração sysfs ou teste Android declarado.

## 2026-10-21 — relatório UART/MUIC recebido

Coleta v1 efetivamente executada no SM-G998B/HZC2 via shell Shizuku. uart_en
presente 0660 system:radio, valor bloqueado; seleção AP/CP e ADC indisponíveis;
attached_dev = No VPS. Mensagem cruzada com lookup negativo no driver, sem
inferir ausência física de cabo ou UART desabilitada. Hash e achados registrados
em docs/runtime-collection.md, sem publicar o arquivo bruto. Não solicitar
repetição desta coleta. Estado de entrada e transporte físico seguem pendentes.

## 2026-10-21 — callback de log em memória

Rastreado callback 0xff6c8 até região 0xf0010000/2 MiB, cursor header+0x200 e wrap +0x208. DTS e debug-snapshot corroboram os mesmos endereços/offsets; kernel pode preservar e exportar last_kmsg sob condições. Criado leitor offline com 6 reconstruções/limites e 7 recusas PASS. Nenhum dump runtime adquirido ou escrita feita em região reservada.

## 2026-10-21 — coleta limitada de logs preparada

Confirmados callbacks read-only last_kmsg/first_kmsg e sec_log na fonte. Criado coletor para rish com metadados, limite 2 MiB/5 s por arquivo e recusa de pasta existente. Fixture host passou leitura exata, limite, ausência e recusa de sobrescrita; Android pendente. Documentado que proc captures não são dumps físicos para o leitor de snapshot.

## 2026-10-21 — coleta de logs recebida sem interfaces acessíveis

Relatório completo do coletor de boot logs recebido, uid=2000. last_kmsg,
first_kmsg e sec_log ausentes/ocultos; nenhum ramo de captura executado.
Hash e limites registrados em docs/boot-log-collection.md. Não solicitar
binários inexistentes nem repetir coleta. A ausência observada não demonstra
ausência de logs na RAM. Continuam pendentes contrato de boot e observação.

## 2026-10-21 — cópia do kernel ligada ao destino KASLR

Rastreado setup do contexto para cópias boot header v2/v3, destino x23 =
0x80080000 + deslocamento. Cópias usam bytes kernel e tamanho do contêiner;
mesmo campo participa do salto final. Inspector ampliado e diagnóstico
testado em EL1/EL2 nos 64 offsets: 128/128 PASS em QEMU, sem executar LK.
Contrato de verificação, RAM/reservas e observação física continuam pendentes.

## 2026-10-21 — recusa de entrada com bit de cache ligado

Fixture QEMU independente configura SCTLR.C por MRS/ORR/MSR/ISB em EL1/EL2
e salta para a Image real. As duas entradas foram recusadas antes de alterar
registro/código/sentinelas; argumentos e SP preservados. Teste padrão passou
6 entradas aceitas + 2 recusas. M ligada e caches sujas não são cobertos.
Sem mudança no código/contrato do diagnóstico ou R10 de produção.

## 2026-10-21 — MMU ligada e roadmap persistido

Fixture renomeada/ampliada para entry_diag_state.S: tabelas L0/L1 fornecidas
pelo harness, bloco identidade read-only na RAM QEMU, MAIR/TCR/TTBR0/TLBI
por EL. AT/PAR confirma leitura e falha de escrita antes de entrar na Image.
Teste padrão: seis entradas aceitas e seis recusas C/M/M|C em EL1/EL2 PASS.
Registro, código, sentinelas, tabelas, argumentos e SP preservados. Nenhuma
mudança no diagnóstico de produção ou execução física. Roadmap no repositório
registra o marco e a prioridade do contrato de carregamento/observação.

## 2026-10-21 — kernel Exynos-2100 indicado pelo usuário

Consultado lineage-22.2 no SHA 37c14d86996a49edbea8953f2523b202546b8958, Linux5.4.290. Comparados 18 arquivos com o Kernel.tar.gz recebido: 13 idênticos. Clocks CAL/binding/pinctrl deram ligações UART0 concretas; escrita pinmux LK 0x10430080 diverge do GPG0_CON 0x10430120 derivado da fonte. Diff GIC só trata readback VGIC e falha de CPU PM. Manifesto e relatório integrados sem alterar drivers ou reivindicar teste físico.

## 2026-10-21 — auditoria dos offsets pinmux

Macro e núcleo pinctrl confirmam offsets diretos. Fonte 2100: GPG0_CON
0x10430120, pinos 2/3; LK altera campos 6/7 em 0x10430080. Este offset
é gpp4/4 pinos no mapa2100, mas gpg0/8 no mapa9820 da árvore: hipótese de
legado, não prova. Word 0x10430120 existe em sboot+0x30565c, consumidor
ainda não identificado. Inspetor ampliado; nenhum acesso MMIO adicionado.

## 2026-10-21 — pinmux UART0 compatível encontrado antes do LK

Busca MOVZ/MOVK no sboot inteiro encontrou 0x1d46c configurando
0x10430120, máscara ffff00ff, valor3300. BLs em17e4c/1d5ac; rotina1d59c
passa nominais26MHz/115200 à configuração UART0. É sequência independente
do word30565c, cujo consumidor permanece desconhecido. Novo achado permite
hipótese de pinmux herdado no LK, sem confirmar execução/persistência.
Inspector e documentação atualizados; nenhum MMIO ou driver habilitado.

## 2026-10-21 — clocks UART0 e nominal do wrapper BL2

Encontradas tabelas mux/div PERIC0 em30670/30680 e duplicadas369c8/369d8.
UART_DBG seleciona IP0_USER e encoded divisor2; bit4 IP0_USER é ligado.
Entrada160c0 chama wrapper1d4b4 com 133250000/115200, gerando divisor71
compatível com LK0x47. Caminho26MHz anterior é separado, sem claim de
transição temporal. Inspector e docs ampliados; frequência real não medida.

## 2026-10-21 — origem nominal PLL_SHARED2 e auditoria offline

Identificados writes TOP mux2/div0 em169a8/1699c, repetidos36544/36538.
Fonte CAL liga PLL_SHARED2_D2 à tabela799500000/M123/P2/S1. Cadeia /2/1/3
fecha133250000 e divisorUART71. Nova auditoria offline hash-bound valida
as seleções e aritmética, recusando fontes/firmware diferentes. Gates/QCH
continuam sem estado de handoff determinado; nenhum acesso físico realizado.

## 2026-10-21 — gates UART0 e dependência separada do PCLK

Corrigida a descrição de 0x104020b8: gate do sincronizador de reset, distinto
de IPCLK em 0x10402030 e PCLK em 0x10402060. PCLK usa BUS_USER; os outros
dois usam DIV_CLK_PERIC0_UART_DBG. QCH em 0x10403014 tem campos próprios.
Auditoria ampliada para quatro fontes fixadas por hash, extraindo endereços,
campos e pais. Passou o caso real e recusou alteração individual das quatro
fontes (5/5 verificações), compilação Python e diff-check. Busca de literais
não encontrou os quatro endereços no sboot; isso não exclui acessos indiretos.
Write 0x14ce7c com offset 0x20b8 usa buffer de pilha, não CMU comprovada.
Novo documento registra o mapa e os limites; nenhum driver ou MMIO alterado.

## 2026-10-21 — modelo verificável do layout LK v3

BUS_USER/PERIC0: fonte mapeia 0x10400600, TOP10cc/18c4/20cc; busca direta
ampliada não resolveu estado efetivo. Mantida a lacuna, sem novos writes.
Retomado o contrato de carregamento: cópias 12e7f8/12e848 concatenam vendor
e boot ramdisks em 84080000, sem padding no destino. Helper149188 apenas
registra ponteiro staging da região DTB; consumidor final ainda pendente.
Boot/vendor originais recuperados, LZ4 e raw conferidos pelos hashes prévios.
Novo check_lk_v3_layout.py lê somente, limita inputs, exige firmware HZC2 e
offset explícito; recusa truncamento, formatos/offsets fora do modelo e
colisões. Sete testes de host passaram, incluindo 64 cenários e negativos.
CLI stock offset0 reproduziu kernel29469184, vendorRD12017257, bootRD701558,
DTB em vendor+b77000. Extensão Image excede cópia em4507136 bytes, sem
prova de zeroing. Inspector, README, índice e roadmap atualizados. Nenhum
empacotamento, acesso ao aparelho ou teste físico foi realizado.

## 2026-10-21 — consumidor DTB, seletor e segundo merge DPM

Globalcd3560 registrado por149188 é lido por149030('DTB'); tabela de
trabalho emfb400000 e seletor148d68 ligados. Primeiro intervalo inclusivo
custom0/custom1; conversão BE se custom1_BE<=ff, caso contrário loads LE.
Merges14935c/1493d0 usam17a900 (UFDT inferido), copiados para8b080000.
DPM check-header é BL1493a0, distinto do MOV em14939c; auditoria de palavras
conferiu esse offset antes da publicação. Estado do ramo/revisão não observado.
DTBO e DPM originais conferidos pelos hashes prévios. Seletor novo passou
em seis testes de host com fixtures independentes, limites e dois encodings.
Suíte conjunta layout/seleção: 13/13. Conferidos 31 cenários stock e recusas
CLI para DPM incorreto/revisão sem correspondência; auditoria UART preservada.
Aplicados oito overlays de placa e depois DPM com fdtoverlay/libfdt1.7.2:
8/8 candidatos,35 propriedades DPM alteradas, UART/GIC/timer/PSCI mantidos,
nenhum nó RAM. Três logs reserved-memory ficam disabled e security fica0;
isso não prova causa da indisponibilidade de logs ou liberação da memória.
Relatórios JSON sem blobs, documentação e índices atualizados. UFDT Samsung,
edições dinâmicas, reservas e execução no aparelho permanecem sem validação.

## 2026-10-21 — chosen/initrd, reservas e origem do tamanho de RAM

Escritor v3 de chosen ligado aos tamanhos dos headers: início84080000,
fim84ca12df, duas células de4 bytes, sem padding entre os ramdisks.
Modelo v3 passou a emitir os bytes esperados e aceitar --fdt para comparação
parcial, sem declarar mapa/reservas/bootabilidade validados. Os oito candidatos
placa+DPM foram recusados por chosen antigo; cells reserved-memory2/1 conferidos.
Leitor Python comum reforçado para recusar propriedades e caminhos duplicados,
que antes eram sobrescritos no dicionário. Testes reproduzem ocultação de
chosen antigo por segunda propriedade/nó. Suíte conjunta: 19/19.
Construtor148770 consulta larguras de células, escreve reg e compatible;
documentados el2_code, earlymem por HVC e kaslr, além de extras no ramo modo5,
sem assumir execução/sucesso. Getter11b758 lê64 bits de02038848 e usa cache;
setter11b798 pode limitar esse tamanho, chamado no caminho DRAMSIZE de147310.
Nenhum valor real desses serviços, mapa completo ou estado final foi capturado.
Inspector, relatório stock, README, catálogo e roadmap atualizados; sem writes
no telefone e sem novos arquivos solicitados ao usuário.

## 2026-10-22 UTC — uH earlymem e Harx soc_info

Membros uh.bin/harx.bin descomprimidos do BL HZC2 recebido, com hashes e
consumo LZ4 conferidos; nenhum blob novo no Git. HVC 0x83000004 do LK ligado
ao registro do callback 0x6c3c no uH, aplicação 0/comando 4, construtor
0x3368, tabela 0x16000 e ponteiro 0xc1401708. O handler 0x1708 altera lista
e estado, calcula tamanho no ramo automático, aloca e grava base de 64 bits
e tamanho de 32 bits nos buffers previamente zerados pelo LK. Não é consulta
pura; não se observaram os intervalos ou o resultado real.

Harx consulta 0x8200012e e exige versão 0x66001000, com mensagens soc_info.
LK usa o identificador legado -0x12e com a mesma versão, sem tradução
comprovada entre IDs. O header do kernel dá nome SJTAG ao ID positivo;
registrada a divergência sem importar essa semântica para o BL. O getter
Harx também lê 0x02038848, exige múltiplo de 1 GiB e evita leitura sem cache
quando a MMU de EL2 está ligada.

Novo inspetor com biblioteca padrão, leitura limitada e hash obrigatório
para as três imagens; relatório JSON só com metadados e instruções. Três
testes de limites passaram e 19 testes LK continuaram passando. README,
índices e roadmap atualizados. Continuação: origem dos intervalos uH e
tradução soc_info. Nenhum arquivo extra solicitado, serviço executado ou
acesso ao telefone realizado.

## 2026-10-22 UTC — origem dos intervalos LK → uH

Referência ao wrapper 0x209a38 localizada por ADRP+ADD em 0xfb4e0/0xfb4e8,
passada como callback ao percurso 0x148c38 em 0xfb4f0. O percurso compara
o prefixo memory do nome, lê a primeira tupla reg como base64/tamanho32
big-endian e chama o callback por BLR em 0x148d2c. Não filtra device_type,
status ou traduz ranges; não percorre tuplas adicionais. A chamada seguinte
0xfb4fc entra no escritor de reservas e pedido earlymem. Wrapper sempre
retorna zero, sem comprovar aceitação pelo uH.

Novo check_lk_uh_ranges.py vinculado ao sboot HZC2 na CLI, leitura FDT de
até 2 MiB e modelo limitado a células explícitas 2/1, tuplas completas e
fim sem overflow. Essas verificações de host não são atribuídas ao LK.
Relatório conserva ordem e tuplas ignoradas; não simula alocação ou memória
livre. Oito testes novos passaram; total com LK/EL2: 30 testes de host.
CLI sintética passou e DTB base stock de 389876 bytes foi recusado por
ausência de bancos. Hash do vendor_boot raw conferido novamente.

Inspetor EL2 e JSON ampliados com chamadas, palavras e handler do comando 2.
README, índices e roadmap atualizados. Próxima lacuna: valores/ramos usados
para construir os bancos e tradução soc_info, sem novo arquivo necessário
ou execução no aparelho.

## 2026-10-22 UTC — retorno constante do serviço de memória Harx

Helper LK 0xf9320 ligado ao HVC OEM 0xc6000020, separado do namespace uH.
Handler Harx 0x1534 reconhece o ID e usa tabela i16 em 0xc9c0, relativa
a 0x1b0c. Índices 0/1/2 chegam a caminhos MOVZ/MOVK: versão 0xe1200100,
base 0xc0000000 e tamanho 0x01400000. Resultado gravado no contexto por
0x2128. O chamador exige versão e conserva os buffers apenas no sucesso.

Ramo 0xfaf38–0xfaf58 cria RAM até a base Harx e avança x19 para o fim,
omitindo condicionalmente 20 MiB até 0xc1400000. Sem afirmar que esse ramo
executou ou que o restante está livre. Escritor do flag relativo 0x487c90
localizado em 0xf90d8, antes do HVC 0xc6000040, posteriormente identificado
como registro de callback/buffer de crash; flag 1 não prova sucesso desse
registro. Soc_info Harx tem nomes impressos distintos para
quantidade reservada (índice 1) e tamanho Secure DRAM (índice 20); mantida
a lacuna da tradução para o identificador legado LK.

Inspetor ampliado com decodificador limitado de folhas constantes, tabela
assinada, verificação do destino de saída e metadados do ramo LK. Três
testes novos de decodificação/recusa passaram; com LK e EL2: 33 testes de
host. CLI conferida nas três imagens recebidas; JSON, README, índices e
roadmap atualizados. Continuam pendentes respostas soc_info/SEC_PGTBL e
estado efetivo de boot. Nenhum arquivo adicional solicitado, serviço
executado, driver alterado ou acesso ao telefone realizado.

## 2026-10-22 UTC — candidato sysfs de log Harx

Fonte exynos-el2.c identificou atributo exynos_el2_log, modo declarado 0644,
getter HVC 0xc6000043 e store separado que reseta cursor. Configuração
embutida na Image stock extraída entre IKCFG_ST/ED: 203018 bytes, hash
55dde3bb7c52e99eccdb82b925a4b831c03fd32a19a2b64bdf7bda993e92a2e1;
EXYNOS_EL2=m e páginas de 4 KiB. DTB base tem /el2_dynamic_lv3. Isso não
prova módulo carregado, probe bem-sucedido ou permissão do shell.

Header HVC e handler Harx ligam índices 3/4 ao RAM log c1200000/200000.
Getter bb0 atualiza cursor em c48/c6c; reset b8c é outra operação, nunca
solicitada pelo coletor. Corrigida a classificação antiga de c6000040:
registro de callback/buffer de crash, confirmado por 1bc8→da0 e store e10,
sem generalizar a falha desse registro para toda a inicialização Harx.

Novo auditor offline exige hashes do Kernel.tar.gz e imagens boot/vendor,
verifica seis fontes e gera metadados sem extrair caminhos. Coletor faz
uma captura nova de até 4096 bytes/5 s, sem loop, aliases adicionais ou
escrita/reset do atributo; pode avançar o cursor durante leitura normal.
Sete testes novos passaram, inclusive limite, pasta existente e timeout;
total com LK/EL2: 40 testes de host. Evidências JSON, README, roadmap e
índices atualizados. Resultado no aparelho pendente; nenhuma das coletas
rish bloqueadas foi repetida. Soc_info/SEC_PGTBL continuam sem valores reais.

## 2026-10-22 UTC — coleta Harx recebida: atributo presente, leitura bloqueada

Recebido report.txt de 807 bytes, SHA-256
9aacaa65650eba56609b1f5755073dee98742c2b28c6181fd4ed9a21a3f7fead.
Horário informado 01:21:21 UTC, sem confirmação externa do relógio. Sessão
uid=2000, contexto shell; modelo/build/bootloader confirmam SM-G998B/HZC2.
Nó /sys/devices/platform/el2_dynamic_lv3/exynos_el2_log existe, ls mostra
0644 root:root e tamanho 4096. Teste -r retornou falso: UNREADABLE.

Coletor encerrou antes de abrir o atributo; não houve captura, READ_EXIT
ou chamada do getter por essa execução. Não solicitar el2-log.txt nem
repetir a coleta. 4096 é metadado sysfs, não quantidade de log disponível;
0644 não identifica a causa da restrição. Não atribuir especificamente a
SELinux sem evidência de política/auditoria. Presença corrobora atributo
do driver, sem revelar RAM, SEC_PGTBL ou estado de handoff.

Metadados sanitizados separados da evidência estática; original não publicado.
README, hardware, guia de coleta, índice e roadmap atualizados. Somente
documentação/metadados: JSON e diff conferidos, sem rerodar os 40 testes de
host anteriores. Análise estática segue com os arquivos já recebidos.

## 2026-10-21 Campo Grande / 2026-10-22 UTC — SEC_PGTBL e LDFW

LDFW extraído do membro exato do BL, consumo LZ4 completo, tamanho 8388608
e hash 9d52a013bffde6f3d734e02a359ce9323a7db75878fce60569f5989b63e057fd
conferidos. Marcador CryptoManagerV50 em 0x30 e nome ldfw.img em 0x3fc09c;
sem atribuir semântica de carga/decriptação aos campos e sem recuperar handler.
Mensagens LK indicam dependência LDFW, não localização comprovada do provedor.

Chamadas SMC 0x82002060 índices 1/2 em 0xfae40/0xfae90 isoladas. Base usa
X0 com sentinelas de 64 bits e alinhamento 1 MiB; tamanho usa W0, descarta
bits superiores e tem sentinelas de 32 bits. Em 0xfaeac, AND X1,X21,#0xfffff
testa novamente a base normalizada, não o tamanho. Sob a preservação de
X21/W22 esperada pelo chamador, esse teste não rejeita um tamanho desalinhado.
O modelo conserva essa aceitação e oferece guarda aritmética adicional,
sem confundi-la com checagem LK ou autorização de memória livre.

Novo inspetor stdlib exige as duas identidades antes de emitir evidência ou
cenário. Respostas são opcionais, explicitamente hipotéticas, sem padrões.
Sete testes novos passaram: sentinelas X/W, truncamento, alinhamento, wrap,
limites de input e CLI com firmware incorreto. CLI original e exemplo
sintético conferidos; relatório sem cenário versionado, sem novos blobs.
README, hardware, catálogo e roadmap atualizados. Nenhuma repetição das
coletas bloqueadas ou alteração de driver/payload. Próxima lacuna continua
sendo o provedor e os valores efetivos soc_info/SEC_PGTBL.

## 2026-10-21 Campo Grande / 2026-10-22 UTC — contêiner LDFW e Unicorn

Aplicadas as propostas de análise estática/emulação aos arquivos já recebidos.
Percurso por magic 0x10adab1e e tamanho +0x4 recupera seis registros até
0x3fc000: CryptoManagerV50, fmp_fw_V20, drm_fw, srpmb_fw, hdcp_fw e tail_fw.
Cabeçalho comum cruzado com U-Boot fixado em 3d9115a; offsets de tamanho,
versão e nome corroborados pelo próprio LK. Loop em 0xf6658–0xf6694;
0xf66b0 chama wrapper 0xf60e8, SMC -0x500 em 0xf60fc, buffer fa000000 e
prefixo de 3fc000 bytes. É entrega ao monitor, sem execução observada.

Formato relacionado Exynos9830, commit 5142272, interpreta +0x28 como
cifragem e +0x44/+0x48 como início/fim exclusivo. Cinco registros têm flag 1;
DRM em 0x228000 tem start_smc_id 0x82002000 e intervalo 0x228150–0x23a5b0,
74.848 bytes. A diferença de 0x60 para a consulta é pista, não dispatch
recuperado. Ensaio offline limitado com a hipótese/chave pública 9830 não
validou plaintext; nenhuma imagem modificada foi gravada ou publicada.
Algoritmo/chaves/IV/base runtime do HZC2 continuam sem validação. Apresentação
original OffensiveCon 2022 corrobora LDFWs cifrados na arquitetura S21.

No tail em claro, conferidos cinco leaves AArch64 MOV W0,#0;RET. Não foram
atribuídos ao SEC_PGTBL. Novo parser stdlib limita input/registros/tamanhos,
rejeita intervalos malformados e mantém assinatura/provedor não verificados.

Unicorn 2.1.4 instalado fora do Git. Novo harness executa o chamador real
0xfae2c–0xfaec8 e ramos de erro com somente três páginas RX. Intercepta SMC,
exige argumentos conhecidos, fornece duas respostas explícitas, omite printf
e envenena voláteis; orçamento de 256 visitas/1s por cenário. 80 combinações
e 64 pares de seed fixa, total 144, coincidiram com X21/W20/W22/X27 do modelo.
O tamanho sintético 0x1000 com base 0xe0000000 manteve W22=1. Provedor não executado;
sem retorno real, MMIO, mapa de RAM ou alegação de estado do aparelho.

14 testes de host passaram, incluindo sete novos de parser/identidade.
Relatórios metadata-only atualizados/versionados; README, hardware, índice,
catálogo e roadmap revistos. As suítes anteriores R8/R9/R10 não foram
reexecutadas, pois seus arquivos não mudaram. Para recuperar especificamente
o handler falta DRM HZC2 em claro com origem verificável ou fonte equivalente;
o contêiner cifrado e os READMEs já enviados não precisam ser reenviados.
Nenhuma coleta bloqueada foi repetida, sem root ou tracing no telefone.

## 2026-10-21 Campo Grande / 2026-10-22 UTC — enum DRM e contexto dos retornos

Conferida a sugestão de smc.h no Kernel.tar.gz já recebido. Arquivo real:
include/soc/samsung/exynos-smc.h, 8105 bytes, SHA c896ed8086009ae3055c6ac6b3164744c9e7cf7286a0ad993eba2b4792b7db49.
Header público em Exynos-2100/universal2100, commit 37c14d8, é idêntico
(Git blob 45c8d284835868ed8e9970340590c3294aba9fbd). Enum drmdrv_result_t
contém 52 valores, confirmando a família 0x1001–0x100b proposta pelo usuário.
SMC_PROTECTION_SET=82002010 e SMC_DRM_FW_LOADING=82002011 também confirmados.
Esse header não declara a consulta 82002060 ou o carregamento legado -500;
definições não fornecem corpo seguro, chaves ou enum produzido pela consulta.

Chamadores ION HPA, MFC ops/PM e GPU conferidos na fonte recebida: operações
de proteção testam DRMDRV_OK. Não transferido esse teste para SEC_PGTBL,
que usa zero como inválido. No LK, resposta de -500 passa por W0 signed,
casos -1/1230/1231, prefixo de assinatura fdaa e desempacotamento de
tentativas/falhas em 16 bits. Wrapper efetivo escreve X0=fffffffffffffb00.
Palavras/strings e metadados de fonte registrados, sem executar o serviço.

Opção --drm-header nos inspetor/emulador requer identidade exata. Parser de
enum aceita somente inteiros explícitos e rejeita expressões/duplicidades,
sem eval. Os 52 nomes são catálogo de status, sem reclassificar dados de RAM.
Unicorn repetiu os 144 cenários básicos e mais 104 injeções hipotéticas das
52 palavras como base/tamanho: 248/248 coincidiram. Exemplo fornecido 1003
como tamanho mantém W22=1 e fim e0001003; não demonstra retorno real do DRM.

20 testes de host passaram (14 anteriores e seis de enum/contexto/hash).
Relatórios JSON e documentação atualizados. Nenhuma suíte R8/R9/R10 foi
reexecutada, sem mudanças nesses componentes. O harness contém só o chamador
Normal World com SMC interceptado: não existe RAM Secure descriptografada
nele para dump. ELF também não é requisito garantido para plaintext LDFW.
Sem novos pedidos de arquivos já recebidos, sem coleta/root/tracing no telefone.

## 2026-10-22 Campo Grande — DTS recebidos e reprodução da base HZC2

Recuperados os dois DTS enviados e conferida identidade com os membros
exatos do Kernel.tar.gz c5ad9994…86bf2: base 495720 bytes/586ca569…8ca8 e
overlay UNIVERSAL2100 rev11 234843 bytes/e623b6ed…e43a. Os originais ficaram
intactos. A compilação direta da base produziu 2249 nós, com apenas três
propriedades diferentes da base binária HZC2: /ems/pe-list/list@0..2/cpus.
Escapes como \04 e \07 consumiam dígitos da próxima string como octal.

Patch de três linhas troca essas representações por listas separadas por
vírgula. Aplicação com GNU patch a uma cópia e compilação DTC 1.7.2 -a 4
reproduziram todos os 389876 bytes da base de vendor_boot em 0xb77040,
SHA d75cd25518112ec3a64235497b33f2caf84d60e8080b92c17ef98774c439aa2d.
Caminhos/propriedades também comparados com o parser estrito. Transporte
LZ4 de boot/vendor consumido integralmente e hashes brutos conferidos.
Ferramentas Debian extraídas fora do Git, sem root ou alteração de binários
versionados. Avisos herdados do compilador foram contados, sem alegar
validação de todos os bindings ou efeito observado no scheduler do telefone.

Overlay genérico compilou e aplicado à base tem 3311 nós, UART0 okay,
UART1 disabled. A referência P3S r17 do mesmo pacote tem 3778 nós depois
da aplicação e ambas UARTs okay. Seu DTBO compilado difere do hash stock
da entrada 2, embora tenha o mesmo tamanho; não foi feita a comparação
das propriedades desse overlay com o binário stock. Metadados rev11/0x11
não determinam a revisão efetivamente selecionada no aparelho.

As duas aplicações fdtoverlay 1.7.2 conservaram GIC/timer/PSCI e não criaram
nós RAM. Mantiveram initrd 84000000–841fffff e foram corretamente recusadas
pela checagem LK v3, cujo modelo stock produz 84080000–84ca12df, fim
exclusivo. Inventário bruto de reserved-memory: 46 descendentes, 29 com
reg, 16 size sem reg e um contêiner. Não deduzir endereços de heaps, código
DRM em claro ou RAM livre a partir dessas declarações.

Patch pequeno, relatório JSON e reprodução documentados; README, índice,
hardware, referência externa e roadmap atualizados. Nenhum blob de firmware
ou DTS completo acrescentado ao Git. R8/R9/R10 não mudaram e suas suítes
anteriores não foram reexecutadas. Sem nova coleta bloqueada, pedido de
reenvio, flash ou teste físico. Próxima lacuna: ajustes dinâmicos de memória
e estado/valores efetivos do LK.

## 2026-10-22 Campo Grande — aritmética do construtor de bancos RAM

Seguido o construtor 0xfad60 e os blocos 0xfb670–0xfb7cc no sboot HZC2
identificado por SHA. Pacote BL já recebido recuperado, SHA/MD5 de transporte
e consumo integral LZ4 conferidos; sboot/uH/Harx brutos bateram as identidades
anteriores. Capstone 5.0.7 e Unicorn 2.1.4 usados fora do Git, sem firmware,
dependências ou novos toolchains binários acrescentados ao repositório.

Modelo novo recebe nove entradas explícitas. Versão soc_info é comparada em
W com 66001000; base X=-1 e quantidade W=-1 estacionam antes dos bancos.
Cursor usa soma X da base com quantidade truncada para W. Recortes Harx e
SEC_PGTBL ligados às chamadas 0xf1570, tamanhos calculados em W, sem atribuir
validação de ordem/overlap às subtrações. Escritor formata memory@%lx e
reg como base de 64 bits/tamanho de 32; ferramenta registra bytes se escrito,
sem executar editor, criar árvore ou afirmar sucesso da modificação.

Acima de 2 GiB, o laço começa em 0x880000000 e pede blocos inteiros de
0x20000000, contando por teto do restante/512 MiB. Último bloco não é
reduzido ao restante. Caso artificial de 2 GiB+1 deixa 1fffffff bytes além
do restante fornecido; caso de 12 GiB fornecidos pede 20 blocos altos.
Não foram inferidos total efetivo, disponibilidade ou defeito no aparelho.

Harness executa três páginas RX originais e pilha RW de 128 KiB. Intercepta
SMC, substitui getter/Harx/printf e envenena voláteis, preservando callee-saved
esperados. Salta FAEF4→FAF28 para omitir preparação FDT, MMIO do flag e os
ramos de bootargs; termina em FAF84 ou nas três paradas soc_info. Captura
argumentos dos oito pontos de chamada ao escritor sem executá-lo. Limites:
4096 visitas/1s por caso, guardas de PC/SMC; nada de MMIO físico ou Secure
World mapeado. Limite de 128 chamadas é da representação host, não do LK.

268/268 cenários coincidiram: 192 combinações, 12 de borda e 64 da seed
fad60. São 263 fases concluídas e cinco paradas; máximo 877 visitas e 128
chamadas. CLI com cenário explícito também conferida. 44 testes de host LK
passaram, incluindo 17 novos para limiares, wraps, recortes, células, JSON
limitado/duplicado/profundo, identidade e recusa de firmware incorreto.

Ferramentas, relatórios metadata-only e reprodução documentados; README,
hardware, índice, catálogo e roadmap atualizados. R8/R9/R10 não mudaram;
suas suítes não foram reexecutadas. Nenhuma coleta bloqueada repetida,
pedido de reenvio ou teste/flash no telefone. Respostas efetivas dos serviços,
sucesso do editor e FDT final continuam abertos.

## 2026-10-22 Campo Grande — novo roadmap e estado consolidado

Revisada a main a048682 e a evidência das entregas para substituir o roadmap
acumulado por um estado por frente, prioridades P1–P6 e critérios de saída.
Separados dois marcos: primeiro registro de entrada no S21 e R10 físico em
uma CPU. A Image diagnóstica só grava em seu próprio intervalo, não lê FDT
ou usa pilha/periféricos. Para esse marco basta comprovar a região inteira,
coerência, entrada, carregamento e leitura; FDT/memória e reservas confiáveis
continuam requisitos do R10, investigados em paralelo. Não inferido que esses critérios
já estejam atendidos ou que o diagnóstico possa ser executado agora.

Prioridade imediata definida como auditoria final de entrada/coerência do LK,
com canal de observação e memória dinâmica em paralelo. DRM cifrado foi
tratado como limite específico da análise do provedor, sem torná-lo condição
universal para o diagnóstico mínimo. Mantidos bloqueios de coleta Shizuku,
arquivos já recebidos e distinção entre respostas simuladas/estado real.

README e índice apontam para o roadmap como entrada de planejamento. Main
e zero PRs abertos conferidos pelo GitHub. Revisão somente documental:
links, estrutura e consistência das contagens conferidos; suítes anteriores
não reexecutadas. Nenhum código de payload, firmware ou arquivo recebido
alterado; modificação local preexistente de magisk.apk ficou fora da entrega.

## 2026-10-22 Campo Grande — helper de cache e argumentos finais do LK

Iniciada P1 do novo roadmap no sboot HZC2 já recebido e identificado por
hash. Seguidos 18a3a8, seletores SCTLR, percurso 18997c/189848 e limpeza
189db8. M=1 chama DC CISW por set/way e limpa M/C somente no EL atual;
M=0/C=1 conserva C. I e SCTLR dos outros níveis permanecem inalterados.
Não há mudança de EL nos caminhos suportados do helper. LoC e CCSIDR são
interpretados com campos legados; não inferida geometria A55/A78/X1.

Modelo novo recebe nove entradas explícitas e conserva sequência de
CSSELR/DC/DSB/ISB/DAIF/SCTLR. Harness Unicorn executa as instruções originais
desde FBDD4 até o BLR e para no alvo sintético antes do payload. MRS/MSR/DC
e barreiras são fornecidos/registrados, sem simular tradução, cache suja,
traps ou RES1/RAO/WI. São omitidas chamadas IRQ-disable, modo/saída e printf,
sob preservação do estado de sistema; voláteis são envenenados. Sem alegar
que essas substituições executem cache ou validem coerência física.

352/352 cenários coincidiram: 288 matriz +64 seed18a3a8, 174 com manutenção
e 178 sem; 64 deslocamentos de kernel cobertos. Máximos 2370 visitas e 266
operandos DC. 14 testes novos passaram para M/C/I, EL ativo, DAIF, operandos,
guardas JSON e identidade. CLI com cenário M=0/C=1 em EL2 também conferida;
SCTLR_EL1 não foi alterado. Argumentos finais condicionais X0=8b080000,
X1–X3=0, alvo=80080000+offset_u32 e LR=FBE18 foram reproduzidos.

Fronteiras mantidas: SMC -3ff em FBDD0 antes do trecho, printf e callbacks
mutáveis depois do helper (BR em 20c624 e BLR em 20c4dc). Corpo direto de
F29A0/MMIO conhecido não fecha efeitos de seus chamados. Mascaramento
explícito força só IRQ; não presume DAIF completo ou EL final no aparelho.

Protocolo arm64 de boot foi lido no Kernel.tar.gz recebido (booting.rst,
11898 bytes/bf8bf803…24c), e TF-A v1.5 consultado como referência primária,
sem atribuir ao upstream identidade com Samsung. PoC/coerência de sistema
continua pendente; I-cache ligada é admitida pelo protocolo de boot.

Ferramentas, hashes de trechos, exemplo artificial e relatórios versionados;
README, hardware, índice, catálogo e roadmap atualizados. R8/R9/R10 e a
Image diagnóstica não mudaram; suas suítes e os 44 testes LK anteriores não
foram reexecutados. Sem firmware/dependências novos no Git, coleta bloqueada
repetida ou teste físico. Alteração preexistente do APK ficou fora do commit.

## 2026-10-22 — referências HackiOS / XNU indicadas pelo usuário

Clonados separadamente hackios-xnu-kernel em 8e611870 e hackios-xnu-userland
em 906425b7. Revisão direcionada dos perfis, contrato de carga, GIC/PSCI,
retorno/logs, substitutos IOKit, init/ABI, montagem de imagens e frontend
AIR/Mesa. Alvos upstream redwood/Snapdragon e QEMU; kernel, UEFI e iOS não
foram executados nesta revisão. Resultados de interface
gráfica e corpus AIR permanecem relatos upstream.

Conferidos 7/7 hashes do prebuilt/SHA256SUMS; formatos Mach-O arm64 e EFI
AArch64 identificados. Exercitado common/new-device.sh com DTB base HZC2
verificado por hash e DTC 1.7.2: oito CPUs, shift 8, small_cores=0x0f;
GIC ficou TODO porque o parser cobre quatro ou pelo menos oito células,
enquanto nosso reg tem seis (endereço 2, tamanho 1). Saída gerada somente
na cópia externa, sem perfil executável adicionado ao S21-baremetal.

Registrados contratos distintos XNUP/Mach-O/boot_args/árvore Apple e
S21R10/ELF/FDT; stride GICR fixo 0x20000 e mapa de 1 MiB versus os 2 MiB
HZC2; timer virtual INTID27 versus físico INTID30 do R10; dependência de
UEFI/protocolos USB Qualcomm. Retorno/log em RAM e framebuffer com CPU são
referências úteis, ainda sem backend Samsung. write_logs pode gravar em
logdump no alvo upstream. AIR → NIR é oportunidade de pesquisa, sem driver
Mali fornecido pelo caminho freedreno/ir3.

Nova referência e manifesto de hashes publicados; README, índice e
roadmap incluem X0–X4 como frente de laboratório. P1–P6 e os requisitos
físicos foram preservados. Nenhum arquivo adicional solicitado, IPSW/SDK
baixado, código de payload modificado ou suíte R8/R9/R10 reexecutada.
Modificação preexistente do APK e arquivos temporários do toolchain
permanecem fora da entrega.

## 2026-10-22 — XNU no QEMU e objetivo Android/XNU

Usuário aprovou continuar com a possibilidade futura de escolher Android
ou XNU/userland iOS. Criado laboratório separado: UEFI Debian não Secure
Boot, loader/kernel HackiOS prebuilt nos commits e hashes já examinados,
APFS mínimo e programa Darwin próprio em assembly. GNU as/objcopy geram
texto sem SDK; empacotador fixo cria Mach-O estático de 16 KiB. Nenhum
programa Apple de userland, IPSW ou SDK foi usado. Kernel não recompilado.

Diagnóstico roda como /sbin/launchd apenas pelo nome exigido na entrada;
confere PID1/UID0, conteúdo exato/EOF de um arquivo APFS, select de 200 ms
e avanço de relógio entre 100 ms e 10 s, depois pede RB_HALT. Corrigido
argumento opcional X2 de gettimeofday após conferir kern_time.c da base
Apple: residual não nulo podia produzir EFAULT. Ensaio de calibração com
hello upstream terminava em panic ao sair de PID1; casos finais usam nosso
programa e encerram sem panic, voltando ao carregador.

Caso final positivo: 17 critérios satisfeitos, QEMU saiu 0. Controle com
mesmo executável e arquivo do mesmo tamanho, alterado em um único byte:
FAIL APFS fixture, QEMU saiu 0, harness saiu 1. Isso demonstra recusa mesmo
com encerramento normal; as fases posteriores não foram executadas no
controle. 13 testes de host passaram, separados das duas execuções QEMU.

Runner verifica entradas por SHA/revisão, exige UEFI testada e pasta nova,
cria NVRAM/FAT próprios e registra comandos, hashes, resultado e serial.
Publicados relatório e transcrições completas em texto com controles
escapados; hashes brutos separados. Sem novos binários, imagens ou
dependências no Git. README, índices e roadmap registram X1 concluído
com prebuilt e D0–D4 até eventual escolha de boot. P1/P2 Samsung mantidos;
nenhum teste no S21, menu de boot ou userland iOS executado. R8/R9/R10 e
firmware recebido não mudaram; suas suítes não foram reexecutadas.

## 2026-10-22 — contrato binário XNU e captura no arm_init

Avançado X2 no host: codec próprio de boot_args revisão/versão 2, árvore
Apple canônica e política conservadora de intervalos. Conferidos 736 bytes
de estrutura e 13 offsets com sizeof/offsetof em C LP64, usando boot.h
Apple fixado por hash sem alterações; dois includes alheios ao layout
foram substituídos por stubs. Quatro fontes Apple identificadas no
manifesto. Não houve build do kernel XNU.

28 testes de host passaram: codecs, truncamentos, limites/overflow,
duplicidades, memória incompleta, buracos/reservas/sobreposições e recursos
incompatíveis. Fixture Samsung preserva GICR de 2 MiB, oito MPIDRs e SMC,
mas sua RAM é sintética e não autoriza memória no aparelho.

Nova execução QEMU com kernel/loader/UEFI já conferidos, FAT/NVRAM próprios
e breakpoint de execução no arm_init do prebuilt. Leitura GDB sem alterar
registradores/buffers capturou 736 bytes de argumentos e 14800 de árvore;
decode/encode reproduziu cada byte. x0 era virtual no estágio C; PA foi
derivado da janela linear. Não é observação da entrada MMU-off ou Samsung.
Breakpoint removido, execução retomada: 17 critérios PASS, QEMU saiu 0.

Consistência de memória usa declaração explícita da fixture QEMU de 6 GiB
e protege o contêiner de entrada. Não capturamos o mapa completo UEFI;
trust_established e hardware_ready continuam false. Parser C R10 existente
com ASan/UBSan aceitou a estrutura da base HZC2, mas recusou sua política:
sem bancos RAM, 29 reservas e uma não resolvida. Nenhum plano de carga
Samsung gerado.

Publicados contrato, manifesto com hashes/comandos e scripts de teste/
captura; README, índices, roadmap e estratégia agora marcam X2/D2 parcial.
Próximo X2: tradução FDT → árvore Apple com proveniência, sem preencher
RAM desconhecida. P1/P2 físicos mantidos; nenhum anexo adicional pedido,
binário bruto versionado, shim habilitado ou operação no aparelho. Suítes
antigas R8/R9/R10 e do init XNU não foram reexecutadas. APK preexistente e
temporários do toolchain excluídos da entrega.

## 2026-10-22 — projeção FDT Samsung e correções de preparação HackiOS

Usuário trouxe relato GLM-5.3 de execução do userland iOS no QEMU, ainda
em andamento. Heads upstream conferidos: kernel 8e611870, userland 906425b7,
iguais aos commits já auditados. Não recebemos nessa mensagem print final
ou serial bruto completo daquela execução; os checkpoints gráficos
permanecem relato externo. Nenhum download iOS/SDK ou sessão GUI local.

Continuado X2: inspetor C de host expõe o parser R10 existente, sem defaults
de destino ou alteração de produção. Adaptador reutiliza também o leitor
FDT limitado; cruza intervalos GIC e MPIDRs/ordem, lê PSCI/clock/timer
virtual explícitos e registra propriedades de origem. Projeta somente
recursos na árvore Apple, sem RAMDisk, janela DRAM, estado de CPUs ou
identidade Apple. Bases MMIO não são usadas para tocar hardware.

Base HZC2 gerou fragmento de 1944 bytes, reemitido byte a byte. Preservados
oito MPIDRs, SMC, GICD/10000, GICR/200000 e 26 MHz nominais; físico INTID30,
virtual INTID27, flag Linux use-physical-timer. Sem bancos RAM e com 29
reservas/indicador não resolvido, não gerou plano de carga. Initrd
declarado [84000000,841fffff) foi conservado: tamanho 1fffff, sem arredondar
para 2 MiB. FDT base não é o resultado dinâmico do bootloader.

29 testes novos passaram com ASan/UBSan, incluindo composição positiva de
memória sintética, bancos acima de 4 GiB e recusas por RAM/reservas/PSCI/
CPU/timer/GIC/corrupção/sobreposição. LeakSanitizer desativado porque o
host instrumentado não permite inspeção de threads; demais sanitizers
ativos. API de candidato protege initrd Linux e buffers vivos, exige
declaração explícita de completude e sempre conserva hardware_ready=false.

Relato GLM aproveitado por reprodução independente: seis fixtures de jobs
mostram colisão em RWA_PACKED16 com variável ausente/presente e modos
0664 sob umask002, conservados pelo leitor APFS original com UID/GID0.
Renomear iterador preserva nomes; umask022 produz modos0644/diretório0755.
Quatro fragmentos Bash reproduzem/controlam falhas de drawable_test
ausente e timedatectl com set-e. Patch preserva whitespace, foi conferido
por git apply --check e bash -n e não altera o checkout externo. Não foi
executado build completo, APFS completo ou launchd/SpringBoard.

Documentados adaptação, patch, hashes e ensaios; fragmento inteiro incluído
em hexadecimal no manifesto. README/índices/roadmap/estratégia atualizados.
Próximo X2: integrar projeção ao caminho de carga do laboratório com
memória explícita e contraprovas. P1/P2 físicos mantidos; nenhum arquivo
extra solicitado, operação no telefone ou reexecução das suítes antigas.
APK preexistente e temporários do toolchain fora da entrega.

## 2026-10-22 — consumidor EFI dos recursos, executado no QEMU

Integrada a projeção ao carregador de laboratório: variante compilada do
loader upstream 8e611870, com validador C freestanding e entrada adtres no
XNUP. Cópia do fonte verificada por hash; checkout externo intacto. EFI
AA64 de 71680 bytes, compilada com Clang/LLD 19.1.7, sem SDK Apple. Kernel
continua prebuilt; somente o carregador foi recompilado.

Fixture FDT explícita declara uma CPU, 6 GiB, HVC, 62,5 MHz e GIC QEMU.
Perfil acrescenta PL011; fragmento Apple de 908 bytes. Parser C limita
payload/nomes/padding/duplicidades e bounds Mach-O; consumidor exige o
perfil, compara CNTFRQ/MPIDR e confere intervalos antes do salto. Não é
parser geral Apple, autenticação de executáveis ou caminho Samsung.

Reinício do ambiente perdeu dependências/ensaios temporários e reabriu um
checkout antigo. Main recuperada por fast-forward, clones fixados e
ferramentas recompostos. Baseline antigo reexecutado por essa mudança de
ambiente: 17/17. Nenhum arquivo adicional solicitado ao usuário.

Execuções finais: positivo 20 critérios PASS, incluindo as marcas nativas
de recursos/layout. GDB somente leitura em arm_init conferiu GIC, CPU,
PSCI, contador, I/O/UART e reemissão de 736/14800 bytes; removido breakpoint
e retomado até init/APFS/timer/RB_HALT/retorno normal. Cinco recusas:
fragmento truncado, frequência alterada, GIC incompatível, entrada duplicada
e comando Mach-O zero. Todas sem marca de cópia/salto/Darwin/init e com
recusa explícita, apesar de QEMU sair 0.

16 testes de host do mesmo C passaram com ASan/UBSan, incluindo todos os
prefixos do fragmento e recusa do fragmento HZC2. Duas compilações em pastas
diferentes no mesmo host geraram EFI de SHA72bf433f...; isso não é build
independente do kernel. Fixture/memória UEFI não descrevem o S21; mapa
completo de reservas do firmware não foi capturado. hardware_ready=false.

Publicados código, instruções, manifestos de build/ferramentas e seis
transcrições; README, índices, estratégia e roadmap atualizados. Artefatos
brutos e dependências fora do Git. P1/P2 físicos mantidos; sem operação no
telefone, userland iOS ou SMP. Suítes R8/R9/R10 não reexecutadas; fontes
de produção e temporários de toolchain preservados fora desta alteração.

## 2026-10-22 (2026-10-23 UTC) — reservas e mapa completo UEFI no laboratório XNU

Continuado o item de memória proposto ao usuário. Main de partida 729e7f0.
Identificada lacuna concreta: o loader evitava o payload ao escolher a
janela, mas não reservava sua memória. Variante agora exige os 64 MiB
convencionais e faz AllocatePages/AllocateAddress/EfiLoaderData antes da
leitura. Seleção da janela usa mapa validado e exige status/endereço exatos.

Novo C freestanding limita GetMemoryMap a 64 KiB, 1024 descritores,
versão 1 e stride 40..256 em múltiplos de oito. Confere overflow,
alinhamento, sobreposição, cobertura integral e política de tipo/atributos.
Não presume tamanho 40 para caminhar o mapa nem ordem dos descritores.
ABI do prefixo conferido por static asserts. Mapas completos capturados
antes da reserva do payload, antes da reserva da janela, antes da cópia
e na preparação do salto. Falha de mapa/posse provoca recusa.

Execução final: 80/82/82/82 descritores, stride 48. Payload
[f0000000,f4000000), janela [f4000000,1be000000), duas reservas com status
0. UEFI juntou ambas num descritor LoaderData; corrigida a exclusão da
janela no percurso de cache para recortar ambos os lados de um descritor
sobreposto. Nenhuma validação de cache Samsung inferida desse ensaio.

Runner cruza os mapas reais com boot_args/árvore obtidos por GDB somente
leitura. RAM/reservas para essa conferência vêm de GetMemoryMap, não da
fixture FDT. Todos os segmentos, ramdisk, árvore e argumentos cobertos.
Mapas emitidos sem filtros, byte a byte em hexadecimal, após retorno ou
recusa; a última captura é usada na manutenção de cache, sem alocação ou
emissão dos mapas entre ela e o salto. UEFI continua residente, sem EBS.

Nove execuções finais PASS: positivo com 22 critérios; cinco recusas
anteriores de recursos/payload; três falhas de memória via APIs UEFI reais
em binários de teste separados (payload ocupado, página da janela tomada
por BootServicesData e página do payload devolvida). Cada falha exige
sucesso da API provocadora, recusa específica e ausência de cópia/salto/
Darwin/init. Positivo retomou até PID1/APFS/timer/RB_HALT/retorno normal.

22 testes novos de memória/evidência passaram, incluindo o mesmo C com
ASan/UBSan e verificador Python independente. Reexecutados os 16 testes
dos recursos, todos PASS. LeakSanitizer desativado pelo host instrumentado.
EFI normal final: 75264 bytes, SHA256
510b1dcb693a93db2de3ea2707884b18bac2533c1656cd7e7371a1f3d6b33430.
Kernel continua prebuilt; loader recompilado e init próprio reaproveitado
do baseline verificado.

Publicados nove logs completos, manifesto com hashes/comandos e guia de
reprodução; bytes dos mapas reconstruídos das transcrições e comparados
aos binários da execução. README/índices/roadmap/estratégia atualizados.
O registro é do mapa reportado pela UEFI naquele instante: não autentica
imagens arbitrárias, não prova preservação anterior do payload nem memória,
entrada, caches ou observação Samsung. P1/P2 físicos continuam abertos.
Nenhum arquivo adicional solicitado, flash, interface iOS ou SMP.
R8/R9/R10/shim e baseline anterior preservados; sem repetir essas suítes.


## 2026-10-23 — ramfb: prebuilt confirmado, correção e capturas reais

Novo relato GLM informa interface iOS funcional com bypass do ramfb no
loader. Prints/log bruto daquela sessão não recebidos; teste subsequente
do fluxo original ainda incompleto. Atualizado o estado externo sem
convertê-lo em reprodução local de iOS ou evidência Samsung.

Workspace restaurado com checkout anterior; main recuperada por fast-forward.
Fontes e toolchain recuperados pelos hashes publicados. Baseline XNU com
init próprio repetido: 17/17. O prebuilt original SHA9749fa6c... declara
800x600 após mudar o ramfb a 1125x2436. Desmontagem confirma print sem
releitura após gatilho; QMP somente leitura encontra control=0 em RAM.
A fonte original recompilada com Clang19/O1 funciona: falha demonstrada
por versão do binário, não generalizada a qualquer compilação.

Correção fonte: volatile, barreiras, leitura limitada da conclusão,
EFI_DEVICE_ERROR em erro/timeout; SCREEN só atualizado no sucesso.
Seis casos QEMU: prebuilt, rebuild original sem instrumentação, original
com padrão, corrigido com padrão, erro real por seletor somente leitura e
timeout por gatilho omitido. Todos com critérios satisfeitos. Captura PNG
nativa; PPM do QEMU tinha padding de linha e foi abandonado como formato
de captura para evitar diagonais artificiais no leitor de imagens.

Builder EFI do S21-baremetal aplica a correção; consumidor com mapas UEFI
retomou XNU/init/APFS/timer/RB_HALT com 22/22 critérios. Sem relaxar perfil
headless do verificador. Patch independente conferido com git apply --check.
Publicados manifesto, sete seriais completos, trecho de desmontagem,
capturas reais e guia; README/índices/roadmap atualizados. Nenhum novo firmware
necessário. Próximo gráfico: contrato/reserva do framebuffer com kernel,
então userland/interface. P1/P2 físicos continuam abertos.


## 2026-10-23 — contrato de vídeo no XNU e propriedade do framebuffer

Novo perfil explícito XR24, 1125x2436/stride4500/depth32/display1.
C ligado ao EFI confere geometria/overflow; binding guarda a alocação
bem-sucedida do ramfb. Antes da cópia e no mapa final, exige LoaderData WB,
sem atributos proibidos, separado do payload e da janela. boot_args também
conferido; padrão headless do verificador permanece recusando vídeo não
declarado. Python cruza os seis campos capturados com binding e os quatro
mapas brutos, inclusive a última página arredondada.

QEMU: captura somente leitura em arm_init EL1, 736 bytes/árvore completa
reemitidos; PNG nativo1125x2436. Campo base1bdced000, 10962000 bytes pixels,
reserva10964992 (a75000). Janela f4000000+ c8000000, sem sobreposição.
Retomada confirma MiniIOMobileFramebuffer1125x2436 sobre painel1125x2436,
PID1/APFS/timer/RB_HALT/retorno. 25/25 critérios com vídeo e 22/22 sem vídeo.

Três builds negativos recusados antes da cópia/salto: stride+1, SCREENbase
no payload e página do framebuffer ocupada via APIs UEFI reais com status0.
Uma tentativa anterior terminou no banner UEFI e foi recusada por ausência
da alocação; causa não estabelecida. Log incompleto preservado, sem contar
como negativa bem-sucedida. Execuções finais em invocações individuais,
sem retry automático: todos os cinco cenários passaram. Na conferência
final, dois logs paralelos divergiram dos hashes registrados; descartados
como evidência e reexecutados sequencialmente com arquivos íntegros.
Não foi atribuída uma causa não demonstrada a essas divergências.

12 testes novos do vídeo mais 28 de contrato e 22 de memória: 62/62.
Publicados manifesto, cinco seriais completos, testes, argumentos/árvore
binários capturados e PNG; README/roadmap/índices atualizados. Kernel ainda
prebuilt, init próprio, UEFI residente. Sem SpringBoard/input/iOS local,
SMP ou Samsung. Próximo gráfico é preparar/reproduzir o userland com
revisões, imagens, patches e interação identificáveis. P1/P2 físicos abertos.


## 2026-10-23 — disco residente no consumidor EFI restrito

Descritor binário `resident` versionado, preservando os quatro itens XNUP
obrigatórios e a cmdline restrita. Payload reservado antes do GOP; com
residente, janela inteira reservada antecipadamente. O primeiro acesso ao
cabeçalho exige EfiLoaderData para a imagem inteira; não é autenticação APFS
nem prova do estado anterior à aplicação EFI.

Dois discos conferidos no C antes da cópia/salto e pelo leitor Python na
árvore capturada: residente em md0, payload pequeno em md1. A prova usou
4 MiB de APFS próprio como residente e 16 KiB de zeros como md1; PID 1,
arquivo APFS, timer e retorno passaram. Capturamos boot_args, árvore e
primeiro bloco APFS em arm_init, com GDB somente de leitura.

Seis casos residentes passaram (29/30 critérios nos positivos sem/com vídeo,
quatro recusas); três regressões passaram (25/22 critérios e recusa de
framebuffer em 7 critérios). Os 62 testes de host passaram. Registramos a
fase de aquisição do framebuffer para conferir páginas convencionais antes
e EfiLoaderData depois, mantendo a política dos registros históricos.

Uma repetição parou ainda no firmware UEFI por timeout de 90 segundos;
o log anterior à aplicação foi preservado e excluído dos PASS. O retry
com diretório/NVRAM novos passou. Não atribuímos causa ao guard.

Ver [contrato e reprodução](docs/xnu-resident-contract.md) e
[relatório/hashes/mapas](docs/references/xnu-resident-20261023/report.json).
O userland iOS completo pelo consumidor restrito continua pendente de perfil
explícito, memória e nova evidência de interface. Nenhum teste Samsung foi
realizado nesta etapa.
