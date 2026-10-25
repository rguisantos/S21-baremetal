# HZC2: erro NEWTIME, dump do cabeçalho e depuração

Continuação do [registro NEWTIME](newtime-record-hzc2.md), sobre o sboot
de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets abaixo são do arquivo. Ponteiros nominais usam delta 0x020ea000;
não são bindings observados no telefone.

**O helper de erro marca uma palavra do cabeçalho e solicita um dump por
console.** A chamada a 0x204d4 lê os 0x1a0 bytes anteriores ao diretório;
não contém stores na fonte. Isso não prova preservação durante todo o
tratamento: há callbacks mutáveis, buffer opcional de log e uma rotina
de depuração com leitura de hardware e laço. O primeiro u64 físico e a
geometria que substitui o marcador continuam desconhecidos.

## Caminho selecionado e escritas

| Offset / condição | Comportamento conferido | Limite |
|---|---|---|
| Wrapper 0x2f6c0 | Status 1/3/4 encaminham W0=27; status 2 encaminha W0=5 a 0x1fdb8 | Mapeamento já conferido na etapa anterior |
| 0x1fdd0–0x1fdd8 | Lê contexto ativo de 0x31998 e seu campo +0 | O contexto inicial é nominalmente 0x307e0; preservação runtime não provada |
| Console não nulo | Chama 0x21574, 0x20958, 0x204d4 e 0x20200, nessa ordem, se cada anterior retorna | De 0x21574 foi selecionado somente o prefixo até 0x21608; efeitos completos abertos |
| 0x20970–0x20978 | Read/modify/write u32 em AP 0x02073624: `antes OR (1 << (W0 & 31))` | Não atômico; se R=0x02073600, campo R+0x24 |
| 0x1fde8–0x1fdf4 | Passa W0=0x02073600, W1=0x1a0 ao dump 0x204d4 | Endereço fixo do dump; não recarrega o ponteiro R de 0x30520 |
| 0x1fe00–0x1fe18 | Recarrega contexto/console e, se não nulo, envia a string de 0x2fea9 | `READY TO DEBUG!`, com quebras de linha |
| 0x1fe1c–0x1fe28 | WFI seguido por restauração da pilha/registradores e RET | Não é um branch incondicional para si; retomada real após WFI não demonstrada |

O erro de lookup que retorna 4 pode deixar descritores/dados anteriores já
gravados e não publica o tamanho final. Se o wrapper chega a 0x20958 com
27, a marca é **0x08000000**; para o erro 2, com 5, é **0x20**. O OR
preserva os bits anteriores. Essa escrita a +0x24 não substitui o primeiro
u64. Não se conclui que todas as demais chamadas também o preservem.

Se o campo +0 do contexto é nulo na primeira verificação, as quatro
chamadas são puladas. O contexto é desreferenciado antes da verificação:
isso não trata um ponteiro de contexto nulo como válido. Existe outra
recarga/verificação antes da mensagem e do WFI; não se presumiu estabilidade
dos ponteiros entre essas operações.

## Console nominal e efeitos fora do dump

O u64 inicial de 0x307e0 aponta nominalmente para **0x30b50**. Nessa tabela,
o campo +8 aponta para **0x1d560**, que percorre uma string, acrescenta CR
antes de LF e chama **0x1d4dc** por caractere. O campo +24 aponta para
**0x1d430**, conversor u32 com largura/base fornecidas e dígitos hexadecimais
maiúsculos. O conversor grava somente no buffer recebido pelo chamador;
no dump, esse buffer fica na pilha.

0x1d4c8 espera pelo bit 1 de **0x10540010**, sem timeout no trecho
selecionado; 0x1d4dc grava uma palavra em **0x10540020**. Também consulta o
ponteiro mutável de **0x31c20** e, sob assinatura/condições do buffer,
atualiza campos e grava o caractere em endereço derivado dele. Não foi
provado que esse buffer existe, é legível, está configurado ou é disjunto
do registro no telefone. A identificação estática desses acessos não
estabelece clock, pinmux, ligação externa ou um canal físico utilizável.

## Leitura do dump

0x204d4 conserva o endereço de entrada em W25, calcula base alinhada a
16 em W22 e limite W24=`(endereço & 15) + tamanho`, módulo 2^32.
W21 começa em zero e avança de quatro em quatro. **0x20654 carrega uma
palavra mesmo quando sua representação será substituída por espaços**
por estar antes do início solicitado. O endereço efetivo soma base e
índice zero-estendidos em X; o endereço mostrado é calculado em W.

Na chamada selecionada, endereço alinhado 0x02073600 e tamanho 0x1a0
produzem **104 LDRs**, até 0x0207379c, fim exclusivo **0x020737a0**.
Se R=0x02073600, o diretório NEWTIME começa justamente nesse fim. Sob
esse binding e argumentos preservados, a chamada não lê diretório/payload.

O helper não é um leitor genérico com limites validados: pedidos curtos
leem palavras inteiras; tamanho zero com início desalinhado ainda pode
ler palavras anteriores; a adição W pode reduzir o limite por overflow.
Para limite W de 0xfffffffd..0xffffffff, o contador W avança até
0xfffffffc e volta a zero, sem alcançar a condição de término, supondo
que leituras/callbacks retornem e o estado permaneça estável. Esses
limites foram modelados/testados no host; **não são os argumentos da
chamada NEWTIME nem foram executados como varreduras enormes no QEMU**.

## Rotina de depuração ainda parcial

0x20200 começa com uma leitura de **0x10000000** em 0x20220 e examina
quatro palavras de **[0x020736d0, 0x020736e0)**. Depois chama um slot de
0x31408 e pode entrar no laço em **0x20344**, condicionado por console e
pelo byte de estado **0x319f8**. Os back edges de 0x204ac/0x204bc voltam
ao laço; 0x204c0 é seu epílogo. Não se atribuiu significado físico aos
valores lidos nem se executou esse laço.

O corpo selecionado chama **0x1ffbc**, outro caminho de dump, que pode
modificar um caractere de uma string interna e copiar dados para buffers
de saída. A saída acumulada passa por 0x1ff18 e por um callback indireto
em **0x1ff3c**, com argumento 0x82000301. Esses callbacks, o restante de
0x21574 e seus efeitos transitivos continuam abertos. A presença de WFI
no helper externo não demonstra que ele seja sempre alcançado ou que o
chamador volte a executar.

## Validação e reprodução

[Análise estática](references/newtime-error-hzc2.json) e
[GNU 2.44](references/newtime-error-gnu-hzc2.json): **662 palavras,
92 alvos relativos, 34 operandos selecionados**, três ponteiros nominais
e nove strings. Testemunhos de instruções fixados pelo índice SHA-256
`d11bd7a714e20dca8ab1bd1a2d51618d36f78152132a44f0e0fa98aaed1651c2`.
Não é cobertura de todos os caminhos/callees do firmware.

[QEMU](references/newtime-error-qemu-hzc2.json): **26 casos do dump e
14 do fragmento de flags**, em dois deltas RAM, 0x40000000/0x40200000.
Executam o dump e conversor originais. O slot de saída recebe um RET de
laboratório em RAM; GDB captura as strings e cada endereço de LDR. Não
executa UART, o helper completo, a rotina de depuração ou MMIO Samsung.
Fonte inteira de 0x2400 bytes, guardas, ABI/SP, instruções, strings e
bindings do contexto são conferidos. A transcrição completa é comparada
com a expectativa do host, incluindo espaços e palavras parcialmente
fora do pedido. Nos 14 casos de flags, executam somente LSL/LDR/ORR/STR
originais de **[0x2096c, 0x2097c)**, com **X3 fornecido pelo harness**
para R+0x24 em RAM. O produtor do endereço absoluto não executa nesse
fragmento; apenas esse campo pode mudar na comparação do registro inteiro.

```bash
python3 scripts/inspect_newtime_error_hzc2.py /caminho/sboot.bin
python3 scripts/check_newtime_error_gnu.py /caminho/sboot.bin
python3 scripts/emulate_newtime_error_qemu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py' -v
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
```

**Nove testes novos e 92 anteriores passaram**, além de nove recusas CLI
de imagem curta/longa/alterada, exit 2 sem JSON e antes de QEMU. Relatórios
estático/GNU reproduzidos byte a byte; Python compilado e links locais
conferidos. [Registro da validação](references/newtime-error-validation-hzc2.json).

A [continuação da geometria](bl2-geometry-packing-hzc2.md) delimita o
empacotador posterior sob retornos fornecidos. Próximo: seguir a publicação
no registro e os bindings das recargas; fechar aliases ACPM e, quando
pertinente, callbacks/efeitos externos ainda abertos. Nenhum ensaio aqui fornece registro físico,
capacidade RAM, reservas ou FDT final.
