# HZC2: canal 1, FVP comando6 e ponte para DVFS

Análise estática de 2026-10-29 (Campo Grande), base remota `a2b02e2`.
O [pedido do método +56](newtime-method56-hzc2.md) agora tem destinatário
nominal delimitado: canal1 → plugin2 `fvp` → comando6 → serviço do plugin7
`plugin_DVFS_0_0_0.fw`. A operação física continua aberta.

Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; endereços core são locais ao ACPM. Sem execução
Samsung ou ampliação QEMU. Os aliases de hardware continuam condicionais.

## Configuração compartilhada e duas filas

O [rastreio ACPM anterior](acpm-handshake-hzc2.md) delimita duas cópias:
core `[0x4000,0x9000)` ↔ arquivo `[0x38000,0x3d000)` e core
`[0xf800,0x39800)` ↔ arquivo `[0x3d000,0x67000)`. Elas têm deltas distintos;
o endereço AP candidato é `u32(core+0x02039000)`, sob alias SRAM.

`0x39b5e` publica core0x73c0 em core0x8008. Sob esse alias, é o campo que
BL2 lê em AP0x02041008. O registro do canal1 está em core0x7408, passo72;
os acessos BL2 T+96/T+120/T+124/T+128 correspondem aos campos
+24/+48/+52/+56 desse registro: pedido, resposta, contagem e passo.

O inicializador publica core0x8800 em initdata+72. O alocador `0x398e8`
percorre **15** registros e só monta as filas quando +24 e +48 são zero.
O dataset inicial tem canal0 com count15/stride16 e canal1 com count3/stride16.
O plano dos dois primeiros, sob origem e campos preservados, é:

| Campo canal1 | Core | AP candidato |
|---|---|---|
| Pedidos BL2 → ACPM, registro+24 | 0x8a50 | 0x02041a50 |
| Respostas ACPM → BL2, registro+48 | 0x8a10 | 0x02041a10 |
| Leitura / escrita de pedido, +16/+20 | 0x8a48 / 0x8a4c | somar0x02039000 |
| Leitura / escrita de resposta, +40/+44 | 0x8a08 / 0x8a0c | somar0x02039000 |

Assim, TX-4 e RX-8 usados pelo BL2 têm contrapartes concretas no canal.
Não foram atribuídos índices iniciais zero à execução. Ponteiros já
preenchidos pulam a alocação e podem mudar o plano; count/stride modificados
ou outros escritores também invalidam os endereços candidatos.

## Despacho até o plugin FVP

Para tipo de evento128 e máscara **exatamente2**, `0x39cc6/0x39cc8` escolhe
`0x39d52`: canal1 e plugin2. Máscaras simultâneas seguem outra seleção e
não foram igualadas a esse caso. A API core0x7960+8 aponta para essa função.

O descritor plugin2 é core0x71b0. Seu inicializador core0x11801, publicado
por `0x399c2`, corresponde ao arquivo0x3f000. No laço de inicialização,
o descritor habilitado é passado ao BLX `0x38e90`. `0x3f00a` publica a
interface core0x1205c; seu primeiro u32 é core0x1196d, handler de recepção
no arquivo **0x3f16c**. `0x3929a` o chama com R0=&ponteiro_do_pedido e
R1=canal. Inicialização e evento efetivos não foram observados.

O handler separa low16/high16 da palavra0, lê valor da palavra1 e comando
da **palavra2**. Canal15 tem outro caminho; canal1 usa o switch de sete
entradas em core0x11f84. Entrada6 = core0x11b8c → arquivo **0x3f38c**.
Logo `{0,valor24,6,6}` significa domínio0, valor24 e comando6 nesse caminho;
a última palavra não escolhe o comando.

O caso6/domain0 grava o valor solicitado em core0x120f4 por `0x3f4b0`.
A seleção posterior combina campos +4/+8/+12 do estado e políticas/caps
runtime; o valor efetivo encaminhado não foi igualado sempre ao solicitado.
Essas stores no estado ACPM ficam fora da restauração do buffer B pelo BL2.
A [continuação da seleção](newtime-fvp-effective-hzc2.md) reconstrói esse
máximo unsigned e o limite posterior para comando6/domínio0, incluindo
indicador anterior ao limite e retorno sem rollback local selecionado.

## Serviço DVFS e próxima função

Antes de chamar os plugins, `0x38e46` instala a API core0x710c em +8 de
cada descritor. FVP usa API+28 → core0x4b05 → arquivo **0x38b04**.
O relay seleciona plugin7 e seu método +12, exigindo:

- contagem >7;
- byte habilitado +32 não zero;
- callback presente;
- bit do plugin chamador permitido em +20 do descritor destinatário.

O mask inicial do plugin7 é 0xb34, que permite bit2 (0x4) do FVP. Isso não
substitui os demais gates nem prova preservação desse mask. O shift Thumb
por registrador usa contador low8; valores >=32 zeram o resultado. Não
foi reutilizada a máscara de cinco bits das instruções AArch64 W.

O inicializador do plugin7 em `0x56e04` instala interface core0x2e828;
seu método +12 contém core0x2e36d → arquivo **0x5bb6c**. O relay repassa
ponteiros para domínio0, valor efetivo e modo0 (frame privado inicializado).
A tabela de modos em core0x2f400 tem slot0 core0x2c3e5 → arquivo
**0x59be4**. Essa função e seus efeitos são a próxima fronteira.
O resultado do relay continua opaco, incluindo seus retornos por gates.
A [auditoria posterior do receptor](newtime-dvfs-receiver-hzc2.md) agora
delimita wrapper/callback/init e corrige a interpretação do limiar e do
retorno intermediário; consumidores DMC e efeitos físicos seguem abertos.

## Resposta publicada e limite da confirmação

No caminho genérico, FVP constrói palavra0 como
`header_alto16 | low16(resultado_interno)` e escreve palavra1. Não se
presumiu que palavras2/3 sejam reinicializadas nesse caminho.

Sua API+12 aponta ao alocador de resposta `0x386bc`; API+16 aponta ao
publicador **0x38738**. O alocador compara leitura contra próximo índice
circular; fila cheia chega ao laço WFI `0x38734`, sem timeout nesse trecho.
O publicador readquire o slot via `0x3876a → 0x386bc`, faz LSR16/LSL16
na palavra0, combina o header alto salvo, executa DSB e grava o header
antes de avançar o índice/sinalizar.

Sob slot/config/frame privados e estáveis, essa projeção remove os 16 bits
baixos colocados pelo FVP. No pedido selecionado com header alto zero,
a palavra0 publicada é zero para todos os 65536 resultados baixos.
O teste do BL2 ainda exige status low4 não zero, mas **o casamento com
zero não comprova resultado interno zero ou sucesso físico do DVFS**.
Um exemplo de host usa resultado10: palavra construída10, publicada0.
Isso descreve as instruções selecionadas, sem atribuir significado de erro
ou sucesso ao valor10 e sem diagnosticar uma falha de protocolo no aparelho.

## Reprodução e limites

```sh
python3 scripts/inspect_newtime_command6_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_command6_hzc2.py),
[25 testes novos](../scripts/test_newtime_command6.py),
[JSON](references/newtime-command6-hzc2.json) e
[validação](references/newtime-command6-validation-20261029.json).
GNU: 814 instruções/932 halfwords, 112 alvos relativos, 10 referências
a literais e 96 operandos selecionados.
Os testes cobrem skips do alocador, campos do pacote, gates de serviço,
semântica Thumb de shifts e todos os resultados baixos da projeção.

Mapa/aliases, chamadas intermediárias, registradores transportados,
frames, filas, configuração e interfaces precisam permanecer compatíveis
com as arestas mostradas. O corpo de 0x59be4, hardware e unidade física,
consumo do B temporário NEWTIME, BR posterior do slot20 e slot47/X0 seguem
abertos. A chegada nominal ao plugin não demonstra uma operação no aparelho.
