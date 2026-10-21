# Guia da documentação

A entrada do projeto é o [README principal](../README.md). Este índice separa implementação, evidências e histórico. Os documentos descrevem testes de software; nenhum registra execução R10 no telefone.

## Implementação e testes atuais

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
