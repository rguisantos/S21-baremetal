# HZC2: estágios do sboot e entrada de LK

Revisão de 2026-10-21 (America/Campo_Grande). Complementa [bootloader-hzc2.md](bootloader-hzc2.md) e verifica as notas externas BL2/cadeia de boot e o relatório “Reverse Engineering Complete”. Análise estática do arquivo recebido, sem execução no telefone.

**Conclusão principal:** o detector reproduz os intervalos propostos, e o código em 0xec000 inicia LK chamando uma rotina que preserva EL1 ou programa retorno para **EL1h**. Isso não sustenta “kernel em EL2 confirmado”. A análise do salto/FDT já registrada pertence a LK, não ao intervalo BL2. A identificação TF-A v1.5 em partes da imagem não transforma todo sboot em um único BL2 TF-A.

## 1. Fontes fixadas e alcance

- [halal-beef/sboot-split-detector, commit 0c0acea](https://github.com/halal-beef/sboot-split-detector/tree/0c0aceaae0872c86f5140404affcaf2b557cd451): README e detect-splits.py lidos; detector executado no HZC2. O próprio projeto declara que os splits podem ser imprecisos.
- [Creeeeger/CVE-2024-56426, commit 3d6d94a](https://github.com/Creeeeger/CVE-2024-56426/tree/3d6d94a210669b50833b23289460f5577d329229): split.py consultado como referência de **Exynos 9830/990**. Usa tabela fixa de regiões, importada de soc_data; não é um detector genérico de Exynos 2100. Nenhum exploit, patch de segurança ou reassinatura executado.
- [TF-A upstream, bl2_main.c](https://github.com/ARM-software/arm-trusted-firmware/blob/master/bl2/bl2_main.c): referência arquitetural, não fonte correspondente ao fork Samsung. [Firmware design v2.14.0](https://trustedfirmware-a.readthedocs.io/en/v2.14.0/design/firmware-design.html) distingue firmware não seguro de seu próximo consumidor; o EL selecionado para BL33 não demonstra o EL em que LK entregará um kernel depois.
- sboot HZC2: **4.194.304 bytes**, SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`. Integridade do pacote de origem registrada na análise anterior.

## 2. Limites reproduzidos e validação independente

O primeiro u32 little-endian contém 24 blocos de 512 bytes: BL1 termina em 0x3000. O primeiro u32 em 0x3000 contém 152 blocos: EPBL tem 0x13000 bytes e termina em 0x16000. São observações no HZC2, não prova de cabeçalhos estáveis em todas as gerações.

| Rótulo candidato | Início | Fim exclusivo | Tamanho | SHA-256 do intervalo |
|---|---:|---:|---:|---|
| fwbl1 | 0x0 | 0x3000 | 12288 | `257e8973ff16c3577db0db11f7dbbd710b57565aadd32cde8f2e716ac538e802` |
| epbl | 0x3000 | 0x16000 | 77824 | `f76967e5ad1bad5d4ecf578e6092bb46965da17a5990e3ac1c0ecd927de8a09b` |
| bl2 | 0x16000 | 0xec000 | 876544 | `77b137fcda67d50dd91f91b408061264f22868f2f45576e458af70c65ec6c94b` |
| lk | 0xec000 | 0x36c000 | 2621440 | `aae70a745fa40b6abb985b19f93e87154742c782df5ec838b5eaf5bce405b595` |
| el3_mon | 0x36c000 | 0x3ac000 | 262144 | `956fad12611837ed13c3edacd60e54fb161c52664e72ee018db9894a679e0880` |
| tail_unclassified | 0x3ac000 | 0x400000 | 344064 | `28010f4380400ed3f5cc28e9c74d7a1bf888d963341dd13a8e17c4b40819faad` |

BL2 ocupa **856 KiB**, não 872 KiB. O intervalo de 0x6c000 citado para o 990 tem 432 KiB. Tamanho maior não identifica sozinho quais funções ou políticas foram adicionadas.

O prefixo de 12 bytes `130000000400000000000000` ocorre em **0x26e0, 0x15df0, 0xebdf0 e 0x3abdf0**. O detector usa o prefixo do EPBL em 0x15df0, soma 0x210 e alinha os próximos finais para 0xec000 e 0x3ac000. Esses são finais calculados; não são os offsets brutos do prefixo. Seus três u32 são 19, 4 e 0; esta análise não os rebatiza como “tamanho + tipo” nem valida sua semântica criptográfica.

**O limite LK/monitor não veio de um footer igual.** O detector identifica a string Samsung LK Boot e usa `LK_SIZE = 0x280000`, dando 0xec000 + 0x280000 = 0x36c000. Nesse final não há o mesmo prefixo em end-0x210. A entrada AArch64 em 0xec000, a string em 0x23c438 e o cabeçalho/entrada de monitor em 0x36c000 fornecem corroboração independente, mas não substituem parser completo das assinaturas. A cauda 0x3ac000–0x400000 foi contabilizada e não descartada.

O EPBL contém strings de auto-descriptografia (0x3a95 e 0x3ab5) e código de entrada parcialmente legível. Não foi demonstrado que todo seu conteúdo esteja pronto para desassemblagem direta. Encontrar operandos de cópia em um estágio não determina todos os bancos, reservas e ajustes posteriores de RAM.

## 3. Evidência de EL1 na entrada de LK

A primeira instrução no intervalo LK é `BL` em **0xec000**, palavra **0x940036d3**, que chama **0xf9b4c** (LK+0xdb4c). O retorno normal segue para instalação da pilha, limpeza da BSS e chamada em 0xec028.

| Offset no sboot | Instrução/ação observada |
|---|---|
| 0xf9b4c | `mrs x4, CurrentEL` |
| 0xf9b50–0xf9b58 | se CurrentEL=4, retorna imediatamente: já está em EL1 |
| 0xf9b5c–0xf9b60 | testa CurrentEL=8 e seleciona o caminho EL2 |
| 0xf9b74–0xf9b7c | caminho superior: ELR_EL3 aponta à continuação; SPSR_EL3 recebe 0x3c5 |
| 0xf9b84–0xf9b90 | caminho EL2: ELR_EL2 aponta à continuação; SPSR_EL2 recebe 0x3c5 |
| 0xf9ba0 | configura HCR_EL2 no caminho de descida |
| 0xf9bb0 | configura SP_EL1 |
| 0xf9bb8 | `eret` |
| 0xf9bbc | `ret` para a entrada LK |

Os dois produtores de 0x3c5 têm palavra **0xd28078a4**; o ERET tem palavra **0xd69f03e0**. O campo de modo é 5 (**EL1h**) e DAIF está mascarado. Portanto, a intenção demonstrável dessa rotina é executar a continuação de LK em EL1. A rotina não programa EL2h (modo 9).

**Limite:** não foi executada a cadeia Samsung inteira, nem provado o comportamento de todos os serviços de firmware posteriores. Não transformar isso em “EL1 medido na entrada do kernel”. Mas a afirmação de EL2 confirmado pelo resumo é contrariada pelo caminho encontrado e não pode orientar o payload.

O R10 atual exige EL2 e sua recusa de EL1 permanece deliberada. Antes de adaptá-lo, é necessário projetar uma entrada EL1 que não tente escrever HCR_EL2/CNTHCTL_EL2 e observar as permissões herdadas para ICC/timer. Nenhuma mudança funcional no R10 foi feita por esta análise.

## 4. Endereços de link e limites da inferência

LK contém literais em 0xec030/0xec038 com **0xe8388000** (pilha/início da BSS) e em 0xec040 com **0xe8c1ca28** (fim da BSS no laço). São compatíveis com LK ligado em **0xe8000000**: o global relativo 0x474000 usado na análise anterior passaria a 0xe8388000, e o ponteiro do FDT em 0x4740f8 passaria a 0xe83880f8.

Há ainda constantes **0xe8000000** nos offsets BL2 0x1651c e 0x36234, passadas em x3 a wrappers SMC. Essa concordância reforça a hipótese de base de LK no HZC2, sem demonstrar o carregamento físico efetivo ou a semântica desses serviços.

As rotinas de cópia BL2 em 0x161d8, 0x16228, 0x16250 e 0x16278 usam diversos literais, incluindo 0x0203d000, 0x02175000 e 0x90000000. Não se identificou um único “endereço BL2” que autorize transplantar a tabela do 990. O rótulo DRAM para 0x15600000 na nota externa exige mapa do SoC e rastreamento próprios; um endereço de execução não prova quem inicializou DDR ou em qual momento.

Em especial, nenhum endereço de link/cópia de bootloader equivale a mapa de **RAM livre após o handoff**. Isso depende dos nós dinâmicos, reservas, segurança, firmware residente e estado da execução já descritos em bootloader-hzc2.md.

## 5. Correções do relatório do branch kilo

Branch consultado em **f624360f7bd5abdd2b2300321acf5cd16c798592**. Desde 9dca396, há somente os commits documentais f6556bb e f624360, alterando README.md e EXYNOS2100_HARDWARE.md. Não houve correção do packer ou implementação de teste SMP nesses commits.

| Alegação | Conferência |
|---|---|
| sboot = BL2 + TF-A / BL2 diretamente ao kernel | Contêiner com múltiplos estágios; salto/FDT analisados ficam em LK |
| EL2 confirmado | Entrada LK programa/preserva EL1; EL final do kernel não foi observado |
| 0x80080000 fixo confirmado | É base nominal somada a deslocamento de até 0x1f8000 no caminho rastreado; ver análise anterior |
| PSCI HVC e SMC, testar ambos | Base declara SMC; [editor posterior pode escrever hvc](lk-psci-final-edit-hzc2.md), com mensagem observada. Isso não comprova serviço PSCI nem autoriza testar ambos |
| UART 565 diferente de 533 | SPI 533 corresponde a INTID 565; é conversão de numeração, não divergência |
| MCT “SPI 975–986” extraído de /proc/interrupts | Sem arquivo bruto rastreável nesse branch, não foi verificada a coluna usada; IRQ Linux, hwirq/INTID e número SPI não são intercambiáveis |
| configure_dtb em 0x216900 | A string está em **0x216a80** |
| JUMP2K em 0x216a30 | Está em **0x2169c0**; em 0x216a30 há ddi_id |
| bootargs_init em 0x216a40 | Há correspondências em 0x216514 e **0x216a48** |
| set_bootargs em 0x216a50 | Há correspondências em **0x216a70** e 0x23cfac |
| Chamadas externas 0x1001cxxxx/TEE | A instrução em 0x1efcd0 é BL relativo para **0x1c4820**, dentro de LK; o valor alto é compatível com erro de extensão de sinal no desassemblador |
| Packer/validador funcionando | Implementações antigas continuam iguais às do PR #4 encerrado; defeitos reproduzidos em branch-packer-review.md |
| run_r10 com -smp 4 testa SMP | O alvo apenas imprime aviso; não inicia QEMU |
| fastboot boot shim.elf é próximo teste | Não há caminho Samsung demonstrado para esse ELF; shim permanece em quarentena na main |
| DECON 0x19f00000 confirmado | Alegação ainda sem evidência primária conferida nesta revisão; não incorporada como base do driver |

O commit f6556bb declara coleta live, mas a árvore versionada desse head não inclui `coleta/` ou os dumps citados. Isso não prova que a coleta não ocorreu; impede verificar aqui sua origem, colunas e conteúdo. A coleta sem root anteriormente recebida continua registrada em runtime-collection.md. Nenhum dado novo foi atribuído ao aparelho apenas por estar no resumo.

Para BL com branches relativos, o deslocamento imm26 é **com sinal**, multiplicado por quatro. A palavra 0x97ff52d4 em 0x1efcd0 resulta em 0x1c4820. Não é necessário supor uma chamada a secure world para explicar essa instrução.

## 6. Reprodução e resultado

Criado [inspect_sboot_hzc2.py](../scripts/inspect_sboot_hzc2.py), Python standard library, somente leitura. Aceita exclusivamente o tamanho e SHA-256 do sboot recebido. Emite JSON com regiões candidatas/hashes, limites de cabeçalho, ocorrências de prefixos, strings, palavras de instrução, branch com extensão de sinal e valores de SPSR. Não extrai imagens, não valida assinaturas nem executa firmware.

```bash
python3 scripts/inspect_sboot_hzc2.py /caminho/sboot.bin > hzc2-report.json
```

Validação: imagem HZC2 aceita; arquivo de quatro bytes, arquivo alterado mantendo tamanho e arquivo com byte extra recusados com saída JSON vazia; SHA do original preservado. O BL positivo da entrada e o BL negativo de 0x1efcd0 foram comparados com a desassemblagem Capstone 5.0.7. O detector externo foi executado somente após leitura do código, com a imagem original e sem extração.

A verificação não altera os resultados anteriores R8/R9/QEMU, não foi uma nova regressão do kernel e não prova SMP ou hardware. O próximo passo útil é conferir o caminho completo LK→kernel e preparar diagnóstico com entrada EL1/EL2 observável; não ampliar para SMP/DECON antes de resolver esse contrato.

Atualização de 2026-10-23: a [auditoria das sete cópias fixas BL2](descriptor-provenance-hzc2.md) registra origem, destino, extensão e passos dos corpos selecionados. Seus destinos não intersectam a janela do descritor -0xe6; isso não é mapa de RAM livre ou validação da sequência física.
