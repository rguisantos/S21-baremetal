# HZC2: callback AVB de confiança da chave e consulta ao monitor

Análise estática de **2026-10-30 (Campo Grande)**, base main `6ea0c37` após
PR #58. Sboot de 4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; endereços de objetos são relativos ao modelo LK.
Nenhum firmware Samsung, SMC ou operação no telefone foi executado.

**Conclusão:** no caminho AVB selecionado, a confiança da chave passa pelo
callback `0x180d50`. Ele solicita ao monitor material de chave com o nome
`vbmeta` e compara os bytes recebidos com a chave candidata. O status da
consulta é devolvido separadamente do byte de confiança; o consumidor testa
o status primeiro. A igualdade entre essa chave fornecida pelo monitor e a
[chave embutida da PR #58](lk-embedded-avb-key-hzc2.md) continua sem prova.

## Quem instala e quem chama o callback

`0x180de8` constrói uma tabela de operações no endereço relativo `0xd05900`.
`0x180e70`, com argumento não nulo, exporta esse mesmo endereço por ponteiro.
O analisador decodifica ADRP/ADD, stores de pares e loads/calls indiretos para
ligar os campos abaixo. Não lê o conteúdo desse objeto como se estivesse no
arquivo nem presume que a tabela permaneça inalterada em execução.

| Campo da tabela | Escrita no inicializador | Uso selecionado |
|---|---|---|
| +48 | Segunda metade do STP em `0x180e58`, alvo `0x180d50` | LDR X6 em `0x122870`, BLR X6 em `0x122880` |
| +72 | Primeira metade do STP em `0x180e5c`, alvo `0x17ffd0` | LDR X2 em `0x17f690`, BLR X2 em `0x17f694` |

O wrapper chama inicializador e exportador em `0x17f678`/`0x17f680`, consulta
o campo +72 e passa a tabela a `0x1244b0` em `0x17f6b0`. Os campos correspondem
nominalmente a `validate_vbmeta_public_key` e `read_is_device_unlocked` na
referência AvbOps. Bindings, contexto, viabilidade e preservação reais não
foram observados. Outros flags e caminhos podem usar outros callbacks.

## Pedido de chave e comparação

O callback conserva X1 como chave candidata, X2 como comprimento e X5 como
ponteiro do byte `out_is_trusted`. Usa um buffer alinhado a 128 bytes dentro
da própria moldura de pilha e chama `0x180c50(buffer, comprimento, "vbmeta")`.
Não há referência direta ao objeto `0x31d740` nesse corpo local.

O helper solicita a zeragem de 64 bytes do pedido em `0xd058c0`, publica
ponteiro/comprimento/nome, faz manutenção de cache e chama `0xf6088`:

| Argumento ou campo | Valor nominal |
|---|---|
| X0 da SMC | `0xc200101d` |
| X1 da SMC | 16 (`0x10`) |
| X2 da SMC | Pedido relativo `0xd058c0` |
| X3 da SMC | 0 |
| Pedido +0 | Ponteiro u64 do buffer de saída |
| Pedido +8 | Comprimento u64 fornecido pelo chamador |
| Pedido +16 | Bytes do nome; comprimento aceito pelo teste local até oito |
| Pedido +24 | Comprimento do nome em u64, formado dos 32 bits baixos |

O nome literal tem seis caracteres. A mensagem de falha nomeia leitura de
AVB pubkey. Isso sustenta a interpretação nominal, sem reconstruir o serviço
seguro, seu armazenamento ou a chave ativa. O helper invalida o intervalo de
saída mesmo no caminho de erro, se a impressão retornar, e devolve os 32 bits
baixos do resultado. Não há conteúdo de chave recebido do monitor nesta análise.

`0x180d8c` chama o helper; W20 conserva seu resultado. Em erro, o callback
primeiro grava zero no byte de confiança, mas **continua a comparação** em
`0x180da8`. O comparador `0x1b2290` percorre o comprimento fornecido, incluindo
bytes zero; não é uma comparação terminada por NUL. Depois, `0x180db4`
sobrescreve o byte com o resultado de igualdade e `0x180dcc` devolve W20.
Assim, o byte sozinho não certifica sucesso da consulta. Os limites válidos
dos buffers/argumentos dependem também das etapas anteriores e do contexto.

## Como o consumidor separa status e confiança

O bloco `0x122884..0x122898` testa W0 antes de ler o byte em `frame+520`.
As classes abaixo são locais, sob retorno normal e preservação dos objetos:

| Resultado do callback | Byte final | Decisão selecionada |
|---|---|---|
| W0=1 | Qualquer | Encaminha erro OOM, valor 1 |
| W0 diferente de 0/1 | Qualquer | Seleciona erro de I/O, valor 2 |
| W0=0 | Zero | Seleciona chave rejeitada, valor 5 |
| W0=0 | Não zero | Continua as verificações restantes |

O ramo de chave rejeitada pode continuar no trecho `0x122898`, conforme um
flag local, após registrar erro 5. Não se generaliza essa tabela para rejeição
ou aceitação final do slot. Flags alternativos, chave de partição encadeada,
metadados e verificações posteriores possuem caminhos próprios. Um byte true
após falha da consulta não supera o teste anterior de W0 neste consumidor.

## Consulta de desbloqueio usada pelo wrapper

O callback +72 tem a string `exynos_read_is_device_unlocked`. Inicializa um
u32 local com 1 e consulta um gate em `0x8a6370`. Se o gate for 1, chama o
getter `0x10b8f8`; caso contrário, conserva o valor local. Devolve W0=0 e
escreve o booleano `valor_local != 1`. O retorno do getter não é testado.

O getter possui um **outro** gate, em `0x8a636c`. Se zero, retorna `0x40300`
sem gravar na saída; no outro caminho, copia o cache u32 de `0x8a5f44` e
retorna zero. Portanto, sob preservação, uma falha sem gravação mantém o
valor local 1 e produz false. Um valor de cache diferente de 1 produz true;
o trecho não valida um domínio booleano para o cache.

Isso fecha a semântica local do callback. Não é uma nova medição OEM, KG,
FRP ou ro.boot.flash.locked do aparelho. O wrapper entrega esse byte como
flags W3 ao slot verifier, com W4=0. Na referência upstream, o bit 0 se
chama `ALLOW_VERIFICATION_ERROR`.

O trecho posterior conserva o resultado em W24 e seleciona rótulos:

| Byte de desbloqueio preservado | Resultado do slot verifier | Rótulo local |
|---|---|---|
| 1 | 0, 3, 4 ou 5 | `orange` |
| 1 | Outros valores u32 | `red` |
| 0 | 0 | `green` |
| 0 | 5 | `yellow` |
| 0 | Outros valores u32 | `red` |

O intervalo 3..5 vem de SUB W/CMP/B.LS unsigned em `0x17f6c4..0x17f6cc`.
Os nomes correspondem nominalmente a erro de verificação, rollback e chave
rejeitada no header de referência. Os trechos selecionam strings e convergem
para processamento posterior; **rótulo não é autorização ou prova de boot**.
O retorno completo e as ações posteriores do wrapper continuam abertos.

## Fontes e reprodução

A referência de ABI e nomes dos resultados é o mirror AOSP
AndroidBootloader/platform_external_avb, commit
`b27a9aa53d2db7720e4d88d6950dcd979da97de3`:

- [avb_ops.h](https://github.com/AndroidBootloader/platform_external_avb/blob/b27a9aa53d2db7720e4d88d6950dcd979da97de3/libavb/avb_ops.h), SHA-256 `04e2adaaf6aae58073376afebbd6e9d699d44557681374905561e93a479f0774`.
- [avb_slot_verify.h](https://github.com/AndroidBootloader/platform_external_avb/blob/b27a9aa53d2db7720e4d88d6950dcd979da97de3/libavb/avb_slot_verify.h), SHA-256 `21bd02f65875e7cbdbd7166cee8a50d099bd9564883a50eb5342229ed7900ed4`.

Esses fontes corroboram contrato e nomes, sem serem declarados fonte
correspondente do fork Samsung. As decisões descritas vêm das instruções
HZC2, não de uma suposição de que o fork inteiro seja igual ao upstream.

```bash
python3 scripts/inspect_lk_avb_trust.py /caminho/sboot.bin
python3 scripts/test_lk_avb_trust.py -v
```

O [relatório](references/lk-avb-key-trust-hzc2.json) confere 342 palavras GNU,
58 destinos relativos, 44 operandos selecionados e 11 literais em 17 grafos locais. Os grafos
mantêm chamadas opacas e saídas do recorte como
fronteiras; não executam registros, memória ou serviços. Treze testes novos
de binding/recusa passaram sem firmware, além das regressões 17/12 das
PRs #58/#57. O CI executa os testes novos antes do baseline R10.

Foi fechado o binding nominal do callback e seu fornecedor imediato. A
chave efetiva e a implementação do pedido seguro continuam fronteiras.
Próximo: verificador criptográfico `0x1262b0` e decisão do wrapper
`0x17f5d0` sobre o resultado de `0x1244b0`. Carga física, posse/coerência de
memória e aquisição dos 128 bytes continuam pendentes na
[matriz Samsung](samsung-diagnostic-contract.md).

[Validação local](references/lk-avb-key-trust-validation-20261030.json): relatório reproduzido byte a byte, 13 testes novos, regressões 17/12 e baseline completo de nove etapas aprovados; links de arquivos conferidos.
