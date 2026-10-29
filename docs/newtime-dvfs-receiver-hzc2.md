# HZC2: receptor DVFS, transição intermediária e limites da confirmação

Auditoria estática de 2026-10-29 (Campo Grande), base remota `ed48cba`.
O material GLM permite aproveitar a cadeia nominal modo0 e os alvos de
instrução, com correções de fluxo, inicialização, broadcast e testes.
A [seleção FVP](newtime-fvp-effective-hzc2.md) já produz o valor efetivo E;
esta entrega o liga ao receptor sem igualá-lo ao pedido bruto.

Mesmo sboot de4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; dados core são locais ao ACPM Thumb.
No intervalo selecionado, `file=core+0x2d800`; alias físico não verificado.
Sem execução Samsung ou ampliação QEMU.

## Reprodução do material recebido

Vieram extrator,47 testes,JSON e helper shell. A cópia original foi
preservada. Em cópia temporária, foram ajustados somente os caminhos do
firmware/binutils e o acesso ao GNU pelo wrapper do repositório. Os47
testes passaram. O JSON regenerado é idêntico ao anexo depois de normalizar
apenas a versão GNU2.42→2.44. Os2341 registros de instrução conferem em
bytes; há2314 PCs únicos, com janelas sobrepostas e pools de literais
também disassemblados. Esses números não representam cobertura de2341
instruções executáveis distintas.

Isso reproduz o programa externo, mas não valida todas as suas conclusões:
o teste `fvp_projection` retorna `internal&0xffff` e exige10 para entrada10,
apesar do nome afirmar remoção low16. A [publicação já auditada](newtime-command6-hzc2.md)
produz0 nesse caso. Além disso,40 regexes de instrução e80 literais não
verificam individualmente todas as38 descrições MMIO curadas pelo script.
Os hashes dos anexos e as adaptações estão na validação desta entrega.

## Ponteiros, valores e estado após o handshake

O método+12 em `0x5bb6c` recebe ponteiros domínio/valor/modo. Para modo0,
`0x5bbc0/0x5bbc2` desreferenciam domínio e E; `0x5bbc4` chama o slot0 da
tabela core0x2f400. O ponteiro inicial0x2c3e5 corresponde a `0x59be4`.
O callback inicial +40 da entrada0 é0x2c0dd → `0x598dc`. Preservação dessas
células e passagem pelos gates do relay continuam condicionais.

`0x56ee0` escreve core0x38e00 no MMIO0xa5900108 e espera o registrador
zerar **antes de ler os dados vivos**. Só então publica a base em0x2fbf4.
O primeiro laço tem29 entradas:

| Campo da entrada i, DOM=core0x2f44c | Valor escrito |
|---|---|
| DOM+48*i+12 | **u32(0x38e00+52*i)** |
| DOM+48*i+32 | u32(M32[sub_i+24]<<8) \| (old_i&255) |

Em `0x56f42`, R4 avança52; portanto +12 não recebe a mesma base em todos
os domínios. Um segundo laço deriva registros29..36 e não foi modelado
como mais oito cópias idênticas do primeiro.
Os zeros do arquivo em0x66600 não demonstram o conteúdo após o handshake,
nem que o corrente vivo seja zero ou que minlock sempre seja PRE.

## Minlock e retorno do callback de duas etapas

`0x59be4` captura `cur=M32[entry+32]>>8` antes do despacho. Sob retorno
normal e preservação dos registradores transportados, escolhe uma chamada
a `0x59a90`: PRE se cur<=E, POST se cur>E. O retorno do despacho é salvo
em R4 e reposto em R0 em `0x59c52`, depois do POST opcional. O retorno
minlock não é agregado a esse resultado. Chamada ao helper não prova
que ele publique uma notificação ou que o destinatário aceite o pedido.

Para o callback nominal domínio0, A é o campo corrente relido, B é
M32[core0x2f248] e E é o alvo. Se B estiver estritamente entre A e E,
ocorrem duas chamadas, se a primeira retornar:

1. `0x59906 ->0x5944c(A,B,entry)`.
2. `0x5990c` **relê B**, independentemente do campo corrente.
3. `0x59916 ->0x5944c(B_recarregado,E,entry)`.

Não há teste do retorno da primeira chamada. Seu resultado é sobrescrito
pela recarga de B. Uma primeira chamada que retorne0xffffffff pode ser
seguida por uma segunda que retorne0; o callback devolve somente o segundo
resultado. Se a primeira alterar B, a segunda recebe esse novo valor.
Também não se provou que a primeira efetivamente alcance B ou que preserve
memória/MMIO. O caso de uma etapa devolve o único resultado.

## O limiar escolhe caminhos; não é uma recusa

`0x5acec` lê contagem u8 em sub+1 e offset u16 em sub+20; compara low24 das
palavras da tabela ao valor completo u32. Contagem zero retorna-1; a busca
sem coincidência usa o último índice. As duas falhas de lookup em
`0x594a8/0x594ae` chegam aos retornos-1 `0x59896/0x5989c`.

As comparações com M32[core0x2f230], em `0x59614..0x5961c`, **não são
retornos de erro**. A>limiar desvia para0x59692 e continua; E>limiar chega
a0x598a2 e escolhe outro caminho por status31 de MMIO0xac00010c.
O seletor resulta1 para E<=limiar,2 para E>limiar/status31=0 e3 para
E>limiar/status31=1. O valor anterior também muda a pré-sequência escolhida.
Há chamadas e broadcast anteriores a essas comparações; não se deve
tratá-las como validação anterior a todos os efeitos.

Se o caminho terminal for alcançado, `0x5974c` grava E em MMIO0xa5900100,
e `0x59890` grava `u32(E<<8)|(old&255)` no campo+32 da **entrada0 literal**.
A store final não usa genericamente a entrada recebida como argumento.
`0x59892` retorna0 localmente. Isso não agrega aceitação de todos os RPCs,
notificações e polls: há retornos RPC signed>0 que apenas levam a outra
notificação, seguindo depois. Não se demonstrou sucesso físico.

## Broadcast, RMW e chamada de notificação

O helper `0x587a4` visita **quatro** registradores:
`[0xac000800,0xac400800)` com passo0x100000. A comparação ocorre depois
do incremento; o limite superior é exclusivo. Na chamada final, R0=24,
R1=0xf1 e R2=0xf0: `(old&~0xf1000000)|0xf0000000`, que também limpa bit24.
Não são cinco registradores nem argumentos finais(24,0xf0,0xf0).

O RMW `0x582a4` escreve `(old&0xcffffffc)|(value&0x30000003)`. O poll é
pulado para **value inteiro igual** a0x10000001; outras palavras com os
mesmos bits mascarados podem ainda entrar no poll. Status31 de addr+8
controla a entrada, bit29 nas releituras controla a saída. O trecho não
tem timeout. Nenhum avanço posterior é garantido se o poll não terminar.

A notificação minlock em `0x59bba` carrega diretamente a célula
`M32[core0x2eccc+16]`, inicialmente0x2a321 → arquivo0x57b20. Não há
desreferência extra `M32[M32[core0x2eccc]+16]`. A tabela permanece sujeita
a inicialização, escritores e preservação runtime.

## Reprodução própria e próxima fronteira

```sh
python3 scripts/inspect_newtime_dvfs_receiver_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime_dvfs_receiver.py'
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_dvfs_receiver_hzc2.py),
[28 testes próprios](../scripts/test_newtime_dvfs_receiver.py),
[JSON](references/newtime-dvfs-receiver-hzc2.json) e
[proveniência/validação](references/newtime-dvfs-receiver-validation-20261029.json).
As regressões incluem avaliação limitada das palavras Thumb reais para216
combinações do callback, recarga B com primeira falha,29 entradas com dados
vivos não zero, oito combinações dos limiares/status, preservação do retorno
do despacho e broadcast com limite exclusivo. Hooks dos callees são opacos
e explícitos; orçamento de host não é timeout de firmware.

Esta auditoria não substitui um mapa completo dos38 acessos/polls externos.
Interfaces dos plugins DMC/DD/sci, origens das tabelas vivas, aliases e
aplicação física permanecem abertos. A seleção FVP já foi feita; a frente
complementar útil agora é o método+12 do plugin_DMC e os consumidores dos
subcomandos8/9, mantendo slot47/X0 e os demais caminhos indiretos abertos.
