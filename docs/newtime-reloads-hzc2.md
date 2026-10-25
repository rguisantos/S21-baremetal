# HZC2: recargas dos payloads NEWTIME e bindings ainda abertos

Análise **estática, 2026-10-25 (Campo Grande)**, base `eb1f1d7` / PR #27.
Nenhuma instrução do firmware foi executada. O escopo QEMU permanece igual.

**Há outro consumidor da coluna 1 em `0x28808`.** Ele lê 15 palavras do
payload e as encaminha por um método indireto. Isso não estabelece o uso
físico dos campos. O leitor de AP`0x0207365c` continua sem ligação comprovada.
A preservação de ponteiros e slots também continua aberta: recarregar uma
célula entre chamadas não demonstra que seu conteúdo permaneceu igual.

## Imagem e reprodução

Foi recuperado o pacote BL já fornecido; seus membros sboot/vddcal foram
extraídos em diretório externo ao Git e conferidos contra os hashes anteriores.
Esta entrega só usa `sboot.bin`, 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Os PCs e células abaixo são offsets de arquivo; a tradução de ponteiros BL2
usa o delta **nominal** `0x020ea000`. Endereços AP são literais, não medições.

```bash
python3 scripts/inspect_newtime_reloads_hzc2.py /caminho/sboot.bin
```

O [leitor reproduzível](../scripts/inspect_newtime_reloads_hzc2.py) exige o
hash exato e GNU do repositório. O [JSON](references/newtime-reloads-hzc2.json)
registra todas as **324 instruções**, 18 alvos relativos conferidos, hashes
por intervalo, células iniciais e argumentos derivados dos payloads fornecidos.
Não se trata de um inventário completo de aliases ou escritas no sboot.

## Outro leitor da coluna 1

A célula `0x30ec0`, índice **14** de `0x30e50`, contém `0x02112808`, alvo
nominal `0x28808`. Não foi encontrado B/BL direto para essa entrada no intervalo
alinhado `[0x16000,0x2fd00)`; o ponteiro nominal aparece em `0x30ec0`.
Isso não exclui despachos indiretos, aliases ou entradas internas.

Em `0x2880c/0x28814`, X19 recebe a âncora S=`0x31688`. A rotina recarrega
S+208 (`0x31758`) **15 vezes** e lê os offsets 0,4,…,56 do payload. Cada
chamada intermediária pode alterar o estado; não se supõe uma lista estável
no aparelho. Sob a hipótese de ponteiro/payload preservados:

| Campo | Operação | Encaminhamento |
|---|---|---|
| Palavras 0–13 | LDR W2 (u32, extensão por zero) | 14 BLRs; X0=-101, X1=tag, X2=valor, X3=0 |
| Palavra 14, offset 56 | LDRSW X2 em `0x28a54` | BR final em `0x28a68`, após restaurar X19/LR; X2 com extensão de sinal |

As tags são `0x468d0100`, `0101`, `0104`–`0107`, `010a`–`0111` e
`0x468d012d` (prefixo `0x468d` em todas). Tags não fornecem nomes físicos.
O JSON inclui os 15 PCs de carga e os 15 conjuntos de argumentos para cada
subtabela `0x12b`/`0x11b`, ambas de 60 bytes. Por exemplo, a palavra 1 é
0 versus `0x100001`; a palavra 12 é `0x1e02` versus `0x3e02`.
A folha anterior `0x2e4b4` continua derivando 0 versus 28 da palavra 1
sob os mesmos bindings condicionais descritos no [relatório das colunas](newtime-columns-hzc2.md).

O alvo é buscado, a cada envio, em **`[ponteiro_carregado_de_0x31998 + 72]`**.
É uma tabela de métodos diferente da tabela `0x30e50`; o deslocamento 72
não identifica por si só uma função. `0x31998` vale **zero no arquivo**.
Não há destino nominal utilizável ali sem inicialização em runtime.

Dois escritores desse binding foram conferidos:

| PC | Condição e origem | Destino |
|---|---|---|
| `0x1dcbc` | X3 não nulo, teste em `0x1dcb4` | S+784=`0x31998`, STR X3 |
| `0x2d394` | X0 não nulo, teste em `0x2d390` | S+784=`0x31998`, STR X0 |

Identificar quem fornece esses argumentos e qual método ocupa +72 é a
próxima aresta desta cadeia. Não foi atribuído a ela um nome como log,
telemetria ou programação DRAM sem resolver esse destino.

## Recargas, publicação e limites de preservação

- **Coluna 1:** `0x2d774` publica X7 em S+208; a folha `0x2e4b8` o lê
  uma vez; o novo consumidor o relê antes de cada envio. O primeiro acesso
  à folha lê payload+4 e grava u32 em AP`0x0207365c` por `0x2e4f4`.
- **Coluna 12:** `0x2d71c` publica o ponteiro em S+24=`0x316a0`;
  `0x2ce08/28/40/54` o recarregam entre helpers. A contagem também é
  relida em `0x2cdf8`. As quatro leituras de uma iteração não estão
  demonstradas como provenientes da mesma região imutável.
- **Slots:** os valores iniciais 25/26 de `0x30e50` e 24/26 de `0x31408`
  continuam nos dados e no JSON. Esta rodada não prova ausência de outras
  escritas diretas, indexadas, em pares, por cópia ou por alias nessas células.
  Não se pode promover os alvos nominais a bindings observados.

Há ainda uma alteração concreta na **tabela de bases** usada pelos alvos
nominais `0x27a7c`/`0x28480`. Na rotina `0x2d270`, se a chamada indireta
`0x2d27c` retorna W0=1, as escritas `0x2d298/2a4/2ac/2b4/2c0` substituem
as cinco bases de `0x30f98` por `0x1c03f000`, `0x1c13f000`, `0x1c23f000`,
`0x1c33f000`, `0x1a34f000`. As bases iniciais terminavam em `6000`.
Isso muda os destinos nominais de MMIO se esse caminho ocorrer; a ordem
real dessa alteração frente aos consumidores não foi observada. Ela não
é uma escrita nos slots de funções e não demonstra mudança desses slots.

## AP0x0207365c: pendência preservada

O store u32 `0x2e4f4` está reconferido. A busca integral dos bytes de
`0x0207365c` como literal little endian u32/u64 não encontrou ocorrências
no sboot. O próprio escritor constrói o endereço por MOV/MOVK, portanto
esse resultado **não exclui leitores**, endereços construídos, bases mais
offset, aliases ou consumo em outra imagem. Nenhum leitor foi estabelecido
por esta entrega; a semântica física do valor 0/28 permanece aberta.

## Validação e continuação

Relatório reproduzido byte a byte; GNU conferiu palavras, operandos do novo
leitor e alvos relativos. Recusas de arquivo curto, longo e alterado foram
verificadas; suíte de host NEWTIME executada sem alterar o harness.

O primeiro item do [plano consolidado](newtime-plan-consolidated-hzc2.md)
ficou **parcial**. Próximo: origem dos argumentos que inicializam `0x31998`,
destino do método +72 e escritores/aliases dos ponteiros/slots. Leitores
AP e ordem real continuam pendentes. Os consumidores externos ao callback
continuam fora do escopo de execução QEMU autorizado.
