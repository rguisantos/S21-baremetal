# Roadmap até o primeiro diagnóstico no S21

Estado em 2026-10-21. Alvo: SM-G998B/p3s, firmware stock HZC2 observado nas
propriedades recebidas. O R10 e o diagnóstico ainda não foram executados no
telefone. Os resultados de QEMU não validam SoC, Harx ou LK Samsung.

| Etapa | Estado e resultado | Critério restante |
|---|---|---|
| 1. Entrada do diagnóstico | EL1/EL2; relocação em 64 offsets testada anteriormente; recusas C/M/M|C agora conferidas por tradução real em QEMU | EL3/traps superiores e caches herdadas permanecem fora do escopo dessa matriz |
| 2. Contrato Samsung | Cópias e KASLR ligados; seleção DTB/DTBO/DPM rastreada; initrd de chosen ligado às cópias, escritores de reservas e getter de RAM localizados | Fechar retornos de serviços/ramos, mapa efetivo, checks posteriores e estado final de entrada |
| 3. Observação | UART0 debug identificada nas fontes; callbacks UART/log em memória rastreados | Acesso físico ou recuperação verificável de um registro no aparelho |
| 4. Carregamento | Image diagnóstica e S21R10 são formatos separados; shim em quarentena | Caminho compatível com o estado real do bootloader, artefato revisado e recuperação definida |
| 5. Primeiro diagnóstico físico | Pendente | Executar e recuperar EL, argumentos, endereço e SCTLR |
| 6. R10 uma CPU | Componentes e main real testados em QEMU | Adaptar ao observado e comprovar FDT/memória/exceções/GIC/timer no S21 |
| 7. Expansão | Pendente | PSCI/SMP e periféricos após validação da base |

## Próxima prioridade

A matriz de entrada EL1/EL2 já aceita M=C=0 e recusa as três combinações
restantes, antes de gravar o registro. O trabalho seguinte deve priorizar
**contrato Samsung e observação**, para que novos testes respondam a riscos
concretos do carregamento. Ampliar QEMU não resolve sozinho o canal de leitura.

As fontes e o BL recebidos bastam para continuar a análise estática. Qualquer
pedido novo de arquivo deve apontar uma lacuna específica. As coletas rish
já concluídas não disponibilizaram FDT, seleção UART/ADC ou logs de boot;
não repetir esses procedimentos nas mesmas condições. Não se pressupõe root.

## Evidências

- [Diagnóstico e matriz de entrada](entry-diagnostic.md).
- [Cópia da Image e salto](lk-kernel-copy.md).
- [Modelo de layout LK v3 e testes de host](lk-v3-layout.md).
- [Seleção e merges DTB/DTBO/DPM](lk-dtb-pipeline.md).
- [Initrd, reservas e origem do tamanho de RAM](lk-dynamic-fdt.md).
- [Console e UART0](lk-console-handoff.md), [jig/MUIC](uart-routing.md).
- [Log em memória](lk-memory-log.md).
- [Resultados de coleta](runtime-collection.md), [logs indisponíveis](boot-log-collection.md).

A passagem ao teste físico depende do caminho de carregamento e da capacidade
de recuperar uma evidência. Nenhum comando de flash é derivado dos testes atuais.

A [comparação Exynos-2100](exynos-2100-reference.md) detalha mux/divisor/QCH da UART0. Prioridade de observação: resolver o pinmux do DTS versus a escrita LK antes de adaptar a inicialização UART.

Auditoria posterior: os offsets pinctrl são diretos e a divergência LK/DTS
persiste. A semelhança com um layout Exynos 9820 é hipótese de código legado,
sem validação física. Não habilitar um novo caminho UART pela simples troca
de endereço; retomar também as verificações do contrato Samsung.

A busca ampliada encontrou [pinmux UART0 compatível no intervalo BL2](bl2-uart-hzc2.md), anterior à escrita divergente do LK. O marco de análise avançou; falta acompanhar clocks/estado entre estágios e observar o handoff real.

O [rastreio de clocks UART0](uart-clock-stages.md) ligou tabelas PERIC0 à inicialização e encontrou nominal133,25 MHz no wrapper principal. A observação da frequência e das dependências no handoff continua pendente.

A auditoria offline da árvore UART0 liga o mux TOP a PLL_SHARED2_D2 e fecha nominalmente 133,25 MHz. Próximas lacunas: programação/estado efetivo da PLL e QCH/gates no handoff; a conta nominal não libera a UART.

O [inventário de gates](uart-gates.md) separa reset-sync/IPCLK/PCLK/QCH e mostra que PCLK usa BUS_USER. A auditoria verifica essas associações nas fontes; rastrear o caminho BUS e acessos indiretos permanece necessário antes de propor uma inicialização mínima.
