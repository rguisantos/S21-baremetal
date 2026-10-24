# HZC2: proveniência do layout HASH e limites das referências

Continuação de **2026-10-23 (Campo Grande)**, após o merge do PR #5
(`2df91f32`). Usa o mesmo sboot HZC2 identificado por SHA-256; não executa
firmware ou serviços. O [protocolo anterior](epbl-protocol-hzc2.md) conserva
o fluxo 48 → material 32/IV 16 e a comparação final de 32 bytes.

**Avanço:** dez offsets HASH e o arranjo DMA alto/baixo/tamanho agora têm
corroboração em referências de implementação identificadas. Isso refina a
origem dos nomes e a entrada candidata `[0x1fc00,0x1fffc)`. O modo `0x19`
continua sem algoritmo HZC2 demonstrado; fontes de outra versão não podem
substituir seus dados de entrada ou sua resposta real.

## Fontes e perfis distintos

| Referência | Revisão fixada | Escopo e base declarada |
|---|---|---|
| Header ACE Samsung distribuído em meizuosc/m462 | `a2a3737c06577015d8d3f6c6aa36e53c90d57d5b` | perfil `CONFIG_ACE_USE_SSS_VER_6`, base `0x11100000` |
| Fireplace: headers, implementação HASH e README | `262ff996ee411f0975cdbdfe059d67b4060bb7d7` | emulador experimental Exynos9830/SM-G986B, base `0x1a520000` |
| Instruções HZC2 recebidas | sboot SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91` | base construída pelo prefixo `0x18330000` |

Os cinco arquivos externos são verificados por **SHA-256 e blob Git**, com
leitura limitada a 64 KiB. O header ACE é somente pré-processado com
`cc -E -dM -nostdinc -DCONFIG_ACE_USE_SSS_VER_6`; nenhum código C é compilado
ou executado. O leitor resolve uma gramática pequena de expressões inteiras,
sem `eval`, com limites de profundidade, deslocamento e tamanho. O switch
HASH do emulador é lido por gramática restrita, preservando os casos e
rejeitando comandos desconhecidos.

URLs, hashes e caminhos completos estão no [manifesto](references/epbl-hash-sources-hzc2.json).
As definições estabelecem o comportamento dessas fontes, não uma medição
ou especificação correspondente do hardware HZC2.

## Offsets corroborados

| Campo nas referências | Offset relativo comum | Evidência HZC2 |
|---|---|---|
| seletor HASH | `+0x1000` | configuração `0x19`, depois ramo com `0x14` |
| FIFO/controle | `+0x1008` | escrita de 1 |
| status | `+0x1010` | leituras e testes/acknowledgements |
| tamanho baixo/alto | `+0x1020 / +0x1024` | palavras preparadas no prefixo |
| comprimento anterior baixo/alto | `+0x1030 / +0x1034` | transferências de contexto conferidas abaixo |
| início de material HMAC | `+0x1100` | primeiro word dos 32 enviados |
| início do estado IV | `+0x1180` | percurso condicional de restauração |
| início do resultado | `+0x11c0` | leituras do prefixo |

São **dez definições de offset**, não dez chamadas medidas. O header ACE
nomeia explicitamente 16 words de material e oito de resultado, enquanto a
primeira etapa HZC2 escreve 32 e lê 12. Essa cobertura parcial impede tratar
o header como descrição completa da primeira etapa.

O Fireplace nomeia `+0x40/+0x44/+0x48` como endereço alto/endereço baixo/tamanho.
Aplicados às palavras HZC2 `0 / 0x1fc00 / 0x3fc`, corroboram a entrada candidata
em `0x1fc00`, de 1020 bytes, fim exclusivo `0x1fffc`. Continuam sem prova o
binding físico, o conteúdo dessa região e sua classificação como ROM/RAM.
Nenhum BootROM Exynos9830 foi usado como se fosse a entrada HZC2.

## O seletor 0x19 não foi identificado por analogia

O switch do Fireplace implementa `0x10/0x11`, `0x14/0x34/0x15` e
`0x1a/0x1b`. Ele define SHA-256 sem HMAC para `0x14`, SHA-512 para `0x1a`
e HMAC-SHA-512 para `0x1b`; **`0x19` cai na rejeição padrão**.

Já o header ACE legado associa seu nibble `0x9` a um nome de operação
externa HMAC-SHA1. Com o bit de start `0x10`, a expressão também resulta
em `0x19`. Isso demonstra a ambiguidade de versões: não autoriza chamar
esse modo HZC2 de HMAC-SHA1, SHA-384, HMAC-SHA384 ou SHA-512.

O tamanho de 48 bytes lido pelo código tampouco resolve o algoritmo. Não
foram acrescentados retornos de sucesso, dados fabricados, ensaios de chave
por tentativa ou um algoritmo ao emulador. O comportamento de recusa da
referência é preservado no relatório.

## Correção da ordem dos contadores

A documentação do PR #5 havia chamado alto/baixo na ordem inversa. O código
original e o inventário MMIO estavam corretos; agora o relatório inclui os
loads/stores que ligam explicitamente cada campo:

| Origem no contexto do wrapper | Load/Store | Destino MMIO | Nome nas duas referências |
|---|---|---|---|
| `+0x44` | `0x3ebc / 0x3ec0` | `+0x1030` | baixo |
| `+0x40` | `0x3ecc / 0x3ed0` | `+0x1034` | alto |

Dois testes novos recusam a troca dessas origens. O wrapper mantém ambos
zero no ramo descrito; a correção não altera R10, firmware ou resultado de
execução. Não mede o estado do contador no aparelho.

## Reprodução e resultados

Com os arquivos externos exatos indicados no manifesto:

```sh
python3 scripts/check_epbl_hash_sources.py /caminho/sboot.bin \
  --ace /refs/ace_sfr.h \
  --internal /refs/fireplace_sss_internal.h \
  --public /refs/fireplace_sss.h \
  --hash /refs/fireplace_sss_hash.c \
  --readme /refs/fireplace_README.md
(cd scripts && python3 -m unittest test_epbl_hash_sources test_epbl_protocol test_epbl_frontier test_epbl_preparation -v)
```

**83 testes passaram:** 12 do leitor de fontes, 35 de protocolo (incluindo os
dois novos de contadores), 18 de fronteiras e 18 da preparação. A comparação
foi executada com os cinco arquivos reais verificados. O relatório de
protocolo foi reemitido com os vínculos novos; a conferência GNU mantém
1095 palavras/114 destinos/177 acessos MMIO.

- [Comparação, fontes e limites](references/epbl-hash-sources-hzc2.json)
- [Saída dos 83 testes](references/epbl-hash-sources-host-tests.txt)
- [Protocolo com os campos de contador ligados](references/epbl-protocol-hzc2.json)

A revisão do PR #5 terminou sem achados bloqueadores e foi mergeada. A
orientação permanente agora inclui revisão, correção dos bloqueadores,
merge do head revisado e sincronização da main, além de commits e organização.

**Próxima lacuna técnica:** implementação correspondente ao modo HZC2 `0x19`,
conteúdo verificável da entrada candidata ou saída real de 48 bytes. Um
emulador com offsets semelhantes continua sem esse contrato. Vetores e
handler `-0x3ff` permanecem pendentes; recuperação do diagnóstico no S21
segue em paralelo conforme o [roadmap](roadmap.md). Não houve ensaio físico
ou novo QEMU nesta entrega.

Continuação de 2026-10-24: o [TZAR do próprio HZC2](tzar-crypto-hzc2.md)
foi descomprimido e inventariado. A fronteira EVP/dispositivo e a tradução
de seletores agora estão localizadas, ainda sem binding ao modo EPBL `0x19`.
