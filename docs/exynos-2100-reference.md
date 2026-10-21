# Referência Exynos-2100/universal2100: o que aproveitar

Inspeção de 2026-10-21 do repositório indicado pelo usuário:
[Exynos-2100/android_kernel_samsung_universal2100](https://github.com/Exynos-2100/android_kernel_samsung_universal2100).
Branch padrão consultado: **lineage-22.2**, commit fixado
**37c14d86996a49edbea8953f2523b202546b8958**. O Makefile declara Linux **5.4.290**.
O projeto declara suporte a o1s/t2s/p3s/r9s e é um fork. Não confundir com as
organizações `exynos2100`, `exy2100` ou `exynos-republic`, que têm nomes parecidos.
Não foi clonado o histórico completo nem compilado o kernel.

A referência recebida do usuário contém 5.4.242; o patchlevel maior desse
branch não comprova equivalência ao firmware HZC2 de 2026. O branch foi
consultado por SHA, evitando mudanças futuras nas evidências abaixo.

## Resultado da comparação

Foram lidos **18 arquivos selecionados**, comparados byte a byte e por SHA-256
com o Kernel.tar.gz recebido (hash c5ad9994…86bf2). **13 são idênticos; cinco
diferem.** Isso é comparação de um recorte, não auditoria de toda a árvore.
O [manifesto](references/exynos-2100-37c14d8.json) contém caminhos e hashes dos
dois lados. Fontes baixadas e o pacote completo permanecem fora do Git.

| Área | Comparação | Aproveitamento no S21-baremetal |
|---|---|---|
| UART/USI: exynos_tty.c + serial_s3c.h | Idênticos | Referência pública para reset USI, clock request, fração do baud e polling; sem correção nova em relação ao pacote recebido |
| Pinctrl: pinctrl-exynos-arm64.c | Idêntico | Banco GPIO, offsets e larguras de campos para confrontar o estado UART0 |
| Clock: clk-exynos2100.c, binding e cinco arquivos CAL | Idênticos | Rastrear IDs do DTS até mux/divisor/QCH e campos de registrador |
| MCT: exynos_mct.c | Idêntico | Protocolo de update/ack; continua fora da sequência inicial R10 |
| Debug-snapshot | Idêntico | Corrobora a análise dos logs; não altera as permissões observadas no Android |
| GICv3 | Duas diferenças localizadas | Correções de virtualização/retorno de power management; não exigidas pelo fluxo R10 atual |
| DTS base e overlay p3s r22 | Diferentes | Cruzar configuração e revisões; não substituir as imagens stock ou o FDT dinâmico |
| Makefile e defconfig p3s | Diferentes | Contexto de build e recursos; não são prova de boot do payload |

## Prioridade imediata: UART0 e clocks

Os caminhos abaixo são relativos à raiz do kernel fixado. A UART0 em
`arch/arm64/boot/dts/exynos/exynos2100.dts` conserva as propriedades já
observadas: 0x10540000, debug 115200/8, USI v2 e pads gpg0-2/gpg0-3.

### IDs do clock resolvidos

No binding `include/dt-bindings/clock/exynos2100.h`:

- CLK_PERIC0_BASE = 1750;
- GATE_PERIC0_TOP0_QCH_UART_DBG = base+4 = **1754 / 0x6da**;
- UART_DBG = base+32 = **1782 / 0x6f6**.

São os dois IDs usados pela UART0 no DTS. `clk-exynos2100.c` liga o primeiro
a PERIC0_TOP0_QCH_UART_DBG, pai UMUX_CLKCMU_PERIC0_BUS, alias console-pclk0;
o segundo a DIV_CLK_PERIC0_UART_DBG. Isso fecha a ligação nominal que antes
estava apenas nos IDs numéricos. Não estabelece a frequência efetiva.

`cmucal-node.c` liga o divisor ao mux MUX_CLK_PERIC0_UART_DBG. Os pais
listados são OSCCLK_PERIC0, MUX_CLKCMU_PERIC0_IP0_USER,
MUX_CLKCMU_PERIC0_IP1_USER e OSCCLK_PERIC0. `cmucal-sfr.c` define:

| Elemento | Endereço derivado da fonte | Campos identificados |
|---|---|---|
| CMU_PERIC0 | 0x10400000, tamanho 0x8000 | Bloco de registradores |
| Mux UART_DBG | 0x10401000 | seleção bits 1:0, busy bit 16, automatic gating bit 28 |
| Divisor UART_DBG | 0x10401800 | ratio bits 3:0, busy bit 16, automatic gating bit 28 |
| Gate IP clock UART_DBG | 0x104020b8 | CG_VAL bit 21, MANUAL bit 20, automatic gating bit 28 |
| QCH UART_DBG | 0x10403014 | enable bit 0, clock request bit 1; outros campos na fonte |

Esses endereços resultam de base+offset nas tabelas CAL; não foram lidos no
aparelho. Não representam uma sequência validada de habilitação. Faltam estado
herdado, dependências do domínio, permissões e protocolo completo dos helpers.
26 MHz de fin_pll não deve ser usado como se fosse sempre o clock da UART.

Fontes principais:
[clock CCF](https://github.com/Exynos-2100/android_kernel_samsung_universal2100/blob/37c14d86996a49edbea8953f2523b202546b8958/drivers/clk/samsung/clk-exynos2100.c),
[CAL nodes](https://github.com/Exynos-2100/android_kernel_samsung_universal2100/blob/37c14d86996a49edbea8953f2523b202546b8958/drivers/soc/samsung/cal-if/exynos2100/cmucal-node.c),
[CAL SFR](https://github.com/Exynos-2100/android_kernel_samsung_universal2100/blob/37c14d86996a49edbea8953f2523b202546b8958/drivers/soc/samsung/cal-if/exynos2100/cmucal-sfr.c).

### Pinctrl: informação útil e uma divergência a resolver

O controller GPIO_PERIC0 tem base **0x10430000**. O driver lista `gpg0` com
seis pinos e offset **0x120**. O tipo do banco usa CON/DAT/PUD/DRV em
+0/+4/+8/+0xc, com larguras 4/1/4/4 bits por pino. Assim, pela fonte:

- GPG0_CON: **0x10430120**;
- GPG0_PUD: **0x10430128**;
- os campos CON dos pinos 2/3 ocupam bits 11:8 e 15:12; o DTS pede função 3.

Isso ajuda a projetar uma inspeção e uma configuração mínima futura. Não
define a direção TX/RX individual, tensão ou test point da placa.

**Divergência:** a rotina LK em 0xef3e0, já analisada, manipula
**0x10430080**, com o valor 0x33000000 inserido na parte alta do word.
Esse não é o GPG0_CON derivado acima. Não se demonstrou que a escrita do LK
configure os mesmos pads do DTS, nem que a revisão/mapa usados sejam iguais.
A discrepância impede transformar as duas sequências em um único driver
sem rastrear melhor o roteamento e a revisão. Ambas as fontes são registradas;
não se escolhe um endereço por conveniência.

## Overlay p3s e DTS base

O repositório possui oito overlays em `arch/arm64/boot/dts/samsung/p3s`.
Foi lido o **r22**, não presumido como a revisão deste aparelho. Em __fixups__,
serial_0 aponta para fragment@88 e serial_1 para fragment@89; ambos recebem
status okay. O mesmo trecho aparece no r22 do pacote recebido. Isso reafirma
que disabled no DTS base não determina o estado após overlay, conforme já
observado na análise das imagens stock.

Após normalizar apenas a representação textual de listas string `\0` para
listas separadas por vírgula, o diff do DTS base se reduz a **dois valores
freq_mif de cenários MFC UHD**, 0x22e980 → 0x177bb8. Essa comparação textual
não é prova de DTBs compilados idênticos. UART/GIC/timer não receberam ali
uma alteração que resolva o bring-up.

O overlay r22 tem outras diferenças, incluindo dados de display/touch e
endereços kallsyms da build. Não portar endereços kallsyms, retirar reservas
ou trocar o overlay stock por esse arquivo para fazer o payload caber.

## Diferenças no GIC: guardar para o momento correto

O diff de `drivers/irqchip/irq-gic-v3.c` mostra somente:

1. read-back após gravar GICD_ISACTIVER, para ordenar ativação antes de uma
   desativação dirigida por guest;
2. reinicialização da CPU interface também em CPU_PM_ENTER_FAILED, além de
   CPU_PM_EXIT.

O R10 atual não implementa VGIC/guest ou esse ciclo de power management.
Essas mudanças não corrigem um problema confirmado na sua sequência atual.
A afinidade de redistributor e os registradores ICC corretos já estão na main.
Guardar o diff como referência, sem enxertar dependências Linux no bare-metal.

## O que integrar agora e depois

**Agora:** referência fixada por SHA, hashes e ligações UART0↔clock↔pinctrl
na documentação. Isso já foi integrado, sem copiar outro kernel ao projeto.

**Próximo trabalho de driver:** seguir os helpers CAL e o estado de pinmux do
LK para resolver a divergência, depois desenhar uma sequência mínima com
polling/timeout e clock conhecido. Validar primeiro em modelo/testes; o QEMU
virt não emula esses registradores Exynos. Manter o backend UART opt-in até
haver contrato verificável no hardware.

**Depois da base:** MCT, PSCI/power domains e display/USB podem usar esse
repositório como índice de arquivos. Não foram auditados integralmente aqui;
a presença de um driver não equivale a um port bare-metal pronto.
Ao adaptar código, preservar os avisos de autoria e licença dos arquivos.

O repositório não fornece, por si só, um dump live de RAM, medição do EL final,
permissões Harx ou canal de log funcional. As coletas Shizuku continuam com os
limites documentados; nenhum novo arquivo foi solicitado ao usuário.

## Auditoria do pinmux — continuação 2026-10-21

A discrepância foi conferida até o núcleo do driver recebido. O macro
`EXYNOS9_PIN_BANK_EINTG` em `pinctrl-exynos.h` atribui diretamente o argumento
`reg` a `pctl_offset`. `pinctrl-samsung.c` copia esse campo para o banco e
calcula o acesso como `pctl_base + pctl_offset + reg_offset[FUNC]`.
`pctl_base` vem do recurso MMIO do controller. Não há nessa cadeia uma
conversão que transforme offset 0x120 em 0x80.

| Caminho | Registro CON | Campos selecionados | Máscara/valor de função |
|---|---|---|---|
| Fonte Exynos 2100 + DTS UART0 | 0x10430120 | pinos 2 e 3, quatro bits cada | limpar 0x0000ff00, inserir 0x00003300 |
| Rotina LK em 0xef3e0 | 0x10430080 | campos 6 e 7 de um word CON | preservar 0x00ffffff, inserir 0x33000000 |

A segunda linha descreve o efeito aritmético do word, não demonstra pinos
implementados. No mapa Exynos 2100 consultado, offset 0x80 é **gpp4, com
quatro pinos**; campos 6/7 não correspondem aos pinos desse banco listados na
fonte. O banco gpg0 de seis pinos, offset 0x120, fica fora dos condicionais
EVT0 que alteram outros controladores neste arquivo. Não foi encontrada aí
uma seleção de build que explique a troca de banco.

A mesma árvore contém `exynos9820_pin_banks5`: gpg0 tem **oito pinos em
0x80**. Isso torna plausível uma sequência de pinmux herdada de outro mapa,
mas é apenas uma inferência por semelhança. Não se conclui que o sboot HZC2
inteiro seja para outro SoC, que a rotina não execute ou que mudar seu endereço
seja suficiente para inicializar o console. Ela pode depender de configuração
anterior; o efeito real sobre os pads não foi medido.

Foi localizado também o word little-endian **0x10430120 em offset 0x30565c**
do sboot. Esse achado vem de busca de bytes, sem provar que represente um
registrador usado. O consumidor e a semântica da estrutura não foram
identificados. Portanto sua presença não resolve a divergência nem é tratada
como uma segunda sequência funcional de UART.

O inspetor HZC2 agora inclui `uart_pinmux_audit`, com as palavras da rotina,
máscara/valor e ocorrências do word. A busca de candidatos MOVZ/MOVK de 0x1043
foi limitada ao intervalo LK 0xec000–0x20c630; ela não exclui construção de
endereços por tabelas, aliases ou chamadas indiretas em outros locais.

**Decisão de implementação:** conservar o mapa fonte e a sequência LK como
evidências distintas. Nenhuma escrita pinctrl nova foi introduzida no R10.
Para uma inicialização própria, serão necessários mapa/revisão e roteamento
confirmados, além dos clocks. O backend herdado só deve ser habilitado quando
o estado UART correspondente for verificável. Prosseguir no contrato de
carregamento continua útil sem repetir as coletas Shizuku bloqueadas.
