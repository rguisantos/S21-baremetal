# HZC2: leitor da coluna 12, registros de calibração e limites de vddcal

Análise **estática, 2026-10-25 (Campo Grande)**, sobre main após o PR #25,
`17c7e74a3f9ebe8ba5c70b4893916cb83ce2c53b`. Nenhuma rotina adicional foi
executada no QEMU ou no telefone. O ensaio contínuo anterior permanece
limitado ao callback NEWTIME e seus helpers, com parada **antes** da carga
em `0x19774`, AP`0x158609bc`. Portanto ainda não existe uma observação
“após o retorno do callback” sob essas restrições.

**O leitor do payload da coluna 12 foi localizado em `0x2cdb8`.** Ele
percorre palavras de 32 bits e encaminha campos a helpers que, sob os
ponteiros nominais iniciais, chegam a escritas em blocos de registradores.
Isso identifica uma sequência de operações no código; não estabelece o
nome físico dos comandos, sua execução real ou a seleção observada no S21.

## Entradas e reprodução

O leitor exige os dois arquivos exatos, já inventariados em
[BL HZC2](bootloader-hzc2.md):

| Arquivo | Bytes | SHA-256 |
|---|---:|---|
| sboot.bin | 4194304 | a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91 |
| vddcal_fw.bin | 2097152 | 2bac8e0eedc9395d7f5630442130a9ccae5a9201e700299a0a60a9565e886e39 |

Todos os PCs/endereço de dados relativos abaixo são offsets de arquivo.
Ponteiros BL2 são traduzidos com o delta **nominal `0x020ea000`**; endereços
AP e bases de registradores são literais do código/dados, sem medição.

```bash
python3 scripts/inspect_newtime_consumers_hzc2.py /caminho/sboot.bin /caminho/vddcal_fw.bin
python3 scripts/inspect_newtime_consumers_hzc2.py /caminho/sboot.bin /caminho/vddcal_fw.bin --gnu
python3 -m unittest discover -s scripts -p 'test_newtime*.py' -v
```

[Relatório estático](references/newtime-consumers-hzc2.json),
[conferência GNU](references/newtime-consumers-gnu-hzc2.json) e
[validação](references/newtime-consumers-validation-hzc2.json).

## Coluna 12: cadeia estática encontrada

A publicação condicional anterior continua necessária: construção bem
sucedida do registro, alias de R com AP`0x02073600`, ausência de mudanças
relevantes nos descritores, ponteiros e tabelas de funções.

1. `0x2d5e8/0x2d5ec` lê a contagem do descritor em AP`0x02073850` e a
   guarda como byte em `0x31698`. `0x2d708/0x2d71c` lê seu offset e guarda
   o ponteiro de payload em `0x316a0`. Evidência fixada no
   [estudo das colunas 1/12](newtime-columns-hzc2.md).
2. **`0x2cdb8`** lê a contagem em `0x2cdc0` e retorna se ela for no máximo
   um. O laço relê essa contagem em `0x2cdf8` e percorre `payload+4*i`.
3. As cargas do ponteiro estão em `0x2ce08`, `0x2ce28`, `0x2ce40` e
   `0x2ce54`. As leituras do payload são `0x2ce10` (u32), `0x2ce30`
   (byte +1), `0x2ce44` e `0x2ce58` (byte +0).
4. O campo **bits 16:12** vai para `0x2cbec`. Os campos **11:8, 7:4 e
   3:0**, nessa ordem, vão para `0x2cd1c`. Há chamadas a `0x2cb9c` antes
   e depois dos três campos baixos.

Sob bindings estáveis, cada palavra produz a sequência abaixo:

| Helper / campo | Argumentos para o slot 25 de `0x30e50` |
|---|---|
| `0x2cbec`, campo 16:12 igual a 1 | W2=9; três chamadas com W3=1,1,1 |
| `0x2cbec`, demais valores | W2=9; W3=2,4,1 |
| `0x2cb9c` | Duas chamadas com W2=9, W3=0 |
| `0x2cd1c`, nibble 0–7 | W2=9, W3=`1 << nibble` |
| `0x2cd1c`, nibble 8 / 9 / 10 | W2=73 / 57 / 59, W3=0 |
| `0x2cd1c`, nibble 11–15 | Retorna sem chamar o slot |

O slot 25 contém `0x02111a7c`, nominalmente **`0x27a7c`**. Essa rotina
insere os dois bits baixos de W1 em 29:28 e os sete bits baixos de W2 em
26:20 da palavra de controle. W3 é reduzido a oito bits. Escreve:

| PC | Destino |
|---|---|
| 0x27ad8 | base+0: controle |
| 0x27ae0 | base+56: literal 22 |
| 0x27ae8 | base+8: dados derivados de W3 |
| 0x27aec | base+4: literal 16 |

As cinco bases iniciais em `0x30f98` são `0x1c036000`, `0x1c136000`,
`0x1c236000`, `0x1c336000` e `0x1a346000`. O caminho depende de W0
selecionar 0–4; outros valores retornam sem essas escritas. Os rótulos
“comando” e “dados” descrevem o fluxo, **não nomes de registradores ou
parâmetros DRAM confirmados**.

As subtabelas `0x71` e `0x73` contêm 44 e 41 u32. O JSON mostra os campos
e argumentos calculados para todas as 85 palavras. A primeira, `0x1390`,
é comum: seletor 1, nibbles 3/9/0. O código relê ponteiro e contagem entre
chamadas; o modelo de uma lista estável não prova preservação em runtime.
Não há ligação demonstrada dessa sequência com a entrada de 162 bytes.

## `0x31c30`: escritor e sentido do fluxo de dados

O valor inicial no arquivo é `0xffffffffffffffff`. O escritor encontrado
está fora da cadeia permitida no ensaio QEMU:

- `0x25d3c/0x25d44` calcula `&0x31c30`; `0x25d48` salva esse endereço
  em `[sp+128]`. Ele é recuperado como argumento X2 em `0x25ed8`.
- `0x25ee8` chama `0x22014` com tamanho `u8(objeto_atual+12) * 162`.
  Essa rotina seleciona rótulos `vref_soc_lv` / `vref_mem_lv`, chama o
  provedor `0x21f84`, que registra uma área por `0x21dc0` e copia bytes
  pela rotina `0x1fcc4`. Estado e endereço efetivos continuam desconhecidos.
- `0x25eec` recupera o endereço da célula; **`0x25ef0` grava X0 nela**.
  `0x25f08` zera a área retornada, com o mesmo tamanho calculado.
- `0x25b80` zera o scratch de 108 bytes em `0x31f30`, chama `0x259f4`
  e agrega resultados de `0x31fa0` por `0x257b8`. Se W20 difere de
  `0x34183418`, calcula `signed(W20)*162`, lê `0x31c30` em `0x25c18`
  e chama `0x25a98` com **X2=registro de 162 bytes; X3=scratch de 108**.
- Em `0x25a98`, `LDRH` lê o scratch e `STRH`/`STURB` atualizam campos
  do registro de 162 bytes, com comparação contra campos já acumulados.
  Exemplos: `0x25ae8/0x25af0` e `0x25b18/0x25b30`.

Portanto, **nesse caminho o registro de 162 bytes recebe resultados do
buffer de 108 bytes**. Não foi demonstrado que ele fornece os dados para
preencher o buffer, nem que deriva diretamente da seleção NEWTIME.
Os nomes `vref_*` sustentam tratar isso como candidato a estado de
calibração; não estabelecem a semântica de cada campo.

## Base comum e correções de layout/despacho

Usar **S=`0x31688`** como âncora organiza os endereços:

| Campo relativo | Offset | Uso verificado |
|---|---|---|
| S+0x10 | 0x31698 | Byte de contagem da coluna 12 |
| S+0x18 | 0x316a0 | Ponteiro do payload da coluna 12 |
| S+0xd0 | 0x31758 | Ponteiro do payload da coluna 1 |
| S+0x5a8 | 0x31c30 | Ponteiro mutável para registros de 162 bytes |
| S+0x8a8 | 0x31f30 | Scratch de 108 bytes |
| S+0x918 | 0x31fa0 | Área de registros com passo de 108 bytes |

`0x31fa0` é zerado e recebe campos de dados; a interpretação como
“tabela de ponteiros” não é sustentada por esses acessos. A âncora comum
não demonstra os limites de um objeto da linguagem fonte ou dependência
de dados entre todos os seus offsets.

Outras correções verificadas:

- `0x26e14` reserva **2176+96=2272 bytes** incluindo o quadro de
  registradores salvos. Há 64 combinações por passagem e **uma ou duas
  passagens**, conforme o byte `0x31939`. O vetor de 16×108 bytes em
  SP+544 é reutilizado entre canais/passagens. Modos dos três BLs:
  `0x244c4`=0, `0x244f0`=**2**, `0x25058`=1.
- `0x269f0` usa as quatro bases iniciais `0x1c040000`, `0x1c140000`,
  `0x1c240000`, `0x1c340000` da tabela `0x30fc0`.
- A entrada 26 de `0x31408`, célula `0x314d8`, contém
  `0x02117c18`: alvo nominal **`0x2dc18` confirmado nos dados**.
  A execução e a origem de um índice dinâmico continuam sem prova.
- `0x263d8` é `MOV W2,#26`, não uma chamada ao índice 26: o BLR em
  `0x263e4` usa o slot **25**. Os BLRs `0x26478` e `0x264d4` usam
  o slot **26**, alvo nominal `0x28480`.
- `0x28480` **faz escritas** em base+0 e base+4 e lê base+12, usando
  a tabela `0x30f98`. Não é um acessor puro em RAM.

O bloco LK `0x198b38` pertence a outra cadeia. O literal 26 ali não
vincula a estrutura LK ao índice 26 dessas tabelas BL2; divisão/resto
também não bastam para nomear uma configuração de clock DRAM.

## Alcançabilidade: referências adicionais, ordem real aberta

`0x2d5f8` é uma instrução interna à função iniciada em **`0x2d568`**.
Há um ponteiro nominal para essa entrada na célula **`0x314c8`**, índice
24 de `0x31408`. O leitor **`0x2cdb8`** aparece em `0x313c8`.
A folha da coluna 1 **`0x2e4b4`** recebe BL direto em **`0x2f0d4`**.

`0x244b8` também não deve ser procurado apenas como função independente:
`0x244ac` compara W0, cai/salta para `0x244b8` ou salta a `0x25050`.
Há BL para `0x244ac` em `0x23148`; `0x22f6c` chama `0x25050`.
Buscar só prólogos ou chamadas ao endereço interno perde essas arestas.

O leitor registra candidatos B/BL alinhados em `[0x16000,0x2fd00)` e
ocorrências dos ponteiros nominais em todos os offsets do sboot. Esse
inventário não é um grafo completo: dados podem parecer instruções,
chamadas indiretas e escritas nas tabelas precisam de análise própria.
Não estabelece a ordem real entre configuração, calibração e publicação.

## `vddcal_fw`: presença de NEWTIME e mapeamento ainda aberto

Conferidos os cinco registros com passo 40: **início `0xf7500`**, nomes
em +8, campo u64 em +24 e ponteiro em +32. Assim, o primeiro nome fica
em `0xf7508`, e o registro NEWTIME começa em `0xf75a0`.
O campo em +24 coincide com o comprimento dos cinco nomes (6/7/3/3/7).
Isso sugere comprimento, não prova que seja um tipo. O índice em
`0xf89e0` guarda `0xffff0000000f7500`, coerente com o início do registro
oito bytes antes do nome; outros valores são preservados no JSON.

O ponteiro NEWTIME é `0xffff000000067630`. **Tratar seus 48 bits baixos
como offset direto não foi validado**: em `0x67630` existe
`ADD X0,X29,#0x18`, dentro de uma rotina cujo prólogo está em `0x675e0`.
O bloco inspecionado aloca estruturas de 24 bytes e percorre entradas
desse tamanho, mas o vínculo do ponteiro do diretório com essa entrada
de função continua aberto. Bits altos `ffff` sozinhos não provam que
um carregador ajuste o ponteiro.

As duas chaves DRAM não aparecem como u64 little endian nesse arquivo.
Isso não exclui valores construídos ou recebidos em runtime. A string e
o diretório sustentam uma frente de investigação separada; **ainda não
provam uma segunda cadeia funcional consumindo as linhas 10/15 do sboot**.
Ausência de um padrão ADRP+ADD ou BL direto não prova ausência de chamador.

## Validação e próxima fronteira

Passaram **53 testes de host** (nove novos), GNU de **1031 palavras do
sboot e 140 de vddcal**, 156 alvos relativos e 34 operandos selecionados.
Os dois relatórios novos foram reproduzidos byte a byte. Doze recusas
CLI cobrem imagem curta, longa e alterada, para cada entrada e ambos os
modos. Conferidos 736 links locais da documentação do projeto (excluídas
as dependências em tools), compilação Python e diff. Nenhum ensaio QEMU
foi ampliado ou repetido nesta entrega.

Próximo trabalho estático: identificar os comandos 9/73/57/59 com fonte
primária do bloco de hardware, seguir o uso de AP`0x0207365c`, verificar
as escritas nos slots/ponteiros e resolver o mapeamento de vddcal antes
de perseguir seu despacho. Os quatro pontos de observação propostos
fora da cadeia do callback continuam **não autorizados por esse plano**;
exigem uma decisão explícita de escopo para futura execução.

Samsung/D1Z/12 GB permanecem observados no log do bootloader. A lista
`available_frequencies` não mostra o estado habilitado de cada OPP.
Ausência de DEVFREQ, leitura de AP`0x02073600` e mapa final de RAM/FDT
continuam abertos. Os READMEs recebidos são instruções genéricas de
build; não identificam o binário stock nem resolvem essas pendências.
