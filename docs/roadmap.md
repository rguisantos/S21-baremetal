# Roadmap e estado do S21-baremetal

Atualizado em **2026-10-24 (Campo Grande)**. Base técnica revisada:
[main após revisão/merge do PR #17, be47018](https://github.com/rguisantos/S21-baremetal/commit/be47018c54773836d493f21e761a12bd8faef237).
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
| Construção de RAM no LK / produtor BL2 | **Aritmética conferida; geometria real pendente** | [BL2](bl2-ram-size-hzc2.md): escrita em 0x02038848 e folha original em 66 execuções QEMU. [Registro anterior](bl2-geometry-record-hzc2.md): duas recargas de 0x02073600, marcador/cópias/restaurações condicionais; 70 testes e GNU 148 palavras. Consulta MMIO e reescrita de bases delimitadas; bytes, bindings e respostas reais abertos. Construtor LK: 268 cenários anteriores, sem FDT final |
| Cache/MMU e argumentos finais LK | **Helper conferido; cadeia final ainda parcial** | Helper: 352 cenários anteriores; [chamadas finais](lk-final-edges.md): 1834 instruções conferidas e 29 testes de host. Bindings mutáveis, SMC anterior e estado físico ainda abertos |
| Preparação do monitor e lista LK | **Buffers e offsets corroborados; provedor aberto** | [Fontes HASH](epbl-hash-provenance-hzc2.md): dez offsets ACE/Fireplace e dialecto DMA concordam; nomes dos contadores corrigidos, 83 testes. Modo 0x19 não implementado no emulador Exynos9830; dados/algoritmo HZC2, vetores e transformação abertos. Inventário anterior: 1095 instruções/114 alvos/177 acessos MMIO |
| SEC_PGTBL/LDFW | **Chamador conferido; provedor aberto** | 248 cenários Unicorn e 20 testes de host; 52 status na fonte não comprovam o retorno da consulta; DRM candidato cifrado |
| UART e recuperação de logs | **Rastreio estático avançado; canal físico pendente** | UART0/pinmux/clock nominal/gates documentados; frequência e roteamento efetivos não medidos; coleta shell bloqueada |
| Primeiro diagnóstico físico | **Pendente** | Depende dos critérios de carregamento, região da imagem, entrada e leitura do registro abaixo |
| XNU/Darwin no QEMU | **Init próprio e referência iOS gráfica executados** | SpringBoard, Ajustes e Geral conferidos em PNG nativo 1125×2436; quatro CPUs, kernel prebuilt e imagens APFS identificados; sem hardware Samsung |
| Contrato/adaptador XNU | **X2 parcial; recursos e memória UEFI conferidos no QEMU** | Loader recompilado, payload/janela reservados, quatro mapas completos; 22 critérios positivos, oito recusas, 22 testes de memória/evidência e 16 de recursos; falta contrato físico Samsung |
| Display ramfb QEMU | **Contrato e reserva executados com XNU** | 25 critérios gráficos, 22 sem display, três recusas e 62 testes de host; interface local reproduzida no ensaio de referência separado |
| Disco residente e userland no consumidor EFI | **Perfil gráfico executado no QEMU** | [iOS com perfil explícito](xnu-guarded-userland.md): uma CPU, 7 GiB, 1,66 GiB de folga, mapas/boot_args capturados e Ajustes/Geral/Sobre por toque; sem Samsung |
| Preparação do userland HackiOS | **Imagens construídas e checkpoint restaurado** | Três DMGs com CRC/SHA-256, 407 plists 0644, 19 arquivos prebuilt conferidos; patch exato e fonte ramfb corrigida; [ensaio gráfico](hackios-userland-qemu.md) |
| R10 físico, depois SMP/periféricos | **Etapas futuras** | Uma CPU primeiro; PSCI/SMP, SPIs, MCT e display após comprovar a base |

As contagens acima pertencem a suítes diferentes e não devem ser somadas
como uma porcentagem de prontidão. A etapa anterior do perfil iOS concluiu
interface, retorno nativo de 900 s e conferência dos quatro mapas, com três
recusas QEMU, 74 testes de host e quatro controles semânticos. A análise
anterior delimitou 13 saídas pendentes e dois produtores VBAR. Nesta entrega,
o protocolo EPBL liga buffers e configurações em 1095 instruções/114 alvos,
com 177 acessos MMIO conferidos e 33 testes novos/36 regressões. A entrada
DMA é candidata; seus dados, a transformação e os vetores seguem abertos.
O dispatcher parcial/pedido in-place e as etapas BL2 anteriores mantêm suas
contagens próprias. A entrada vetorial e o conteúdo runtime das tabelas seguem abertos.
Esses ensaios EPBL não executaram firmware. A continuação de memória
executou somente a folha BL2 de 44 instruções no QEMU, em 66 casos
sintéticos; não executou inicialização Samsung nem alterou o estado físico.
O kernel XNU continua prebuilt.

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

A [branch pública rebased-11](xfwdrev-kernel-reference.md), fixada em
756951a, fornece outra referência de drivers/config p3s e uma candidata
para instrumentação Linux. Três compilações DTS e duas aplicações de
overlay passaram no host, sem bancos RAM; o driver UART é idêntico ao já
recebido. Kexec e /dev/mem estão desativados na configuração consultada.
Antes de usar essa alternativa para observar o FDT recebido e as reservas,
é necessário validar o build e um caminho físico de instalação/leitura.
Isso ainda não resolve EL2, o registro de entrada ou o canal de recuperação.

| Prioridade | Trabalho concreto | Critério de conclusão |
|---|---|---|
| **P1 — entrada e coerência** | Dez offsets e dialecto DMA corroborados em fontes, com diferenças de versão preservadas; obter implementação HZC2 de `0x19`, conteúdo verificável da entrada `[0x1fc00,0x1fffc)` ou saída real de 48 bytes; depois transformação/vetores. Campos herdados de -0xe6 e escritores indiretos abertos | Implementação correspondente ou observação verificável; referências ACE/Exynos9830 e dados de outro SoC não substituem o contrato HZC2 |
| **P1 — observação, em paralelo** | Fechar um canal para recuperar o registro: UART com configuração/ligação demonstradas ou outro caminho legível e verificável | Recuperar os 128 bytes e identificar imagem/endereço de origem; gravação sem leitura não conclui o marco |
| **P2 — memória dinâmica, em paralelo** | Recargas de 0x02073600 identificadas; seguir quem produz seu primeiro u64 e os gates que o preservam/substituem. Manter demais slots, escritores/bindings, soc_info/SEC_PGTBL/Harx e ajustes FDT abertos | Comprovar bindings e valores efetivos, eventual limite LK e bancos/reservas finais; a fórmula testada não fornece esses dados |
| **P3 — carregamento do diagnóstico** | Definir artefato e percurso compatíveis com a cadeia Samsung, considerando suas verificações e condições reais de recuperação | Formato, destino, extensão reservada, coerência, entrada e canal de leitura conferidos; repetir testes apenas para mudanças concretas |
| **P4 — primeiro diagnóstico no S21** | Executar a Image mínima pelo caminho estabelecido e recuperar o registro | Registro completo com marcador/versão e argumentos, EL/SCTLR/endereço interpretáveis; documentar recusas ou traps observados |
| **P5 — R10 em uma CPU** | Adaptar entrada ao observado; integrar FDT final, exceções, GIC herdado e timer | Boot e IRQs observados no aparelho, respeitando memória/reservas e sem falhas silenciosas |
| **P6 — expansão** | Planejar PSCI/SMP e periféricos, com topologia e dependências reais | Critérios e testes próprios por recurso; não antecipar display/GPU/MCT ao funcionamento da base |

**Próxima entrega técnica na frente de memória: seguir os produtores da
primeira palavra do registro em `0x02073600` e seus gates de preservação.**
O [consumidor Linux](bl2-kernel-consumers-hzc2.md) lê essa palavra como
`dram_type`, imprime `DEVFREQ : dram:` e compara uma constante também
presente no BL2 HZC2. Buscar observação correspondente em logs já
disponíveis, preservando a distinção entre a fonte pública e o binário
em execução. CHIPID corrobora o gate das bases como `main_rev == 1`, sem
medir esse valor; bootstat oferece outra pista de parâmetros de tempo.
O [callback NEWTIME](boot-metadata-hzc2.md) foi resolvido nominalmente,
com store u64 por ponteiro atualizado a partir de 0x15900108. O destino
seria 0x02073600 sob a cadeia preservada se o registrador fosse 0x38e00;
o [produtor ACPM](acpm-handshake-hzc2.md) publica exatamente 0x38e00 em
local 0xa5900108 e espera zero. Seu inicializador e um consumidor Thumb da
assinatura DRAM foram ligados nominalmente; DTS nomeia IPC/SRAM AP.
GNU conferiu 100 palavras AArch64 e 141 instruções Thumb. Alias de hardware,
amostra recebida e preservação seguem condicionais. A
[tabela ECT/NEWTIME](newtime-ect-hzc2.md) agora está ligada ao lookup:
57 descritores, 22 seletores especiais incluindo 0xcafe, parser original
e prefixo até o primeiro store em 56 casos QEMU. O argumento/frame e as
16 células selecionadas foram conferidos sob bindings de laboratório;
80 testes de host e GNU de 353 palavras passaram. Próximo: alocador, gates e
escritas posteriores, além de corroborar aliases/bindings físicos.
Os argumentos bootstat no LK também
foram ligados: BL1 recebe literal 100; nomes não comprovam durações.
O [rastreio anterior à consulta](bl2-geometry-record-hzc2.md) identifica
recargas de 64 bits para o primeiro slot, com nibble 4–7 copiado a um byte
de estado. O literal intermediário `0xcafe` e a chamada nominal da função
com a segunda recarga foram delimitados, mantendo os callbacks abertos.

As cópias fixas podem transportar a palavra para `0x021ab600` e depois
`0x9004a600`; isso não mapeia bytes do arquivo nem observa uma execução.
Uma limpeza condicional pede 44 bytes zero e outra restauração transfere
seis campos de 32 bits, todos fora da primeira palavra. Foram 70 testes e
GNU de 148 palavras/dez destinos/nove ponteiros ou literais. O registro e
os três slots restantes continuam sem valores reais.

A [consulta](bl2-geometry-query-hzc2.md) e a [reescrita das bases](bl2-query-base-rewrite-hzc2.md)
conservam suas condições e hipóteses. Os planos iniciais não presumem uma
configuração ativa. As 66 execuções QEMU anteriores validaram somente a
folha de aritmética, sem medir geometria ou capacidade do S21.

A prioridade física continua fechar entrada/coerência e um canal de leitura
para o diagnóstico mínimo. As duas frentes podem avançar com evidências
independentes. O total BL2 também pode sofrer limite no cache LK e não
substitui as respostas soc_info/SEC_PGTBL/Harx ou o resultado do editor FDT.

Na preparação EPBL, a [comparação de fontes HASH](epbl-hash-provenance-hzc2.md)
corrobora dez offsets e o layout DMA, mas o modo `0x19`, os dados reais e a
transformação continuam abertos. O [rastreio de buffers](epbl-protocol-hzc2.md)
e o [grafo](epbl-frontier-hzc2.md) delimitam as fronteiras; repetir respostas
MMIO simuladas não demonstra sua resolução no HZC2.

O [TZAR](tzar-crypto-hzc2.md) e a [ligação ioctl](teegris-ioctl-boundary-hzc2.md)
levam ao wrapper X7=15/SVC #0. A [etapa BiEn/TZSW](tzsw-bien-hzc2.md)
recusou a hipótese Exynos9830 em duas implementações AES, sem plaintext
aceito. Esta rota depende de código em claro correspondente; não repetir a
hipótese recusada nem transformar esse bloqueio em requisito universal do
diagnóstico. Os READMEs de build anexos não fornecem o consumidor SVC.

## Frente XNU/Darwin em laboratório

Os dois projetos [HackiOS examinados por commit](hackios-xnu-reference.md)
oferecem uma base XNU ARM genérica, carregador Mach-O/boot_args, APFS e
adaptações de userland iOS 16.5. Seu alvo físico é redwood/Snapdragon; não
há port p3s entregue. Após a revisão estática, foi
[reproduzido o boot XNU com programa próprio no QEMU](xnu-qemu-lab.md).
O baseline usou kernel e loader prebuilt verificados. A variante atual
recompila o loader e valida suas reservas UEFI; a referência iOS gráfica foi executada separadamente com as imagens APFS
preparadas. Build XNU a partir dos fontes e execução física continuam pendentes.

| Etapa | Estado / dependência |
|---|---|
| X0 — referência e diferenças | Concluída: 7 hashes prebuilt conferidos; gerador reconhece CPUs, mas deixa GIC TODO no nosso DTB 2+1 células |
| X1 — XNU + programa mínimo no QEMU | Concluído com prebuilt externo: caso positivo, controle negativo e 13 testes de host; build dos fontes segue como validação separada |
| X2 — contrato Samsung → XNU | Parcial: codec/projeção, consumidor EFI e reservas UEFI executados no QEMU; plano de memória e entrada Samsung verificáveis continuam pendentes, separados do ABI FDT do R10 |
| X3 — XNU físico em uma CPU | Depende de carregamento, memória, entrada e observação demonstrados nos marcos físicos acima |
| X4 — APFS/userland/interface | SpringBoard e navegação em Ajustes reproduzidos no QEMU pelo ABI upstream; checkpoint com restauração conferida. Userland completo das imagens preparadas executado no consumidor validado com perfil explícito, uma CPU e capturas de interação. Próximo: repetição fria automatizada e avanço dos contratos físicos P1/P2 |

Essa frente não conclui P1–P6 ou os Marcos A/B. GICR, timer virtual/físico,
USB/UEFI Qualcomm e Mali exigem adaptações próprias. Não é necessário
reenviar firmware para continuar a análise; a revisão contém fontes,
limites e critérios de aceitação dessa frente.

O usuário aprovou investigar a futura escolha Android/XNU no telefone.
A [estratégia](dual-boot-strategy.md) separa o laboratório já executado,
diagnóstico físico, adaptação XNU, userland/interface e seleção de boot.
O [contrato binário](xnu-boot-contract.md) foi conferido com os buffers do
laboratório, e o [adaptador de recursos](xnu-fdt-adapter.md) já preserva
GIC/CPUs/PSCI/timer do FDT. A [variante EFI](xnu-efi-adapter-lab.md) já
consome o fragmento no QEMU. A [validação de memória UEFI](xnu-uefi-memory.md)
agora exige reservas exatas do payload/janela e cruza os buffers com quatro
mapas completos. A RAM sintética do FDT não é mais a declaração usada para
essa conferência. Recursos periféricos ainda usam o perfil QEMU fixado.
P1/P2 seguem abertos; a base HZC2 não gerou plano físico.

As falhas de preparação trazidas no relato GLM foram
[reproduzidas com entradas sintéticas](hackios-userland-host.md). Os
checkpoints gráficos agora constam como execução concluída no relato do GLM,
com loader modificado; PNGs/log bruto ainda não recebidos aqui. O
[defeito ramfb do prebuilt foi reproduzido localmente](xnu-ramfb-audit.md),
com correção na fonte e seis controles. O [contrato/reserva do framebuffer já foi conferido com o kernel](xnu-video-contract.md).
A interface local e a interação já foram reproduzidas com as imagens identificadas,
inclusive no consumidor EFI validado. Isso não altera o estado de XNU físico,
display Exynos ou escolha de boot; a prioridade atual é P1/P2.

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

Os PRs #5 a #8 foram revisados e mergeados; esta continuação parte da
main `cd8b512` e segue o fluxo de revisão/merge do projeto. O [worklog](../worklog.md) conserva a sequência histórica
das descobertas; esta página organiza prioridades e critérios atuais.
