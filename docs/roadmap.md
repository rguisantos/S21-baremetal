# Roadmap até o primeiro diagnóstico no S21

Estado em 2026-10-22 (Campo Grande). Alvo: SM-G998B/p3s, firmware stock HZC2 observado nas
propriedades recebidas. O R10 e o diagnóstico ainda não foram executados no
telefone. Os resultados de QEMU não validam SoC, Harx ou LK Samsung.

| Etapa | Estado e resultado | Critério restante |
|---|---|---|
| 1. Entrada do diagnóstico | EL1/EL2; relocação em 64 offsets testada anteriormente; recusas C/M/M+C agora conferidas por tradução real em QEMU | EL3/traps superiores e caches herdadas permanecem fora do escopo dessa matriz |
| 2. Contrato Samsung | Cópias/KASLR, seleção DTB/DTBO/DPM e initrd ligados; DTS corrigido reproduz a base stock; construtor de bancos conferido em 268 cenários fornecidos; percurso memory alimenta uH | Fechar retornos soc_info/SEC_PGTBL e ramos efetivos, sucesso das edições, mapa completo, checks posteriores e estado final de entrada |
| 3. Observação | UART0 e logs rastreados; exynos_el2_log confirmado no aparelho, mas UNREADABLE para uid=2000, sem captura | Continuar investigação estática e estabelecer outro canal verificável; não repetir as coletas bloqueadas |
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

O [exynos_el2_log](harx-log-observation.md), sustentado por fonte/config/DT,
foi testado: o atributo existe, mas a sessão shell não tem permissão de
leitura. A captura não chegou a abrir seu conteúdo. Esse caminho também
está encerrado nas condições atuais, sem repetir leituras ou pedir um log
que não foi capturado. O material recebido basta para a análise estática.

No [SEC_PGTBL/LDFW](sec-pgtbl-hzc2.md), o chamador LK está conferido por
248 cenários Unicorn com respostas substituídas, incluindo 104 injeções
hipotéticas dos 52 status declarados no header Samsung recebido. O enum
não foi ligado ao retorno da consulta ou à carga -0x500. O contêiner tem seis
registros; o DRM candidato está marcado como cifrado e a carga até SMC
-0x500 foi ligada ao LK. Para recuperar esse handler, a lacuna específica
é código DRM HZC2 em claro com origem verificável ou fonte correspondente.
Reenviar o mesmo contêiner cifrado não ajuda. Emulação/simbolismo do provedor
dependem primeiro desse código e da reconstrução de seu estado de entrada.
Outros chamadores e trechos em claro podem continuar sendo analisados.

A [base DTS recebida](dts-source-roundtrip.md) agora reproduz o DTB HZC2
byte a byte após um patch de três listas de CPUs. Esse marco permite usar a
base textual com identidade conferida. O overlay genérico não substitui o
P3S; ambos os candidatos aplicados no host continuam sem bancos RAM e com
initrd antigo. A prioridade seguinte permanece nos ajustes dinâmicos e nos
valores efetivos do LK, sem preencher as lacunas com esses candidatos.

O [construtor dos bancos](lk-memory-bank-constructor.md) passou a ter modelo
e comparação com as instruções originais: 268 cenários fornecidos e 44
testes de host. Aritmética de divisão e blocos altos está conferida; não se
modelou sucesso do editor ou inferiram entradas reais. Próxima lacuna:
origem/valores efetivos de soc_info, total de RAM e SEC_PGTBL, seguidos do
FDT resultante e estado de entrada. Novos cenários sintéticos não substituem
essas evidências.

## Evidências

- [Diagnóstico e matriz de entrada](entry-diagnostic.md).
- [Cópia da Image e salto](lk-kernel-copy.md).
- [Modelo de layout LK v3 e testes de host](lk-v3-layout.md).
- [Seleção e merges DTB/DTBO/DPM](lk-dtb-pipeline.md).
- [DTS recebidos e identidade binária da base stock](dts-source-roundtrip.md).
- [Initrd, reservas e origem do tamanho de RAM](lk-dynamic-fdt.md).
- [Argumentos do construtor de bancos RAM e conferência em Unicorn](lk-memory-bank-constructor.md).
- [Alocação earlymem no uH e soc_info no Harx](el2-earlymem-hzc2.md).
- [Intervalos do FDT enviados ao uH e teste do percurso LK](lk-uh-range-registration.md).
- [Retornos constantes Harx e condição do construtor de RAM](lk-harx-memory-gap.md).
- [Respostas SEC_PGTBL no LK e limite atual do LDFW](sec-pgtbl-hzc2.md).
- [Candidato sysfs do log Harx e evidências da Image stock](harx-log-observation.md).
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
