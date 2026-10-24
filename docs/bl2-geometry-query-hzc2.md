# BL2 HZC2: consulta que alimenta a geometria

Continuação de **2026-10-24 (Campo Grande)** do
[produtor do total de RAM](bl2-ram-size-hzc2.md). Mesmo sboot de 4194304
bytes, SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
O callback candidato da geometria foi seguido até acessos de 32 bits a
bases literais. Isso identifica a origem da palavra retornada, sem obter
respostas do aparelho ou executar o controlador.

## Ligação nominal e chamada

| Uso em `0x2f130` | Célula derivada | Ponteiro bruto | Alvo nominal |
|---|---|---|---|
| Preparação antes da consulta | `0x31040` | `0x0211424c` | `0x2a24c–0x2a2a8`, 23 instruções |
| Consulta | `0x30f20` | `0x02112480` | `0x28480–0x284e4`, 25 instruções |

Os alvos usam o delta **nominal** `0x020ea000`. As células vêm dos ADRP/ADD
e loads do chamador, não de uma procura por ponteiros parecidos. A colocação
física e os bindings das tabelas mutáveis continuam sem observação.

O chamador fornece W0=slot 0–3, W1=termo 1/2 e W2=seletor 5/6/7/8. Os
calls da consulta estão em `0x2f1d4`, `0x2f21c`, `0x2f244`, `0x2f268`.
Se a resposta do seletor 5 for zero, não faz as consultas 6/7/8 daquele
termo. As respostas 5/8 alimentam os campos da
[folha de cálculo já conferida](bl2-ram-size-hzc2.md#origem-candidata-das-palavras-de-geometria).

## Bases e acessos selecionados

| Slot | Base da consulta, tabela `0x30f98` | Endereço de preparação, tabela `0x30fc0` + `0x50` |
|---|---|---|
| 0 | `0x1c036000` | `0x1c040050` |
| 1 | `0x1c136000` | `0x1c140050` |
| 2 | `0x1c236000` | `0x1c240050` |
| 3 | `0x1c336000` | `0x1c340050` |
| 4 | `0x1a346000` | `0x1a350050` |

São valores brutos de dez u64 do arquivo identificado. Não demonstram o
mapeamento vivo, clock, permissões ou o nome dos blocos/registradores no
SoC. Os nomes “comando”, “disparo” e “resposta” abaixo descrevem seu uso no
código, sem atribuir semântica de uma especificação do controlador.

**Continuação:** um [escritor condicional das cinco bases de consulta](bl2-query-base-rewrite-hzc2.md)
foi identificado em `0x2d270`. Se o callback nominal retornar 1 a partir dos
bits 20–23 de `0x10000010`, grava bases terminadas em `0xf000` na tabela
`0x30f98`. Caso contrário, conserva seu conteúdo anterior, sem restaurar o
arquivo. A tabela acima descreve os bytes iniciais; nenhuma das configurações
foi observada como ativa no S21. O corpo não reescreve a tabela `0x30fc0`.

Para slots 0–3, a consulta lê W3 de `base+0`, insere campos e faz:

1. `0x284d0`: escreve a palavra de comando de 32 bits em `base+0`.
2. `0x284d4`: escreve o literal 1 de 32 bits em `base+4`.
3. `0x284d8`: lê 32 bits de `base+0xc`; esse valor vai para W0 no retorno.

A palavra escrita é:

```text
(controle_lido & 0xc80fffff)
  | ((W1 & 3) << 28)
  | ((W2 & 0x7f) << 20)
```

`UXTB W2` precede a inserção; o BFI usa apenas sete desses oito bits. O
termo usa dois bits. Os demais bits da palavra lida permanecem, inclusive
27, 30 e 31. A resposta não é mascarada a um byte nesta rotina; `MOV W0,W3`
zera a metade alta de X0. O empacotamento posterior seleciona seus campos.

Para W0=4, a leitura inicial vem da **base do slot 0**, mas as escritas e
a leitura de resposta usam a **base do slot 4**. W0 unsigned >4 retorna
X0=`0x00000000ffffffff`, sem acessar as tabelas ou MMIO. Essa assimetria
não comprova broadcast ou defeito; o chamador de geometria usa somente 0–3.

## Preparação imediatamente anterior

O outro callback lê 32 bits de `base_preparação+0x50`, escreve o valor com
bit 24 ligado e depois escreve com esse bit desligado. Preserva os demais
bits; não restaura o estado original do bit 24 se já estava ligado. Retorna
zero para slots 0–4. No slot 4, também lê inicialmente do slot 0 e escreve
no slot 4. Valores unsigned >4 retornam X0=`0x00000000ffffffff` sem acesso.

As duas rotinas completas não têm polling, barreira ou chamada de serviço.
Isso delimita **esses corpos**, sem comprovar conclusão do dispositivo ou
o comportamento das chamadas/configurações ao redor. Não se deduziu um
protocolo DDR/JEDEC, latência ou condição de prontidão apenas desse padrão.

## Ferramentas e conferência

```bash
python3 scripts/inspect_bl2_geometry_query.py /caminho/sboot.bin
python3 scripts/inspect_bl2_geometry_query.py /caminho/sboot.bin --slot 0 --term 2 --selector 8
python3 scripts/check_bl2_geometry_query_gnu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
```

O inspetor exige tamanho/SHA-256 exatos. Confere os dois corpos completos,
deriva células/tabelas dos endereços e extrai os BFI. O plano opcional exige
os três u32 explícitos. Emite operações **simbólicas**: a palavra inicial e
a resposta permanecem desconhecidas, sem injetar retornos ou calcular RAM.
Suas bases vêm somente da tabela inicial do arquivo, sem aplicar a
reescrita; o inspetor da continuação aceita uma palavra explícita para esse
cenário condicional.
Erros de entrada retornam 2, sem JSON parcial.

**48 testes passaram**: 14 novos controles de campos, slots, entradas,
truncamento, mudanças de instruções e parser GNU, mais 34 regressões BL2.
A CLI passou três planos simbólicos (slots 0/4/5) e quatro recusas.
GNU objdump **2.44** conferiu **82 palavras, seis destinos relativos,
17 operandos, dois BFI e 12 ponteiros**. Os ponteiros são lidos do hexdump
textual GNU, independentemente do leitor binário Python. Evidências:
[estática](references/bl2-geometry-query-hzc2.json) e
[GNU](references/bl2-geometry-query-gnu-hzc2.json).

Não houve novo QEMU, execução de firmware/serviço/MMIO ou ensaio físico;
as 66 execuções anteriores pertencem somente à folha aritmética. Nenhum
blob foi adicionado. README, índice, roadmap e worklog foram atualizados.

A continuação identificou um [escritor das bases de acesso](bl2-query-base-rewrite-hzc2.md).
A próxima investigação mantém os demais escritores/configurações e os
bindings dos callbacks abertos. Para fechar o total real, ainda
faltam bindings comprovados e respostas/estado observados. O total pode
sofrer limite no LK e continua insuficiente para determinar bancos, reservas
ou RAM livre sem as demais entradas e o FDT efetivo.
