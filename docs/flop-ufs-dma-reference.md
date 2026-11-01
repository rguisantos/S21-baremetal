# FlopKernel: novas referências úteis de UFS, DMA e UART

A ampliação da leitura do repositório indicado pelo usuário trouxe três
esclarecimentos aplicáveis ao projeto: unidade dos campos PRDT, contratos
de memória DMA e distinção entre os drivers seriais. A revisão continua
fixada em `4553117a5014928dff55595f46627e0d77bcf133`; nove arquivos
adicionais têm tamanho, SHA-256 e blob Git conferidos no
[manifesto](references/flop-ufs-dma-source-reference.json). Não houve
build ou execução do kernel, seus scripts ou operações no telefone.

## PRDT em bytes e stride dependente de configuração

[`ufs-exynos.c`, exynos_ufs_set_features](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/ufs/ufs-exynos.c#L494)
ativa `UFSHCD_QUIRK_PRDT_BYTE_GRAN`. O
[`ufshcd.h`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/ufs/ufshcd.h#L680)
define essa opção para controladores que expressam PRDTO/PRDTL em bytes.
O [mapeamento SG no driver comum](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/ufs/ufshcd.c#L2252)
codifica quantidade de segmentos×`sg_entry_size` quando a opção está
ligada. A configuração do descritor também usa offsets/comprimento da
resposta sem a divisão por quatro do ramo genérico.

Isso sustenta a interpretação do campo16 para uma entrada de stride16
observada no [LK](lk-ufs-completion-hzc2.md). É coerência de formato
com a referência Exynos, sem medição da configuração física do LK.
Não se deve interpretar automaticamente esse campo como 16 entradas.

Há também uma diferença útil: o stride Linux não é universalmente16.
O driver comum inicia `sg_entry_size` com o tamanho de `ufshcd_sg_entry`,
mas [exynos_ufs_fmp_config](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/ufs/ufs-exynos-fmp.c#L173)
pode trocá-lo por `sizeof(struct fmp_table_setting)`. A opção FMP consta
no unified_defconfig anteriormente conferido. Não se copia esse layout
configurável para o LK, cujo stride16 foi observado nas instruções.

## DMA: alinhamento, endereço e coerência são contratos distintos

[`ufshcd_memory_alloc`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/ufs/ufshcd.c#L3611)
solicita por `dmam_alloc_coherent` as áreas de comandos, transferência e
tarefas. Mantém ponteiros de CPU separados dos endereços DMA, testa
retornos/alinhamento e programa os descritores usando esses endereços
DMA. A escolha de máscara tenta 64 bits quando suportado e recorre a
32 bits conforme o resultado, sem assumir que todo host suporte ambos.

A [documentação DMA da própria árvore](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/Documentation/DMA-API.txt#L27)
distingue o ponteiro virtual retornado do handle destinado ao dispositivo.
Esse contrato não é satisfeito apenas por alinhar um ponteiro de heap.
O [alocador/host LK](lk-ufs-host-memory-hzc2.md) agora tem seus argumentos
e stores delimitados, mantendo tradução, atributos e posse como fronteiras.

No [parse do DT Exynos](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/ufs/ufs-exynos.c#L2207),
ausência de `dma-coherent` faz o driver colocar zero no valor de IOCC.
O caminho de controle usa contextos de syscon/DT e `regmap_update_bits`.
Portanto, a propriedade no DTS e o suporte no código são referências
de configuração, sem provar o valor vivo de IOCC no handoff do bootloader.

## UART: selecionar o arquivo e o contexto corretos

O [Makefile serial](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/tty/serial/Makefile#L33)
liga `CONFIG_SERIAL_SAMSUNG` a `samsung_tty.o` e `CONFIG_SERIAL_EXYNOS`
a `exynos_tty.o`. O unified_defconfig consultado contém o primeiro como
y e o segundo como m, com 16 portas para Exynos. A presença do flag de
console Samsung não comprova por si qual driver ou porta está ativo.
O [Kconfig](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/tty/serial/Kconfig#L297)
também delimita as dependências desse suporte.

Em [exynos_tty.c](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/tty/serial/exynos_tty.c#L2159),
`exynos_usi_init` trata reset conforme `dbg_uart_ch`, limpa reset e
configura a solicitação de clock de recepção por USI_OPTION. Essa fonte
ajuda a conferir o contexto de reset/clock; não demonstra pinmux ativo,
canal físico disponível ou uma rota nova de captura. As fronteiras
anteriores de [console LK](lk-console-handoff.md) continuam válidas.

## Aplicação ao roadmap

As descobertas de PRDT/DMA foram incorporadas à continuação UFS e aos
testes de binding do host. O material serial permanece referência para
uma futura conferência de saída física, sem reproduzir escritas MMIO
do driver. A árvore custom continua distinta das fontes stock/HZC2 e
não resolve sozinha carregamento, memória livre ou captura do diagnóstico.

A [tradução do pool LK](lk-pool-mmu-hzc2.md) agora acrescenta três fontes ARM64 fixadas para bits de descritores e bytes MAIR. O perfil EL1/4KiB gera identidade/cacheável, sem importar o índice Linux de MT_NORMAL ou certificar coerência DMA.

Continuação de31/10/2026: O [cruzamento PHY/IOCC](lk-ufs-iocc-hzc2.md) agora resolve os phandles do DTS exynos2100 fixado: PMU15860000+728 para isolamento e sysreg11020000+700 para IOCC. Somente a tabela alternativa LK com consulta1 coincide com a máscara300000; isso não importa o contrato DMA Linux para o LK.
