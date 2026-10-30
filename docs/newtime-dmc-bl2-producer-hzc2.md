# HZC2: produtor BL2 das máscaras e da base DMC

Continuação estática sobre `aab7d05`, no mesmo sboot de4194304 bytes,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Os produtores nominais das três palavras DMC foram encontrados no BL2.
A ligação exige o alias AP/core já delimitado no
[handshake ACPM](acpm-handshake-hzc2.md), construção NEWTIME completa e
preservação até as leituras; nenhuma dessas condições foi medida no S21.

## As três stores e suas fontes

O helper BL2 `0x2d568` deriva ponteiros dos descritores do registro fixo
AP0x02073600. O descritor12 ocupa +0x260 e o descritor14 ocupa +0x280.
São índices começando em zero: correspondem às colunas13 e15 da linha
especial NEWTIME, cuja coluna0 contém o seletor.

| Publicação BL2 | Endereço AP | Leitor DMC sob alias | Fonte selecionada |
|---|---|---|---|
| 0x2d840, STR W | 0x02073660 | core0x3a660, máscara de8 | M32[payload12+60] |
| 0x2d82c, STR W | 0x02073664 | core0x3a664, base fallback | u32(payload14_AP−0x02039000) |
| 0x2d850, STR W | 0x02073668 | core0x3a668, máscara de9 | M32[payload12+88] |

`0x2d728..0x2d734` publica o ponteiro do payload12 em S+616;
`0x2d758..0x2d764` publica payload14 em S+744. Ambos usam soma W32 e
SXTW. Depois há uma chamada `0x2d810→0x2d960`. A fatia final relê as duas
células de estado. A ABI dos registradores não garante preservação delas;
os testes variam registradores voláteis e mantêm a memória explicitamente.

A constante W0=`0xfdfc7000` equivale a **−0x02039000 módulo2³²**.
Assim, o ponteiro AP é convertido para core pela soma W em0x2d820;
não é copiado como ponteiro AP bruto para o firmware Thumb.

## Ligação ao construtor NEWTIME

O [callback de construção](newtime-record-hzc2.md) produz diretório em
R+0x1a0,16 descritores de16 bytes, com offset de payload em+4. Sob
R=AP0x02073600 e o alias SRAM, esse diretório é core0x3a7a0, exatamente a
base usada pelo [carregador e writer DMC](newtime-dmc-config-hzc2.md).
A origem deixa de ser apenas “RAM além da imagem”: existe um construtor
BL2 nominal correspondente. O conteúdo físico e sua preservação seguem abertos.

Com a fonte ECT embutida preservada, o descritor12 escolhe uma das tabelas
0x81/0x82/0x83, todas de1×23 palavras. As máscaras são células15 e22.
Enumerando as22 linhas e512 sequências de ramos relevantes:

| Tabela do descritor12 | Máscara8 | Máscara9 | Construções completas |
|---|---:|---:|---:|
| 0x81 | 0x1ff0 | 0x1fff | 4096 |
| 0x82 | 0x1fc0 | 0 | 4352 |
| 0x83 | 0 | 0 | 64 |

São8512 construções completas e2752 parciais/erro excluídas dessa tabela.
As contagens não são probabilidades nem frequências de boot. O log que
contém a chave da linha15 não comprova que essa construção rodou no aparelho.
Nos helpers Thumb originais, esses valores aceitam respectivamente níveis
4..12/0..12,6..12/nenhum e nenhum/nenhum. Isso descreve o teste de máscara,
não toda a execução ou os efeitos do handler9, que ainda tem sua cauda MMIO.

## A base fallback e o cache agora concordam sob condições

O descritor14 escolhe a tabela **0xa1**,2×44 u32, em todas as construções
completas. Seu offset de payload tem28 valores distintos nesses caminhos;
os grupos exportados combinam máscaras e offsets em34 perfis.

- BL2: `u32(u32(AP_RECORD+offset14)−AP_SRAM)` vai ao header+0x64.
- Carregador DMC: `u32(core0x3a600+offset14)` vai ao cache core0x38404.

Sob o mesmo descritor/alias, as expressões são iguais. Alterar o descritor
entre os dois caminhos quebra essa igualdade; há uma regressão para isso.
O fallback continua condicionado a cache zero, conforme a auditoria anterior.

A tabela0xa1 fornece h pela segunda palavra das linhas18..30 e g2 pelas
linhas31..43 para inputs0..12. O JSON exporta as células e os valores
lidos nas palavras Thumb reais; não atribui unidades físicas. Não há
checagem geral de limites inferida para outros inputs.

## Reprodução e limites

```sh
python3 scripts/inspect_newtime_dmc_bl2_producer_hzc2.py /caminho/sboot.bin --json /tmp/dmc-bl2.json
python3 -m unittest discover -s scripts -p 'test_newtime_dmc_bl2_producer.py'
```

[Extrator](../scripts/inspect_newtime_dmc_bl2_producer_hzc2.py),
[13 testes](../scripts/test_newtime_dmc_bl2_producer.py),
[JSON](references/newtime-dmc-bl2-producer-hzc2.json).
O extrator revalida o callback e o plano de construção anteriores pelo hash;
GNU confere34 palavras AArch64/20 operandos e55 instruções Thumb,
6 alvos relativos e8 literais. JSON reproduzido exatamente; imagem curta,
longa ou alterada recusa exit2 sem JSON. Suíte NEWTIME:573 testes passaram.

Avaliadores parciais decodificam as palavras reais: ponteiros SXTW e
conversão W,34 perfis, máscaras lidas em Thumb, cache/fallback e os valores
h/g2 para13 entradas. Casos aleatórios de offset verificam wrap sem
atribuir endereços válidos ao aparelho. Memória ausente falha.

Este é um produtor **condicional**, sem exclusividade: outras stores,
comandos de configuração, fontes alteradas, construção parcial e chamadas
opacas podem mudar o registro. Próximo: ordem/alcançabilidade efetiva da
publicação BL2 versus init/leitura DMC e aliases por fonte correspondente.
Slot47/X0, efeito físico e dados vivos permanecem abertos. Sem novo QEMU.
