# Guia da documentação

A entrada do projeto é o [README principal](../README.md). Este índice separa implementação, evidências e histórico. Os documentos descrevem testes de software; nenhum registra execução R10 no telefone.

## Implementação e testes atuais

- [Diagnóstico de entrada EL1/EL2](entry-diagnostic.md): Image independente, registro de estado e 12 casos QEMU no teste padrão.

- [R10 em uma CPU](r10-single-cpu.md): entrada, exceções, GIC e timer.
- [FDT e política de memória](fdt-resources.md).
- [Formato S21R10](payload-format.md): empacotador e validação.
- [Carregador EL2 no QEMU](qemu-el2-loader.md): materialização, main real e recusas.
- [Validação anterior](validation-2026-10-20.md) e [nova revisão e arquivos pendentes](repository-review-2026-10-21.md).

## Evidências do aparelho e fontes externas

- [Hardware](../EXYNOS2100_HARDWARE.md) e [firmware stock HZC2](stock-firmware-hzc2.md).
- [Fontes Samsung e READMEs recebidos](samsung-reference.md).
- [Proton: fonte](proton-reference.md), [binários](proton-binary.md) e [contrato do carregador Samsung](loader-contract.md).
- [Referência TWRP](twrp-reference.md) e [limites da coleta Shizuku](runtime-collection.md).

## Histórico e decisões

- [Integração dos PRs](../PR_INTEGRATION.md).
- [Revisão do branch kilo](branch-packer-review.md): por que seu packer e as alegações de SMP não devem substituir a main.
- [Worklog](../worklog.md): registro cronológico, não guia de execução atual.
- [Notas arquivadas](archive/exynos2100-notes-legacy.md): hipóteses antigas preservadas.

## Organização dos diretórios

| Diretório | Finalidade |
|---|---|
| `r8/` | Código R8/R9/R10, Makefile e fixtures/testes C/assembly |
| `shim/` | Shim legado em quarentena e componentes atuais do contêiner; consultar os documentos antes de executar |
| `scripts/` | Testes, bootstrap, inspeção e ferramentas históricas; [catálogo](../scripts/README.md) |
| `tools/` | Empacotador e toolchain/QEMU local; binários grandes preexistentes |
| `samsung_kernel/` | Recorte de referência, **não** árvore compilável completa; [escopo](../samsung_kernel/README.md) |
| `docs/archive/` | Documentação superada conservada para rastreabilidade |

`build/`, logs e caches Python são gerados e ignorados. Não adicionar dumps privados, pacotes firmware ou novos toolchains para documentar uma análise: registrar origem, tamanho e hash. A remoção dos binários já versionados exigiria planejar a distribuição offline; não foi feita nesta organização.

## BL HZC2 recebido

[Inventário, integridade e primeira análise do salto para o kernel](bootloader-hzc2.md). O pacote BL solicitado já foi recebido e analisado; não há novo arquivo necessário para continuar a análise estática. Atualização: PR #4 posteriormente criado, revisado e encerrado como substituído pela main. A análise do BL agora rastreia a origem do deslocamento do kernel e a construção dinâmica de nós RAM.

- [Splits do sboot HZC2 e entrada LK em EL1](sboot-layout-hzc2.md): validação do detector, inspeção reproduzível e revisão do relatório externo atualizado.

- [Console LK e handoff final HZC2](lk-console-handoff.md): caminho de saída e pista de base 0x10540000.

- [Roteamento UART, jig e coleta somente de leitura](uart-routing.md).

- [Log em memória LK/debug-snapshot](lk-memory-log.md): cursor, preservação pelo kernel e leitor offline.

- [Coleta limitada de logs pelo rish](boot-log-collection.md): interfaces de snapshot, metadados e limites.

- [Cópia da Image e destino de salto no LK](lk-kernel-copy.md): contexto e caminhos Android v2/v3.

- [Modelo offline LK v3](lk-v3-layout.md): kernel, ramdisks concatenados, extensão Image e região DTB, com testes de host.

- [Pipeline DTB/DTBO/DPM](lk-dtb-pipeline.md): ponteiro vendor ligado ao buffer do kernel, seletor por revisão e oito candidatos de host.

- [Escritas dinâmicas no FDT](lk-dynamic-fdt.md): initrd ligado às cópias, checagem parcial de chosen, reservas condicionais e origem do tamanho de RAM.

- [uH earlymem e Harx soc_info](el2-earlymem-hzc2.md): handler do HVC ligado ao LK, efeitos de alocação e relatório offline vinculado aos três hashes HZC2.

- [Intervalos LK → uH](lk-uh-range-registration.md): percurso dos nós memory do FDT, primeira tupla de reg, comando 2 e checagem offline dos argumentos.

- [Intervalo Harx no construtor de RAM](lk-harx-memory-gap.md): retornos constantes do serviço OEM, condição do LK e dependências ainda abertas.

- [Candidato de observação pelo log Harx](harx-log-observation.md): fonte, configuração da Image stock, DTB e coletor de uma página; leitura pode avançar cursor, acesso no telefone pendente.

- [Roadmap atual até o diagnóstico físico](roadmap.md): marcos, critérios e bloqueios.

- [Kernel Exynos-2100/universal2100](exynos-2100-reference.md): comparação fixada por commit, aproveitamento e limites.

- [UART0 no intervalo BL2 HZC2](bl2-uart-hzc2.md): pinmux compatível, chamadas diretas e configuração nominal.

- [Clocks UART0 entre BL2 e LK](uart-clock-stages.md): tabelas PERIC0, wrapper principal e divisor.

- [Gates e QCH UART0](uart-gates.md): sincronizador de reset, IPCLK/PCLK, campos CAL e limites da busca estática.
