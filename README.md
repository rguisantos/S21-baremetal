# S21-baremetal — AArch64 no QEMU e investigação do Exynos 2100

Kit de bring-up AArch64 com MMU, níveis de exceção, GICv3, timer e microkernel didático. A frente R10 investiga um payload para o Galaxy S21 Ultra **SM-G998B / p3s**, com evidências das imagens originais **G998BXXSJHZC2** fornecidas pelo usuário, que usa Android 15.

**Estado em 2026-10-21:** R8/R9 passam a regressão em QEMU; R10 compila e tem testes de componentes e integração em QEMU, mas ainda não foi executado no telefone. PRs #2 e #3 foram consolidadas na main. O DTB stock confirma recursos do SoC, mas não descreve a RAM disponível após o bootloader.

## Módulos e validação

| Módulo | Conteúdo | Evidência atual |
|---|---|---|
| R8A | MMU, alias virtual e faults deliberados | QEMU PASS |
| R8B | EL3 → EL2 → EL1 e acesso privilegiado negado | QEMU PASS |
| R8C | GICv3 e timer físico, INTID 30 | QEMU PASS |
| R9 | EL0, SVC, tarefas, troca de contexto e preempção | QEMU PASS |
| R10 | Entrada EL2 → EL1, FDT, GIC herdado, timer e exceções fatais | Compilação; modelos host; integração com carregador sintético no QEMU |
| Carregador de teste EL2 | Contêiner → main R10 real, UART QEMU | Materialização conferida por GDB; timer IRQ; cinco recusas; uma CPU |
| Diagnóstico de entrada | Image independente, captura EL1/EL2 sem periféricos | [6 casos QEMU PASS](docs/entry-diagnostic.md); sem execução no telefone |
| Shim | Legado em quarentena; inspeção S21R10 v1 | Compilação; entrada padrão estaciona; handoff desativado |

Há dois testes R10: o estágio anterior substitui a função C principal; o novo carregador EL2 materializa o contêiner e inicia também a main de produção, trocando apenas o backend UART por PL011 QEMU. A memória é conferida antes do salto e as IRQs depois dele. Isso não emula o Exynos, Harx, USI nem o bootloader Samsung.

## Compilar e reproduzir

Ambiente usado: Linux x86_64, Bash, make, Python 3 e compilador C nativo (`cc`) para os testes host. Toolchain AArch64 GCC 14.2 e QEMU 10.0.13 estão extraídos de pacotes Debian em `tools/root`; os pacotes em `tools/debs` permitem reconstrução com `scripts/bootstrap_tools.sh` e `dpkg-deb`, sem root. O repositório é grande por incluir essas ferramentas.

```bash
make -C r8 -j4 all
make -C r8 regress
python3 scripts/test_fdt.py
python3 scripts/test_payload.py
python3 scripts/test_payload_stage.py
python3 scripts/test_payload_loader.py
python3 scripts/test_entry_diag.py
bash scripts/test_pr_fixes.sh
bash scripts/test_r10_stage.sh
```

Os caminhos são relativos ao repositório: não há dependência de `/home/z`. É possível sobrescrever `TOOLS=/caminho/tools/root`; na ausência das ferramentas locais, o Makefile procura o cross-toolchain e QEMU no PATH. O wrapper `scripts/cross-run.sh` isola as bibliotecas do toolchain local; QEMU usa seu loader e dados locais.

`r8/build/` e `r8/logs/` são resultados gerados, não evidências binárias distribuídas. A regressão leva aproximadamente dois minutos porque os módulos estacionam intencionalmente. O harness confere assinaturas PASS; timeout 124 é esperado. Para execução individual:

```bash
timeout 25 make -C r8 run_r8a
timeout 25 make -C r8 run_r8b
timeout 40 make -C r8 run_r8c
timeout 35 make -C r8 run_r9
```

`make -C r8 run_r10` e `run_r10_hw` apenas informam o estado do ELF experimental. Não fazem flash nem demonstram um método de carregamento Samsung. O endereço padrão `0x80080000` continua sendo hipótese de linkedição, não RAM livre comprovada.

## R10 atual

**Evidência nova do BL HZC2:** a entrada de LK programa/preserva EL1; não há EL2 confirmado no salto para o kernel. O requisito EL2 atual do R10 foi testado no carregador sintético QEMU e ainda precisa de adaptação/validação para o Samsung. [Splits, instruções e correções do relatório externo](docs/sboot-layout-hzc2.md).

A entrada primária exige EL2 com MMU/D-cache de EL2 e EL1 desligados e preserva o FDT recebido em x0. A main permanece em uma CPU, sem ativar MMU, MCT, SMP ou PSCI. O parser verifica RAM, reservas, initrd, afinidade completa da CPU, GIC e timer antes de acessar o GIC. Descrições incompletas provocam parada, sem preencher lacunas com endereços presumidos. Pilhas agora integram o `p_memsz` do segmento ELF.

O Distributor pertence ao firmware e é somente lido. A interface de CPU usa registradores ICC; o redistributor é descoberto por afinidade em GICR_TYPER. Somente interrupções privadas são suportadas. Exceções inesperadas registram o contexto e estacionam; o R10 não usa a recuperação didática `ELR += 4` de R8.

A UART fica desativada por padrão. `R10_UART_FIRMWARE_CONFIGURED` só permite usar uma instância cuja configuração herdada tenha sido verificada; não inicializa clock, pinmux ou USI. MCT e SMP permanecem experimentais e fora da sequência inicial.

## Fontes e documentação

Comece pelo [índice organizado](docs/README.md) e pela [revisão atual com arquivos pendentes](docs/repository-review-2026-10-21.md). O catálogo de scripts distingue ferramentas atuais de experimentos históricos.

- [Mapa de hardware confirmado e pendências](EXYNOS2100_HARDWARE.md)
- [Imagens stock HZC2: cabeçalhos, DTB, overlays e hashes](docs/stock-firmware-hzc2.md)
- [Pacote Samsung: base, delta e drivers consultados](docs/samsung-reference.md)
- [Parser FDT, política de memória e contrato do carregador](docs/fdt-resources.md)
- [Entrada/GIC/timer/exceções e cobertura em uma CPU](docs/r10-single-cpu.md)
- [Carregamento Samsung e instalador Proton: contrato e lacunas](docs/loader-contract.md)
- [Revisão do empacotador do branch kilo e alegações de SMP](docs/branch-packer-review.md)
- [Carregador EL2 QEMU: main R10 real e recusas antes da cópia](docs/qemu-el2-loader.md)
- [Contêiner S21R10 v1: empacotador, validação e limites](docs/payload-format.md)
- [ZIP Proton publicado: hashes, Linux/EFI e DTB real](docs/proton-binary.md)
- [Proton+ v6.1.0: kernel, Mali r38p1 e recursos GPU](docs/proton-reference.md)
- [Referência TWRP indicada: DTB e configuração de recovery](docs/twrp-reference.md)
- [Coleta sem root com Shizuku: resultado e limites](docs/runtime-collection.md)
- [Resultados reproduzidos nesta revisão](docs/validation-2026-10-20.md)
- [Integração dos PRs](PR_INTEGRATION.md) e [histórico de investigação](worklog.md)

`scripts/test_fdt.py --inspect arquivo.dtb` compila e executa o parser C real com ASan/UBSan, além das fixtures. Forneça um FDT bruto, separando antes eventuais tabelas Android. Ferramentas forenses antigas em `scripts/`, incluindo `parse_fdt.py` e `abl_triage.py`, não substituem essa validação: seus leitores de formatos ainda precisam de revisão antes de serem usados como evidência.

## Próximos passos para o telefone

Faltam um contrato de carregamento verificável, mapa de RAM e reservas após os ajustes do bootloader, estado de entrada/caches e acesso ICC/timer confirmado. Os DTBs stock e TWRP não resolvem essas lacunas. A coleta via Shizuku já foi tentada e documentada; ela não concede acesso root. Depois disso, fechar USI/clock/pinmux e só então ampliar para SPI, MCT e SMP com a topologia real.

As [notas antigas de hardware](docs/archive/exynos2100-notes-legacy.md) foram preservadas como histórico e contêm hipóteses superadas. A documentação atual distingue resultados observados de trabalho ainda não validado.

A Image do Proton publicada foi inspecionada: é Linux ARM64 com EFI stub, não um executável Windows que substitui Linux. O contêiner S21R10 agora pode ser gerado e validado offline, mas não habilita o shim ou testes de flash. Consulte as evidências binárias e o formato acima.

## BL HZC2 recebido

[Inventário, integridade e primeira análise do salto para o kernel](docs/bootloader-hzc2.md). O pacote BL solicitado já foi recebido e analisado; não há novo arquivo necessário para continuar a análise estática. Atualização: PR #4 posteriormente criado, revisado e encerrado como substituído pela main. A análise do BL agora rastreia a origem do deslocamento do kernel e a construção dinâmica de nós RAM.

A análise estática do [console LK HZC2](docs/lk-console-handoff.md) encontrou um caminho que seleciona `0x10540000`. O cruzamento com a fonte Samsung identifica UART0, canal debug configurado para 115200/8; ativação e conexão física seguem pendentes.

A [seleção do console por jig e MUIC](docs/uart-routing.md) foi rastreada no LK e cruzada com o driver MAX77705. Há um coletor somente de leitura para os atributos UART/MUIC no Android.

A [coleta UART/MUIC no aparelho](docs/runtime-collection.md#coleta-uartmuic-recebida--2026-10-21) confirmou SM-G998B/HZC2 e os limites do shell: `uart_en` existe, mas é ilegível; `attached_dev` retornou `No VPS`. A habilitação e a seleção AP/CP continuam desconhecidas.

O callback adicional do LK foi identificado como [log em memória debug-snapshot](docs/lk-memory-log.md), em região de 2 MiB. Há um leitor offline com testes sintéticos; ainda não foi obtido dump dessa região no telefone.

Para testar o acesso aos logs sem root, há um [procedimento limitado pelo rish](docs/boot-log-collection.md), com relatório de permissões e capturas de até 2 MiB por arquivo. A execução no aparelho foi concluída: os três nós apareceram ausentes ou ocultos pelo acesso do shell, sem conteúdo capturado.

A [cadeia de cópia da Image no LK](docs/lk-kernel-copy.md) foi ligada ao destino do salto. O diagnóstico independente passou em 128 casos QEMU cobrindo EL1/EL2 e todos os 64 deslocamentos decodificados; nenhum teste físico foi realizado.
