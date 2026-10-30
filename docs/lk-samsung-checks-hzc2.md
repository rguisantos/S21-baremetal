# LK HZC2: pedido de assinatura, rollback e política de binário personalizado

As três rotinas chamadas pelo [processamento de partições](lk-build-id-partitions-hzc2.md)
têm papéis distintos: `0x1526f8` seleciona nomes e prepara verificação pelo
monitor, `0x150aa8` compara revisões para rollback e `0x1516b8` executa
política/efeitos de erro para binário personalizado. Os retornos zero
dessas camadas não significam todos a mesma coisa; nenhum deles comprova
aceitação física de uma Image no telefone.

Base main `bf39300`, após PR #62. `sboot.bin` HZC2 de 4.194.304 bytes,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo. O delta nominal VA−arquivo `0xe7f14000` traduz
ponteiros iniciais, sem medir endereço físico, RAM livre ou estado vivo.
Nenhuma instrução Samsung, SMC ou operação no telefone foi executada.

## Seleção de nomes e pré-checagem

`0x1526f8` recebe nome, base e tamanho W32. Copia 208 bytes da tabela
`0x23e298`: são 26 ponteiros para nomes C comparados integralmente, com
distinção de caixa. Se nenhum nome coincide, retorna 0 **sem esse pedido**
de verificação. Isso não descreve os controles anteriores/posteriores ou
os chamadores indiretos do boot inteiro.

O extrator conserva exatamente os 26 nomes, incluindo o último:
`VDDCAL_FWINIT_BOOT`, uma única string NUL-terminada em `0x240548`.
`INIT_BOOT` e `VDDCAL_FW` isolados não são entradas dessa tabela. Não se
atribui intenção a essa concatenação nem se corrigem os bytes para nomes
esperados. A tabela também contém BOOT, RECOVERY, DTBO, VBMETA,
VBMETA_SYSTEM e VENDOR_BOOT, entre outros; lista completa no relatório.

Para um nome correspondente, o seletor forma:

| Argumento derivado | Fórmula local |
|---|---|
| SignInfo para `0x152428` | base + SXTW(tamanho W32) −0x310 |
| Trailer para `0x1525f8` | base + SXTW(tamanho W32) −0x210 |

A primeira fórmula é usada **antes** do teste signed tamanho>512. Esse
teste isolado não estabelece que todos os bytes ou ambos os intervalos
estejam dentro da imagem; a aritmética e os callees não foram certificados
como seguros para toda entrada.

`0x152428` pula sua comparação de nome se o bit 17 consultado estiver limpo
ou o nome for PIT, DPM ou VDDCAL_FW. Caso contrário, exige prefixo Signer
reconhecido, obtém informações da partição e compara o prefixo em
SignInfo+156 com o nome de referência em partinfo+68. Ausência/divergência
seleciona retorno −1, com caminhos de UI/log; igualdade seleciona 0. A
comparação usa `strlen(SignInfo+156)`, não igualdade integral garantida.
Origem do flag, buffers e validade das informações continuam pendentes.

## Pedido ao monitor e tradução de resultado

`0x1525f8` escolhe modo 14 por padrão. Se a consulta com argumento 4 retorna 0,
base≤`0x94000000` e a soma u64 base+SXTW(tamanho) é maior que `0x93ffffff`,
seleciona modo 16. A soma segue a aritmética da instrução; não é prova de
limites, ausência de wrap ou localização física da imagem. Ambos os modos
chamam `0x17dbc0`.

| Elemento | Valor preparado no caminho selecionado |
|---|---|
| SMC X0 | `0xffffffffffffff10` |
| X1 | Modo 14 ou 16, passado por W1 e estendido com zeros |
| X2 | Descritor na pilha, alinhado em 128 bytes |
| X3 | 0 |
| Descritor+40 u64 | Base da imagem |
| Descritor+48 u64 | Comprimento recebido em X1; caller fornece SXTW do tamanho W32 |
| Descritor+56 u64 | Ponteiro para trailer/assinatura |

O código solicita limpeza de cache para 192 bytes do descritor, para a
imagem e para 528 bytes do trailer. Só essas três stores no descritor foram
identificadas nesse corpo; a inicialização dos demais bytes não foi
estabelecida. Não se inferem zeros ou significado dos campos restantes.
O resultado do monitor retorna pelo wrapper sem uma observação física.

O caller interpreta apenas o low32 do retorno:

| Low32 retornado pelo pedido | Resultado local de `0x1525f8` |
|---|---|
| 0 | 0 |
| 0xffffffff | Imprime “non-secure chip. Skip” e retorna 0 |
| Outro não zero | Imprime falha e retorna −1 |

A mensagem do segundo ramo não mede o estado seguro real do S21.
`Verify_Signature_Ecdsa` é um nome de diagnóstico do arquivo, sem prova
da implementação/algoritmo executado no monitor. Este serviço também é
distinto do pedido de chave `0xc200101d`/sub16 da análise AVB anterior.

## Revisão para rollback

`0x150aa8` rejeita ponteiro nulo com −1. Se o campo u64 context+64 for zero,
imprime skip do commercial bit e retorna 0. Com o campo não zero, lê os
bytes 136..138 do registro e calcula, em W32:

`100*(byte136−'0') + 10*(byte137−'0') + (byte138−'0')`

Não há validação local de que sejam dígitos; subtrações/somas usam wrap
u32. O índice por nome é BOOT 0, RECOVERY 1, DTBO 2, VBMETA 3, VENDOR_BOOT 4,
INIT_BOOT 5; outros nomes devolvem índice −1. Esse mapa é separado da tabela
de 26 nomes da assinatura.

| Comparação unsigned | Comportamento local |
|---|---|
| Contador do dispositivo > revisão calculada | Log/UI de KERNEL REV. CHECK FAIL, depois retorno −1 se os callees retornarem |
| Contadores iguais | Retorno 0 |
| Contador do dispositivo < revisão | Chama `0x150800` para atualização e força retorno 0 sem testar o status da atualização |

O getter `0x1509b0` tem caminhos de fallback: para índices 0..5, retorna 19
se gates/leitura/valor não satisfazem os testes locais; para outros índices
aceitos usa 0 nesses fallbacks, e índice unsigned>64 retorna 0. O backend
`0x10ada0` e a atualização `0x150800` permanecem opacos nesta entrega.
**19 é um fallback do código**, não uma nova medição de RPMB/efuse, nem
prova de que um contador foi atualizado com sucesso.

## Política de binário personalizado

`0x1516b8` consulta o helper `0x1558a8`. Para os dois u64 do contexto em
`+160/+168`, esse getter retorna: (0,0)→0, (0,1)→1, (1,1)→2 e outros→−1.
A rotina testa especificamente 1 e também compara o cache relativo
`0xcd63a0` aos prefixos Prenormal/Locked/Active/Error, sem distinção de
caixa ASCII. Getters repetidos não foram assumidos estáveis em execução.

Os caminhos contêm diagnósticos de binário oficial, saldo de parcelamento,
OEM Lock e CC Mode, além de chamadas ao registrador de erro `0x156310`,
UI/espera e pedidos de modo. Seus predicados externos e efeitos continuam
fronteiras. Não se mede KG/OEM/FRP pelo nome de uma string.

O corpo não contém RET local. Há uma saída de cauda para `0x150330` e um
laço de consulta de entrada em `0x151920`, cujas continuações dependem dos
callees. O destino de cauda contém diagnósticos EFUSE/warranty bit: campos
context+72/+80 escolhem ramos de skip ou chamadas a `0xf88c0/0xf8968`.
Essas chamadas não foram executadas nem tiveram seus efeitos físicos
demonstrados. A política não é tratada como um bool simples de autorização.

## Reprodução e limites

```bash
python3 scripts/inspect_lk_samsung_checks.py /caminho/sboot.bin
python3 scripts/test_lk_samsung_checks.py -v
```

O [relatório](references/lk-samsung-checks-hzc2.json) confere 801 palavras
GNU, 211 destinos relativos, 75 operandos, 19 literais, 14 grafos e 26 entradas
de tabela, com identidade do firmware exigida antes do GNU. O parser de
nomes usa limites de arquivo/ASCII/NUL como política conservadora do
analisador; esses limites não são atribuídos ao firmware.

Dezesseis testes novos conferem nomes/ponteiros exatos, concatenação, ordem,
duplicatas, terminadores, limites e escritas no descritor. Não executam
firmware ou pedidos seguros. Regressões AVB 48 e Build-id 14 passaram;
baseline completo de nove etapas aprovado e
[validação reproduzível](references/lk-samsung-checks-validation-20261030.json).

Os corpos locais das três camadas deixam de ser lacunas. Continuam abertos
o serviço seguro `0xffffffffffffff10`, a aquisição/persistência dos
contadores, os predicados de política e o fornecedor da chave AVB. Carga,
memória e captura do [diagnóstico físico](samsung-diagnostic-contract.md)
permanecem sem prova. Nenhuma conclusão desta entrega é autorização para
gravar ou executar firmware no aparelho de uso pessoal.

Continuação: o [backend dos contadores e pedidos RPMB](lk-rpmb-hzc2.md) liga `0x10ada0`/`0x10ade0` ao dispositivo `scsirpmb` e aos pedidos seguros de nonce/MAC. Distingue a célula de revisão do contador de escrita e documenta a ordem dos resultados; persistência permanece sem prova.
