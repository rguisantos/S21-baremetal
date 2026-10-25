# HZC2: plano consolidado para as colunas 1 e 12 da NEWTIME

Atualizado em **2026-10-25 (Campo Grande)**. Base revisada: PR #26,
merge `3daf8f33364b9e2d4d9bafdbdd4f28b4d220de58`.
Esta consolidação é documental; não registra uma nova execução.

Por orientação do usuário, as **seções 2.8 a 2.13 do plano recebido em
2026-10-24 estão substituídas**, como base de trabalho, pelo relatório
[Consumidores NEWTIME e limites de vddcal](newtime-consumers-hzc2.md).
O texto original da conversa permanece como histórico. As demais partes
do plano devem ser lidas com as ressalvas dos relatórios, especialmente
quanto a seleção no aparelho, formatos dos descritores e estado do QEMU.

## Pergunta e estado atual

Determinar como as diferenças das colunas 1 e 12 são usadas pelo código
e qual significado físico possuem. Há leitores e escritas nominais
identificados; o significado físico e a execução real seguem abertos.

| Coluna | Linha 10, chave comparada pelo driver | Linha 15, chave presente no log |
|---|---|---|
| 0 | 0x0001000860000110 | 0x0001000850500130 |
| 1 | 0x12b | 0x11b |
| 12 | 0x71 | 0x73 |

As colunas 1/12 são **chaves de subtabelas**, não valores de timing já
interpretados. A palavra impressa no boot corresponde à chave da linha
15; o log não mostra o callback selecionando ou publicando essa linha.

| Nível de evidência | Resultado disponível | Limite |
|---|---|---|
| Log do aparelho | Samsung/D1Z, 12 GB e palavra da linha 15 | Sem leitura direta de AP0x02073600 |
| Callback contínuo em QEMU | Quatro casos copiam a cauda e param antes de 0x19774/AP0x158609bc | Sem retorno completo ou resposta MMIO |
| Análise estática da coluna 1 | Ponteiro do payload em 0x31758; folha 0x2e4b4 deriva 0/28 e escreve nominalmente em AP0x0207365c | Preservação, uso posterior e significado físico abertos |
| Análise estática da coluna 12 | 0x2cdb8 lê 0x316a0; campos seguem por helpers ao slot nominal 25/0x27a7c e suas escritas | Ordem real, bindings e nomes físicos dos comandos abertos |
| vddcal | Diretório, ponteiro bruto e parser candidato inspecionados | Mapeamento do ponteiro e rota de chamada não estabelecidos |

Fontes: [observação no bugreport](dram-observed-hzc2.md),
[colunas e ensaio contínuo](newtime-columns-hzc2.md) e
[consumidores estáticos](newtime-consumers-hzc2.md).
Os resultados usam os hashes exatos de sboot/vddcal registrados nesses
relatórios; a aceitação das correções não acrescenta evidência de runtime.

## Correções adotadas

| Tema do plano anterior | Base substituta |
|---|---|
| Escritor de 0x31c30 desconhecido | 0x25ef0 grava o retorno de 0x22014, por endereço salvo na pilha |
| Origem do scratch de 108 bytes | Em 0x25a98, o fluxo verificado é do scratch de 108 para campos do registro de 162 bytes |
| 0x31fa0 como tabela de ponteiros | Área de dados com passo de 108 bytes |
| 0x26e14: pilha e laços | Quadro total de 2272 bytes; 64 combinações por passagem, uma ou duas passagens |
| Modo em 0x244f0 | W0=2 |
| Slot 26 de 0x31408 | Célula 0x314d8 contém ponteiro nominal para 0x2dc18; execução ainda aberta |
| 0x28480 como acessor puro | Escreve em base+0/base+4 e lê base+12, conforme seleção válida |
| Endereços relativos a S=0x31688 | Âncora comum útil; não prova limites de um objeto fonte ou dependência entre os campos |
| Diretório de vddcal | Registros em 0xf7500, passo 40, nome +8, campo u64 +24 e ponteiro +32 |
| Manipulador vddcal identificado em 0x67630 | Ponteiro bruto termina em 0x67630, que é offset interno ao parser candidato com prólogo em 0x675e0; vínculo ainda aberto |

Precisão adicional sobre o despacho em `0x30e50`:

| MOV W2,#26 — argumento | LDR do ponteiro de função | Chamada BLR | Slot nominal |
|---|---|---|---:|
| 0x263d8 | 0x263d4, deslocamento 200 | 0x263e4 | 25 |
| 0x2646c | 0x26470, deslocamento 208 | 0x26478 | 26 |
| 0x264c4 | 0x264cc, deslocamento 208 | 0x264d4 | 26 |

Logo, `0x2646c` e `0x264c4` também são instruções que carregam o
argumento 26. O índice da tabela vem do deslocamento do LDR dividido
por oito. Essa distinção evita confundir argumento, slot e PC da chamada.

O callback usa entradas de metadados parseados de **32 bytes**, scratch
de **144 bytes** para as 16 subchaves e descritores de saída de **16 bytes**.
Os formatos e as condições de transformação das chaves permanecem no
[relatório das colunas](newtime-columns-hzc2.md).

## Escopo de execução preservado

O ensaio contínuo existente permite somente o callback `0x193fc` e sua
cadeia explicitamente autorizada no
[runner](../scripts/trace_newtime_columns_qemu.py). Ele verifica cada
acesso de memória antes de executar e tem limite pré-fixado de 20000
instruções por caso. Código fora da lista, instruções de sistema,
memória não permitida, epílogo compartilhado ou limite encerram o rastreio.

O QEMU funciona neste ambiente pelo loader/bibliotecas do repositório;
a causa do aborto relatado no outro ambiente não foi diagnosticada.
A observação usa GNU e single-step GDB. `-d exec` isoladamente não
fornece todos os endereços/valores de memória exigidos pelo plano.

Mantêm-se as duas chaves, mesma preparação de RAM/heap/pilha por caso,
parada antes de MMIO e ausência de stubs/respostas SMC. O epílogo
compartilhado, antes chamado ERROR, não identifica erro só por seu PC.
Continuar “após o retorno” depende de obter esse retorno sob um escopo
válido; ele não foi observado no ensaio contínuo atual.

**Não executar por este plano** `0x26e14`, `0x25b80`, `0x2d5f8` ou
`0x2e4b4`. A mesma restrição vale para os demais consumidores fora da
cadeia, inclusive `0x2cdb8`. Uma execução futura exige decisão explícita
de escopo, com entradas, regiões, instruções permitidas e parada definidos
antes do ensaio. As rotinas podem continuar sendo analisadas estaticamente.

## Próximos passos estáticos

A consolidação original não executou estes itens. O primeiro avançou
parcialmente no [rastreio de recargas](newtime-reloads-hzc2.md): outro
leitor da coluna 1 e escritores do binding 0x31998; leitor AP e preservação
continuam abertos. A [continuação do binding](newtime-smc-binding-hzc2.md)
liga um inicializador concreto à folha SMC e deriva endereços candidatos
pela convenção pública; a segunda origem e o monitor seguem abertos.
A [auditoria do slot47](newtime-slot47-hzc2.md) distingue bases e
descarta quatro candidatos, mantendo despacho/X0 abertos.
Os demais itens permanecem pendentes. Nenhum depende
de ampliar o escopo QEMU.

| Ordem | Trabalho | Critério para encerrar a etapa |
|---:|---|---|
| 1 | Seguir leitores de AP0x0207365c e escritas/recargas de 0x316a0, 0x31758 e dos slots envolvidos | PCs, largura, operações e condições documentados; lacunas de chamadas indiretas explicitadas |
| 2 | Identificar os valores W2 9/73/57/59 — 0x09/0x49/0x39/0x3b — com documentação ou fonte primária correspondente ao bloco HZC2 | Correspondência entre endereço, campo e significado, com versão/proveniência; nomes de outro SoC ficam como hipótese |
| 3 | Resolver a tradução dos ponteiros de vddcal antes de seguir seu despacho NEWTIME | Regra de mapeamento justificada por código/metadados, compatível com a entrada de função e referências; bits altos ffff não bastam |
| 4 | Ampliar o grafo estático entre publicação, configuração e calibração | Arestas e condições verificáveis; separar caminhos possíveis de ordem observada no aparelho |

Cada entrega deve preservar os hashes, conferir instruções/operandos
relevantes e atualizar relatório, índices e worklog. A conclusão física
exige evidência adicional de bindings/execução; um grafo estático ou a
presença de strings não substitui essa evidência.

## Pendências que permanecem

- Ordem real entre configuração, calibração e publicação.
- Preservação e valores efetivos de ponteiros, slots e registros.
- Significado físico dos comandos e uso final das diferenças das linhas.
- Mapeamento e chamada do parser candidato de vddcal.
- Ausência de DEVFREQ nos logs e leitura direta de AP0x02073600.
- Registradores, resposta SMC, UART e mapa RAM/FDT do diagnóstico físico.

`available_frequencies` não revela o estado habilitado de cada OPP.
Samsung/D1Z/12 GB continuam descritos como **observados no log do bootloader**.
Dados pessoais do bugreport permanecem fora dos artefatos públicos.
