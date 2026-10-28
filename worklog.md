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


## 2026-10-23 — perfil iOS no consumidor EFI validado

Perfil XNUP opcional de 32 bytes: versão/ID/epoch/reservado, tag restrita,
residente maior que 1 GiB e até 3 GiB, imagem pequena de até 8 MiB. O C gera
uma CPU, timer de retorno de 900 s e input virtio; nenhum argumento livre.
7 GiB declarados, pelo menos 1 GiB de folga real após topOfKernelData.
Recusa de 6 GiB antes de reservar a janela e ler o cabeçalho residente.

Captura somente de leitura em arm_init: boot_args/árvore/header APFS via
GDB e buffers UEFI/claims/perfil/framebuffer via QMP pmemsave. Mapa de
símbolos e base efetiva identificam as células. O leitor independente
recalcula reservas, discos md0/md1, folga e vídeo. Replay e quatro
adulterações com checksums atualizados foram exercitados. 74 testes de
host passaram; três recusas nativas com o mesmo EFI e compatibilidade
residente gráfica (30 critérios) e embedded headless (22) preservados.

A primeira tentativa revelou uma representação otimizada de frame_size:
o compilador guardava booleano e reconstruía a constante no C. As células
de observação passaram a volatile uint64_t. Outra tentativa mostrou a
interface, mas o observador cortou a reimpressão após retorno do kernel;
o prazo externo passou a ser 900+300 s após a retomada, mantendo o limite
nativo de 900 s. Uma sessão posterior se perdeu entre turnos, sem relatório
final. As três tentativas não contam como PASS completo.

O runner passou a exigir retorno nativo razão zero e quatro snapshots
reemitidos idênticos à captura inicial, além do contrato e processo zero.
Esses são os mapas da preparação, não um mapa novo após o userland.
O resultado final é registrado no manifesto e guia desta entrega.

Execução final aceita: 1024,6 s totais, retorno nativo de orçamento observado,
razão zero e QEMU zero. Os quatro mapas reemitidos coincidiram byte a byte,
com stride/versão/chave/claims iguais aos capturados na entrada. Replay do
pacote preservado e quatro controles semânticos passaram novamente.
SpringBoard, Ajustes, Geral e Sobre foram inspecionados individualmente;
Sobre exibe 16.5 e identidade iPhone X sintética. A confirmação humana fica
separada do campo automático de GUI. EFI efetivo na ESP, payload e todos os
bytes do backing residente conferidos contra os hashes identificados.

README, roadmap, índices e ferramentas atualizados. UEFI permanece ativo,
kernel prebuilt externo, sem rede/discos do host e sem teste Samsung.
Não foi necessário novo arquivo do aparelho nesta etapa QEMU. P1/P2 físicos
continuam pendentes; em consulta final, não há PR aberto no repositório.


## 2026-10-23 — grafo estático das chamadas finais LK HZC2

BL recebido recuperado e conferido pelo SHA-256 original; sboot exato 4 MiB.
Inspetor stdlib vinculado por hash, limite 8192 PCs, decodificador restrito de
controle e parada antes do BLR do payload. Grafo direto: 421 palavras; expansão
dos templates conhecidos: 1834 palavras/31 BL/18 saídas indiretas. Tabela de
91 halfwords com sinal e 26 destinos, 15 BLR do formatador e duas fronteiras
mutáveis (operações/lista) preservadas como hipóteses, sem completude runtime.

MRS SCTLR_EL1 em dois helpers de sincronização e preenchimento; DC ZVA
condicional, SEVL/WFE, máscara IRQ condicional e UART em polling sem timeout.
Nenhum MSR na forma de registrador ou ERET/SMC/HVC nos nós expandidos. Isso
não prova progresso nem preservação por callbacks não limitados, traps/MMIO
ou serviço seguro. Em EL2, SCTLR_EL1 pode divergir do SCTLR limpo pelo helper.

SMC anterior ligado ao wrapper SMC #0/RET, sem resultado testado pelo chamador.
Despacho de -0x3ff não localizado. Veneer do monitor aponta a helper/vetor que
não foram validados como plaintext nos bytes recebidos; hashes/palavras no
relatório, sem atribuir cifra por entropia ou executar código seguro.

GNU objdump 2.44 coincidiu em todas as 1834 palavras e 395 destinos relativos;
recortes direto e IRQ também conferidos. 15 testes novos e 14 regressões do
helper: 29 PASS. Não repetida a emulação 352/352, sem mudança em R10/diagnóstico
ou teste físico. README/roadmap/índices atualizados, inclusive um parágrafo
antigo que ainda tratava a interface QEMU já concluída como etapa futura.
Marco A ainda exige posse/coerência, carregamento e leitura dos 128 bytes.


## 2026-10-23 — pedidos BL2 do monitor e mutações da lista LK

Inspetor stdlib vinculado ao sboot HZC2 exato, sem executar serviço seguro.
Wrappers 0x16500/0x36218 byte a byte iguais (52 bytes): X0=-0xe7,
X2=0x40000, X3=0xe8000000; X1=0x1b61 para W0=0, 0x36c para W0=0x20,
zero nos demais modos. Correlações com 0x36c000/0x36c200 e intervalo
candidato de 0x40000 bytes não demonstram unidades, leitura, cópia ou
decriptação. Chamador testa W0 e estaciona se não zero; retorno real aberto.
Pedido posterior -0xe8 e palavras brutas do cabeçalho preservados sem
atribuir papel runtime a X3 ou propriedade de memória aos literais.

Busca ampliada de BL para B/BL encontrou inserção por salto de cauda em
0x16f6e4 e remoção em 0x16f714, objeto 0x31e5c8/callback 0x16f018.
Gate 0x170750 retorna zero; wrappers não alteram a lista e corpo do callback
retorna cedo sob instruções inalteradas e chamada normal. Helpers de lista
ligam/desligam campos 0/8 sem escrever callback +16. Sem prova geral de
aliases, escritores indiretos, imutabilidade da tabela ou lista completa.
Grafo histórico de 1834 palavras mantido com bindings explícitos.

Consulta LK -0x12d usa buffer de 180 bytes e imprime informações do monitor;
não é dump plaintext do handler -0x3ff. IDs -0xe7/-0xe8/-0x12d/-0x3ff
separados. Nenhum serviço foi mockado como retorno real ou executado.

14 testes novos + 15 regressões do grafo: 29 PASS. GNU objdump 2.44
coincidiu nas 160 palavras e 31 destinos relativos dos blocos selecionados;
dados de tabela/cabeçalho excluídos da contagem. Evidência JSON, linhas
GNU e saída de testes versionadas, sem incluir firmware. README/roadmap e
índices atualizados; nova nota detalha premissas e lacunas. Sem mudança em
R10/diagnóstico e sem repetir ensaios QEMU ou coletas shell bloqueadas.
Próximo: provedor seguro e escritores indiretos, observação física em paralelo.


## 2026-10-23 — origem X2 do modo BL2 e campos herdados de -0xe6

Getter -0xe9 ligado ao veneer que zera X2, faz DSB/SMC e move X2 para X0.
Inicialização de X2 não é resposta medida. Seletor W confere truncamento,
LSRV módulo 32, subtração/limite sem sinal e tabela de onze bytes; quatro
modos possíveis (0, 0x14, 0x20, 0x40). Entrada X2 opcional sempre explícita
e marcada como hipotética. Sequência -0xed opcional, -0xe6/teste W0, store
MMIO intermediário e -0xe7/teste W0 preservada sem executar os serviços.

Intérprete restrito do construtor original -0xe6, até o BL do veneer,
reconstrói argumentos e stores em dicionário de 28 bytes. Modo 0x14 não
escreve +0x18; 0x40 não escreve +0x10/+0x14/+0x18. Campos mantidos como
null, sem inventar memória inicial ou contrato do provedor. Limite 64 PCs,
recusa de loops/escapes, registradores desconhecidos e stores fora da janela;
pilha/prologo abstraídos após conferência, sem memória física acessada.
Correlações dos valores com intervalo LK não definem unidades ou operação.

ADR EPBL para VBAR candidato 0xe800 conferido; primeira palavra 831dc011
apresentada como indefinida pelo GNU, sem despacho seguro plaintext ligado.
Não atribuir cifra/semântica por aparência. Busca ADRP+ADD limitada encontrou
cinco referências selecionadas, inclusive célula stdout e tríade inicial
com o mesmo ponteiro. Não é censo geral de escritores/aliases em execução.

24 testes novos e 14 regressões: 38 PASS. GNU 2.44 coincidiu em 116 palavras
e 25 destinos de código; vetor bruto excluído dessa contagem. Conferência
GNU não é segunda execução independente do modelo. Relatórios e testes
versionados, README/roadmap/índices atualizados. Sem alteração R10 ou nova
execução QEMU/Samsung; serviços seguros, estado físico e leitura continuam
abertos. Nenhum novo arquivo necessário para esta investigação estática.


## 2026-10-23 — estado anterior do descritor: cópias fixas e limite LK

Checkout restaurado do GitHub após manutenção do ambiente; pacote BL original
recuperado e conferido pelo SHA-256 5b48c27798b103ec906112fc4baad1aacd8d39c970dae6c478d3bd559e2cf31f.
sboot descomprimido com tamanho/hash originais, sem alteração de firmware.

Inspetor vinculado por hash confere sete helpers BL2: três LDR X literais,
corpo de cópia W/pares X, CMP/B.LT e DSB/ISB/RET exatos. Intervalos positivos
divisíveis pelo passo, sem tocar memória física. Nenhum destino alcança
[0xe7ffe000,0xe7ffe01c). Isso exclui esses corpos/literais, não stores
arbitrários, preparação anterior ou efeitos seguros. Inicializador não localizado.

Construtores 0x1643c e 0x36154 têm os mesmos 140 bytes; modelo anterior
reproduz argumentos/campos e as mesmas lacunas nos quatro modos. Censo B/BL
alinhado encontra uma chamada direta ao primeiro e nenhuma ao segundo; não
prova duplicata inalcançável. Scan restrito MOVZ/MOVK encontra quatro
testemunhos para o descritor e quatro LK para 0xe7fffe00, valor distinto
0x1e00 acima, usado em limites SUB/CMP/branches e não em stores nesse recorte.
Nenhum dos dois valores aparece como literal LE contíguo de quatro/oito bytes;
não é prova contra outros encodings, aliases ou ponteiros externos.

16 testes novos + 24 regressões: 40 PASS. GNU objdump 2.44 coincide em 165
palavras/23 destinos relativos e 21 endereços de literais dos helpers.
Relatórios, saída de testes e nota com intervalos publicados; README, índices
e roadmap atualizados. O resultado é delimitação de hipóteses, sem preencher
campos desconhecidos ou aumentar prontidão física. Nenhum ensaio QEMU/Samsung
repetido. Serviços seguros, posse/coerência e recuperação do registro abertos.


## 2026-10-23 — preparação EPBL e dispatcher comum parcial

Prefixo legível liga chamada condicional 0x3044 à preparação 0x312c,
antes do candidato VBAR 0xe800. Flag externo e marcador SUCC podem pular
a preparação; STAR/FAIL e ramo de falha preservados sem execução.
Pedido 0x3878 -> 0x4248 -> 0x3ad4 usa origem=destino 0x02028700,
extensão 0xb6e0. MMIO na base 0x18330000 alimenta buffers; status
internos 0x1106/0x1107 não foram atribuídos aos retornos dos SMC.

Hipótese nominal de delta 0x02024000 consistente com ponteiro/version
em 0x4540 e registros EBRS/EBHS; mapeia o pedido para [0x4700,0xfde0).
Não é endereço físico medido ou reserva. Um ensaio exploratório de
SHA384/SHA512 + AES-CBC, com variantes de comprimento/byte order, não
produziu correspondência ao registro comparado sob hipótese SHA256.
Nenhum plaintext verificado foi recuperado; essas tentativas não foram
usadas para declarar algoritmo, chave, falha do firmware ou PASS.

Dispatcher comum 0x4424 normaliza prefixo FFFF por complemento+1 W e
OR 0x82000000. IDs -0xe6/-0xe7/-0x3ff/-0x500 continuam comandos
distintos, owner 66 nos exemplos. Guarda 0x43d8 testa bit 30 e recusaria
negativos se a chamada entrasse por ela; vetor/entrada efetivos não ligados.
Classificação via byte em ponteiro nominal 0x02034280, zero no arquivo
não é valor runtime. Bit 7 recusa; demais classes selecionam ponteiro
em slot de 32 bytes baseado em 0xe410, BLR X15 em 0x4494. A janela
conservadora [0xe410,0xf410) fica dentro da região candidata in-place.
Sem interpretar seus bytes como bindings runtime ou inventar handlers.

18 testes novos + 16 regressões: 34 PASS. GNU objdump 2.44 coincide em
311 palavras e 46 destinos relativos dos dez blocos prefixos; região
candidata/tabelas excluídas da contagem de código validado. Inspetor
stdlib, relatórios, testes, README/roadmap/índices atualizados. Nenhum
serviço seguro/MMIO executado, sem alteração de firmware/R10 ou teste
QEMU/Samsung. Próximo limite: entrada vetorial e transformação/preparação
verificável antes de resolver handlers; observação física segue em paralelo.


## 2026-10-23 — fronteira do prefixo EPBL e segundo produtor VBAR

Veneer ADR X30/B/RET confere continuação 0x3028. Grafo estático restrito
a [0x3000,0x4540), orçamento de 2048 PCs e cortes em [0x4700,0xfde0).
1182 instruções, 13 arestas diretas à região pendente; passos após BL
sob hipótese de retorno normal, ambas alternativas condicionais. Uma tabela
de quatro bytes 03 00 00 02 expande BR X9 a três destinos. BR X0 mantém
fronteira conservadora; helper MOV X0,XZR/RET não foi propagado para podar
condicional. Sem prova de viabilidade ou progresso. Dispatcher não visitado
por esse grafo direto não significa inalcançável por exceções, que são omitidas.

Segunda escrita VBAR em 0x4358, literal 0x02032800 em 0x43c0, concorda
com ADR relativo ao candidato 0xe800: delta 0x02024000. Caminho contém
BL 0xc9ec antes do writer e é parcialmente pendente. Janela de 16 vetores
[0xe800,0xf000) inteiramente na região pendente; entradas não vinculadas.
Janela conservadora dos slots não prova 128 descritores válidos alocados.

Referência primária s5p-sss.c do repositório Exynos-2100 fixada no commit
37c14d86996a49edbea8953f2523b202546b8958, blob recalculado
86a13b738c2deb168edf749b3268e57131bca22e. Compatibles s5pv210/exynos4210/
exynos5433-slim, offsets HASH distintos e definições antigas; não basta
para importar protocolo/algoritmo/chave do EPBL. Fonte não prova binding
no HZC2. Metadados e diferenças publicados, sem copiar o driver inteiro.

18 testes novos + 18 regressões: 36 PASS. GNU objdump 2.44 confere todas
as 1182 palavras/138 destinos e SHA do índice PC/palavra. Relatório guarda
intervalos e todas as saídas pendentes. README/roadmap/índices atualizados.
Nenhuma transformação, execução MMIO/firmware ou novo teste QEMU/S21.
Avanço seguinte depende de preparação/ligação verificáveis ou observação,
não de repetir modelos com respostas seguras inventadas.

## 2026-10-23 — protocolo EPBL: buffers, palavras DMA e resultados

Passo 1 solicitado após revisão da main ff90d419. BL original recuperado,
SHA-256 do pacote e sboot conferidos; nenhuma alteração de firmware.
Novo inspetor stdlib e conferidor GNU, com recortes/hash obrigatórios.

Rastreio liga seed de 32 bytes (candidato 0x469a) ao scratch de 128 bytes,
32 words enviados ao MMIO e 12 words lidos: primeira saída de 48 bytes.
Os primeiros 32 viram material da operação seguinte; os 16 restantes vão
ao campo IV. Request origem=destino 0x02028700, extensão 0xb6e0, modo 1,
direção 1, controle 0xfab. AES-256-CBC é inferência corroborada pelos bits
SSS publicados; não binding HZC2 ou material real recuperado.

Pares origem/destino do consumidor demonstram ordem alto32/baixo32/tamanho.
Aplicá-la às palavras 0/0x1fc00/0x3fc da primeira etapa indica candidato
[0x1fc00,0x1fffc), 1020 bytes. Essa interpretação corrige a leitura inicial
exploratória de endereço zero/tamanho 0x1fc00. Palavras brutas e inferência
ficam separadas; não se declarou ROM, fusíveis, RAM ou conteúdo conhecido.

Wrapper zera somente contadores do contexto; neste percurso eles evitam
ler estado não inicializado. O ramo final lê oito words/32 bytes e os
compara ao candidato EBHS+4. Status internos e cinco polls limitados foram
conferidos; DMA tem releitura após o limite. Nenhuma duração física inferida.

Fontes primárias SSS/Exynos9830 fixadas por commit/blob. Um ensaio com a
chave/IV públicos Exynos9830 não coincidiu com o registro sob hipótese
SHA-256; não gerou plaintext verificado ou binário publicado. Fonte HASH
correspondente, dados da entrada e saída real de 48 bytes continuam abertos.

33 testes novos + 36 regressões: 69 PASS. GNU 2.44 coincide em 1095 palavras,
114 destinos e 177 endereços/larguras/operações MMIO (38 leituras/139 escritas).
Conferidor independente interpreta texto GNU para endereços; não executa
fluxo de buffers ou hardware. Documentação/índices/roadmap atualizados.
Sem novo QEMU/S21, sem mudança R10/shim, sem ligação vetorial/SMC. Próxima
lacuna: binding/conteúdo da entrada candidata, semântica de 0x19 ou saída
observada, antes de validar transformação e handlers. Observação física
segue como frente separada; não repetidas coletas shell bloqueadas.

## 2026-10-23 — orientação permanente de commits e organização

Usuário determinou: sempre fazer commit e organizar o repositório. Orientação
registrada em AGENTS.md, com organização por módulo, atualização dos índices,
preservação de evidências e validação proporcional às mudanças. Entrega EPBL
mantida em branch próprio com código, relatório, referências e testes.


## 2026-10-23 — revisão/merge PR #5 e proveniência HASH

Usuário determinou concluir revisão e merge das entregas, além de commits e
organização. AGENTS.md atualizado. PR #5: head636c56a, revisão automática
sem achados/threads pendentes e conferência própria registrada. Merge
2df91f32 executado; main local sincronizada antes da continuação.

Nova referência Samsung GPL ace_sfr.h, perfil SSS v6, fornece os offsets HASH
que faltavam na comparação s5p-sss. Comparação executada com cinco fontes
por commit/SHA-256/blob: header ACE e quatro arquivos Fireplace Exynos9830.
Dez offsets HASH e palavras DMA alto/baixo/tamanho concordam. Bases distintas
11100000/1a520000/18330000 e cobertura parcial da primeira etapa preservadas.
Não se declarou binding físico ou entrada candidata identificada no S21.

Switch do emulador implementa 0x1a/0x1b como SHA512/HMAC-SHA512 e rejeita
0x19. Header legado dá outro nome ao nibble9. Nenhuma dessas definições
foi transferida para atribuir algoritmo HZC2 ou fabricar saída. BootROM de
outro SoC não foi usado como substituto da entrada HZC2.

Corrigida documentação que nomeava alto/baixo ao contrário: contexto+44
vai a MMIO+1030 e contexto+40 a+1034. Instruções originais intactas; dois
testes novos conferem a ligação e recusam a troca. Relatório reemitido.

12 testes novos de fontes +2 de contador +69 anteriores: 83 PASS. Comparação
real dos arquivos passou; conferência GNU reproduz a evidência anterior de
1095 palavras/114 destinos/177 acessos sem diferença. Header somente
pré-processado, sem execução C/emulador/firmware/MMIO. Fontes completas e
binários externos permanecem fora do Git. README/índices/roadmap atualizados.
Próximo bloqueio: implementação 0x19 correspondente, entrada verificável ou
saída real de48 bytes; vetores/SMC-3ff e diagnóstico físico continuam abertos.

## 2026-10-24 — TZAR HZC2 e fronteira criptográfica

Continuação sobre main 65040a6, PR #6 revisado/mergeado. BL e componente
tzar.img identificados pelos mesmos hashes já inventariados. Descompressão
do primeiro bloco interno LZ4, 6159648 bytes: arquivo de 44 registros
consumido integralmente, nomes/tamanhos/hashes publicados. Cauda de 4502836
bytes contabilizada por hash, sem interpretação completa. Nenhum binário
ou fonte proprietária integral adicionado ao Git.

Leitor restrito em memória usa liblz4 e ELF64 AArch64; offsets do contêiner
não precisam estar alinhados, e endereços ELF são traduzidos pelos segmentos.
Recusas para nomes duplicados/não canônicos, comprimentos, truncamento,
tabelas ELF, BSS e mapeamento ambíguo. Checker GNU usa duas cópias temporárias
com nomes controlados, removidas ao final. Nenhuma biblioteca executada.

libscrypto64 delega SHA384_Update/Final a SHA512_Update/Final. libteesl64
separa atualização EVP dos três seletores 500000d2/d4/d6 encaminhados ao
dispositivo /dev/crypto. Helper 281f8 produz 02010000/02030000/02040000 e
OR 1 quando W1=1; chamador prepara buffer 6c e ioctl 7. Atualização usa ioctl 1.
São códigos de API/pedido, sem equivalência demonstrada ao MMIO EPBL19.
Consumidor no driver, bytes DMA e saída real continuam pendentes.

15 testes passaram; GNU 2.44 confere 15 símbolos dinâmicos, 127 palavras e 34
destinos relativos. Aviso sh_info de libteesl preservado na evidência, sem
divergência nos recortes. README/índices/roadmap e integração atualizados.
Sem nova tentativa de chave, firmware/SMC/MMIO executado ou QEMU/S21.

## 2026-10-24 — ligação ioctl e fronteira SVC TEEGRIS

Continuação sobre main 2f31df4. PR #7 integrado após revisão própria;
revisão automática ainda pendente, sem apontamentos/threads retornados.
Nenhuma aprovação automática presumida. O mesmo TZAR HZC2 fornece libteesl
e libtzsl, com identidades já presentes no inventário de 44 entradas.

Novo leitor liga os dois calls de ioctl a PLT 9760, GOT 61698 e relocação
JUMP_SLOT do símbolo 67. VERNEED requer TEEGRIS_4/libtzsl.so, índice local 4;
a provedora tem SONAME correspondente e símbolo 98/ioctl em 8654, 72 bytes,
versão local 2 com o mesmo nome. Contrato declarado, sem resolução em execução
ou exclusão de interposição. Gramáticas restritas e testes de corrupção
para DYNAMIC, versões e RELA, com recusa de elos/slots ambíguos.

Wrapper completo de 18 instruções: estende W0/W1, preserva X2 até o trap,
prepara X7=15 e executa SVC #0 em 866c. Handler/consumidor após a exceção
não identificado. CMN/B.LS converte somente X0 entre -4095 e -1 para errno
positivo e W0 ffffffff; -4096 não entra nesse ramo. Fora dele, retorno
trunca a 32 bits e errno não é escrito no recorte. Modelo aceita u64 explícito;
nenhuma resposta de dispositivo foi injetada.

30 testes passaram (15 novos + 15 TZAR). GNU 2.44 confere índices/nomes de
versão, biblioteca requerida, SONAME, relocação, exportação e 24 palavras/
quatro destinos. Relatórios anteriores do TZAR reproduzidos byte a byte.
Leitor ELF compartilhado recusa sobreposição mesmo se só um segmento for
executável; checker compartilha apenas o runner GNU, mantendo o parse textual
independente da leitura binária. Índices/roadmap/integração atualizados.
Sem ELF/firmware/syscall/SMC/MMIO executado e sem novo QEMU/S21.

## 2026-10-24 — BiEn TZSW e validação de candidatos

Continuação sobre main cd8b512. Revisão automática do PR #8 confirmada
concluída sem achados no head fd78916; PR #7 ainda running, sem apontamentos.
READMEs anexos conferidos: instruções de build, sem implementação do consumidor
SVC. Firmware TZSW HZC2 permanece com tamanho/SHA-256 do inventário original.

Envelope BiEn em 0x10 e tag teegris; palavras LE 0x28/0x2c delimitam candidato
[0x1000,0x9d8f0), 641264 bytes, corroborado por palavras de extensão iguais.
Referência primária CreckerROM bc9aa70: quatro arquivos identificados por
SHA-256/blob. Utilitário declara Exynos9830, sem perfil Exynos2100. Fontes
somente lidas; AST lê constantes e perfil literal, sem importar/executar código.

Um conjunto público de parâmetros foi avaliado em memória. cryptography
50.0.2 e OpenSSL 3.0.13 coincidem no bundle e payload. SHA-256 e5440865...
difere do campo b24b95f1...; marcador de userboot ausente. Resultado negativo
sob essa hipótese, sem plaintext aceito, desassemblado ou salvo. Não exclui
algoritmo/layout/material diferente do HZC2. Nenhuma chave derivada emitida.

Novo inspetor valida futuros candidatos pelo tamanho, igualdade fora da
região e digest do original; digest substituído é recusado. Candidato
inválido: JSON de recusa e exit 1. Erros de entrada/referência: exit 2 sem
JSON parcial. Inspeção/ensaio negativo concluídos usam exit 0, sem declarar
sucesso criptográfico. Arquivo bruto real também recusado como candidato.

15 testes passaram, incluindo positivo sintético e controles de corrupção,
metadados, AST e referências. Identidade do original preservada. Relatório
guarda hashes, fontes, versões dos backends e limites; sem binários no Git.
Índices/roadmap/integração atualizados. Esta ramificação SVC depende de
código correspondente em claro; diagnóstico/entrada/observação e memória
seguem em paralelo. Sem novo QEMU/S21 ou execução de firmware/serviços.


## 2026-10-24 — produtor BL2 do total de RAM e folha de geometria

Continuação sobre main 169d704. PR #9 revisado/mergeado, revisão automática
completed sem achados no head 383656d, sem threads pendentes. A rota SVC
continua dependente de código em claro validado; investigação avançou na
frente de memória, sem repetir a hipótese criptográfica recusada.

Novo produtor: os calls 160bc/16128 levam ao inicializador 17e14, que chama
1dc90 em 18000 e publica X0 com STR de 64 bits em 02038848 no retorno.
O getter/cache/limite LK já era conhecido; corrigida a linha desatualizada
do construtor que dizia não ter recuperado o getter. Nenhum valor real
foi atribuído ao total do aparelho.

Caminho selecionado: helper 1d830 retorna em 1e85c, resultado é armazenado
na célula relativa 31940 e recarregado na cauda 1f9cc. Chamadas intermediárias
e possíveis escritores indiretos permanecem abertos. Três ponteiros brutos
em 31500/31558/31358 apontam nominalmente a 2f130/2fa98/2caec com delta
020ea000. Tradução e binding runtime explicitamente não comprovados.

Folha 2caec–2cb9c: quatro u64 em 31978..31990, tabela de sete u16 em 30080,
gate por byte, um/dois termos escolhidos pelo nibble da palavra zero,
índice >6 contribui zero, seletor 1 duplica, soma em MiB deslocada 20 bits.
Empacotamento candidato 2f130 liga os seletores 5/8 aos campos usados;
callback da consulta vem de 30f20, com retornos e resolução ainda abertos.

Inspetor exige tamanho/SHA-256 exatos; geometria é array explícito de quatro
u64, sem default e com leitura limitada a 4096 bytes. Dez testes novos
cobrem os ramos críticos, parser, overflow e recusa de imagem; 24 regressões
BL2 passaram (34 no conjunto), além de 73 regressões LK. CLI: cenário
sintético 12 GiB e quatro recusas exit 2/sem JSON conferidos. GNU 2.44 confere 300 palavras, 23 destinos e
12 operandos, incluindo construção do destino e acessos da folha.

No QEMU virt/EL1, somente as 44 instruções e 14 bytes de tabela originais
foram injetados. Image de diagnóstico é veículo, parando antes da execução.
33 cenários sintéticos × duas posições = 66/66 coincidiram, preservando
SP inválido, X19–X30, código/tabela/entradas/guardas. Inclui todos os índices,
modo global, gates, fator 1/2, bits altos e seed determinística 2caec.
Sem inicialização DRAM, callbacks, SMC/MMIO, escrita em 02038848 ou FDT.
Nenhum novo teste físico, R8/R9/R10 ou firmware proprietário adicionado.

README, índice, roadmap e referências de memória atualizados. Próxima
investigação: preparação/binding das consultas de geometria e célula 30f20;
seguem pendentes valores reais, limite LK, respostas seguras e mapa final.


## 2026-10-24 — callback da geometria BL2 seguido até MMIO

Continuação sobre main b3f8340. PR #10 integrado após revisão própria e
automática sem achados no head 84b5692; main limpa/sincronizada. READMEs
anexos conferidos: build de kernel Android 11 e módulos de plataforma
Android 15, sem implementação dessa consulta de bootloader.

Célula 30f20 contém 02112480, alvo nominal 28480; célula 31040 contém
0211424c, alvo nominal 2a24c. Células derivadas dos ADRP/ADD/loads do
chamador 2f130; delta 020ea000 permanece nominal, sem binding físico
ou exclusão de escritores das tabelas. Firmware continua tamanho/SHA
fixados, sem executar callbacks, serviços ou acessos físicos.

Consulta: 25 instruções. Slots 0..3 leem controle da própria base, inserem
W1[1:0] em 28..29 e W2[6:0] em 20..26, escrevem controle e literal 1 em
+4, leem 32 bits de +c e retornam em W0 (X0 zero-extended). Máscara
preservada c80fffff. Cinco u64 em 30f98: 1c036000/1c136000/1c236000/
1c336000/1a346000. Slot 4 lê controle inicial do slot 0 e usa slot 4 nos
acessos seguintes. W0 unsigned >4 retorna X0 00000000ffffffff, sem MMIO.
Não se atribuiu broadcast ou defeito a essa assimetria.

Preparação: 23 instruções, cinco bases em 30fc0: 1c040000/1c140000/
1c240000/1c340000/1a350000. Lê +50, escreve com bit 24 ligado e depois
limpo, preservando os demais; mesma assimetria do slot 4. Não restaura
bit 24 anterior. Nenhum polling/barreira ou serviço nos dois corpos;
conclusão do dispositivo e chamadas externas continuam desconhecidas.

Inspetor confere corpos completos e deriva tabelas/BFI; plano opcional
exige três u32 explícitos e conserva controle/resposta como desconhecidos,
sem calcular RAM ou injetar retorno. 14 novos testes + 34 regressões BL2
passaram (48). CLI: três planos simbólicos slots 0/4/5 e quatro recusas
exit 2 sem JSON. GNU 2.44: 82 palavras, seis destinos, 17 operandos,
dois BFI e 12 ponteiros; ponteiros extraídos do hexdump GNU, sem reutilizar
o leitor binário. Nenhum novo QEMU, hardware ou blob no Git.

README/índice/roadmap e integração atualizados. Próximo rastreio:
preparação dos controladores e escritores das tabelas 30e50/30fe8. Ainda
faltam bindings e respostas reais, eventual limite LK e mapa FDT final.


## 2026-10-24 — reescrita condicional das bases da consulta BL2

Continuação sobre main 5bccfd4, PR #11 revisado/mergeado com revisão
própria e automática sem achados no head b210c7f. Investigação de escritores
identificou um produtor positivo da tabela de bases 30f98, distinto de
escritores dos ponteiros de código 30e50/30fe8.

Corpo 2d270: callback da célula 31458, ponteiro 021183d0, alvo nominal
2e3d0. Getter constrói 10000010, lê W0, extrai bits 20..23 e retorna.
CMP W0,1/B.NE seleciona 15 instruções de construtor em 2d288..2d2c4.
Cinco STR X gravam 1c03f000/1c13f000/1c23f000/1c33f000/1a34f000 nas
células 30f98..30fb8, substituindo sob essa condição os valores iniciais
terminados em 6000. Ramo diferente de 1 não escreve/restaura; conserva
estado herdado. Sem valor de nibble ou configuração ativa inferidos.

Ligação selecionada: página X20 em 1dee4, ADD408/LDR32 em 1e0dc/e0 e
BLR em 1e0e4; célula nominal 31428 contém 02118ff0 -> 2eff0. Wrapper
chama diretamente 2d270 em 2effc, antes da fase de geometria no caminho
selecionado. Preservação de X20 pelas chamadas e bindings mutáveis não
comprovados fisicamente. O construtor não escreve a tabela 30fc0 ou
ponteiros de código; não há prova global de imutabilidade.

Intérprete de host restrito a ADRP, MOVZ/MOVK X, ADD X imediato com
LSL12 e STR X, até 16 instruções. Recusa unknowns, memória lida, calls,
branches, pilha, stores de outra largura/fora das cinco células e
duplicidade/incompletude. Cenário exige palavra u32 explícita e identifica
a tabela inicial do arquivo como hipótese. Consulta integrada continua
com controle e resposta desconhecidos. Inspetor anterior sinaliza que
não aplica reescrita e que seus valores são apenas iniciais do arquivo.

58 testes BL2 passaram (dez novos + 48 regressões); inclui 16 nibbles,
persistência no skip, larguras e recusas do construtor/CLI. CLI: três
planos condicionais e quatro recusas exit 2/sem JSON. GNU 2.44: 39 palavras,
dois destinos, sete operandos, cinco stores e sete ponteiros. Valores e
destinos dos stores reconstruídos independentemente pelo texto GNU.
Relatório GNU anterior da consulta reproduzido sem alteração; evidência
estática atualizada somente para explicitar o escopo das bases.

README, índice, roadmap e integração organizados. Nenhum novo QEMU,
firmware/MMIO/serviço executado ou blob adicionado. Próximo rastreio:
estado anterior/recargas da geometria, demais escritores e bindings; ainda
faltam respostas reais, eventual limite LK e mapa final.


## 2026-10-24 — registro anterior e recargas da geometria BL2

Continuação sobre main 4d4fd72, PR #12 revisado/mergeado com revisão própria
e automática sem achados no head 33ae7df. READMEs anexos novamente
conferidos: instruções de build, sem valores runtime do registro BL2.

Dois caminhos recarregam u64 de 02073600 para o primeiro slot relativo
31978 e extraem bits 4..7 para o byte 31939. Prefixo de 2d364, registrado
na célula 31580 -> 02117364, sem chamador resolvido nesta entrega; segundo
trecho em 2d568, com contexto de X6/X19 explicitado, load 2d7e0 e store
2d7e4. Nenhum conteúdo do registro, mapeamento de arquivo ou valor dos
três slots restantes foi recuperado.

1e2c0/1e2c4 produzem/gravam u64 cafe no mesmo slot antes dos calls
1e2d0 e 1e2e0. Células derivadas do chamador 31510 -> 021196c0/2f6c0 e
314c8 -> 02117568/2d568; segundo call passa W0=W1=12. Delta e preservação
de registradores são hipóteses nominais. Não se presumiu que chamadas,
ramos de erro ou callbacks retornem normalmente ou conservem estado.

Cópias 161d8 e 16200, já conferidas em etapa anterior, incluem a palavra:
02073600 -> 021ab600 -> 9004a600, sob seus literais. Sem execução/ordem ou
bytes observados. Ramo 2f744 pode chamar preenchimento de 44 bytes zero em
02073600; helper de nove instruções conferido para esse pedido. Outro gate
em 2f7fc controla seis transferências W de 021ab600+offset para
02073600+offset, nos offsets 28/4c/34/50/6c/a0. Nenhuma toca os primeiros
oito bytes. Isso não determina o estado após a função/cadeia inteira.

Novo inspetor somente estático: tamanho/SHA exatos, prefixos conferidos,
endereços por MOVZ/MOVK, larguras/registradores e spans com limites. Origem
conservada como unknown_record_u64; sem novos cenários de respostas ou
cálculo de RAM. 70 testes BL2 passaram (12 novos + 58 regressões), incluindo
recusas de imagem exit 2/sem JSON parcial. GNU 2.44: 148 palavras, dez
alvos, 18 operandos, quatro produtores, seis cópias de campos e nove
ponteiros/literais, conferidos por texto e hexdump independentes.

README/índice/roadmap/integração atualizados. Nenhum novo QEMU, execução de
firmware/MMIO/serviço, dump físico ou blob no Git. Próximo rastreio:
produtores da primeira palavra e gates de preservação/substituição. Ainda
faltam bytes reais, demais slots, bindings, respostas, limite LK e FDT final.

## 2026-10-24 — referência pública xfwdrev/rebased-11

Pedido do usuário para examinar android_kernel_samsung_ex2100/rebased-11.
Base local: main 69940c8 após PR #13 revisado/mergeado. Fixado commit
756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0 (2026-10-19 UTC), árvore
3cb6380ea1348c26fc4eeea0d4562dedba88e0e0. Quinze arquivos selecionados,
com tamanhos, SHA-256 e identidade de blob Git no relatório; READMEs anexos
relidos, sem modificá-los.

Linux 5.4.304-openela, nome ChicletKernel e config p3s por fragmento.
build.sh descreve LLVM/Clang r614150, boot/vendor_boot v3 e metadados
Android 16; nenhum build completo executado ou compatibilidade inferida.
build_kernel.sh ainda chama defconfig t2sxxx ausente na lista consultada.
Config base desativa KEXEC/KEXEC_FILE/CRASH_DUMP/DEVMEM/UH e declara
console Samsung, PSTORE/RAM e DEBUG_SNAPSHOT_BUILT_IN. Isso não mede o
estado de Harx/EL2 nem comprova leitura/persistência de logs.

Hashes comparados com a evidência Samsung anterior: UART e overlay
UNIVERSAL2100 rev11 idênticos; Makefile, GIC, MCT e base DTS diferentes.
Base pública já corrige as três listas de CPUs. DTC/libfdt 1.7.2 extraídos
fora do checkout: três DTS compilados sem edição, alinhamento quatro, e
dois overlays aplicados. Parser FDT existente aceitou os cinco resultados.
Base 393452 bytes/2292 nós, diferente da base HZC2 comprovada. Genérico
aplicado: UART0 okay/UART1 disabled; p3s r22: ambas okay. Todos sem nós
RAM, com chosen initrd antigo; avisos de bindings preservados por categoria.

Documentação, índices, roadmap e integração atualizados. Candidata futura:
instrumentar um kernel Linux para observar FDT/reservas após validar build
e percurso físico de instalação/recuperação. Sem mudança no payload ou
nos decodificadores BL2, sem nova execução QEMU/telefone/serviços seguros.
Produtor do registro BL2, memória final e primeiro diagnóstico continuam
pendentes. Fontes externas, ferramentas e DTBs gerados não entraram no Git.

## 2026-10-24 — menções BL2 no kernel e consumidor do registro DRAM

Usuário esclareceu que a indicação do repositório visava suas menções a
BL2. Corrigido o foco da investigação anterior de build/DTS. Base main
51a8828, PR #14 com revisão própria concluída, automática ainda running.
Busca indexada bl2/BL2 retornou 75 caminhos no commit externo 756951a;
não é censo completo. Seguidas referências diretas Samsung e endereços
conhecidos, com 12 arquivos adicionais fixados por tamanho/SHA-256/blob.

exynos-devfreq.c, exynos_init_freq_table/DEVFREQ_MIF: ioremap de 1024 bytes
em 02073600, lê W alto em +4 e W baixo em +0, reconstrói u64 e imprime
DEVFREQ : dram: %llx. Comparação com 0001000860000110 rotulada dram d1z,
seguida de três OPP disables. Não é produtor nem amostra u64 atômica
comprovada. No BL2 HZC2, 14 palavras de 2f4d8 conferidas por prefixo e
helpers existentes: a mesma constante construída por quatro MOVZ/MOVK,
comparada em 2f504 com o slot 31978, recarregado do registro na etapa
anterior. Sem assumir execução, preservação ou conteúdo real.

CHIPID: variante Exynos 2100 rev_reg=10/main_rev_bit=20/sub_rev_bit=16,
mask=f e DTS chipid@10000000 corroboram o campo 10000010[23:20] como
main_rev. Gate BL2 nominal corresponde a main_rev==1, sem medir revisão
ou escolher bases ativas. Bootstat declara parâmetros BL1/BL2/BL3 0440 e
proc enhanced_boot_stat; sboot contém formatos correspondentes em
23b200/23b220/23b240. Xrefs/argumentos/runtime não seguidos nesta entrega.

Comentário GPU from BL2 seguido por frontend/backend/CAL/vclk: dados
em cache, atribuições ECT DVFS/GEN e ASV, e possível elevação pelo DT.
Comentário não prova escritor BL2 único. Separados exemplos de homônimos
em sysmmu e bio. Dois relatórios estáticos anteriores reproduzidos sem
alteração; fontes, palavras selecionadas, strings, campo CHIPID e links
conferidos. Documentação, índices, roadmap e integração organizados.
Nenhuma leitura MMIO, nova execução QEMU, kernel completo ou operação no
telefone. Próximo: obter observação verificável da palavra se houver log
disponível e seguir seus produtores; FDT/memória final continuam abertos.

## 2026-10-24 — callback NEWTIME e argumentos bootstat HZC2

Continuação sobre main 9cf76c2, PR #15 revisado/mergeado. Revisão automática
do #15 conferida completed sem achados no head 026f809; #14 ainda running.
Sem mudanças alheias no checkout de entrada. Não foi repetida a coleta
shell/Shizuku bloqueada ou qualquer ensaio físico.

Contexto X3 nominal 307e0 passado em 18000 a 1dc90; store condicionado em
31998. Wrapper 2f6c0 lê o slot 31978, contexto+40 e chama ponteiro inicial
da célula 30808, 021033fc -> 193fc. O callback consulta NEWTIME e chave
11111111. Em 19694 escreve u64 do frame+136 pelo ponteiro lido de 30520;
o frame recebe X0 na entrada, mas preservação e efeito líquido da função
completa não são declarados. Dados e linha escolhida continuam abertos.

30520 inicia como 02075600, mas 17fe8 atualiza a célula com 31a48+1800.
Escritor selecionado 17a0c recebe W de 15900108, soma 02039000 em W e
estende para X. Sob preservação da cadeia, destino02073600 exige word
38e00; é critério derivado, não medição ou cenário fornecido. Alias e
primeira escrita física no registro permanecem sem comprovação. A busca
exploratória local de constantes em blocos não foi tratada como censo.

Bootstat: três ADRP/ADD ligam formatos 23b200/220/240 aos índices 0/1/2 do
getter149848 e ao helper144618. Setter149830 usa tabela relativa cd3568,
stride8, valor W1 zero-extend armazenado em X; sem bounds nesses corpos.
Inventário BL no intervalo LK tem quatro calls: ee6ac(index0,literal100),
ee6e4(index1), eec30/eed50(index2). Os três últimos usam retorno111c40,
entrada0 e UMULH/shifts; 111c40 lê CNTPCT_EL0 e segue a1118f8. Unidades,
resultado, caminhos executados e entrega final ao kernel não verificados.
Os nomes BL1/2/3 não comprovam durações medidas dos três estágios.

Novo inspetor hash-bound e conferência GNU reproduzível: 156 palavras,
26 alvos, 39 operandos, três produtores e seis ponteiros/strings. Dumps de
strings pedidos em spans múltiplos de quatro, preservando o parser GNU
estrito compartilhado. 70 regressões BL2 passaram; seis recusas CLI de
imagem curta/longa/alterada, exit2 sem JSON parcial; py_compile, relatórios
e critério aritmético de alias conferidos. Documentação, índices, catálogo,
roadmap e integração organizados; sem novo QEMU/MMIO/serviço/telefone.
Próximo: origem/valor15900108, bindings/preservação e registro real, mantendo
demais escritores, slots, RAM/reservas e FDT final abertos.

## 2026-10-24 — publicação ACPM e destino condicional NEWTIME

Continuação sobre main 83fad63, PR #16 revisado/mergeado, revisão automática
completed sem achados no head 0791538. Um temporário de restauração não
rastreado foi preservado fora do checkout com SHA-256 conferido, antes de
abrir feat/acpm-handshake-provenance. Sem outras alterações alheias.

DTS público fixado no commit756951a, exynos2100.dts 501932 bytes, SHA
a92a3c3a2dcba40460d51343a23590d5f48c0ad3330ba33864e77aa446859f4e:
acpm_ipc declara IPC15900000/1000, SRAM02039000/41000 e initdata8000.
Coincide com registrador/base BL2; não comprova alias de porta ou runtime.
Os novos comandos exigem tamanho/SHA exatos dos dois arquivos e campos
do nó, sem parâmetros opcionais de valores de registrador/tabela.

Loops16228/16250 copiam nominalmente file38000..3d000 para0203d000 e
file3d000..67000 para02048800. Sob alias SRAM, locais4000..9000 e
f800..39800. Vetor SPf800/reset4261 e resetfile38260→main38c90 corroboram
o primeiro mapeamento; colocação/cópia/reset não executados. GNU ARM do
cross-binutils existente permite Thumb, sem dependência nova instalada.

Inicialização39b48 configura descritores locais7150/13; helper3998c
configura callback29601 no descritor7 (stride48), nominalfile56e00.
O laço38e6a testa byte+32, carrega callback+4 e BLX38e90. Descritor
inicial7 tem flag1; 56e1e chama56ee0. O caminho contém outras chamadas,
sem prova de preservação, alcance completo ou execução física.

56eee/56ef0 leem literais56fd8=a5900108 e56fdc=38e00. STR56ef2 publica
u32; poll56ef6/56efa espera zero. Depois guarda38e00 em célula2fbf4 e
38e00+1800=3a600 em2fd98. BL2call17eb0→17974 zera15900108 em179a8,
poll179e4 espera não zero; NOVA leitura179f8 pode diferir. SomaW com
02039000, storeX17a0c em31a48 e clear17a50. PonteiroNEWTIME30520
atualizado17fe8 com31a48+1800: publicação38e00 satisfaz destino02073600.
Aliases a5900108↔15900108 e localzero↔02039000, leitura/publicação,
execução e preservação continuam condicionais. Não é handshake executado.

ConsumidorThumb3f558 lê locais3a600/3a604 em dois W e compara assinatura
0001000860000110, igual ao BL2/devfreq. Sob aliasSRAM, endereçoAP02073600;
local3a600 fica além da segunda cópia, não é byte de arquivo nem valor
observado ou amostra atômica comprovada. Lookup/linhaNEWTIME e frame+136
seguem abertos; demais escritores, slots e mapaRAM/FDT não resolvidos.

Relatórios estático/GNU reproduzidos byte a byte: 100 palavras AArch64,
141 instruções Thumb/168halfwords, 10+14 alvos, 15 xrefs a literais,
34 operandos selecionados e22 spans de dados. 70 regressõesBL2 passaram;
12 recusasCLI (sboot/DTS curtos,longos,alterados, dois comandos) exit2
sem JSON parcial. py_compile, 278 links locais e diff --check passaram.
Documentação, índices, catálogo, roadmap e integração do PR16 atualizados.
Sem novoQEMU, kernel completo, firmware executado ou operação no telefone.
Próximo: lookup/linhaNEWTIME e preservação do frame/ponteiro; corroborar
aliases por fonte correspondente ou observação verificável.

## 2026-10-24 — ECT/NEWTIME e prefixo da primeira escrita no QEMU

Retomada da main be47018, PR #17 revisado/mergeado. A revisão automática
agora informa completed, sem achados ou pendências no head 46dbd46. Árvore
de entrada limpa; branch feat/newtime-ect-selection. Os READMEs anexos de
build foram relidos nos caminhos locais e não fornecem dados NEWTIME.

O loop 16278 tem origem nominal 02153000..02167000, arquivo69000..7d000,
e destino90000000. O caminho1ca68 guarda a própria origem02153000 em
31c10 e segue ao parserECT1c87c, sob gates anteriores não executados.
Bloco PARA007n com total_size110c4 e nove nomes/offsets. NEWTIME está em
70404..77994, 30096 bytes, versão0.81, 57 descritores. Registro309d0 tem
12 entradas de32; última30b30 contém nomeNEWTIME, comprimento7, callback
nominal1c3dc e handle inicialzero. Dispatcher1c9c4 chama parser de bloco;
1c3dc instala handle em entrada+24. Lookup1c55c por nome,1c83c por chave.

Chave11111111 tem corpo706bc, dados706c8, mode2/17colunas/22linhas u64.
Linha0 tem seletor0xcafe; linha10 tem0001000860000110, a assinatura já
comparada em BL2/Thumb/devfreq. Demais56 descritores usam mode1. Fontes
ECT .c/.h fixados no commit756951a, hashes e blobs no manifesto, corroboram
nomes, enum, campos e lookup. Não se presume identidade entre builds.

Prefixo193fc..19694 guarda entrada em frame+136; para comparação usa
low32 quando bit63 está ativo, senão u64 inteiro em frame+152. Helper
1c540 combina dois W. Linha encontrada copia16 células u64 para área de
pilha com144 bytes; store19694 recarrega entrada original de frame+136
e escreve pelo ponteiro de30520. Erros selecionados preparam3/2/1 para
nome/chave/linha ausentes. Formas vazias/corrompidas não são modeladas;
checagens de limites do novo leitor de host não são atribuídas ao BL2.

QEMU virt EL1, deltas40000000/40200000. Nenhuma instrução foi alterada;
ponteiros absolutos do registro foram relocados como dados. Heap, pilha,
destino e entradas fornecidos pelo laboratório. Parser original1c3dc e
helpers reconstruíram57 descritores em cada colocação; todos os campos
e ponteiros de dados conferidos. Não executado parserECT completo/gates.

56 casos de prefixo: 22 seletores embutidos e duas entradas bit63/low32cafe
por colocação, total48 primeiras escritas. Seleção,16células copiadas,
frame+136 e valor original de64bits no destino conferidos. Quatro controles
por colocação (linha ausente, positivo com bits altos, nome ausente, chave
ausente) deram1/1/3/2 antes do epílogo, total8, sem tocar destino. Positivos
param antes do STR19694, executam uma instrução e param19698; negativos
param199fc. Código, bloco fonte e sentinelas de pilha/destino intactos.
Sem stubs, respostas MMIO/SMC ou execução do corpo posterior, que contém
outras consultas/cópias/alocador e leitura158609bc[31]. Preservação
conferida só nesse prefixo/bindings, não na função inteira ou no telefone.

GNU2.44:353 palavras/50alvos/24operandos/8spans, inclusive30096 bytes
NEWTIME. Relatórios estático/GNU reproduzidos byte a byte; 10 testes novos
de limites/modos/seleção e70 regressões BL2 passaram. Nove recusasCLI dos
três comandos cobrem imagem curta/longa/alterada, exit2 sem JSON e antes
do QEMU. py_compile,291 links locais e diff --check passaram. Documentação,
índices, catálogo, roadmap e integração do PR17 organizados. Sem execução
física, observação DRAM, capacidadeRAM ou FDT final. Próximo: alocador,
gates e escritas posteriores; corroborar bindings/aliases ACPM.

## 2026-10-24 — construção condicional do registro NEWTIME

Continuação da main e9a8344, PR #18 revisado/mergeado; revisão automática
posterior completed sem achados no head a7c19d0. Checkout inicial limpo;
branch feat/newtime-record-lifecycle. Mantido o sboot HZC2 exato e os
limites entre fonte, modelo, execução de laboratório e estado físico.

Sufixo19698..19a24: versões ECT/NEWTIME em R+8/+12, diretório em R+1a0,
16 descritores de16 bytes até R+2a0; dados a partir de R+2a0. O cálculo W
para n=16 dá capacidade2160 e fim R+2400. Campo de tamanho usado em R+16
só é publicado no sucesso. Lacunas não são zeradas. R é o ponteiro ativo
de30520; hipótese de base estável e regiões disjuntas mantida explícita.

Folha18068 recebe pedido signed W, arredonda o próximo cursor a4, grava
31a50 antes da comparação unsigned com31a58, retorna ponteiro antigo sem
realinhá-lo e estaciona em18090 se exceder. Não retorna NULL nem desfaz
escritas. Pedidos das tabelas reais são positivos e pequenos; não se
atribuiu robustez geral ao alocador.

Gate158609bc[31] relido em19774 a cada iteração. Para índices0..8, ramo
ativo ajusta chave em+3 se nibble8, senão−3 em u64. Índices9..15 ignoram
a transformação. Foram enumeradas22 linhas×512 sequências efetivas:
8512 caminhos completos e2752 retornos4 por chave ausente, zero parques
do alocador nesses dados. Tamanho usado nos completos1da0..22dc, folga
mínima292 bytes. As contagens não são probabilidades ou amostras físicas.

Nove chaves ausentes:3128,312b,3148,3248,4248,4348,5148,5248,5348.
Linha3 não completa nenhum dos512 ramos no bloco embutido, sem presumir
que seja selecionada no telefone. Erro4 ocorre após escritas anteriores
e não publica o tamanho final; registro pode estar parcialmente gravado.
Sob base/intervalos preservados, as escritas posteriores do callback não
tocam seu primeiro u64. Wrapper2f6c0 encaminha status1/3/4 a1fdb8 com27,
status2 com5; outros retornam W0−3, inclusive0→fffffffd. Não executado
o helper1fdb8; seus efeitos permanecem fora da preservação conferida.

Novo ensaio QEMU materializa metadados no host e executa prefixo, blocos
originais, helpers e epílogo. Para em19770 antes do endereço/LDR/teste do
gate e escolhe explicitamente PC19788 ou19810: não há leitura MMIO,
resposta de registrador injetada ou execução do gate. Dois deltas de RAM,
40000000/40200000, com bindings de laboratório e nenhuma instrução
alterada. 96 combinações representativas e duas entradas bit63/low32cafe
por colocação:196 casos,142 retornos0 e54 retornos4. Registro completo
de2400 bytes comparado byte a byte, incluindo lacunas e erros parciais;
primeiro u64 preservado após retorno, ABI/SP e guardas conferidos. Código,
fonte ECT e metadados intactos. Seis execuções extras da folha18068
conferem encaixe, arredondamento e parque com cursor já avançado.

GNU2.44 conferiu270 palavras novas/24 alvos/37 operandos, além das353
palavras anteriores, total623. Relatórios estático/GNU reproduzidos byte
a byte; 12 testes novos e80 existentes passaram. Nove recusasCLI dos
três comandos (curta/longa/alterada) exit2 sem JSON antes do QEMU;
py_compile,295 links locais e diff --check passaram. Documentação,
índices, catálogo, roadmap e integração do PR18 organizados. Sem callback
físico, valores do gate/registro, RAM ou FDT final. Próximo: helper1fdb8,
chamadores e origem da geometria que substitui o marcador; corroborar
aliases e bindings ACPM.


## 2026-10-24 — flags, dump e depuração após erro NEWTIME

Continuação da main7723fbd, PR19 revisado/mergeado. Revisão automática
conferida completed sem achados no head d5db0ba. Quatro temporários de
restauração encontrados na toolchain foram preservados fora do repositório
com SHA-256 antes do checkout feat/newtime-error-debug; nenhum adicionado.

Helper1fdb8: sob console não nulo chama21574,20958,204d4,20200. O prefixo
de21574 foi selecionado, sem atribuir efeitos ao restante. 20958 atualiza
AP02073624 por OR u32 com1<<(W0&31), não atômico; argumentos27/5 vindos
do wrapper produzem08000000/20. SeR=02073600, campo+24hex, não primeiro
u64. Dump204d4 recebe endereço fixo02073600 e tamanho1a0, sem ler R de30520.
104 LDRs até0207379c, antes do diretório. Não contém store na fonte.

Contexto nominal307e0 aponta a30b50; +8puts1d560, +24conversor1d430.
Puts acrescenta CR antes de LF e usa1d4dc: espera bit1 de10540010, grava
word10540020 e pode escrever em buffer de log derivado de31c20. Sem
bindings, buffer disjunto ou canalUART físico observados. Não estendida
a preservação do primeiro u64 ao tratamento transitivo inteiro.

20200 lê10000000 e quatro words de020736d0..e0, chama slots indiretos,
pode entrar no laço20344 e usa outro dump1ffbc/saída via1ff18 callback
1ff3c. O helper externo tem WFI seguido por epílogo/RET, não branch para
si. Não presumidos alcance do WFI, despertar ou retorno ao chamador.
Restante de21574, efeitos dos callbacks e rotina física permanecem abertos.

Dumper: base alinhada a16, limiteW soma nibble+tamanho com wrap, LDRs
u32 mesmo quando exibidos como espaços antes de início desalinhado.
Pedidos curtos leem palavra inteira; zero desalinhado pode ler. LimitesW
fffffffd..ffffffff não terminam pelo wrap do contador em passos4, sob
retornos/acessos estáveis; modelados no host, sem varredura enormeQEMU.
Esses extremos não são os argumentos da chamada selecionada.

QEMU:26 dumps com conversor original e slot de saída substituído por RET
em RAM, GDBobserva strings/LDRs;14 fragmentos originais LSL/LDR/ORR/STR
2096c..2097c comX3 fornecido pelo harness para campo+24 em RAM. Dois deltas
40000000/40200000; fonte inteira2400, guardas, ABI/SP, código, strings e
contexto conferidos. Sem UART, MMIO, helper completo ou telefone executados.
GNU2.44:662 palavras/92alvos/34operandos,3ponteiros/9strings. Nove testes
novos e92 anteriores passaram; nove recusasCLI curta/longa/alterada com
exit2 sem JSON antes deQEMU. Relatórios estático/GNU reproduzidos byte a
byte, Python compilado e links locais conferidos. Índices, catálogo,
roadmap e integração19 atualizados. Próximo: origem da geometria após o
marcador, bindings das recargas e aliases ACPM, sem RAM/FDT físico final.


## 2026-10-24 — empacotamento de geometria após o marcador

Continuação da main 6c4e6da, PR20 revisado/mergeado; revisão automática
completed sem achados no head c48ed5f. Checkout inicial limpo e branch
feat/bl2-geometry-packing. Mesmo sboot exato, sem dependência ou blob novo.

Separados o registro AP02073600 e os slots de estado31978..31990. A
recarga2d7e0 pode trazer o próprio marcador escrito pelo NEWTIME anterior;
não garante geometria nova. Mais adiante, 1e85c chama1d830, que seleciona
nominalmente2f130, depois2fa98 e a folha2caec. Execução das fases e binding
runtime não observados; callbacks intermediários não foram executados.

2f130 zera cada slot por STR XZR em2f168 antes de consultas. Para dois
termos, seletor5 W inteiro não zero habilita6/7/8; um W não zero com byte
baixo zero também ativa. Conferidos arrays de respostas completas, modo
0/1/3, campos dos seletores5/6/7/8 e revisão de10000010[23:20]. Termo2
seletores6/7 ficam no scratch, sem empacotar nesses campos. Três constantes
exatas solicitam seletor49/termo3 e nibble56..59; as duas primeiras apagam
nibbles0..3, a terceira preserva todos. Coincidem com seletores das linhas
NEWTIME10/15/12, sem seleção física presumida.

W21 final é modo do slot3, retornado e gravado no byte31939; folha usa o
nibble do slot0. Casos sintéticos divergentes conferem a distinção, sem
alegar defeito ou condição física. O corpo não publica diretamente em
AP02073600; escritores posteriores/indiretos continuam abertos.

QEMU100 cenários (50 vetores em dois deltas40000000/40200000): executa
blocos originais, para antes de cada BLR de preparação/consulta e BL ao
helper CHIPID. Fornece X0 e ajusta LR/PC ao sucessor, preservando demais
registradores/memória nessas arestas. Não executa chamadas ou MMIO.
Cada cenário executa em seguida a folha original com os slots resultantes,
mais100 execuções da folha, sem o callback intermediário2fa98. Conferidos
ordem/argumentos de consultas, zero de cada slot, 784 bytes de estado,
ABI/SP, guardas, código, tabela e células de callbacks. Registro separado
de2400 bytes preservaCAFE no laboratório, sem prova do registro AP físico.

GNU2.44 conferiu386 palavras/27 alvos/33 operandos e7 ponteiros. Dez testes
novos e101 anteriores passaram. Nove recusas CLI curta/longa/alterada,
exit2 sem JSON antes deGNU/QEMU; relatórios estático/GNU reproduzidos byte
a byte, Python compilado, links e diff conferidos. README, índices, catálogo,
roadmap e integração20 atualizados. Próximo: publicação da geometria no
registro e callbacks intermediários, mantendo respostas/aliases reais e
RAM/FDT final como lacunas, sem repetir ensaios físicos bloqueados.


## 2026-10-24 — segunda publicação da geometria por NEWTIME

Continuação da main70dca68, PR21 revisado/mergeado e revisão automática
completed sem achados no head0469ec8. Checkout inicial limpo; branch
feat/bl2-geometry-publication. Mesmo sboot exato; sem blobs/dependências novos.

Após a chamada de cálculo1e85c, o fragmento1ea18..1ea4c incrementa contador
W31c28, copia para AP02073648, lê slot31978 e chama célula31510 nominal
wrapper2f6c0. Wrapper salva argumento em AP02073638 e relê31978 antes de
chamar contexto+40 nominal193fc. Prefixo seleciona NEWTIME/11111111 e
publica o u64 original da segunda amostra pelo ponteiro30520 em19694.
Não presume igualdade entre a amostra do chamador e a recarga do wrapper.

R e endereço fixo são destinos distintos. Ensaios com R02073600/02075600
conferem publicação no ponteiro sem converter a escolha em valor físico.
Erros3/2/1 do prefixo não desfazem contador e cópia fixa já gravados.
Alcançar o primeiro store não prova conclusão do callback: gate/sufixo,
erro4 e helper externo continuam fora da execução desta entrega.

Após retorno do wrapper, chamadas selecionadas1ea50→nominal2ef90 e
1ea60→nominal2d568. Primeiro pode atualizar158609bc a partir de metadados;
segundo contém recarga fixaAP02073600→31978. Essas operações e estados
posteriores não executados aqui. Fases intermediárias, bindings/aliases
físicos e preservação transitiva continuam abertos.

QEMU160 casos em dois deltas40000000/40200000: 74 primeiros stores e86
erros do prefixo. Vetores:22 seletores do bloco embutido, 50 saídas
materializadas do modelo do empacotador por colocação, R alternativo,
controles de nome/chave, bit63/contador wrap e três mudanças explícitas do
slot entre leituras (seis nos dois deltas). Nenhum retorno MMIO fornecido.

Fixture MMU já existente executa M1/C0 com tabelas RW do harness; identidade
RAM40000000..80000000 e alias virtual02000000..02200000 para RAM física
QEMU41000000/41200000. Mapeamento sintético, sem provar barramentoExynos.
Chamadas indiretas do chamador e wrapper realmente executam até19698 ou
199fc. Não há patch de instruções, salto sobre chamada ou reatribuição de
registrador de endereço. Não executa empacotador novamente, callbackinteiro,
erroexterno ou continuação; metadados do parser são materializados no host.

Conferidos LRs salvos, frame/entrada, linha/tail, contador, cópia fixa,
ponteiro, janela4400 com guardas nas visões virtual e física do laboratório,
pilha, fontes, metadados, código, contexto, slot e tabelas/fixtureMMU. Não
alegado ABI restaurado ao parar dentro do callback. GNU464 palavras,
111 novas+353 do prefixo,59 alvos/29 operandos/5 ponteiros. Oito testes
novos e111 anteriores passaram; nove recusas CLI curta/longa/alterada
exit2 sem JSON antes deGNU/QEMU, relatórios estático/GNU reproduzidos byte
a byte, Python compilado e links conferidos. README, índices, catálogo,
roadmap e integração21 organizados. Próximo: efeitos após retorno, recarga,
bindings físicos, respostas reais e RAM/FDT final, sem repetir coleta bloqueada.


## 2026-10-24 — bugreport DRAM e revisão da governança/proveniência

Usuário forneceu ZIP de bugreport e observações do aparelho HZC2. Leitura
local do arquivo exato (35232190 bytes, SHA d7d494cc...) sem comando no
telefone; extração privada fora do Git. Relatório público só com lista de
permissão: kernel atual HZC2/Android15/SM-G998B, dram_info01,08,00,12G,
LAST KMSG com0001000850500130, Samsung, D1Z e12.000000GB. Kernel HZA6 aparece
em PRINT RECOVERY LOG, mantido separado. Não publicado ZIP/cmdline/IDs/appdata.
Log persistido não é snapshot SRAM ao vivo; identidade atual não data todas
as mensagens. Bugreportz/rish/Shizuku é método informado pelo usuário, não
executado nesta análise; nenhuma cópia feita em /sdcard/Download.

Revisado restante do driver público de2702 linhas e todas as ocorrências
DRAM, com hash1133eb69.../commit756951a. RamoMIF lê alto/baixo AP02073600 e
aplica igualdade exata A0001000860000110. ObservadaB0001000850500130 não
coincide: é segundo caso especial do empacotador/linha15NEWTIME. LKpreenche
cacheaa7ea0 por leiturasWAP02073604/600 e usa bits8..15 parafabricante,
32..47 para processo. A/B/C compartilham fabricante1/processo8, retornando
Samsung/D1Z, com modos/densidades diferentes. Não concluída identidade do
stock5.4.242 com fork, política de frequência ou valores dos outros3slots.

229 palavras/36alvos/17operandos GNU; leitor confere5strings/literal1/1024.
Seis casos QEMU A/B/C em duas colocações executam cache/manufacturer/process
originais, com endereçosAP traduzidos paraRAM por MMUsintética, guardas e
ABI/SP. Sem executarprintf inteiro/telefone. Tamanhoformatado LKvem de
cache ouAP02038848, truncado emMiB e escalado, sem amostra exata do u64.
KERNELLOG tem17730linhas/2029531bytesUTF8/2352linhasNPU e zero DEVFREQdram.
Argumento log_buf_len256K não mede capacidade efetiva ou causa da ausência.

PR22 revisadoautomaticamente completed sem achados após merge; procedimento
anterior não aguardou. AGENTSagora exige completed do headexato antes do
merge, além de revisão própria, validações e threads. Autorização permanente
preservada; não se usa ausência dechecks como aprovação automática.

Auditados17arquivos rastreados>=5MiB com hashes/blobs/modos;13payloads
coincidem com .debs locais,3archives têmcontrole/hash, APK coincide comasset
oficial app-debug.apk/Magiskv30.7 (digestGitHub40729525...). Assinaturas/
origem remota dosdebs não autenticadas; manifesto explicitafronteira. Nenhum
binário adicionado/removido; somatório por caminho não é tamanhoGit, com
aliases deduplicados no manifesto. Bootstrap fixado para posterior organização.
Temporário de restauração preservado fora do repositório, sem incorporar.

Extrator tem nove testes de privacidade/seções/campos, incluindo canários e
texto de aplicativos. Passaram 128 testes de host (88 BL2, 31 NEWTIME e nove
novos), 15 recusas CLI com exit2/stdout vazio e compilação Python. Quatro
relatórios reproduzidos byte a byte, incluindo manifesto conferido com
--check. Links locais conferidos, com um caminho relativo legado corrigido.
README, índices, catálogo, roadmap e integração22 atualizados.
Próximo: preservação/recargas e campos reais restantes, sem
promover logpersistido a mapaRAM ou repetir coletas bloqueadas.


## 2026-10-24 — rastreabilidade da regra DRAM e conferência do PR #23

Conferidos novamente o merge 566c977 e o PR #23 por fetch/log/API, incluindo
head 16191d1, pais e árvore 4be5f5c. Comentário automático atualizado às
21:39:29 -04:00 contém completed e nenhum achado/pendência nesse head;
merge às 21:40:34, 65 segundos depois. updated_at não é um campo dedicado
de conclusão; a consulta da sessão anterior também antecedeu o envio do
merge. Zero threads. Metadados técnicos preservados em extrato JSON e
PR_INTEGRATION, sem confundir essa ordem com a falha anterior do PR #22.

Roadmap agora diz DRAM observada no log do bootloader. Incluídas referências
imutáveis às linhas 39, 40, 44 e 45 de inspect_dram_logging_hzc2.py:
fabricante=(word>>8)&255, processo=(word>>32)&65535; 1/8 selecionam Samsung/D1Z.
GNU reconferiu extração, branches e retorno dos ponteiros das strings no
sboot fixado. O getter de processo faz duas cargas: regra de palavra
estável, sem prova de atomicidade física. Não se deduz leitura direta dos
registradores ou identidade do driver stock. Ausência DEVFREQ segue aberta.

Nesta conferência, nove testes de privacidade/campos passaram; relatório
GNU229/36 alvos/17 operandos reproduzido byte a byte. Conferidos JSON da
cronologia, pais/árvore do merge, 697 links locais e diff. Alteração somente
documental; não houve novo ensaio QEMU nem operação no telefone.


## 2026-10-24 — colunas 1/12 da NEWTIME e callback com parada antes de MMIO

Plano recebido confrontado com sboot fixado. Confirmadas diferenças só nas
colunas 0/1/12 entre linhas 10/15; palavras impressas em log não observam
seleção/publicação do callback. Separados metadados parseados de 32 bytes,
scratch de 144 bytes e descritores de saída de 16 bytes. Colunas 1/12 são
chaves: 0x12b/0x11b (ou 0x128/0x118 conforme gate) selecionam 15 u32;
0x71/0x73 selecionam 44/41 u32. Planos condicionais com ramos iguais diferem
em 12 bytes no tamanho final. Valores/estabilidade de gate continuam abertos.

QEMU10.0.13 funciona pelo loader/bibliotecas do r8/Makefile; -help anuncia
-plugin. Não diagnosticado aborto no ambiente do relato. Runner novo usa
GNU e GDB: preflight de cada acesso inteiro, whitelist de código/RAM,
limite pré-fixado de 20000 instruções e recusa de memória não suportada.
Sem plugin carregado, resposta MMIO/SMC ou PC escolhido após o gate.
Quatro casos (linhas10/15, deltas40000000/40200000) executam continuamente
1355/1495 instruções e 580/645 acessos até parar antes de0x19774, X0=158609bc.
Cauda copiada, cabeçalho/cursor e guardas conferidos, com código/ECT/metadados
intactos. Zero leituras posteriores do scratch e do diretório de saída;
sem retorno completo. JSON contém PC/passo/endereço/valor/coluna e hash
da trilha, com a seleção publicada distinguida do conjunto coberto pelo hash.

Estática segue chaves em19820/1988c, lookup1982c→1c83c e cópia19964→19968.
Novo GNU188/11 alvos/10 operandos acompanha leitores posteriores. Coluna1:
offset em2d5f8→ponteiro31758; folha2e4b4 lê segundo u32, calcula0/28 e
destina resultado aAP0207365c. Coluna12: linhas em2d5e8→byte31698 e
offset2d708→ponteiro316a0; próximo leitor pendente. Não executados esses
consumidores posteriores ou nomeado timing físico/registro do controlador.

Novos dados de kernel/aparelho do plano marcados como informados, sem
confundir fonte2701/f69a com referência2702/1133. Fonte pública devfreq.c
fixada (1728 linhas, SHA2bab2a9c...) mostra available_frequencies percorrendo
profile->freq_table: lista isolada não prova OPP habilitada ou ramo não
executado. Ausência DEVFREQ permanece aberta. Sem dados privados novos.

Temporários de restauração encontrados no início preservados com hash fora
do Git. Documentação, README, índices, catálogo, roadmap e integração24
organizados. Próximo: leitor do payload316a0, uso deAP0207365c e limites
reais do registro; nenhum gate, registrador físico ou FDT final medido.

Validação: 141 testes de host (88 BL2, 44 NEWTIME incluindo13 novos e nove
do extrator), 12 recusas CLI exit2/stdout vazio e quatro controles com
orçamento de uma instrução. Quatro relatórios reproduzidos byte a byte,
incluindo QEMU e GNU623 anterior. GNU466 palavras da cadeia do stepper;
Python compilado, 709 links locais e diff conferidos. Registro inteiro
antes do gate comparado byte a byte; registry e ponteiros também conferidos.


## 2026-10-25 — leitor da coluna 12 e proveniência dos registros

Plano ampliado recebido confrontado com sboot/vddcal fixados. Identificado
0x2cdb8 como leitor do payload316a0 e contagem31698. Relê ambos, percorre
u32 e extrai bits16:12 e nibbles11:8/7:4/3:0. Seguidos helpers2cbec,
2cb9c e2cd1c ao slot25 de30e50, nominal27a7c: controle/data/comando em
bases30f98. Publicados modelos das85 palavras das subtabelas71/73;
sem execução, preservação real ou nomes físicos de timing estabelecidos.

Encontrado store25ef0 de retorno22014 em31c30 por endereço salvo noSP.
Provedor usa rótulos vref_soc_lv/vref_mem_lv e tamanho contagem*162.
25a98 lê scratch31f30 de108 bytes e atualiza registro162, sentido inverso
à hipótese recebida.31fa0 é área de dados com passo108, não tabela de
ponteiros neste caminho. ÂncoraS31688 não prova objeto da linguagem fonte.

Corrigidos quadro2272=2176+96 de26e14, uma/duas passagens de64 combinações,
modo2 em244f0 e slot25 (não26) em263e4.28480 faz escritas nos registradores.
Entrada26 de31408 confirmada nominalmente2dc18; entrada24 aponta2d568,
função que contém2d5f8.2cdb8 tem ponteiro313c8;2e4b4 é chamado em2f0d4.
244ac encaminha a244b8/25050. Buscas B/BL limitadas e ponteiros brutos não
viraram prova de alcançabilidade ou ordem runtime.

Em vddcal, registros40 começam8 bytes antes dos nomes; campo+24 coincide
com seus comprimentos. PonteiroNEWTIME ffff000000067630 termina em offset
que é interno ao parser candidato675e0. Tradução/vínculo do handler e
rota de despacho permanecem abertos. Não promovida stringNEWTIME a uma
segunda cadeia funcional, nem bits altosffff a prova de relocação.

Nenhum código fora do callback executado; nenhum novo QEMU necessário
para esta entrega estática. Mantida parada anterior19774/158609bc e
necessidade de decisão explícita para ampliar o escopo. Kernel stock,
OPPs, DEVFREQ, registrador vivo e FDT final continuam separados dos logs.
READMEs recebidos reconferidos, genéricos; sem nova divulgação de dados
pessoais. Cinco temporários de restauração preservados com hash fora doGit.

Validação:53 testes NEWTIME (nove novos), GNU1031+140 palavras,156 alvos
relativos,34 operandos,12 recusas CLI nas duas imagens/modos e quatro
relatórios reproduzidos byte a byte (dois novos e dois anteriores).
Python compilado, links locais/diff conferidos. Índices,README,roadmap e
integração25 atualizados; revisão automática do próximo head deve terminar
sem achados/pendências antes do merge. Próximo: semântica dos comandos da
coluna12, uso deAP0207365c, preservação dos slots e mapeamento vddcal.


## 2026-10-25 — plano NEWTIME consolidado após conferência do usuário

Registrada a orientação de substituir, como base de trabalho, as seções
2.8 a 2.13 do plano recebido pelo relatório newtime-consumers-hzc2.md.
Criado plano consolidado com níveis de evidência, correções, pendências,
próximas análises estáticas e critérios de conclusão. A confirmação do
usuário não foi tratada como nova execução ou prova de estado físico.

Precisados os três despachos: MOVs 263d8/2646c/264c4 carregam W2=26;
LDRs 263d4/26470/264cc usam deslocamentos 200/208/208; BLRs
263e4/26478/264d4 usam slots 25/26/26. Nove instruções reconferidas no
sboot fixado e no GNU. Mantidos como pontos fora do escopo de execução
26e14, 25b80, 2d5f8 e 2e4b4, além dos demais consumidores externos à
cadeia do callback. 67630 permanece offset interno ao parser candidato
vddcal, com mapeamento/vínculo pendentes.

Roadmap passou a apontar para o plano atual: primeiro leitores de
AP0207365c e preservação/recargas de ponteiros e slots; depois semântica
dos comandos, mapeamento vddcal e grafo entre as fases. README, índice,
relatório-base e auditoria da integração #26 atualizados. Nenhum script,
modelo, limite de execução ou resultado científico alterado.

Na retomada havia um log XNU local truncado: os 2560 bytes eram prefixo
exato dos 63167 bytes versionados. Cópia preservada com SHA-256 antes de
recuperar o conteúdo de HEAD; três temporários de ferramentas também
preservados fora do Git. Essa recuperação não gerou diff no log nem
nova evidência de execução.

Validação documental: relatório GNU1171/156 alvos/34 operandos reproduzido
byte a byte; links locais do projeto e diff conferidos. Sem nova suíte
ou QEMU, pois os executáveis e o harness não mudaram. A revisão automática
do novo head deve concluir sem achados/pendências antes da integração.

## 2026-10-25 — recargas NEWTIME e outro leitor da coluna 1

Base eb1f1d7, análise estática. Recuperado o BL fornecido e conferidos os
hashes anteriores de sboot/vddcal; nenhuma imagem adicionada ao Git.
Leitor reproduzível identifica 0x28808, alvo nominal do slot14 de30e50:
15 recargas do payload31758, 14 envios por BLR e um BR final. Os 14
primeiros valores são u32; o último usa LDRSW. Dispatch recarregado de
31998 com método+72; célula inicialmente zero, escrita condicionalmente
por1dcbc(X3) e2d394(X0). Origens e método ainda abertos.

Confirmadas recargas da coluna12 e mudança condicional das cinco bases
30f98 em2d270 (de finais6000 paraf000). Não foi afirmada preservação dos
slots nem exaustividade de aliases/escritas. StoreAP0207365c conferido;
nenhum leitor estabelecido. Ausência de literal u32/u64 não exclui
endereços calculados. Primeiro item do plano ficou parcial, com próxima
aresta31998/método+72. README, índice, plano e roadmap atualizados.

Validação: GNU324 palavras/18 alvos relativos, operandos dos15 envios
conferidos; relatório reproduzido byte a byte. Três recusas CLI (curto,
longo, alterado), 53 testes NEWTIME e links locais passaram; diff conferido.
Não houve execução QEMU ou no telefone nem ampliação de escopo. A revisão
automática do novo head deve concluir sem achados/pendências antes do merge.

## 2026-10-25 — inicializador de 31998 e binding nominal até SMC

Base a50a1db. Rastreado X3 preparado por17fbc/17fc0/17fc4 para tabela307e0,
fornecido porBL18000 a1dc90 e publicado condicionalmente em31998 por1dcbc.
Célula30828 (+72) contém02100420, nominalmente16420: SMC#0;RET. A cadeia
dos15 envios de28808 possui assim destino nominal concreto, condicionado
à preservação. Segundo escritor2d394 recebeX0 ainda sem origem; seu alvo
aparece no slot47 de31408 (célula31580). Execução/ordem não estabelecidas.

A convenção pública de include/soc/samsung/exynos-smc.h na revisão fixada
756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0 usaSMC_CMD_REG=-101 eSFR_W.
Fonte reconferida por URL fixada, hash e linhas de macros registrados.
Inversão deriva15 endereços candidatos de1a340400 a1a3404b4 com lacunas;
nove valores diferem entre subtabelas12b/11b. Não há prova de atendimento,
resposta, nomes físicos de campos ou correspondência da fonte com o monitor
HZC2. Não houve execução QEMU/SMC/telefone nem ampliação do escopo.

Novo extrator e JSON reproduzidos byte a byte; 324 palavras anteriores mais
46 palavras/3 alvos/14 operandos novos conferidos no GNU. Três testes novos
sobre a inversão (conhecidos, limites/roundtrip e classes/tipos inválidos),
56 testes NEWTIME aprovados. Três recusas CLI por imagem curta/longa/alterada,
764 links locais, compilação Python e diff conferidos. Relatório, README,
índice, plano, roadmap e auditoria do PR28 atualizados. Próximo: despacho
do slot47/X0, escritores/aliases e semântica física dos campos candidatos;
AP0207365c e ordem real permanecem abertos. Revisão automática do novo head
deve terminar sem achados/pendências antes da integração.

## 2026-10-25 — auditoria parcial do slot47

Base a60cd37. A origem deX0 e o despacho verdadeiro da célula31580 não
foram resolvidos. Criado inventário reproduzível de26432 palavras BL2,
com LDRX unsigned e LDPX signed sem writeback, testando ambos os elementos.
Deslocamento376 aparece em quatro LDRs (24784/24adc/24ba0/2501c), nenhum
LDP. Nos caminhos de base selecionados, todos usam30fe8, célula31160,
ponteiro02116300/alvo2c300; não são oslot47 de31408/célula31580/alvo2d364.
Os quatroX0=4 não foram atribuídos ao escritor do binding. Retenção da
base conforme ABI e preservação das células continuam condições.

Busca B/BL para todas as instruções da função2d364–2d3bc não encontrou
candidato no intervalo BL2. Isso não exclui índices em registrador, cargas
literais/pre/post-indexadas, cópias, aliases ou outros módulos. Exploração
temporária por disassembly fora desse inventário não foi promovida a prova
de ausência. X0zero só pula store2d394; leituraAP02073600 já ocorre antes
do teste, e callbacks seguem depois. Não há observação runtime.

Relatório/extrator/JSON e quatro testes novos do decoder adicionados;
README, índice, plano, roadmap e auditoria doPR29 atualizados. Próxima
frente: exportações/cópias e bases recebidas que transportem31580, antes
de atribuir um valor aX0. Resultado parcial explicitado, sem ampliarQEMU.
Validação: GNU84 palavras/3 alvos/22 operandos, reprodução byte a byte,
60 testes NEWTIME, três recusasCLI, 772 links, Python e diff aprovados.
Revisão automática deve concluir sem achados/pendências no novo head antes
da integração; nenhuma chamada SMC ou execução no telefone.

## 2026-10-25 — transportes da célula31580, resultado parcial

Base dc5e745. Reaplicado o decoder dos sete corpos exatos de cópia à
janela nominal211b408–211b588. Nenhuma origem/destino intersecta a tabela;
nenhum transporte da célula211b580 por esses corpos/literais. Projeção
exige oito bytes completos, sem promover sobreposição parcial a ponteiro.
Preservação, aliases e execução seguem abertos.

Inventariados 46BL e1B para1fcc4 em16000–ec000; PCs reconferidos noGNU,
sem supor alcançabilidade. Três origens examinadas:211b630 (W19 não fechado),
211b668/32 bytes e21ab6a4/52 bytes. Nenhuma contém os bytes da célula;
destinos desconhecidos não excluem sobrescritas. Restam44 referências sem
análise de argumentos, além de indiretas/outros helpers. BuscaB/BL para
2d364 ampliada atéec000, sem candidato. Literais e formasMOVZ/MOVK
selecionadas não forneceram endereço da tabela/célula; não prova ausência
de exportação ou chamador. OrigemX0 continua sem solução.

Novo extrator, JSON e quatro testes de projeção; documentação atualizada,
README condensado mantendo os links históricos e auditoriaPR30 registrada.
Cinco temporários de ferramentas preexistentes foram preservados fora do
Git com hashes antes de remover suas cópias locais; nenhum binário adicionado.
Validação: GNU141 palavras/56 alvos/11 operandos, reprodução byte a byte,
64 testesNEWTIME e16 dos laços, três recusasCLI, 781 links, Python e diff
aprovados. Sem execuçãoQEMU/SMC/telefone ou ampliação de escopo. Próximo:
argumentos e wrappers das cópias parametrizadas, distinguindo transporte,
sobrescrita e uso como função. Revisão automática do novo head deve concluir
sem achados/pendências antes da integração.

## 2026-10-25 — revisão global e prioridades do projeto

Base 43356de, main remota/local conferidas; zero PRs/issues abertos antes
da entrega documental. Relidos os pontos de entrada, roadmap, código de
entrada/main R10, diagnóstico, linker, loader em quarentena, testes e
frentes Samsung/memória/XNU. READMEs anexos relidos nos caminhos locais.
Escopo selecionado, sem alegar auditoria linha a linha de todos os drivers.

Rerodados FDT43 e materialização17 sob ASan/UBSan; contêiner passou com59
antes do build e60 após compilar o ELF real. A diferença vem de teste
condicionado à existência de r8/build/r10_payload.elf. Compilação real
aprovada, com warnings preexistentes nos módulos experimentais MCT/SMP.
Diagnóstico QEMU:6 entradas+6 recusas. Loader com main real:1 handoff,
25 IRQs observadas e5 recusas. R8/R9 e XNU não foram repetidos nesta revisão.
Comandos, saídas PASS e hashes de logs/fontes registrados em JSON público,
sem firmware, dados do aparelho ou novos executáveis adicionados ao Git.

Não há workflow rastreado em .github. Recomendada como próxima implementação
uma validação única que construa o ELF real, recuse skips obrigatórios e
execute host/QEMU com CI. Implementação ainda planejada; lógica do payload
e testes não mudou. Próxima investigação principal: contrato de carga e
canal de recuperação dos128 bytes do diagnóstico Samsung, com estado de
entrada/coerência. NEWTIME e suas44 referências restantes ficam paralelas;
memória/FDT final e R10 de uma CPU precedem expansão e XNU físico.

Criada revisão global com escopo, resultados e critérios; roadmap atualizado
para base PR31, novos gates e rodapé atual. README e índice apontam para a
revisão atual; catálogo inclui leitores NEWTIME recentes. Documentação do
contêiner explicita59/60 conforme o build. Auditoria PR31 registrada.
Dois temporários preexistentes de ferramentas foram preservados fora do Git
com hashes antes de remover cópias locais. Sem comandos no telefone, flash,
SMC ou ampliação do escopo de execução de firmware. Links e diff conferidos;
revisão automática do novo head deve concluir sem achados/pendências antes
da integração, conforme AGENTS.md.

## 2026-10-25 — baseline obrigatório e workflow de validação

Base d46e787. Implementado scripts/validate_baseline.py: diretório novo,
compilação real antes dos testes, oito etapas obrigatórias, logs separados,
resumo JSON/hashes, timeout e falha se faltarem assinaturas de cobertura.
test_payload.py exige ELF real com --elf/default e sai2 se ausente; não
existe mais PASS59 por skip implícito. Importação das fixtures preservada.
Makefile mantém o default all e adiciona USE_SYSTEM_TOOLS=1 e tool_versions,
permitindo ignorar tools/root sem remover dependências offline.

Sete controles do runner passaram, incluindo exit0 sem cobertura, exit7
com PASS, ELF ausente, Python otimizado, diretório repetido e timeout com
descendente em outra sessão ignorando SIGTERM. Limpeza usa /proc/pidfds
para alcançar processos QEMU em novas sessões sem sinalizar PIDs reciclados.
Controles CLI de timeout inválido, reuso e timeout real também passaram;
o último deixou resumo failed e interrompeu as etapas posteriores.

Baseline completo local passou em build/baseline-final: FDT43,
contêiner60 com BSS/pilhas reais, materialização17, diagnóstico6+6 e
loader1+5;24 IRQs no caso positivo. GCC14.2/binutils2.44/QEMU10.0.13.
Warnings preexistentes de MCT/SMP preservados no log. UBSan fatal no runner.
Comandos, resultados, hashes de logs/fontes registrados em evidência JSON.

Workflow Baseline em PRs/main/manual usa Ubuntu24.04 e ferramentas APT,
com limite15min, token read-only, ações oficiais fixadas por SHA e
logs/resumo como artifact14dias. O YAML não é prova de sucesso hospedado;
conferir o check real e a revisão automática completed do head exato sem
achados/pendências antes de integrar. Não altera proteção de branch nem
substitui AGENTS.md. Pacotes/imagem hospedados ainda não são bit a bit fixos.

README, índice, catálogo, formato e roadmap atualizados; auditoria PR32
registrada. Próxima entrega principal: matriz do percurso Samsung e leitura
dos128 bytes, com acesso/entrada/coerência documentados. Sem execução de
firmware Samsung, SMC ou telefone, sem ampliação do escopo NEWTIME.

### Continuação — CI sem ROM de rede opcional

O primeiro run40240373832 doPR33 passou build e host43/60/17, mas falhou
na abertura GDB do diagnóstico com QEMU8.2.2 doUbuntu24.04. Nenhum merge
foi feito apesar da revisão automática completed limpa no head60b1d91.
Reprodução local desse QEMU, sem ROMs opcionais, mostrou a mensagem
failed to find romfile efi-virtio.rom; com -nic none ele inicia a espera GDB.
Desativada a NIC nos alvos do diagnóstico e loader, que não usam rede.
O harness do diagnóstico agora imprime stderr/QEMU antes de propagar erro,
preservando a causa no log do runner. Nenhuma mudança no código do payload.
Nova validação deve cobrir ambos QEMU10 e8 e repetir CI/revisão no novo head.

Baseline completo repetido e aprovado em QEMU10.0.13 e binário Ubuntu8.2.2,
ambos com GCC14.2/runtime local. O segundo ensaio usou caminho sem ROMs de
rede, sem instalar ipxe; todos43/60/17,12diagnóstico e1+5loader passaram.
Essa compatibilidade local não foi confundida com imagem hospedada.
Evidência atualizada com os dois conjuntos de logs e a falha inicial doCI.

A conferência externa encontrou um log de build incompleto no workspace,
divergente do hash calculado ao concluir a etapa. Captura alterada para
pipe com um único escritor de log antes do hash. O controle de integridade
agora inclui20KB de stderr de um descendente. Também reproduzida a ausência
de task/*/children e a diferença entre PIDs locais e /proc neste ambiente:
limpeza passa a seguir PPid/NSpid e o controle verifica morte por pidfd,
em vez de interpretar arquivo /proc ausente como processo encerrado.

## 2026-10-26 — contrato de carga/recuperação e leitor do registro

Base b70c3a9 apósPR33. Conferidos os contratos existentes de Image, cópia/salto
LK, coerência, logs/console, acesso shell e referência de kernel. READMEs
anexos relidos; são instruções de build, sem transporte de carga/recuperação.
Consolidada matriz do MarcoA: último relato sem root/travado, aceitação de
imagem própria, posse/coerência e aquisição continuam sem percurso completo
demonstrado. Logs stock/bugreport não equivalem à recuperação da Image própria;
debug-snapshot não é RAM livre. Nenhum novo acesso ao aparelho foi feito.

Adicionado inspect_entry_record.py:128bytes exatos, referência Image v1,
base esperada e snapshot completo opcional. Valida header/layout, marcador,
versão/tamanho, EL/M/C, DAIF/SPSel, reservas e endereços. Com snapshot, compara
todo o código/header e registro. Origem, frescor e autenticação continuam
explicitamente não verificados; marcador ausente não identifica uma recusa.
O leitor não dereferencia x0, não procura RAM e não escreve dados do aparelho.

Dezessete testes de host passaram. Harness QEMU usa o leitor nas seis entradas
aceitas e rejeita seis capturas sem marcador; conserva as verificações de
registradores/código/guards. Nova opção --output-dir exporta referência,
registros, snapshots e manifesto QEMU com hashes, recusando diretório existente.
Offset do leitor conferido contra símbolos ELF; nenhuma mudança no assembly.
Baseline/CI ganha nona etapa obrigatória e exige a integração do leitor.

README, índices, diagnóstico, baseline e roadmap atualizados; auditoriaPR33
registrada. Próximo: delimitar uma interface disponível de carga/aquisição,
seus despachos, permissões e preservação, mantendo a investigação estática.
Nenhuma liberação de MMIO/SMC, ampliação NEWTIME, flash ou mudança de bootloader.

Validação final: nove etapas do baseline passaram, incluindo43/60/17,
diagnóstico12, loader1+5 e leitor17. Roundtrip CLI de seis snapshots completos
e seis recusas passou, incluindo não sobrescrita de diretório. Nove hashes
dos logs e hashes de fontes/capturas registrados em evidência JSON. Quatro
remanescentes preexistentes de ferramentas preservados fora do Git antes
da organização local. Revisão automática limpa do head exato e CI devem
concluir antes do merge, conforme AGENTS.md.

## 2026-10-26 — perfis de dump e envio RDX estático

Base715a5e3. Verificado SHA exato do sboot e rastreados pontos ligados a
upload/RDX. Tabela245340 contém quatro entradas de40bytes, copiada para
pilha e convertida por12df68: log,boot_ram,auto_comment,summary.html.
Nenhuma cobre o envelope conservador da janela candidata do diagnóstico.
boot_ram corresponde à janela nominal da imagem LK e não à Image do kernel;
log exporta2MiB sem o cabeçalho exigido pelo leitor debug-snapshot.

Descritor de saída usa flag+0,nome+4,início+24,fim inclusivo+32,stride40.
A conta do fim é modular e o corpo não rejeita tamanho zero/overflow;
guardas do extrator são host. Caminhos acrescentam dados relativos0xcd31d0,
stride32,tamanho=[+8]+[+24],contador em2 e limite de unidades512MiB. Valores
de execução não foram obtidos nem preenchidos a partir dos12GB do log.

Registro de callbacks116e88/17b8d0, bits17/16 e setterORR de bit16 foram
delimitados. Recorte11786c encaminha blocos até0x80000 para112400/112338
e backend18c4c8, com ramo alternativo de armazenamento. Não é prova de
autorização de pedidos, bindings USB, retenção ou canal disponível no telefone.
Gate do cmd_upload e wrapper FMM têm fluxos diferentes; não se equiparam
FMM/AVB nem se atribui escrita de flag ao helper146ba0 não reconstruído.

Novo extrator exige hash/objdump, sem depender de Capstone ou executar firmware;
GNU488palavras/103alvos/61operandos. Quatorze testes novos cobrem layouts,
limites, fim modular e identidade recusada. Relatório, README, índices,
contrato, roadmap e auditoriaPR34 atualizados. Próximo: escritores da tabela
relativa0xcd31d0 e preservação de bindings/bytes no percurso candidato.
Nenhum MMIO/SMC/cliente de dispositivo, alteração de políticas, flash ou
ampliação QEMU; o diagnóstico continua estacionando em WFE sem saída USB.

Validação: 14 testes novos e 15 do decoder de fluxo passaram, relatório
reproduzido byte a byte, duas recusas CLI com cópias truncada/alterada do
sboot e original intacto. GNU488/103/61, Python, hashes e835 links conferidos.
Nenhum código do R10 foi alterado; CI do novo head deve validar o baseline
existente e a revisão automática deve concluir limpa antes de integrar.

## 2026-10-26 — origem RDX encontrada e conclusão para a sonda

Base ce67fc5 após PR35. A busca estática encontrou `0xee370`: o getter
147e88 retorna S=0xcd31a8, o store ee3d8 escreve o primeiro banco em S+0x28
e o laço escreve pares início/tamanho de16bytes, em unidades de512MiB.
No índice4, ee41c muda a base para0x880000000. O append15e0e8 consome dois
bancos por iteração; a string de nome é `ap`. Dois primeiros bancos
produzidos/conservados e append positivo dão o descritor
[0x80000000,0xc0000000), que contém todo o envelope candidato da sonda.
A origem/cobertura nominal está resolvida; não é mapa físico adquirido.

Cache0xaa7ea8 pode ser publicado por11b6c0/11b6f0/11b758 e limitado por
11b798; chamador147310 passa quatro bits. Os12GB do log não substituem a
leitura deAP0x02038848 ou a contagem consumida. O exemplo24 do relatório
é fornecido pelo host. Cauda ímpar lê tamanho adicional não inicializado
pelo produtor; modelo mantém desconhecido. Somar tamanhos não valida
contiguidade, wrap, RAM livre ou preservação de uma tabela alterada.

Tabela305530 e entradas de init29b148/29b178 ligam nominalmente o backend
ao DWC3: 113a60/18d1b0 publica operações,18d210 publica contexto,
slot+0x38→114fe0/114eb8,slot+0x48→114c18/114b10. Seleção de fa7b0 por
nível/flags e precedência dos bits17/16 delimitadas; sem execução ou
garantia de bindings mutáveis, endpoints, autorização completa ou progressoUSB.

Recompilada a fonte inalterada da sonda: Image384bytes,registro em256;
GNU e palavras conferem laços fechados `wfe;b` em0xd0/0xd8. Não contém
chamada/retorno/salto indireto no texto de entrada. Conclusão: a sonda
atual não retoma cooperativamente o LK para produzir o dump. Cobertura
existe no código; aquisição depende de percurso compatível e canal
independente ou retomada com preservação validada. Reset exige observação
de retenção, não está demonstrado. Nenhum `ret` foi acrescentado.

Extrator fixado por hash confere GNU839palavras/202alvos/85operandos,
slots e initrecords;16 testes novos+14 anteriores de dump+15 de fluxo
passaram. Relatórios novo/anterior reproduzidos byte a byte, duas cópias
truncada/alterada recusadas com exit2, original intacto. Prova dos laços,
hashes e comandos em `lk-rdx-memory-validation-20261026.json`.
README, índices, contrato, roadmap e auditoriaPR35 atualizados. Nenhum
firmware Samsung, MMIO/SMC, cliente de dispositivo ou telefone executado;
escopo NEWTIME preservado. Aguardar CI/revisão automática do head exato
e conferir threads antes do merge, conforme AGENTS.md.

Conferidos também845 links relativos do projeto, Python, diff e hashes das
fontes, relatório e dez logs de validação. Documentação de dependências
instaladas em tools/root ficou fora da conferência de links do projeto.

## 2026-10-26 — continuação de retorno da Image no LK

Base3cc06d6 após PR36. Seguido o retorno hipotético normal do BLR X4
em0xfbe14: epílogo0xfbe18 forçaW0=0, recupera X19/X20/X21/X29/X30 e
SP, depois RET. Dois tails do entry inicial `sbl_boot` restauram o frame
e fazem B para0xfbc10, conservando o link nominal do wrapper0xfaa54.
O wrapper força zero novamente, recupera seu frame e retorna a0xfa5f4,
que chama0x11aba8. A string de fallback identifica `thread_exit()`.

Descritor inicial0x29b030,entryFAB48,wrapperFAA40,construtor11a1e0/11a068,
campos thread+270/+278 e seedFA5D0 da pilha estão ligados estaticamente.
Nenhum desses bindings iniciais é medição de thread/contexto do telefone.
Os epílogos dependem de leituras da pilha e não restauram SCTLR/DAIF/TPIDR.
O bootstrap limpa IRQ antes de chamar, não no retorno da Image. Contexto
compatível e preservação não foram estabelecidos; BLR não fornece sozinho
uma ABI de retorno físico para o protocolo de Image.

Thread_exit guarda status em+280/estado5 em+2c e chama119f28. Se esse
scheduler retornar normalmente, alcança panic18f8a8. Corpos locais de
saída/panic não têm RET. Nenhuma transferência direta aos três pontos RDX
selecionados aparece nesses blocos, sem excluir callees, callbacks mutáveis,
outras threads, traps ou reset. O destino nominal é terminar a aplicação;
RET isolado não constitui mecanismo de observação cooperativa. Sonda
permanece em WFE, sem modificação ou execução adicional de firmware.

Novo extrator exige o sboot exato, GNU294palavras/57alvos/58operandos e
sete grafos locais com continuação de chamada explicitamente condicional.
14 testes novos e15 do decoder passaram; relatórios novo, RDX e chamadas
finais reproduzidos exatamente. Duas cópias truncada/alterada recusadas
com exit2 e original intacto. Comandos e hashes em evidência JSON.
README, índices, retorno, matriz Samsung e roadmap atualizados, com
auditoria do PR36. Três remanescentes preexistentes de ferramentas foram
preservados fora do Git com hashes antes da organização local.

CI pós-merge36 encontrado cancelado na instalação, sem baseline executado;
job reexecutado nesta continuação, separado do PASS do head antes do merge.
Nenhum MMIO/SMC, cliente USB, comando no aparelho ou ampliação NEWTIME.
Aguardar CI/revisão automática limpa do novo head e conferir threads antes
do merge, conforme AGENTS.md.

Conferidos859 links relativos e hashes das fontes, relatório e sete logs.
A segunda tentativa do run40431618302 concluiu success no merge3cc06d6,
job121992403220; auditoriaPR36 atualizada antes de publicar esta entrega.

## 2026-10-27 — panic e recuperação de contexto HZC2

Base 0d80be2. Resolvidas as rotinas 205788 (contador), 17d880 (halt) e
205818 (recuperação via contexto e ERET). Produtor 202800 guarda X30 como
PC; não há destino fixo RDX nesse mecanismo. Relatório, JSON e analisador
fixados pelo hash do firmware. GNU 223 palavras/25 destinos;
29 testes existentes do decoder/grafo passaram, reprodução exata e duas
recusas de entrada corrompida. Sem firmware executado ou sonda alterada.
A captura física segue pendente; esta entrega fecha a semântica local de panic.

## 2026-10-27 — configuração LK após a cópia

PR38 reproduzido byte a byte e 29 regressões passaram. Continuação identifica
0x151b10 como dispatcher com ações CP/fingerprint e serviços SMC concretos;
retorno normal zero não é prova de autenticação. Extrator fixado ao SHA,
201 palavras/60 destinos GNU, oito grafos e nove strings. Sem execução
Samsung ou alteração da sonda. Monitor e outros callees seguem fronteiras.

## 2026-10-27 — origem do bitmap de política

Base42d2bb6, CI pós-merge40453852082 success. Fonte sboot restaurada e hash
exato conferido. Encontrados bitmap de32 bytes, produtor get_token_mode,
cópia intermediária workspace+29f68 para resposta+120 e publicação cd6618.
423 palavras/93 destinos GNU; sem execução Samsung. Prefixo ENG e lookup
STEADY são evidência nominal; produção do workspace e valores reais abertos.

## 2026-10-27 — escritor dos modos do token

Base4546b24, PR40 integrado. Ligado comando21 às duas tabelas e ao handler
0x13a998: lista de até128 IDs≤255, OR em workspace+0x29f68 e bit5 ao completar
inclusive lista vazia. Erro tardio deixa escritas locais, mas o caller desvia
antes da publicação global. Parser136eb0/helper138740 e token ativo continuam
opacos. Evidência: [análise](docs/lk-token-modes-hzc2.md) e
[validação](docs/references/lk-token-modes-validation-20261027.json).

## 2026-10-27 — observação do boot stock via ADB/dumpstate

Base436b539; usuário encerrou a alternativa Odin e pediu continuidade com
as coletas recebidas. ZIP privado permaneceu fora do Git. Extrator por lista
de permissão preserva linhas/hashes e seis campos SEC_DRAM/SEC_PGTBL/Harx.
A adjacência SEC_DRAM→Harx produz chamada de tamanho zero no cenário do
construtor, sem prova de FDT final. Token: mensagem316 corresponde ao ramo
de prefixo diferente de ENG, não a prova de partição vazia/bitmap zero.
[Análise](docs/bugreport-boot-hzc2.md) e
[validação](docs/references/bugreport-boot-validation-20261027.json).

## 2026-10-27 — resultado local do banco zero no editor

Basec2e41bb. Seguidos 0xf1570, helpers e editor FDT original HZC2. Com
espaço, cria memory@c0000000 com reg de tamanho zero; falta de espaço deixa
edições parciais. Caso de reg ausente com tipo preexistente termina W0=0
apesar da falha de reg. Dezesseis casos QEMU, duas posições de laboratório,
substituições explícitas de snprintf/strtoul/printf e conferência de bytes,
ABI/sentinelas/código. Modelo do walker encaminha zero, guard uH falharia;
sem walker/HVC/uH físico ou FDT final capturado.
[Análise](docs/lk-zero-bank-editor-hzc2.md) e
[validação](docs/references/lk-bank-editor-validation-20261027.json).

## 2026-10-27 — PSCI editado depois dos bancos

Base8f88999. Seguido trecho posterior: 0xfb52c chama 0xf9470, que sob
flag Harx tenta smc→hvc em /psci/method. Mensagem do ramo após setprop
não negativo observada na linha409533 do LAST KMSG privado, tempo2.946751.
Extrato por lista de permissão separado preserva relatório anterior.
24 casos QEMU com implementação FDT/comparações originais, só printf
substituído; banco zero preservado nessa rotina. Comprimentos curtos aceitos
no ensaio não são evidência de dados malformados no aparelho. Corrigidas
afirmações que confundiam DTB base com método após edições do LK.
[Análise](docs/lk-psci-final-edit-hzc2.md) e
[validação](docs/references/lk-psci-final-validation-20261027.json).

## 2026-10-27 — observação NEWTIME/opção 2 no runner

Basea12a8e2. Revistos escopo/obs.gdb/patch recebidos; harness continue não
usado, originais preservados como referência. Runner mantém preflight,
20000 instruções e fronteiras; snapshots de entrada/parada sem instrução
guest, sem leitura do literal AP fora do envelope. Quatro casos param no
gate, 1355/1495 instruções, hashes iguais à referência. 31f30 já entra ff
no arquivo, sem escritas até o gate: predição zero refutada sem demonstrar
preenchimento pelo descritor. JSON por linha e comparador próprio entregues;
compare.py/run_case.sh originais não recebidos. Nenhum avanço de escopo.
[Relatório](docs/newtime-gate-observation-scope-hzc2.md) e
[validação](docs/references/newtime-gate-observation-validation-20261027.json).

## 2026-10-27 — argumentos das cópias NEWTIME

Base `5b3ef6a`; CI pós-merge do PR #45 aprovado. Revisadas as 44 referências
pendentes e mantidas as três anteriores: 47 locais de B/BL para 0x1fcc4,
mais referências de wrappers. Grupos de 24 strings, buffers, índices com
sinal e metadados delimitados. O único chamador direto de 0x25400 recebe
índice não negativo do laço selecionado sob preservação ABI. O buffer X5
de 64 bytes aponta para investigação do slot 20 de outra tabela. Sem transporte
comprovado de `0x31580` ou origem de X0 resolvida. GNU 1320/231/46, 84 testes
NEWTIME, reprodução exata, três recusas e baseline aprovados. Sem executar
firmware ou ampliar o escopo QEMU.
[Análise](docs/newtime-copy-arguments-hzc2.md) e
[validação](docs/references/newtime-copy-arguments-validation-20261027.json).

## 2026-10-27 — origem dos buffers de canal NEWTIME

Base `68eacaa`, CI pós-merge do PR #46 aprovado. Encontrado escritor
`0x2d468`: quatro bases desde `0x02075a00`, passo 4016, e configuração em
`0x020798c0`. Chamada nominal `0x2f73c`, slot 18 da tabela `0x31408`.
Diretório `0x0223f000` delimitado: registros de 24 bytes, origem/tamanho
u32, lookup de 15 posições sem limite pela contagem. Modelos novos com/sem
charac_lvcc permanecem condicionais; stores antecedem os guards, sem prova
geral de bounds ou rollback. GNU 428/70/64, 95 testes NEWTIME e baseline
aprovados. Sem execução Samsung ou ampliação QEMU; slot 47 ainda aberto.
[Análise](docs/newtime-channel-origins-hzc2.md) e
[validação](docs/references/newtime-channel-origins-validation-20261027.json).

## 2026-10-27 — slot 20 NEWTIME e origem de X5

Base `912edb3`, CI pós-merge do PR #47 aprovado. Scan LDR/LDP de 160 bytes
classifica 16 cargas; oito usam nominalmente `0x30fe8`/slot 20, com nove BLRs:
sete X5 zero, duas SP+0xc0. Delimitadas construção de 16 u32 por diferenças
de amostras + base aditiva, cópia de 64 bytes e leituras low16 no bit 13.
Sem valores físicos ou transporte demonstrado do slot 47. Busca adicional
de LDR literal/ADR/pares ADRP+ADD e offsets 1408/5504 mantém despacho/X0
abertos. GNU 486/48/41, 108 testes NEWTIME e baseline aprovados; análise
estática, sem avanço QEMU.
[Análise](docs/newtime-slot20-hzc2.md) e
[validação](docs/references/newtime-slot20-validation-20261027.json).

## 2026-10-28 — dois switches NEWTIME com entradas relativas

Base `e9bcc87`, CI pós-merge do PR #48 aprovado. Material externo v5
reproduzido (137 testes sem skips, JSON igual salvo caminho da entrada).
Enumerados independentemente os BRs `0x1ada4` e `0x2f928`: arrays
`0x30108`/`0x30130`, 20 halfwords/5 bytes e 12/4 destinos. Os anchors
`0x1ada8`/`0x2f92c` são código, não as tabelas. Nenhuma entrada aponta ao
slot 47; os grafos locais deixam `0x1a668`, `0x1aff0` e o callback em
`0x2fa78` como fronteiras. O callback usa nominalmente slot 38/`0x31538`
→ `0x2d2e4`, condicionado ao bit 12 de AP0x02073698 e à preservação.
GNU 256/26/26, 131 testes NEWTIME (23 novos), 1023 links e baseline
aprovados; sem executar firmware Samsung ou
ampliar QEMU. [Análise](docs/newtime-jump-tables-hzc2.md) e
[validação](docs/references/newtime-jump-tables-validation-20261028.json).

## 2026-10-28 — continuação comum NEWTIME

Base `054f5c8`, CI pós-merge do PR #49 aprovado. Seguido o grafo local de
`0x1aff0`: 227 PCs, sete BLs e RET 0x1b378. Leitor 0x1a26c extrai quatro
campos de 16 bits; os seletores dos 20 casos cobrem 24 palavras sob
preservação, sem limite demonstrado no default. Delimitados layout de
quatro bytes, low24, correções de byte e argumentos; helpers numéricos
permanecem opacos. Contagem signed<=0 e Q zero preservados como endereços
sintáticos possíveis, sem declarar fault/alcançabilidade. Bases dinâmicas
não excluem aliases de 0x31580/0x31998; slot 47 e X0 continuam abertos.
GNU 784/111/52, 151 testes NEWTIME (20 novos), reprodução exata, três
recusas, 1036 links e baseline aprovados. Sem execução Samsung ou avanço
QEMU. [Análise](docs/newtime-common-continuation-hzc2.md) e
[validação](docs/references/newtime-common-continuation-validation-20261028.json).

## 2026-10-28 — auditoria da folha MIF e anexos GLM

Complemento no PR #50 sobre head remoto a6013d1 (árvore equivalente ao
commit local 18c3ec2). Reproduzidos 29 testes, JSON byte a byte e 49 encodings
GNU dos anexos, após adaptação de caminhos/runtime locais. Confirmados
53 palavras, 13 limiares e stores globais 31a70/74/78. Corrigido contrato:
X2/X3 são limiares carregados, não X2=13; CMP do switch é 0x13; ADR não
deriva base absoluta. Scan externo tem falso positivo W/X e não demonstra
exclusividade de escritores/chamadores. X2..X7 não conservam argumentos
iniciais através de chamadas; exemplo condicional MARGIN handle zero deixa
X2=0. Dois overwrites de retorno conferidos por caminhos. Modelo próprio
comparado em 144 estados sintéticos nos quatro GPRs de saída, sem executar
no aparelho/QEMU. Extrator GNU 203/37/34, 167 testes NEWTIME (16 novos),
reprodução exata, três recusas, links locais e baseline aprovados. Slot 47
permanece aberto. [Auditoria](docs/newtime-mif-bins-hzc2.md) e
[validação](docs/references/newtime-mif-bins-validation-20261028.json).

Correção ao cruzar os dois extratores: o E/X26 da continuação pode ser
substituído pelo lookup MARGIN em 0x1ad74/0x1ad78 quando o handle de
0x1ad68 não é zero; a descrição anterior só registrava a busca inicial.
Extrator/JSON/validação corrigidos, reprodução e três recusas repetidas,
167 testes aprovados. O conjunto GNU da continuação agora é 784/111/56.

## 2026-10-28 — resultado secundário e identidade Q=B

Base remota `2abb0e6` no PR #50. Prompt entregue para a frente paralela
MARGIN/callback nominal 0x1b96c/handle 0x30a48. Nesta frente, seguido
0x1a804: 172 PCs, três BLs e um RET. O alocador antecede os gates; seletores
2/3 com gate zero retornam B, caso contrário retorna Qnew. Campos u16 em
Rentry+0x420/+0x422 transportam low16(ponteiro-Rlate), sem reconstrução
integral. Ajustes Y por campos de dois bits, contagem unsigned UMULL e
layout da palavra delimitados; FP/dados dinâmicos continuam opacos.
Casos 2/3 copiam o mesmo bit para tag W27 e gate; o helper restaura X27
no epílogo. Sob preservação, tag/gate zero dá Q=B; se o laço E executa com
byte estável, as duas stores somam duas vezes ao mesmo byte módulo 256.
Não é observação no aparelho nem conclusão física/vulnerabilidade.
GNU 482/47/91, 192 testes NEWTIME (25 novos), JSON exato, três recusas,
links e baseline aprovados. Sem avanço QEMU; slot 47/X0 ainda abertos.
[Análise](docs/newtime-secondary-result-hzc2.md) e
[validação](docs/references/newtime-secondary-result-validation-20261028.json).
