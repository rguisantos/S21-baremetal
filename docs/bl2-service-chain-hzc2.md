# HZC2: origem do modo BL2 e descritor parcialmente preenchido

Análise de **2026-10-23 (Campo Grande)**, continuação da
[preparação do monitor](monitor-preparation-hzc2.md). Usa o mesmo sboot
recebido: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Endereços de instruções são offsets no arquivo; os argumentos e o endereço
do descritor são valores nominais reconstruídos do código.

**Avanço:** a origem do modo foi ligada ao registrador X2 de uma resposta
SMC; o pedido anterior -0xe6 preenche uma janela de sete palavras do descritor, com campos
que não são escritos em todos os modos. O modelo conserva essas lacunas.
O provedor dos serviços e a lista/tabela de saída em execução continuam
abertos. Não houve acesso ao telefone, chamada SMC real ou escrita física.

## A resposta vem de X2, e o seletor trabalha com W

Em `0x1cb10`, o chamador usa o getter `0x1654c`. Ele prepara X0=`-0xe9`
(`0xffffffffffffff17`), X1=0 e chama `0x16428`. O veneer executa:

```text
MOV X2,#0
DSB SY
SMC #0
MOV X0,X2
RET
```

Portanto, o resultado devolvido ao chamador vem de **X2 após o SMC**.
Inicializar X2 com zero antes da chamada não comprova retorno zero; não
foi demonstrado se o serviço o preserva ou substitui. O valor real não
está disponível nesta análise.

Em `0x1cb14–0x1cb34`, o chamador consome W0. Para uma resposta X2 explícita:

1. `v = X2 & 0xffffffff`;
2. `shift = ((v & 0xf) << 2) & 31`;
3. `n = (v >> shift) & 0xf`;
4. `index = (n - 1) & 0xffffffff`;
5. se `index <= 10`, lê a tabela; caso contrário, modo zero.

O `&31` decorre do **LSRV W**: deslocamentos de 32–60 voltam a 0–28.
Aplicar um shift de 64 bits à resposta inteira produziria outro modelo.
A tabela em `0x2fdf8` contém os onze bytes
`20 14 00 40 00 00 00 00 00 00 40`.

| Nibble selecionado n | Modo W19 |
|---|---|
| 1 | `0x20` |
| 2 | `0x14` |
| 4 ou 11 | `0x40` |
| Demais valores de 0 a 15 | `0` |

Por exemplo, respostas **fornecidas ao modelo**, não medidas, `0x11`,
`0x21`, `0x41` e `0xb1` selecionam respectivamente `0x20`, `0x14`, `0x40`
e `0x40`. A resposta `0x100000008` vira W0=8, shift=0, nibble=8 e modo
zero. Não é uma nova definição de modos de armazenamento do hardware.

## Ordem dos pedidos e testes do chamador

| Ponto no chamador | Pedido / ação observada | Tratamento local |
|---|---|---|
| `0x1cb10` | Getter -0xe9 | Usa o retorno X2 via X0/W0 para selecionar W19 |
| `0x1cb4c` | Wrapper -0xed, `0x164c8` | Omitido se modo=`0x40`; não testa seu retorno |
| `0x1cb54` | Wrapper -0xe6, `0x1643c` | W0 zero continua; não zero estaciona em `0x1cb5c` |
| `0x1cb60` | Helper `0x1caf4` | Prepara endereço `0x1586081c` e STR WZR; não executado pelo modelo |
| `0x1cb68` | Wrapper -0xe7, da análise anterior | W0 zero continua; não zero estaciona em `0x1cb70` |

O pedido opcional -0xed prepara X1=`0xf0005000`, X2=`0x2000`, e X3=`0x751`
no modo zero, `0xea` no modo `0x20`, zero nos demais. A função desse buffer
e a operação segura continuam sem implementação correspondente demonstrada.
Não executar o teste de retorno no chamador não significa sucesso.

## Pedido -0xe6: palavras escritas e palavras herdadas

O construtor `0x1643c–0x164c8` prepara X0=`-0xe6`
(`0xffffffffffffff1a`), X1=modo, X2=`0xe7ffe000` e X3=modo. Os stores W
preenchem campos nesse endereço nominal; não escrevemos nesse endereço no
host ou no aparelho. O modelo usa apenas um dicionário de campos.

| Offset no descritor | Modo 0 | Modo `0x14` | Modo `0x20` | Modo `0x40` |
|---|---|---|---|---|
| +0x00 | `0xe8000000` | `0xe8000000` | `0xe8000000` | `0xe8000000` |
| +0x04 | `0x280000` | `0x280000` | `0x280000` | `0x280000` |
| +0x08 | `0x02024c00` | `0x02024c00` | `0x02024c00` | `0x02024c00` |
| +0x0c | 0 | 0 | 0 | 0 |
| +0x10 | `0x761` | `0x1400` | `0xec` | **Sem escrita** |
| +0x14 | `0x1400` | `0xe8000000` | `0x280` | **Sem escrita** |
| +0x18 | `0xe8000000` | **Sem escrita** | `0xe8000000` | **Sem escrita** |

“Sem escrita” não significa zero, defeito ou rejeição garantida. O campo
pode ter valor anterior ou não ser consumido nesse modo; isso depende da
preparação e do provedor. O relatório usa `null` para esses campos, separa
os stores por PC e não cria conteúdo inicial fictício.

Há correlações adicionais com o intervalo candidato LK:

- `0x761 × 512 = 0xec200` e `0xec × 4096 = 0xec000`;
- `0x1400 × 512 = 0x280 × 4096 = 0x280000`;
- `[0xec000, 0x36c000)` tem tamanho `0x280000`, e a base nominal LK
  já investigada é `0xe8000000`.

Essas relações reforçam a pista do pedido anterior associado ao LK, mas
**não definem os campos, unidades, conteúdo do buffer ou operação segura**.
Os IDs -0xe6/-0xe7 não podem ser tratados como o handler -0x3ff do salto final.

## Fronteira do provedor no EPBL

Foi conferida outra pista de preparação: em `0x3064`, um ADR prepara o
candidato `0xe800` para VBAR_EL3. Nos bytes em disco, a primeira palavra
nesse offset é `831dc011`, apresentada como `.inst ... undefined` pelo
GNU objdump 2.44. O vetor não foi validado como instruções plaintext nem
ligado ao despacho dos pedidos BL2.

Isso preserva uma fronteira concreta para investigação; não demonstra
cifra específica, ausência de código em execução, qual estágio faz a
transformação ou que esse VBAR ainda esteja ativo quando o BL2 chama SMC.
Não foi executada a preparação EPBL nem simulada sua rotina de hardware.

## Referências iniciais das tabelas de saída

A busca adicional cobre **apenas** ADRP seguido por ADD imediato sem shift,
adjacente ou separado por um MOV X que não sobrescreva a base. No intervalo
LK `[0xec000, 0x20c630)`, encontrou cinco produtores para os endereços
selecionados: célula `0x31fff0`, início da tríade `0x31ffe8` e três referências
à cabeça `0x3218c0`. Seus PCs constam no JSON.

As células iniciais `0x31ffe8`, `0x31fff0` e `0x31fff8` contêm o mesmo
ponteiro para o objeto `0x3218b0`, sob o delta nominal LK `0xe7f14000`.
Esse objeto referencia a tabela `0x2906f8` em seu campo +8. A cabeça da
lista inicialmente aponta a si própria nos campos +0/+8.

Em particular, `0x17015c` produz o endereço da célula `0x31fff0` e o passa
ao caminho de formatação chamado em `0x170168`; `0x1b1550` produz a base
da tríade, cujo campo +8 é usado pelo helper de saída. São referências,
não stores que substituam o ponteiro. A classificação anterior dos helpers
que inserem/removem a lista continua válida.

**Não foi concluído um censo geral de escritores.** O scan não cobre
outros encodings, ponteiros de 32 bits/desalinhados, aritmética mais longa,
aliases, chamadas indiretas ou mutação em execução. A existência de três
células iniciais para o mesmo objeto não prova que continuem iguais.

## Ferramenta e evidências

```sh
python3 scripts/inspect_bl2_service_chain.py /caminho/sboot.bin
# Resposta hipotética explícita; o relatório a marca como não medida:
python3 scripts/inspect_bl2_service_chain.py /caminho/sboot.bin --response-x2 0x21
(cd scripts && python3 -m unittest test_bl2_service_chain test_monitor_preparation -v)
```

O inspetor só aceita o sboot exato por tamanho/SHA-256, com leitura limitada.
O intérprete do construtor tem orçamento de 64 instruções, rejeita loops,
escapes, leituras de registradores desconhecidos, stores fora dos 28 bytes,
instruções não suportadas e alteração do veneer. Abstrai o prólogo/pilha
validado e para **antes do BL que entregaria ao SMC**. Não executa a cadeia
inteira nem reproduz cache/MMIO/retornos seguros.

Passaram **24 testes novos e 14 regressões da preparação anterior: 38 PASS**.
Há casos de truncamento X/W, shift modular, limites sem sinal, campos
herdados, modos, stores, condições desconhecidas, loops/escapes, adulteração
do SMC e referências ADRP com base sobrescrita. As fixtures do construtor
foram relocadas para o teste; não são um boot BL2 ou teste de hardware.

A comparação separada com GNU objdump 2.44 coincidiu nas **116 palavras e
25 destinos relativos** dos blocos selecionados. O vetor bruto foi excluído
da contagem de instruções válidas. Essa comparação confere palavras e
destinos, não é uma segunda execução independente da semântica do modelo.

- [Pedidos, campos, referências e hashes](references/bl2-service-chain-hzc2.json)
- [Linhas GNU e destinos conferidos](references/bl2-service-chain-validation.json)
- [Saída dos 38 testes](references/bl2-service-chain-host-tests.txt)

Não é necessário reenviar os arquivos já recebidos. O próximo trabalho é
seguir a preparação dos campos herdados e a transformação/despacho seguro
onde houver bytes verificáveis; se a implementação não estiver legível no
material em disco, registrar essa fronteira em vez de atribuir-lhe um mock.
Os requisitos físicos do [roadmap](roadmap.md) e o canal para ler o primeiro
registro continuam pendentes.
