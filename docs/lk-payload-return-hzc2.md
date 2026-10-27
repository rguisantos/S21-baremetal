# LK HZC2: continuação de retorno da Image

Análise estática de **2026-10-26 (Campo Grande)**, base `3cc06d6`, após o
PR #36. Sboot de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo. O delta nominal LK `0xe7f14000` resolve os
ponteiros iniciais; não é medição de endereço no aparelho.

**O LK contém uma continuação depois da Image, mas o retorno normal
selecionado segue para o wrapper de `sbl_boot` e depois para `thread_exit()`.
Não há transferência direta ao RDX nos blocos de retorno examinados.**
Isso fecha o destino nominal do retorno, sem validar um contrato para a
Image retornar, preservação de RAM ou execução no telefone. A sonda continua
inalterada, estacionando em WFE conforme a [análise anterior](lk-rdx-memory-origin-hzc2.md).

## Continuação imediata e valor devolvido

A função do handoff começa em `0xfbc10`, reserva 0x50 bytes e salva X29/X30,
X19/X20 e X21. O salto da Image é `BLR X4` em `0xfbe14`. Se a Image retornar
normalmente pelo link produzido por essa chamada, a continuação é:

| PC | Operação |
|---|---|
| `0xfbe18` | `MOV W0,#0`: descarta o valor retornado pela Image |
| `0xfbe1c` | Recupera X19/X20 da pilha |
| `0xfbe20` | Recupera X21 da pilha |
| `0xfbe24` | Recupera X29/X30 e avança SP em 0x50 |
| `0xfbe28` | `RET`, usando o X30 recuperado |

O link corresponde nominalmente a `0xe800fe18` sob o delta declarado.
`BLR` fornecer um link não transforma o protocolo de entrada da Image em
uma ABI de retorno validada. A [auditoria anterior](lk-final-edges.md)
parava antes da execução da Image; esta entrega inspeciona a continuação
sem executar nenhuma instrução do firmware.

## Aplicação, wrapper e thread

O descritor inicial em `0x29b030` tem 40 bytes. Seu nome aponta para
`sbl_boot` em `0x2161e8`, o campo init é zero e o entry em +0x10 aponta
nominalmente a `0xfab48`. Flags em +0x18 e campo de pilha em +0x20 são zero.
O laço `0xfaa60` usa esse descritor com passo 0x28; no ramo de thread,
flags bit 0 limpo permite a criação e bit 1 limpo seleciona pilha padrão
de 0x100000 bytes. São dados iniciais do arquivo, mutáveis em execução.

`0xfaab8` monta o wrapper `0xfaa40`. Em `0xfab00–0xfab10`, o laço passa
nome, wrapper e descritor a `0x11a1e0`; o adaptador encaminha esses argumentos
a `0x11a068`. Os stores `0x11a0b8` e `0x11a0c8` publicam função e argumento
em +0x270/+0x278 do objeto da thread. O preparador `0xfa5f8` instala
`0xfa5d0` no contexto de pilha inicial. O switch `0xf9aa8` carrega o novo
SP e X30 e termina em RET. Isso liga o template de entrada, sem simular o
escalonador ou provar a thread ativa.

| Ligação nominal | Continuação se retornar normalmente |
|---|---|
| Bootstrap `0xfa5d0`: lê função/argumento do objeto via TPIDR_EL1 e faz BLR em `0xfa5f0` | `0xfa5f4` |
| Wrapper `0xfaa40`: lê entry de descritor+0x10 e faz BLR em `0xfaa50` | `0xfaa54` |
| Entry `0xfab48`: os dois ramos recuperam seu frame e fazem B para `0xfbc10` em `0xfabb4`/`0xfabf0` | O B conserva o link `0xfaa54` do wrapper |
| Handoff `0xfbc10`: chama a Image em `0xfbe14` | `0xfbe18` e epílogo até RET |
| Wrapper após retorno, `0xfaa54–0xfaa5c` | Força W0=0 novamente, recupera X29/X30, avança SP em 16 e retorna a `0xfa5f4` |
| Bootstrap após retorno, `0xfa5f4` | Chama diretamente `0x11aba8`, identificado pela string `thread_exit()` |

O valor que a Image hipotética devolvesse não seleciona o modo upload:
é descartado em `0xfbe18`, e o wrapper também impõe zero. A thread recebe
status zero por essa cadeia nominal, se os frames e o contexto forem os
mesmos dos produtores examinados.

## Saída da thread e fronteiras

`0x11aba8` lê a thread de TPIDR_EL1. Grava W0 em +0x280 no PC `0x11abd8`
e estado 5 em +0x2c no PC `0x11abe0`. Seus ramos contêm chamadas de limpeza
e fila e convergem para `0x119f28`, o escalonador identificado no código.
O conteúdo completo dessas chamadas e o contexto das outras threads não
foram reconstruídos nesta entrega.

Se a chamada ao escalonador retornar por seu link normal, o bloco seguinte
encaminha a string `somehow fell through thread_exit()` para `0x18f8a8`.
Esse corpo referencia `panic (caller %p): ` e termina num ciclo de chamadas,
sem RET local. Também não há RET no corpo local de `thread_exit()`, mesmo
conservando uma continuação condicional para cada chamada opaca.

A fronteira `0xfa5f8`, registrada depois do BL de `0xfa5f4`, existe apenas
se `thread_exit()` retornar normalmente; os grafos locais não oferecem tal
RET. O endereço é o início do preparador de contexto seguinte, não um
callback RDX. Não é tratado como caminho normal de retomada.

Nenhum desses blocos locais chama diretamente `0x15e210`, `0x15e578` ou
`0x116f18`, os pontos RDX selecionados anteriormente. Isso **não demonstra
ausência global de RDX**: callees opacos, panic, scheduler, callbacks mutáveis,
reset e outras threads podem ter outros efeitos. O levantamento prova o
destino nominal do retorno e delimita as dependências restantes.

## Contexto que um retorno exigiria conservar

Se K for o SP na fronteira do handoff e no retorno hipotético da Image, os
epílogos leem:

| Endereço relativo a K | Valor requerido pela cadeia nominal |
|---|---|
| +0x00 / +0x08 | X29 salvo / X30 salvo, este apontando ao wrapper em `0xfaa54` |
| +0x10 / +0x18 / +0x20 | X19 / X20 / X21 salvos |
| +0x50 / +0x58 | X29/X30 do wrapper, este apontando ao bootstrap em `0xfa5f4` |

O primeiro epílogo deixa SP=K+0x50; o segundo, SP=K+0x60. Os valores e a
acessibilidade desses bytes não foram medidos. Os dois epílogos têm apenas
operações GPR/SP e controle, sem instrução para restaurar SCTLR, DAIF ou
TPIDR. O bootstrap limpa o mascaramento IRQ antes de chamar a função,
em `0xfa5e4`; isso não é uma restauração posterior ao payload.

Seria necessário estabelecer estado de execução compatível, validade da
pilha, contexto de thread/serviços e preservação dos valores necessários.
A sonda atual mascara DAIF e não captura X30 no formato S21ENTRY v1.
O registro de entrada existente não valida esse contrato de retorno.
Esta análise não acrescenta RET ou salto para um offset do LK à sonda.

## Decisão e reprodução

A hipótese “fazer a Image retornar já coloca o aparelho em RDX” não é
sustentada pela continuação nominal: ela termina a aplicação. Um mecanismo
de observação cooperativa precisa especificar quem executará o produtor do
dump, com qual contexto e quais bytes preservados. Isso é requisito adicional
ao percurso de carga compatível e à [matriz de aquisição](samsung-diagnostic-contract.md).
Um reset permanece dependente de prova de retenção.

```bash
python3 scripts/inspect_lk_payload_return.py /caminho/sboot.bin
python3 scripts/test_lk_payload_return.py -v
python3 -m unittest discover -s scripts -p test_lk_final_edges.py -v
```

[Relatório reproduzível](references/lk-payload-return-hzc2.json) e
[validação](references/lk-payload-return-validation-20261026.json).
O extrator confere 294 palavras GNU, 57 destinos relativos e 58 operandos
selecionados. Os sete grafos locais exploram os dois lados de condicionais
e mantêm chamadas opacas: a aresta PC+4 só vale se o callee retornar
normalmente. Não avaliam registradores, dados da pilha, viabilidade, traps,
serviços ou hardware. Catorze testes novos conferem essas fronteiras e as
recusas da CLI; nenhuma emulação de firmware ou execução física foi feita.

Continuação: [panic e recuperação de contexto](lk-panic-recovery-hzc2.md) resolve
as três rotinas antes opacas, mantendo callbacks e estado de execução como fronteiras.
