# LK HZC2: retornos do wrapper AVB e tratamento pelo chamador

O wrapper `0x17f5d0` tem dois RET locais: um devolve o resultado do slot
salvo em W24; o outro devolve `0xfdaa4002`. O chamador direto selecionado
descarta esse retorno imediatamente. **Isso não estabelece um bypass:**
se o rótulo nominal permanecer `red`, o wrapper alcança um laço fixo antes
do retorno normal; serviços seguros e outros callees também podem impedir
essa continuação. A análise fecha o corpo local e o consumo imediato do
retorno, sem demonstrar aceitação física de uma Image.

Base main `3eda261`, após PR #60. Sboot HZC2 de 4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo. O delta nominal VA−arquivo `0xe7f14000` não
mede endereço físico, RAM disponível ou preservação em execução. Nenhum
firmware Samsung, SMC ou procedimento no telefone foi executado.

## Do resultado AVB ao restante do wrapper

A [análise do callback](lk-avb-key-trust-hzc2.md) já delimitou a atribuição
inicial de `green/yellow/orange/red` após `0x1244b0`. O resultado do slot é
salvo em W24 por `0x17f6b4` e conservado até o epílogo normal.

Após a convergência em `0x17f724`, o wrapper percorre cinco nomes e chama
`0x17e920` para os que não são excluídos pelo modo/prefixo local. A lista
contém `vbmeta`, `recovery`, `dtbo`, `boot`, `vendor_boot`; `init_boot` é
outro prefixo excluído no ramo recovery. Esse processamento de partições
permanece opaco nesta entrega, assim como o helper opcional `0x17e828`.

Há ainda uma verificação adicional em `0x17deb0`, selecionada no caminho
inicialmente green, fora do modo recovery e com campo relativo
`0xaaa710` igual a 1. Um retorno negativo desse helper causa chamada a
`0x156310`, sobrescrita do rótulo por `red` e entrada no caminho de falha.
Zero/não zero não negativo participa da seleção de mensagem. Isso mostra
que a classificação inicial não encerra o processamento.

As mensagens de authentication success/fail são construídas antes do
dispatch final. Comparações com `red` e `yellow` selecionam chamadas a
`0x156310/0x12ecc8`; `orange` pode passar por uma espera que consulta outro
bit de modo, tempo e entrada. Não se atribui unidade física ao limite
10000, tecla específica ou resultado dos callees sem uma prova adicional.
Os dois ramos escrevem zero/um no campo relativo `0xd05880`; o chamador
posteriormente o lê e o passa a `0x1536e0`. Portanto há efeitos persistentes
além do valor de retorno.

## Dispatch final, códigos e saídas

O byte inicial do rótulo, menos `'g'` em aritmética W32, indexa 19 bytes
na tabela `0x258328`. Os deslocamentos são signed byte×4 sobre `0x17fa34`.
O extrator resolve ADRP/ADD e ADR, confere os literais e decodifica os
MOVs que materializam os códigos em W25.

| Rótulo nominal | Alvo da tabela | Código W25 | Continuação local |
|---|---|---|---|
| green | 0x17fbe8 | 0 | Helper de informações e caminho ao epílogo normal |
| yellow | 0x17fa38 | 1 | Helper de informações e caminho ao epílogo normal |
| orange | 0x17fbe0 | 2 | Helper de informações e caminho ao epílogo normal |
| red | 0x17fbb0 | 3 | Helper de informações e, se ainda red, laço em 0x17fb40 |

Os outros quinze índices da tabela levam ao epílogo de erro. Byte inicial
fora de `'g'..'y'` também pode levar a esse epílogo; o teste W32 evita tratar
um valor menor que `'g'` como índice negativo aceito. A escolha local usa
somente o primeiro byte; não é uma comparação integral do nome nessa etapa.

| Ponto | Comportamento observado estaticamente |
|---|---|
| 0x17f938 e 0x17f950 | MOVZ/MOVK W0 compõem `0xfdaa4002` (signed32 −39174142) |
| 0x17f958 | RET do erro de dispatch, sem reinterpretar esse código como resultado AVB |
| 0x17fb38..0x17fb40 | Comparação de prefixo com `red`; igualdade alcança `B 0x17fb40` |
| 0x17fb8c..0x17fba8 | W0 recebe W24 e a função retorna após restaurar o frame |

O laço tem uma instrução, nenhum RET e nenhuma chamada. É a topologia local
sob o rótulo e os retornos normais requeridos; não comprova comportamento
de interrupções, exceções, resets ou outras threads no aparelho. Os demais
rótulos podem chegar ao retorno normal se os callees intermediários
retornarem e preservarem o estado esperado.

## Informações enviadas ao monitor

Os dois pontos `0x17fa4c/0x17fbc4` chamam `0x17f378` com estado de lock
derivado do byte de read_unlocked, código da cor e ponteiro de dados do
slot. O helper prepara chave e metadados e chama wrappers de pedidos
seguros. Foram conferidos os fragmentos de argumentos e as instruções
SMC; os corpos completos desses wrappers e o monitor continuam fora do
escopo transitivo.

Todos os pedidos abaixo usam X0=`0xc200101d`; os nomes são corroborados
pelos literais de diagnóstico do próprio arquivo, não por execução dos
serviços.

| Pedido nominal | Helper | X1 | Dados preparados pelo caminho selecionado |
|---|---|---|---|
| Chave pública | 0xf6a00 | 3 | Cópia da chave do vbmeta e comprimento |
| Versão/patch do OS | 0xf6c30 | 10 | Campos derivados do header boot em 0x94000000+16 e cache |
| Patches vendor/boot | 0xf6ce8 | 17 | Dois campos em cache |
| Estado de lock | 0xf6da0 | 4 | Valor recebido pelo helper |
| Estado de boot/cor | 0xf6e50 | 9 | Código 0/1/2/3 recebido pelo helper |
| Verified boot hash | 0xf6b70 | 18 | Buffer relativo 0xaaa718, comprimento nominal 32 |
| Bloquear comandos de verified boot | 0xf6f00 | 11 | X2=X3=0 no fragmento do pedido |

Nenhum conteúdo ou resultado efetivo foi observado. O pedido de chave
**3** não resolve a implementação que atende ao pedido de leitura **16**
do callback anterior, nem prova igualdade com a chave embutida.

O helper trata ponteiro de slot nulo, comprimento de chave zero e retornos
dos pedidos intermediários por caminhos locais distintos. Antes de
retornar, chama `0xf6f00`; seu retorno é sobrescrito pelo status já salvo
em W19. No wrapper externo, o status de `0x17f378` é testado apenas para
imprimir Root of trust error; ambos os ramos convergem para a publicação
de metadados e o teste de `red`. Essa continuação local não certifica
sucesso do monitor ou tratamento de todas as falhas.

## Chamador e limite da conclusão

A busca de encodings B/BL alinhados em `[0xec000,0x20c630)` encontra um
referenciador direto de `0x17f5d0`: `BL` em `0xfbc68`, confirmado no GNU.
Chamadores indiretos ou outros intervalos não são enumerados por essa busca.
Na volta, `0xfbc6c` executa **ADRP X0**, sobrescrevendo o retorno antes de
qualquer teste dele. O corpo local `0xfbc10..0xfbf48` contém a continuação
nominal até o handoff, incluindo leituras, chamadas e serviços que ainda
podem ter efeitos de segurança próprios.

Não existe ali um teste adicional do W0 devolvido pelo wrapper. Isso fecha
o consumo imediato do retorno; **não elimina** o laço red, os efeitos dos
metadados, a verificação anterior do slot ou os serviços seguros. Não é
uma autorização para alterar o firmware do aparelho. Os contratos de carga,
memória e aquisição dos 128 bytes do [diagnóstico](samsung-diagnostic-contract.md)
continuam pendentes.

## Reprodução e validação

```bash
python3 scripts/inspect_lk_avb_boot.py /caminho/sboot.bin
python3 scripts/test_lk_avb_boot.py -v
```

O [relatório](references/lk-avb-wrapper-hzc2.json) confere 847 palavras GNU,
220 destinos relativos, 86 operandos selecionados, 20 literais incluindo
quatro cores, 13 grafos locais e sete pedidos SMC. As chamadas opacas têm
apenas continuação condicionada ao retorno normal; BR interrompe a expansão
e a tabela final é registrada separadamente. Os grafos não avaliam
registradores, viabilidade ou memória.

Dezessete testes novos cobrem MOVZ/MOVN/MOVK W32/X64, preservação/substituição
de halfwords, instruções reservadas e sequência inválida, busca alinhada
B/BL, controles diferentes, limites e recusa da imagem antes do GNU. São
testes sintéticos de host, sem execução de firmware. As regressões AVB
anteriores e os 14 testes de grafos de retorno também passaram.
[Validação local](references/lk-avb-wrapper-validation-20261030.json),
incluindo reprodução byte a byte e baseline completo de nove etapas.

A próxima fronteira é `0x17deb0` e o processamento de partições
`0x17e920/0x17e828`, além do fornecedor seguro da chave e da origem da
continuação tolerada no slot. O corpo local do wrapper e seu retorno
imediato deixam de ser lacunas; a aceitação física continua sem prova.
