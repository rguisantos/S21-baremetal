# Exynos 2100 / SM-G998B: estado confirmado

Atualizado em 2026-10-22 UTC. Alvo: Galaxy S21 Ultra `p3s`, firmware informado pelo usuário como original e igual ao instalado, `G998BXXSJHZC2`, Android 15. A string do kernel nas imagens recebidas confirma HZC2 e Linux 5.4.242. Não houve execução do payload nem flash no aparelho.

## Recursos extraídos do firmware

| Recurso | Evidência |
|---|---|
| Kernel | `boot.img` contém Image AArch64; 5.4.242-30958140-abG998BXXSJHZC2 |
| FDT base | `vendor_boot.img`, offset 0xb77040, 389.876 bytes, versão 17 |
| Overlays | 8 em `dtbo.img`; aplicação individual validada |
| CPUs | MPIDRs 0x000, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700 |
| GICD | 0x10200000 / 0x10000 |
| GICR | 0x10240000 / 0x200000; sem stride explícito |
| Timer | físico NS, PPI 14 = INTID 30; DT anuncia 26 MHz |
| PSCI | `smc` no DTB; não selecionar HVC por strings soltas do firmware |
| UART1 | 0x10840000 / 0x100; Exynos USI v2; FIFO 256 |
| IRQ UART1 | SPI 533 = INTID 565 |
| UART status | disabled no base; okay nos oito resultados com overlay |
| RAM | nenhum nó memory no base ou nos oito resultados com overlay |

Tamanho da região GICR dividido pelo número de CPUs não prova stride. Descobrir frames por GICR_TYPER/Last e afinidade completa, considerando VLPIS ou stride declarado. Todos os MPIDRs têm Aff0=0: o código SMP antigo que usa Aff0 como índice permanece inválido para essa topologia e não é chamado.

`okay` na UART não comprova clock, pinmux, USI ou permissão de acesso no handoff. Os valores dos cabeçalhos de boot também não provam PC, EL ou RAM livre. Há reservas acima de 4 GiB; não deduzir memória livre pelo total de RAM ou por um endereço aparente.

## Implementação atual

O R10 exige uma entrada EL2 controlada, mantém MMU desligada, verifica o FDT e o intervalo completo da imagem/pilhas, herda o Distributor e habilita somente a PPI do timer em uma CPU. Usa ICC_IAR1/EOIR1/PMR/IGRPEN1 e frame SGI correto; não reinicializa SPIs nem segurança global. Falhas param no dispatcher específico, sem pular instruções. UART é opt-in; MCT, MMU experimental, SPI e SMP ficam fora da main.

Essa verificação acontece após BSS/pilha iniciais. O carregador deve reservar e tornar coerente a imagem inteira antes da entrada, fornecer um FDT legível e garantir acesso aos registradores usados. O parser não transforma um carregamento não verificado em seguro. Os DTBs stock sem RAM são aceitos para inspeção, mas recusados como autorização para prosseguir no boot.

## Evidências e pendências

- [Firmware stock e hashes](docs/stock-firmware-hzc2.md)
- [Fonte Samsung e protocolo dos drivers](docs/samsung-reference.md)
- [FDT e limites do contrato](docs/fdt-resources.md)
- [Validação de entrada, GIC e timer](docs/r10-single-cpu.md)
- [Comparação com DTB TWRP](docs/twrp-reference.md)
- [Coleta Shizuku já realizada](docs/runtime-collection.md)
- [Log Harx e resultado no aparelho](docs/harx-log-observation.md): atributo confirmado com modo 0644; UNREADABLE para o shell, sem captura. Não repetir a coleta nas mesmas condições.

Continuam pendentes: DTB final/contrato de memória, carregador Samsung/Harx, EL de entrada, manutenção de caches/coerência da imagem, acesso ICC/timer e depuração física/USI. O shim apenas compila; não há método demonstrado de `fastboot boot` para esse Samsung.

As antigas notas de desmontagem e tentativas estão no [arquivo histórico](docs/archive/exynos2100-notes-legacy.md), com hipóteses superadas explicitamente identificadas. Os resultados desta página e das evidências acima prevalecem sobre esse arquivo.

## Entrada LK e limites do resumo externo

A análise do sboot HZC2 identifica LK em 0xec000–0x36c000 como região candidata corroborada por código. Sua primeira chamada leva a uma rotina que preserva EL1 ou prepara SPSR=0x3c5 e ERET para EL1h. Isso contraria o resumo “EL2 confirmado”; o EL no salto final não foi medido. O endereço 0x80080000 é base nominal acrescida de deslocamento, não garantia de RAM livre. Detalhes e ferramenta reproduzível em [sboot-layout-hzc2.md](docs/sboot-layout-hzc2.md).
