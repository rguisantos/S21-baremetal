# Roadmap e estado do S21-baremetal

Atualizado em **2026-10-22 (Campo Grande)**. Base técnica revisada:
[main em 95788e9](https://github.com/rguisantos/S21-baremetal/commit/95788e976fc8b0ada7d507ae5a75dd0c45013495).
Alvo: **Galaxy S21 Ultra SM-G998B/p3s, Exynos 2100, stock G998BXXSJHZC2 / Android 15**.

**Estamos entre a validação de laboratório e o primeiro diagnóstico no
telefone.** Há código funcional e testes em QEMU, uma base DTS que reproduz
o DTB stock e modelos conferidos das chamadas do LK. Ainda faltam o caminho
de carregamento físico, as garantias de entrada/memória e uma forma de
recuperar o resultado. Nenhum diagnóstico ou R10 foi executado no S21.

## Estado por frente

“Concluído” vale para o escopo da evidência indicada. Testes de laboratório
não mudam o estado de validação no telefone.

| Frente | Estado atual | Evidência / o que falta |
|---|---|---|
| R8/R9: fundamentos e microkernel | **Concluído no QEMU** | Regressão 4/4 PASS; MMU, ELs, GIC/timer, EL0/SVC/preempção |
| R10 em uma CPU | **Validado no laboratório; pendente no S21** | Main real com carregador EL2 sintético, timer IRQ e cinco recusas; faltam contrato Samsung, memória e acessos reais |
| Diagnóstico mínimo de entrada | **Implementado e testado no QEMU** | Padrão: 12 casos, seis aceitos e seis recusados; 128 entradas relocadas verificadas em etapa anterior |
| Firmware, fontes e DTB base | **Base identificada; análise da cadeia em andamento** | BL e imagens de boot inventariados; três listas DTS corrigidas reproduzem os 389876 bytes da base HZC2 |
| Construção de RAM no LK | **Lógica conferida; valores reais pendentes** | 268 cenários Unicorn e 44 testes de host; entradas fornecidas, sem executar editor FDT ou provedor seguro |
| Cache/MMU e argumentos finais LK | **Helper conferido; cadeia final ainda parcial** | 352 cenários e 14 testes novos; acessos de sistema substituídos, callbacks/SMC anterior e coerência física ainda abertos |
| SEC_PGTBL/LDFW | **Chamador conferido; provedor aberto** | 248 cenários Unicorn e 20 testes de host; 52 status na fonte não comprovam o retorno da consulta; DRM candidato cifrado |
| UART e recuperação de logs | **Rastreio estático avançado; canal físico pendente** | UART0/pinmux/clock nominal/gates documentados; frequência e roteamento efetivos não medidos; coleta shell bloqueada |
| Primeiro diagnóstico físico | **Pendente** | Depende dos critérios de carregamento, região da imagem, entrada e leitura do registro abaixo |
| XNU/Darwin no QEMU | **Kernel prebuilt + init próprio executados** | PID 1/UID 0, APFS, timer e retorno; arquivo com um byte alterado recusado; 13 testes de host; sem iOS gráfico ou hardware Samsung |
| R10 físico, depois SMP/periféricos | **Etapas futuras** | Uma CPU primeiro; PSCI/SMP, SPIs, MCT e display após comprovar a base |

As contagens acima pertencem a suítes diferentes e não devem ser somadas
como uma porcentagem de prontidão. Os testes citados são os registros das
entregas anteriores; esta revisão do roadmap não os reexecutou.

## Dois marcos físicos com requisitos diferentes

**Marco A — recuperar o primeiro registro de entrada.** A
[Image de diagnóstico](entry-diagnostic.md) aceita EL1/EL2 com M=C=0,
registra argumentos, EL, SCTLR, MPIDR e endereços em 128 bytes dentro da
própria imagem. O código dispensa pilha e não lê FDT nem chama serviços ou
acessa periféricos. Para esse marco, é necessário comprovar propriedade e coerência
da imagem inteira e obter um canal de recuperação do registro. O diagnóstico
não descobre RAM livre e não garante persistência após reset.

**Marco B — executar o R10 no telefone em uma CPU.** Exige também FDT
efetivo com bancos/reservas/initrd válidos, região da imagem/pilhas
reservada, entrada compatível e acesso ICC/timer permitido. O R10 atual
exige EL2; a normalização para EL1 observada na entrada do LK não mede
o EL no salto final. Essa decisão depende da evidência de entrada.

O contrato do R10 exige memória e reservas confiáveis suficientes para
validar a região completa da imagem/pilhas e os demais buffers usados.
Essa investigação pode avançar em paralelo ao Marco A, desde que a reserva
da região inteira do diagnóstico seja demonstrada por outro meio verificável.
Recuperar o código DRM em claro também não é requisito universal para o
diagnóstico mínimo; é a lacuna específica da análise do handler seguro.

## Próximas entregas, em ordem de prioridade

| Prioridade | Trabalho concreto | Critério de conclusão |
|---|---|---|
| **P1 — entrada e coerência** | Helper de cache e argumentos conferidos; seguir o SMC -0x3ff anterior e callbacks posteriores, junto às garantias da imagem | Contrato documentado com evidência para cada condição; distinguir comportamento condicional de estado efetivo |
| **P1 — observação, em paralelo** | Fechar um canal para recuperar o registro: UART com configuração/ligação demonstradas ou outro caminho legível e verificável | Recuperar os 128 bytes e identificar imagem/endereço de origem; gravação sem leitura não conclui o marco |
| **P2 — memória dinâmica, em paralelo** | Seguir produtores do total de RAM e soc_info; delimitar SEC_PGTBL/Harx e os ajustes do FDT | Vincular valores à sua origem e obter/verificar bancos e reservas efetivos; mais respostas simuladas não resolvem essa lacuna |
| **P3 — carregamento do diagnóstico** | Definir artefato e percurso compatíveis com a cadeia Samsung, considerando suas verificações e condições reais de recuperação | Formato, destino, extensão reservada, coerência, entrada e canal de leitura conferidos; repetir testes apenas para mudanças concretas |
| **P4 — primeiro diagnóstico no S21** | Executar a Image mínima pelo caminho estabelecido e recuperar o registro | Registro completo com marcador/versão e argumentos, EL/SCTLR/endereço interpretáveis; documentar recusas ou traps observados |
| **P5 — R10 em uma CPU** | Adaptar entrada ao observado; integrar FDT final, exceções, GIC herdado e timer | Boot e IRQs observados no aparelho, respeitando memória/reservas e sem falhas silenciosas |
| **P6 — expansão** | Planejar PSCI/SMP e periféricos, com topologia e dependências reais | Critérios e testes próprios por recurso; não antecipar display/GPU/MCT ao funcionamento da base |

**Próxima entrega técnica recomendada: continuar P1 nos serviços/callbacks
que cercam o helper**, mantendo observação e memória como frentes paralelas.
A [auditoria do helper](lk-cache-handoff.md) fechou a seleção do EL ativo,
o gate por M e os operandos set/way nesse escopo. Não executou caches/MMU
reais ou os callbacks: repetir a mesma matriz não fecharia essas lacunas.

## Frente XNU/Darwin em laboratório

Os dois projetos [HackiOS examinados por commit](hackios-xnu-reference.md)
oferecem uma base XNU ARM genérica, carregador Mach-O/boot_args, APFS e
adaptações de userland iOS 16.5. Seu alvo físico é redwood/Snapdragon; não
há port p3s entregue. Após a revisão estática, foi
[reproduzido o boot XNU com programa próprio no QEMU](xnu-qemu-lab.md).
O kernel e loader usados são prebuilt verificados; build XNU a partir dos
fontes, serviços iOS e execução física continuam pendentes.

| Etapa | Estado / dependência |
|---|---|
| X0 — referência e diferenças | Concluída: 7 hashes prebuilt conferidos; gerador reconhece CPUs, mas deixa GIC TODO no nosso DTB 2+1 células |
| X1 — XNU + programa mínimo no QEMU | Concluído com prebuilt externo: caso positivo, controle negativo e 13 testes de host; build dos fontes segue como validação separada |
| X2 — contrato Samsung → XNU | Especificação e fixtures futuras; exige boot_args/árvore Apple próprios, separados do ABI FDT do R10 |
| X3 — XNU físico em uma CPU | Depende de carregamento, memória, entrada e observação demonstrados nos marcos físicos acima |
| X4 — APFS/userland/interface | Primeiro no laboratório; no telefone, framebuffer/CPU antes de GPU e periféricos |

Essa frente não conclui P1–P6 ou os Marcos A/B. GICR, timer virtual/físico,
USB/UEFI Qualcomm e Mali exigem adaptações próprias. Não é necessário
reenviar firmware para continuar a análise; a revisão contém fontes,
limites e critérios de aceitação dessa frente.

O usuário aprovou investigar a futura escolha Android/XNU no telefone.
A [estratégia](dual-boot-strategy.md) separa o laboratório já executado,
diagnóstico físico, adaptação XNU, userland/interface e seleção de boot.
O próximo trabalho XNU é especificar e testar o adaptador de argumentos e
memória; isso pode avançar no host em paralelo a P1/P2 sem inventar bancos
ou reservas do S21.

## Critérios para iniciar o Marco A

1. **Carregamento:** percurso Samsung identificado, artefato compatível e
   condições de recuperação definidas. Compilar ELF ou S21R10 não demonstra
   esse percurso; o shim legado permanece em quarentena.
2. **Região e coerência:** toda a Image, inclusive o registro, pertence ao
   diagnóstico e não colide com dados/firmware necessários. O carregador
   fornece código coerente e as condições de tradução/cache são conhecidas.
3. **Entrada:** caminho avaliado para as condições aceitas ou para uma recusa
   observável. A Image não instala vetores para traps de firmware superior.
4. **Resultado:** meio demonstrado de ler o registro no estado em que ele
   existe; não presumir que sobreviva a reset ou perda de energia.

Esses critérios ainda estão abertos. O teste QEMU não estabelece um comando
de flash/chainload Samsung.

## Arquivos e evidências

**Os arquivos já enviados bastam para continuar a investigação estática.**
BL HZC2, boot/vendor_boot/dtbo, fontes Samsung/deltas, DTS e referência Proton
já foram recebidos e analisados no escopo documentado. Os READMEs de build
não fornecem o estado de entrada ou o FDT dinâmico.

O que falta é evidência específica: estado de entrada no aparelho, resultado
dos ajustes FDT e um canal de observação. Para continuar a análise interna do
handler DRM cifrado, falta código HZC2 em claro com origem verificável ou
fonte correspondente. Isso não é pedido de reenvio do LDFW cifrado.

As coletas atuais usaram **uid=2000(shell)/Shizuku**. FDT, mapas e logs
solicitados não ficaram disponíveis; `exynos_el2_log` foi confirmado como
**UNREADABLE**, sem conteúdo capturado. Não repetir as mesmas coletas,
pedir um log inexistente ou pressupor root. Uma nova coleta deve primeiro
demonstrar uma mudança relevante de acesso/canal.

## Evidências que sustentam este estado

| Área | Referências |
|---|---|
| Laboratório e implementação | [Validação anterior](validation-2026-10-20.md), [R10 em uma CPU](r10-single-cpu.md), [carregador EL2 QEMU](qemu-el2-loader.md), [diagnóstico](entry-diagnostic.md) |
| Firmware e base textual | [Stock HZC2](stock-firmware-hzc2.md), [BL e handoff](bootloader-hzc2.md), [entrada LK](sboot-layout-hzc2.md), [cache e argumentos finais](lk-cache-handoff.md), [recompilação DTS](dts-source-roundtrip.md) |
| Cópias e FDT | [Cópia da Image](lk-kernel-copy.md), [layout v3](lk-v3-layout.md), [seleção/overlays](lk-dtb-pipeline.md), [ajustes dinâmicos](lk-dynamic-fdt.md) |
| RAM e serviços | [Construtor dos bancos](lk-memory-bank-constructor.md), [uH earlymem](el2-earlymem-hzc2.md), [intervalos enviados ao uH](lk-uh-range-registration.md), [recorte Harx](lk-harx-memory-gap.md), [SEC_PGTBL/LDFW](sec-pgtbl-hzc2.md) |
| Observação | [Console](lk-console-handoff.md), [roteamento](uart-routing.md), [pinmux BL2](bl2-uart-hzc2.md), [clocks](uart-clock-stages.md), [gates](uart-gates.md), [log em memória](lk-memory-log.md) |
| Limites de acesso atuais | [Coleta Shizuku](runtime-collection.md), [logs de boot](boot-log-collection.md), [log Harx bloqueado](harx-log-observation.md) |

A main foi conferida na preparação deste roadmap; a consulta retornou
**zero PRs abertos**. O [worklog](../worklog.md) conserva a sequência histórica
das descobertas; esta página organiza prioridades e critérios atuais.
