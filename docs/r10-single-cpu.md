# R10: primeiro estágio em uma CPU — 2026-10-20

## Alterações

- Dispatcher R10 separado de `common/exc.c`. SYNC/FIQ/SError e IRQs inesperadas registram ELR/ESR/FAR e param. Nenhuma instrução é pulada. A UART pode estar indisponível; `r10_last_fault` também pode ser inspecionado por debugger.
- Entrada primária independente de Aff0. Exige EL2 com MMU/D-cache de EL2 e EL1 desligados antes de escrever BSS/pilha. O ponteiro FDT é preservado em x19, restaurado em x0 no ERET e armazenado em `g_fdt` pelo C.
- O C faz somente sanidade inicial do cabeçalho FDT. Ainda não extrai RAM, regiões reservadas, GIC ou topologia dele.
- Entrada de secundárias distinta da entrada que zera BSS. O caminho SMP permanece dormente e não validado.
- GIC usa endereços absolutos, reconhece PIDR2 e procura o redistributor por afinidade completa em GICR_TYPER, com Last, limites e VLPIS ou stride explícito.
- O Distributor é somente lido. Não há escrita em GICD_CTLR, configuração em massa de SPIs, inferência de CPUs pelo TYPER nem alteração de segurança. O driver exige Group 1/roteamento herdados e que a PPI já pertença ao grupo não seguro.
- Somente interrupções privadas são suportadas neste estágio. Prioridades usam byte. WAKER/RWP têm timeout. EOImode=0 é solicitado e conferido; configuração incompatível é rejeitada.
- Timer usa CNTFRQ real, arma apenas após habilitar a PPI e não faz EOI. O dispatcher rearma o timer e faz um único EOI. INTIDs especiais não recebem EOI. IRQs são liberadas somente após a configuração.
- A main não chama MMU, MCT, SMP, CPU_ON ou sondagens PSCI. Os módulos experimentais permanecem no código para trabalho posterior, sem serem ativados pela sequência inicial.

## Reprodução e cobertura

```
make -C r8 BUILD=build-r10-fix all
make -C r8 BUILD=build-r10-fix regress
bash scripts/test_pr_fixes.sh
bash scripts/test_r10_stage.sh
```

O último script executa o código real do GIC em um modelo MMIO com ASan/UBSan (sem LeakSanitizer), o dispatcher real em testes de política e uma integração AArch64 no QEMU. O carregador sintético do teste usa um marcador como argumento x0, fornece a configuração GIC do QEMU e substitui a função C principal. São usados a entrada assembly, os vetores, GIC, timer e dispatcher de produção. Isso verifica a transferência do argumento FDT, não o parsing de um DTB real nem a main de hardware.

Assinaturas esperadas:

```
GIC MODEL PASS
EXCEPTION MODEL PASS
R10 BOOT PASS: FDT, BSS, EL1
R10 TIMER PASS: five IRQs through production dispatcher
R10 FATAL kind=0x0 ...
```

O último fault é intencional e deve terminar em park/timeout, sem imprimir `R10 FAULT FAIL`. O modelo também cobre região curta/overflow, afinidade não linear, frame VLPIS, ausência de redistributor, recusa de SPI, prioridade sem sobrescrever bytes vizinhos, RWP/WAKER presos e EOImode incompatível.

## Pendências para hardware

O teste não emula o Exynos. Ainda faltam validar carregamento Samsung/Harx, posição e reserva da imagem e pilhas na RAM, entrada EL real, limpeza da imagem até PoC e coerência de I-cache, DTB ativo e regiões GIC, acesso ao timer físico, atribuição de PPI ao mundo não seguro e clock/pinmux/USI. A main mantém MMU desligada para não reprogramar traduções/caches sem esse contrato. A UART continua opt-in para uma instância previamente configurada e verificada pelo carregador. MCT, SPI/roteamento e SMP ficam para etapas próprias.

A compilação tem warnings preexistentes nos módulos experimentais e nos segmentos RWX didáticos. Nenhuma operação no telefone foi feita.

Referência recebida: [samsung-reference.md](samsung-reference.md).

## Resultado observado nesta entrega

- Os cinco ELFs compilam; shim também compila.
- Regressão R8A/R8B/R8C/R9: **4/4 PASS**.
- UART: **2/2 PASS**; primitivas AArch64: **ATOMIC PASS**.
- GIC e exceções no host: **GIC MODEL PASS**, **EXCEPTION MODEL PASS**.
- Integração QEMU: **R10 BOOT PASS**, **R10 TIMER PASS**, seguido do fault fatal esperado (EC=0). Nenhum retorno após a instrução inválida.

O contrato ainda depende de firmware que permita acesso ICC em EL1 via ICC_SRE_EL2/EL3; não é presumido suporte a trap/hypervisor proprietário. HCR_EL2 deixa IRQ/FIQ/SError direcionados a EL1 neste estágio.
