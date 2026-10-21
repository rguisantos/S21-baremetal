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
