# DRAM observada no bugreport HZC2

O ZIP fornecido pelo usuário tem **35232190 bytes**, SHA-256
`d7d494cc5ceca1d8315afe415097e04fc94cf6802d6165678f96cd9ee6346c34`.
Foi analisado localmente, sem comandos no telefone. O ZIP, os textos brutos,
cmdline completa, identificadores e dados de aplicativos não foram adicionados
ao repositório. O [extrato público](references/bugreport-dram-20261024.json)
contém somente campos técnicos permitidos, seções, números de linha e hashes.

**A nova evidência é um log persistido do bootloader com Samsung/D1Z e 12.000000GB,
acompanhado de `0001000850500130`.** Esse valor não é igual à comparação
`0001000860000110` do driver de referência. O firmware HZC2 conhece ambas
as assinaturas; a observada é o segundo caso especial do empacotador e o
seletor da linha 15 da NEWTIME. Não é um valor inventado para o laboratório.

## Fonte e contexto das observações

O membro principal é `dumpstate-2026-10-24-21-01-59.txt`. As linhas indicadas
abaixo são localizadores para reprodução privada, não links a dados brutos.

| Contexto | Campo técnico extraído |
|---|---|
| Cabeçalho, linha 13 | Kernel 5.4.242-30958140-abG998BXXSJHZC2 |
| Cabeçalho, linha 14 | dram_info=01,08,00,12G; argumento log_buf_len=256K |
| Propriedades, linhas 391389/391515 | Android 15 / SM-G998B |
| LAST KMSG, linha 415311 | 0001000850500130 |
| LAST KMSG, linhas 415331/416226 | Build G998BXXSJHZC2 |
| LAST KMSG, linhas 415717–415719 | Samsung; D1Z; 12.000000GB |
| PRINT RECOVERY LOG, cinco ocorrências | Kernel ...abG998BXXSJHZA6, separado da identidade atual |

`LAST KMSG` vem de `/proc/last_kmsg`: é conteúdo persistido do log do
bootloader coletado no aparelho, não uma leitura ao vivo de SRAM. A identidade
HZC2 aparece no cabeçalho atual e nesse log, mas isso não data cada mensagem
persistida ou demonstra um snapshot simultâneo após LK/kernel. As ocorrências
HZA6 do bloco de recuperação não foram usadas como identidade do boot atual.
A coleta `bugreportz` por `rish`/Shizuku foi informada pelo usuário; este
trabalho não a executou nem copiou o ZIP para `/sdcard/Download`.

## Por que duas palavras diferentes podem identificar D1Z

O [empacotamento anterior](bl2-geometry-packing-hzc2.md) já distinguia três
casos. A análise agora segue os rótulos no próprio LK do sboot fixado:

| Caminho estático | Campo usado |
|---|---|
| 0x11b7f0 | Lê u32 de AP0x02073604 e depois de AP0x02073600, junta u64 e grava cache relativo 0xaa7ea0 |
| 0x11b860 | Extrai cache[15:8]; 1 seleciona string Samsung |
| 0x11b8d8 | Junta bytes cache[39:32] e cache[47:40]; 0x0008 seleciona string D1Z |
| 0x147d7c–0x147da0 | Chama os dois getters e os formatos Manufacturer/Process ver |
| BL2 0x1e864 → 0x1fe54 | Outro caminho imprime o primeiro slot 0x31978 em duas conversões hexadecimais de oito dígitos, alto32 e baixo32 |

Isso liga estaticamente a origem do cache LK ao **mesmo endereço nominal**
lido pelo driver público. O hexadecimal do BL2 vem do estado e a publicação
desse estado pelo NEWTIME é [condicional](bl2-geometry-publication-hzc2.md).
Essa ligação não transforma a linha de log numa leitura direta do endereço,
nem prova que todos os consumidores tenham visto a mesma amostra.

| Campo | Referência A: 0001000860000110 | Observada B: 0001000850500130 |
|---|---|---|
| Fabricante, bits 8–15 | 01 → Samsung | 01 → Samsung |
| Par de processo, bits 32–47 | 0008 → D1Z | 0008 → D1Z |
| Modo, bits 4–7 | 1 | 3 |
| Primeiro índice de densidade | 6 | 5 |
| Segundo índice de densidade | Não usado pela folha nesse modo | 5 |
| Igualdade exata com a constante do driver | Verdadeira | Falsa |

A regra reproduzida no host está fixada no head do PR #23, sem depender de
memória ou de uma leitura atual do telefone:

| Campo/regra | Fonte exata no repositório |
|---|---|
| Fabricante: `(value >> 8) & 0xff` | [inspect_dram_logging_hzc2.py, linha 39](https://github.com/rguisantos/S21-baremetal/blob/16191d1dee3f51eadbdd2bc85584535ae0150279/scripts/inspect_dram_logging_hzc2.py#L39) |
| Processo: `((value >> 32) & 0xff) \| (((value >> 40) & 0xff) << 8)` | [linha 40](https://github.com/rguisantos/S21-baremetal/blob/16191d1dee3f51eadbdd2bc85584535ae0150279/scripts/inspect_dram_logging_hzc2.py#L40) |
| Fabricante 1 seleciona Samsung | [linha 44](https://github.com/rguisantos/S21-baremetal/blob/16191d1dee3f51eadbdd2bc85584535ae0150279/scripts/inspect_dram_logging_hzc2.py#L44) |
| Processo 8 seleciona D1Z | [linha 45](https://github.com/rguisantos/S21-baremetal/blob/16191d1dee3f51eadbdd2bc85584535ae0150279/scripts/inspect_dram_logging_hzc2.py#L45) |

A origem dessa regra é o código LK no sboot de SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Conferência GNU: `ubfx` em 0x11b868 extrai fabricante; comparação/branch
em 0x11b87c/0x11b880 selecionam o retorno 0x22b5a0, string Samsung.
Os `ubfx` em 0x11b8ec/0x11b8f0 e `orr` em 0x11b8f4 montam o par de
processo; comparação/branch em 0x11b8f8/0x11b8fc selecionam o retorno
0x22b600, string D1Z. Os bytes das strings são conferidos pelo leitor
fixado por hash e os helpers originais pelo [ensaio QEMU](references/dram-labels-qemu-hzc2.json).
O getter de processo faz duas cargas do cache; a fórmula acima representa
uma palavra estável e não estabelece atomicidade em execução física.

Os outros três slots de geometria não foram observados no bugreport. Não
foram preenchidos com cópias da palavra B para declarar um total medido.
O tamanho **12.000000GB é uma observação separada do log**. O formato LK
usa 0x11b6f0: total em cache ou u64 de AP0x02038848, deslocado 20 bits e
escalado por 1/1024 antes da impressão. Truncamento, cache e formatação
impedem tratá-lo como amostra exata do u64 publicado ou mapa de RAM livre.

## Driver e ausência da linha DEVFREQ

Foi revisado o restante do driver de referência após a leitura parcial,
incluindo a função de probe, seus erros e a inicialização da tabela. O
arquivo inteiro tem **2702 linhas**, SHA-256
`1133eb69f70fed266d34a8dd1718ba5b879119057ca4eb6fc293341fe0b2f7f6`,
na revisão pública `756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0`.
Todas as ocorrências de DRAM estão registradas na
[análise estática](references/dram-logging-hzc2.json).

Em `exynos_init_freq_table`, o caminho MIF lê o mesmo par alto/baixo de
AP0x02073600, imprime o u64 e testa **igualdade exata com A** antes de
desabilitar três OPPs. Isso é uma condição específica de política de
frequência; não classifica universalmente todas as palavras D1Z. B não passa
nessa igualdade. Não foi comprovado que o binário stock 5.4.242 contém a
mesma implementação do fork consultado, nem que deva aplicar a mesma política.

No bloco `KERNEL LOG` coletado há **17730 linhas**, **2029531 bytes de
texto UTF-8 decodificado**, **2352 linhas contendo NPU** e zero ocorrências
de `DEVFREQ : dram:`. O argumento `log_buf_len=256K` está presente, mas
não mede sozinho o tamanho efetivo do buffer; o texto coletado também não
mede essa capacidade. Diferença de implementação/configuração e perda de
mensagens continuam possibilidades, sem causa estabelecida pela ausência.

**A ausência de DEVFREQ continua pendente.** Ler integralmente o driver
de referência demonstra o caminho que esse código pode executar; não
demonstra o que o kernel stock do aparelho imprimiu.

## Validação e próximo trabalho

[GNU 2.44](references/dram-logging-gnu-hzc2.json) conferiu **229 palavras,
36 alvos relativos e 17 operandos**; o leitor fixado por hash também
conferiu cinco strings e o literal 1/1024.
[QEMU](references/dram-labels-qemu-hzc2.json): seis casos, A/B/C em duas
colocações, executam os helpers originais de preenchimento do cache,
fabricante e processo. Todos retornam Samsung/D1Z, com código, dados,
guardas e ABI/SP conferidos. Endereços AP são traduzidos para RAM QEMU por
MMU sintética; não são leituras físicas do aparelho. Os printfs completos
não executam nesse ensaio.

O extrator tem testes com identificadores-canário, conteúdo de aplicativos,
cmdline e recuperação para impedir exportação acidental ou associação de
histórico à seção errada. O ZIP exato é exigido por tamanho/SHA antes de
emitir o relatório. [Validação](references/dram-observed-validation.json).

```bash
python3 scripts/inspect_bugreport_dram.py /caminho/zip-privado
python3 scripts/inspect_dram_logging_hzc2.py /caminho/sboot.bin /caminho/exynos-devfreq.c --gnu
python3 scripts/emulate_lk_dram_labels_qemu.py /caminho/sboot.bin /caminho/exynos-devfreq.c
python3 -m unittest discover -s scripts -p 'test_bugreport_dram.py' -v
```

Próximo: seguir preservação/recargas do registro e os campos ainda não
observados. Não foram medidos diretamente AP0x02073600, AP0x02038848,
resposta SMC, UART0x10540000 ou FDT final; não se repete coleta bloqueada
nem se presume root a partir deste bugreport.
