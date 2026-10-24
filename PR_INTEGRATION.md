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
