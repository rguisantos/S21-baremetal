> Registro da integração anterior. As pendências de entrada/FDT, dispatcher
> e acessos GIC receberam correções posteriores; o estado atual está em
> [docs/r10-single-cpu.md](docs/r10-single-cpu.md).

# Integração das PRs #2 e #3 — 2026-10-20

A main recebe o histórico da branch kilo/slim-fjord-u2q (incluindo a PR #3)
e a PR #2. A resolução do conflito UART usa os offsets Samsung da PR #2,
acesso de byte a UTXH/URXH, TXFULL no bit 24 de UFSTAT, CR antes de LF,
limite de polling e buffer hexadecimal de 19 bytes.

A inicialização UART não programa clock, divisor, pinmux ou reset USI
presumidos. Por padrão não acessa MMIO. R10_UART_FIRMWARE_CONFIGURED só pode
ser definido quando um carregador tiver configurado e verificado essa
instância com FIFO habilitado. Isso é um pré-requisito externo, não uma
configuração que este código detecta automaticamente.

## Reprodução

- `make -C r8 BUILD=build-review all`: compila R8A, R8B, R8C, R9 e R10.
- `make -C r8 BUILD=build-review regress`: regressão QEMU R8A/B/C e R9.
- `bash scripts/test_pr_fixes.sh`: UART no host com ASan/UBSan, habilitada e
  desabilitada; primitivas atômicas reais da PR #3 em QEMU AArch64.
- `bash shim/build.sh`: compila o shim experimental.

O runtime do cross-binutils expõe somente suas bibliotecas específicas,
sem substituir a libc do host. O QEMU usa explicitamente seu loader e suas
bibliotecas. Caminhos fixos de outro workspace foram removidos. Há avisos
preexistentes de compilação; não é um build sem warnings.

## Limites da validação

O teste atômico é de uma CPU: verifica operandos, resultados, CAS bem e
malsucedido, test-and-set, ticket lock e exclusão reader/writer. Não prova
contenção entre CPUs nem o bring-up SMP do telefone. O QEMU virt não emula
o Exynos 2100. O shim compila, mas seu boot não foi validado.

Continuam pendentes: contrato de entrada EL2/EL1 e passagem FDT, topologia
MPIDR real, descoberta/configuração do GICR, auditoria do GIC (inclusive
endereços absolutos versus offsets), concorrência dos slots de chamadas
entre CPUs, tratamento de CPUs offline, clock/pinmux/USI e testes físicos.
A UART própria do shim também permanece experimental e não é coberta pelos
testes do driver R10. A integração na main não declara prontidão para
flash/chainload e não executa nenhuma operação no telefone.

## Resultado desta execução

- Build separado dos cinco ELFs: passou.
- Regressão: **4/4 PASS** (R8A, R8B, R8C, R9).
- Testes UART: **2/2 PASS** com AddressSanitizer/UBSan. LeakSanitizer
  desativado por limitação de `/proc` neste ambiente; não há alocações nos testes.
- Teste AArch64: **ATOMIC PASS**, encerrado pelo timeout esperado após park.
- Shim: ELF e binário compilados; execução não testada.

## PR #4 — substituído, não mergeado

Em 2026-10-21 UTC, revisado head 9dca3969cc6e6ff571cbfd1cc440f7b27ac93143. O packer/validador antigo e as afirmações sobre Proton já têm substitutos corrigidos na main. PR encerrado com justificativa, preservando o branch e evitando regressão. Evidências em [branch-packer-review](docs/branch-packer-review.md) e [continuação BL](docs/bootloader-hzc2.md).

## PR #5 — revisão e merge do protocolo EPBL

Revisado o head `636c56a4dc36f029afe966de4404aa8b7659c2d1`: revisão automática
concluída sem achados e sem threads pendentes; conferência do diff, dos
limites dos decodificadores e das evidências de 69 testes/GNU. Revisão registrada
no PR. Merge autorizado pelo usuário e executado em
`2df91f32fba86b6b8cb115146463da13661da4a4`; main local sincronizada.

A orientação permanente inclui concluir revisão, corrigir bloqueadores e
fazer o merge do head revisado, conforme [AGENTS.md](AGENTS.md). Não encerrar
uma entrega concluída apenas com PR aberto. A continuação técnica e a correção
dos nomes dos contadores estão em [proveniência HASH](docs/epbl-hash-provenance-hzc2.md).

## PR #6 — revisão e merge da proveniência HASH

Revisão própria registrada no head `c8f41e03781bf9aca19bf4f9684e5160f9f45bb1`,
com diff, limites das referências, 83 testes e evidência GNU conferidos. Sem
achados bloqueadores ou discussões pendentes no momento do merge. Nenhum
status CI configurado foi reportado. Merge em
`65040a6017280cb8c2bb4fac9808119f1bda0540`, main sincronizada antes da
continuação TZAR. Esta é revisão própria; não declara aprovação automática
externa do PR #6.

## PR #7 — revisão própria e merge do TZAR

Head `afec5aba6e4cf4b56064e226ace7bddc761ac116` conferido por revisão
própria registrada: 15 testes, GNU e os 14 blobs publicados coincidem com
a árvore validada. Sem threads ou status de falha reportados. A revisão
automática ainda informava running e não foi considerada aprovada.
Merge normal do head revisado em
`2f31df480b2e6731db38a002ab26ca4bc270a3d9`, sem contornar regras do GitHub.
Main local sincronizada e limpa. Na retomada desta continuação, a revisão
automática seguia pendente e não havia apontamentos ou threads adicionais.

## PR #8 — ligação ioctl e confirmação da revisão automática

Head `fd78916670c71263cb3e1d46f351c028dcb313cc`, revisão própria registrada,
30 testes e GNU conferidos. Merge normal em
`cd8b5124f19c68a1e040d3564f08d8c9d95044fd`, main sincronizada e limpa.
Na integração, a revisão automática ainda estava pendente. Na retomada
desta continuação, foi confirmada como completed, has_any_findings=false
e has_unresolved_findings=false, para o mesmo head. Sem threads pendentes.
A revisão automática do PR #7 ainda informava running nesta conferência.

## PR #9 — BiEn/TZSW e validação de candidatos

Head `383656d88452c5c5467d3e0064b78ef72d0dad53`, revisão própria e automática
concluídas sem achados ou threads pendentes, com 15 testes e o ensaio AES
negativo conferidos. Merge normal em
`169d704ba19af808c0295b1d4048e20c6899d498`; main local sincronizada e limpa
antes da continuação sobre o produtor de RAM no BL2. O ensaio não aceitou
plaintext HZC2 e a integração não declara o handler SVC recuperado.

## PR #10 — produtor BL2 e folha do total de RAM

Head `84b5692855da602aa922dcff46d35c60cd8b58a3`, revisão própria e automática
concluídas sem achados, sem threads pendentes. Os 15 blobs publicados
coincidem com a árvore validada; 34 testes BL2, 73 regressões LK, GNU e
66 execuções isoladas QEMU conferidos. Merge normal em
`b3f8340c3a1d3d1bd9e0b321c1ae62532697cc14`, main sincronizada/limpa antes
da continuação da consulta de geometria. Binding nominal e valores reais
permanecem pendentes; a integração não declara RAM livre ou FDT final.

## PR #11 — consulta de geometria até MMIO

Head `b210c7ffd10cb6b14163a922a649d9f409d41a14`, revisão própria e automática
concluídas sem achados e sem threads pendentes. Os 12 blobs publicados
coincidem com a árvore validada; 48 testes, GNU e planos simbólicos da CLI
conferidos, sem CI configurado. Merge normal em
`5bccfd4192552f2e25070bb53f1a94939d560e55`, main local sincronizada antes
da continuação sobre a reescrita das bases. Os valores iniciais das tabelas
não foram promovidos a estado físico observado.

## PR #12 — reescrita condicional das bases de consulta

Head `33ae7df49dc9aaa013dc7f9604ca1335da415be1`, revisão própria e automática
concluídas sem achados, sem threads ou falhas CI. Os 14 blobs publicados
coincidem com a árvore validada; 58 testes BL2, GNU e planos condicionais
conferidos. Merge normal em `4d4fd72f4fffb2a184d72d6a493df8e791009154`,
main local sincronizada antes da continuação sobre o registro de geometria.
Não foi presumido valor do nibble ou configuração ativa do S21; o ramo
sem escrita preserva o estado anterior, sem restaurar os bytes do arquivo.
