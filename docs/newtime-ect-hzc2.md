# HZC2: tabela NEWTIME e primeira escrita do callback

Continuação de **2026-10-24 (Campo Grande)** do
[rastreio ACPM](acpm-handshake-hzc2.md). Mesmo sboot de 4194304 bytes,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets de código e dados nesta página são relativos ao arquivo. Colocações
QEMU são explicitamente de laboratório.

**O lookup NEWTIME foi ligado ao bloco ECT embutido, e o parser original
mais o prefixo até a primeira escrita foram executados no QEMU.** Os 22
seletores do arquivo incluem **0xcafe** na linha zero e a assinatura DRAM
**0x0001000860000110** na linha dez. Isso explica a compatibilidade do
marcador com a tabela; não identifica a linha usada pelo telefone.

## Origem ECT e registro de parsers

O loop **0x16278** copia 0x14000 bytes de **0x02153000–0x02167000** para
**0x90000000**. Sob o delta nominal BL2 **0x020ea000**, sua origem é arquivo
**[0x69000, 0x7d000)**. Ela começa com `PARA007n`, campo total_size
**0x110c4** e nove blocos no diretório. A interpretação total_size+4 é
usada pelo consumidor BL2; o bloco NEWTIME termina antes do próximo bloco.

O caminho selecionado **0x1ca68–0x1ca84** guarda a própria origem
**0x02153000** no estado 0x31c10 e segue para **0x1c87c**, o parser ECT.
Os gates anteriores e a origem ativa não foram executados no laboratório.
Portanto não se presume que o parser leu a cópia em 0x90000000.

O registro relativo **0x309d0** tem 12 entradas de 32 bytes, com nome,
comprimento, callback e handle. A última, **0x30b30**, contém NEWTIME,
comprimento 7, callback nominal **0x1c3dc** e handle inicial zero.
O dispatcher selecionado **0x1c9ac–0x1c9c8** passa origem ECT+offset e
endereço da entrada ao callback. Este reconstrói o header, aloca descritores
de 32 bytes, lê suas chaves/offsets e instala o handle em entrada+24.

O lookup **0x1c55c** compara nomes das 12 entradas e devolve esse handle.
**0x1c83c** procura uma chave u64 entre os descritores. Não é uma busca
direta por geometria no arquivo.

## Formato e seleção encontrados no arquivo

O diretório aponta NEWTIME no offset ECT **0x7404**: arquivo
**[0x70404, 0x77994)**, **30096 bytes**. Header: parser_version 1,
versão `0.81`, **57 descritores**. Cada descritor wire tem chave u64 e
offset u32; cada corpo começa por mode, número de parâmetros e níveis.
O leitor de host verifica limites, duplicidades, sobreposição e dimensões.
Essas recusas do host não são atribuídas ao firmware original.

A chave especial **0x11111111** tem corpo em **0x706bc** e células a partir
de **0x706c8**: mode **2**, **17 colunas × 22 linhas**, células u64. A fonte
pública chama mode 2 de valor estendido. Os demais descritores deste bloco
usam mode 1 e células de 32 bits no leitor de host.

| Linha da tabela especial | Primeiro u64 usado na comparação | Restante |
|---:|---|---|
| 0 | 0xcafe | 16 chaves, começando por 0x10b, 0x204b, 0x202b |
| 10 | 0x0001000860000110 | 16 chaves, começando por 0x12b, 0x204b, 0x202b |

Os 22 seletores e as duas linhas completas estão no
[relatório estático](references/newtime-ect-hzc2.json). A assinatura da
linha dez coincide com a comparação no BL2, no payload Thumb e no kernel
devfreq já estudados. **Presença na tabela não é leitura do registro DRAM.**

O callback **0x193fc** guarda X0 em frame+136. Para procurar a linha,
se X0 for negativo na interpretação signed de 64 bits, usa somente seus
32 bits baixos em frame+152; caso contrário, mantém o u64 inteiro.
O helper **0x1c540** lê dois W e monta cada célula u64.

Encontrada a linha, o prefixo copia as 16 células seguintes para uma área
dinâmica de pilha, com alocação de **144 bytes** para essa forma da tabela.
Em **0x19684** lê o ponteiro de estado **0x30520**; **0x19690** recarrega
o argumento original do frame+136 e **0x19694** escreve esse u64 no destino.
Logo a normalização da comparação não normaliza o valor da primeira escrita.

Os ramos selecionados preparam códigos 3 para nome ausente, 2 para chave
ausente e 1 para linha não encontrada. Tabela vazia/corrompida não é um
cenário suportado do ensaio; não foi presumido seu comportamento.

## Ensaio do código original no QEMU

O [runner](../scripts/emulate_newtime_qemu.py) usa QEMU virt/EL1 e duas
colocações em RAM, deltas **0x40000000** e **0x40200000**. Os bytes das
instruções permanecem originais. Os ponteiros absolutos dos nomes/callbacks
no registro de parsers são relocados como dados; heap, pilha, destino e
entradas são bindings fornecidos pelo ensaio.

Primeiro executa **0x1c3dc** e seus helpers originais sobre os bytes NEWTIME
do arquivo. Em cada colocação, os **57 descritores reconstruídos** tiveram
chave, offset, mode, dimensões e ponteiro de dados conferidos no host.
Isso não executa o parser ECT completo nem os gates de inicialização.

Depois executa o prefixo **0x193fc–0x19694** e seus helpers originais:

- 22 seletores embutidos por colocação: todos encontram sua linha e copiam
  as 16 células corretas para a área dinâmica de pilha.
- Duas entradas com bit 63 e low32=0xcafe por colocação: encontram a linha
  zero, preservando os bits altos no frame e na escrita de destino.
- Quatro controles por colocação: linha ausente, entrada positiva com bits
  altos, nome ausente e chave ausente; preparam 1/1/3/2, sem tocar o destino.

Total: **56 casos, 48 primeiras escritas e oito ramos de erro**. Nos
positivos, o ensaio para antes do STR, confere registradores/frame, executa
uma instrução e para em **0x19698**. Nos negativos, para em **0x199fc**
antes do epílogo. Código, bloco fonte, sentinelas da pilha e guardas do
destino ficaram intactos. [Resultado](references/newtime-qemu-hzc2.json).

Nenhum helper foi substituído por stub; não houve resposta MMIO/SMC
simulada. A parte posterior do callback não foi executada: ela contém
outras consultas, cópias, alocador e leitura de AP **0x158609bc[31]**.
Assim, a preservação conferida pertence a esse prefixo com esses bindings;
não prova o efeito líquido da função completa ou o estado do telefone.

## Fontes, reprodução e próximo passo

O [manifesto](references/newtime-sources-hzc2.json) fixa dois fontes do
commit **756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0**:
[ect_parser.h](https://github.com/xfwdrev/android_kernel_samsung_ex2100/blob/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0/include/soc/samsung/ect_parser.h)
e [ect_parser.c](https://github.com/xfwdrev/android_kernel_samsung_ex2100/blob/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0/drivers/soc/samsung/ect_parser.c).
Eles corroboram nomes, campos, enum de modos, parsing e lookup por chave;
não estabelecem identidade entre os builds público e HZC2.

```bash
python3 scripts/inspect_newtime_hzc2.py /caminho/sboot.bin
python3 scripts/check_newtime_gnu.py /caminho/sboot.bin
python3 scripts/emulate_newtime_qemu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime_hzc2.py' -v
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
```

[GNU 2.44](references/newtime-gnu-hzc2.json): **353 palavras, 50 alvos,
24 operandos, oito spans de dados**, incluindo os 30096 bytes NEWTIME.
Relatórios estático/GNU reproduzidos byte a byte. **10 testes novos e 70
regressões BL2 passaram**. [Nove recusas CLI](references/newtime-validation-hzc2.json)
cobrem sboot curto, longo e alterado nos três comandos, antes de executar
QEMU, com exit 2 e sem JSON parcial. Compilação Python e links conferidos.

Próximo: seguir alocador, gates e escritas posteriores ao primeiro store,
e corroborar bindings/aliases ACPM. O critério condicional do destino AP
**0x02073600** permanece; nenhum diagnóstico físico, conteúdo real do
registro, capacidade RAM ou FDT final foi obtido nesta etapa.

A [continuação do registro](newtime-record-hzc2.md) delimita o restante
do callback sob ramos explícitos: layout, alocação, cópias, tamanho final
e erros sem rollback. O gate MMIO continua sem amostra e não executa no
novo ensaio; os efeitos do helper de erro fora do callback seguem abertos.
