# HZC2: valor efetivo do FVP antes do serviço DVFS

Análise estática de 2026-10-29 (Campo Grande), base remota `4d36dd1`.
Complementa a [ponte do comando6](newtime-command6-hzc2.md). O corpo do
destinatário `0x59be4` é uma frente separada; esta entrega fecha a seleção
local do valor encaminhado, sob condições explícitas.
A [auditoria do receptor DVFS](newtime-dvfs-receiver-hzc2.md) complementa
esta seleção com o callback e as condições de inicialização/retorno.

Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo, dados são endereços core ACPM. Neste estágio
Thumb, `file=core+0x2d800`; não se demonstrou o alias físico AP/core.

## Entrada selecionada e campos

No canal1, palavra2=6 leva ao caso `0x3f38c`. Domínio low16=0 passa por
`0x3f6a4`: R8=0, R0=0, R5=1, IP=0; frame+20 contém o pedido e frame+24
contém6. O endereço calculado em `0x3f49a..0x3f4ae` é
`S+140*domínio+4*IP`, com S=core0x120f0. `0x3f4b0` grava o pedido em S+4.
Os cálculos são W32 e as comparações relevantes são **sem sinal**.

| Campo core | Papel estrutural no caminho selecionado |
|---|---|
| 0x120f0 / S+0 | valor efetivo, recarregado para o relay |
| 0x120f4 / S+4 | pedido recebido, substituído pelo comando6 |
| 0x120f8 / S+8 | outro valor participante da seleção |
| 0x120fc / S+12 | terceiro valor participante da seleção |
| 0x12100 / S+16 | limite condicional |
| 0x120a0 | habilitação do limite, qualquer u32 não zero |
| 0x12208 | espelho do máximo anterior ao limite |
| 0x12210 | indicador calculado pela relação máximo/valor anterior |

Não foram atribuídos nomes físicos às duas entradas concorrentes, unidade
de frequência ao número ou significado de hardware ao indicador.
No arquivo, os cinco campos S+0..16 são zero e 0x120a0 contém1. O
inicializador `0x3f028/0x3f02a` escreve 0xffffffff nos limites dos dois
domínios, **se executado**. Assim, o zero do arquivo em S+16 não estabelece
um limite ativo zero. Escritores selecionados posteriores incluem comando4
no canal1 (`0x3f5aa`, limite) e comando5/subseletor2 (`0x3f69c`, habilitação).
Isso não é inventário exaustivo de escritores, eventos ou aliases.
A [continuação dos setters](newtime-policy-writers-hzc2.md) agora delimita
os gates e as respostas desses dois escritores, sem chamada direta ao
relay nos trajetos selecionados.

## Máximo, indicador e limite

Sejam R o pedido, B e C os campos S+8/+12 e O o valor anterior S+0.
Sob palavras/raízes preservadas durante o trecho:

`M=max_u32(R,B,C)`

`E = M`, se 0x120a0=0; caso contrário, `E=min_u32(M,S+16)`.

O caminho zera 0x12208 em `0x3f4be` e grava M em `0x3f656` quando o
ramo não zero exige essa store. Ao final da seleção, o espelho é M em
ambos os casos. O indicador 0x12210 recebe1 se M<O, recebe0 se M>O e não
é sobrescrito se M=O. **A comparação é anterior ao limite**.

`0x3f518` atualiza S+0 para M quando necessário; `0x3f53a` pode depois
substituí-lo pelo limite. A comparação com o limite também acontece no
caminho M=O. Os indicadores não são recalculados após essa substituição.

Exemplo sintético: O=200, R=300, B=C=0, limite=100, habilitação=1.
O espelho fica300, indicador0 pela comparação300>200, mas E=100.
Com O=M=300, o limite ainda reduz E para100, conservando o indicador
anterior. Esses casos demonstram a ordem das instruções, sem diagnosticar
erro ou operação física no aparelho.

O gate auxiliar em `0x3f262..0x3f2ca` pode ler 0x12214. Mesmo quando ele
está habilitado e B>R, o ramo exige R0=1 em `0x3f28c`. Neste caminho
comando6/domínio0, R0 continua0; a busca auxiliar `0x3f298` não é tomada.
O BL `0x3f2cc ->0x3f0d0` é selecionado **mesmo se E=O**. Isso não garante
que o relay permita o serviço ou que as chamadas retornem.

## Releitura, ponteiros e retorno

O helper `0x3f0d0` não transmite o pedido original diretamente: para domínio0
ele relê S+0 em `0x3f156` e grava E no frame+16. O frame+20 recebe modo0.
No BLX `0x3f11e`, os argumentos são:

- R0 = descritor lido através de core0x1220c;
- R1 = plugin destinatário7;
- R2 = endereço do domínio no frame+12;
- R3 = endereço do valor efetivo no frame+16;
- argumento de pilha0 = endereço do modo no frame+20.

O relay e a interface DVFS foram ligados nominalmente no documento da
ponte. Aqui seus resultados e possíveis modificações dos argumentos por
ponteiro continuam opacos. Em particular, resultado zero não prova que o
frame+16 permaneça igual ao E anterior à chamada.

`0x3f130` testa o resultado inteiro de32 bits. Se não zero, o caminho
registra uma mensagem e retorna **sem desfazer as stores prévias** no
estado selecionado. Não se afirmou que os callees preservem toda a RAM.
Se zero e o índice previamente lido da tabela core0x1200c for signed>=0,
`0x3f13a` relê frame+16 e `0x3f142` escreve core0x12700+4*índice em W32.
Índice inicial do domínio0=5 dá o candidato core0x12714; preservação da
tabela e ausência de aliases continuam condições. Esse cache pode conter
um valor alterado pelo destinatário por ponteiro.

## Reprodução e fronteiras

```sh
python3 scripts/inspect_newtime_fvp_effective_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime_fvp_effective.py'
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_fvp_effective_hzc2.py),
[28 testes](../scripts/test_newtime_fvp_effective.py),
[evidências](references/newtime-fvp-effective-hzc2.json) e
[validação](references/newtime-fvp-effective-validation-20261029.json).
GNU: 830 instruções, 983 halfwords, 150 alvos relativos e64 operandos
selecionados. A suíte compara a fórmula com um interpretador limitado de
**palavras Thumb cruas**, sem usar o texto GNU como semântica: 4096
combinações de limites mais512 casos determinísticos. Ausência de memória,
opcode não implementado e estouro do orçamento de host recusam a análise.
O orçamento não é timeout do firmware. Os casos com pedidos acima de24 bits
são fixtures sintéticas, não pedidos observados do transporte BL2 low24.

Logging, frames, registradores transportados, palavras/raízes e ordem das
stores precisam permanecer compatíveis com o caminho. As fontes efetivas
de B/C/limite, aliases, concorrência, gates/retornos de plugins, unidade
física e efeitos de `0x59be4` continuam abertos. Sem execução Samsung,
mudança de escopo QEMU ou conclusão nova sobre slot47/X0.
