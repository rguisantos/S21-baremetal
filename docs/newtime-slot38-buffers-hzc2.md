# HZC2: origem e restauração do buffer alterado pelo slot 38

Análise estática de 2026-10-28 (Campo Grande), base remota `0eae442`.
A [folha do slot 38](newtime-slot38-hzc2.md) altera, pelo chamador, o
segundo byte de uma linha das colunas 6/7 NEWTIME. A origem dessa linha e
suas cópias agora estão delimitadas: **72 bytes são salvos antes da consulta
e restaurados depois das chamadas intermediárias**, sob condições explícitas.
Isso não exclui efeitos transitórios ou físicos dessas chamadas.

Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; delta nominal BL2 `0x020ea000`.
Sem execução Samsung, acesso ao aparelho ou ampliação QEMU.

## Origem do destino em 0x22370

F é SP depois do prólogo que reserva 448 bytes. k é W1 de entrada,
preservado em W21. Sob metadados e registradores preservados:

| Buffer | GPR | Ramo baixo | Ramo superior |
|---|---|---|---|
| A | X25 | coluna 4, descritor AP0x020737d0 | coluna 5, AP0x020737e0 |
| B, X2 do dispatcher | X20 | coluna 6, AP0x020737f0 | coluna 7, AP0x02073800 |
| C | X19 | coluna 8, AP0x02073810 | coluna 9, AP0x02073820 |

O ramo superior requer signed32(k)>5 e bit(k&31) dos **16 bits baixos**
da leitura AP0x158609bc ligado. Caso contrário, usa o ramo baixo. A decisão
é local ao wrapper; não foi igualada às escolhas de gate da construção
do registro ou a outra leitura anterior desse registrador.

No ramo baixo, a linha j é k; no superior, u32(k-6). Para B:

```
base = SXTW(u32(0x02073600 + descritor.offset))
deslocamento = SXTW(u32(u32(descritor.columns << 2) * j))
B = u64(base + deslocamento)
```

LDP W lê offset e columns em +4/+8, com elementos de quatro bytes.
LSL/MUL/ADD W podem truncar antes de SXTW; não se substituiu isso por
aritmética unsigned ilimitada. As oito/nove palavras dos dois ramos foram
comparadas com decodificador independente em 90 combinações de limites.

## Janelas condicionais e ausência limitada de alias

As 22 linhas e 512 sequências de escolhas do construtor produzem 8512
planos completos e 2752 com chave ausente no modelo anterior. Somente
os completos entram nesta projeção; não se afirma que um registro parcial
seja impossível de consumir. Os seis descritores das colunas 4..9 formam
**88 perfis distintos**, com multiplicidade/primeiro cenário no JSON.

Para cada perfil, enumeraram-se k u8 e os ramos do controle local possíveis
com uma máscara de 16 bits, sem afirmar viabilidade física. São 33264 casos
de host comprimidos por perfil. A janela conjunta das cópias de 72 bytes
em B fica contida em **[AP0x02074600, AP0x0207925c)**. Nenhuma dessas
janelas intersecta a tabela A nominal `[0x0211b408,0x0211b588)`, a célula
cache `0x0211b8f0` ou o binding `0x0211b998`.

Esta é uma exclusão do **endereço B calculado nesse dataset e alias fixo**.
Não se estende às cópias na pilha, a A/C, às chamadas indiretas, a outros
chamadores, aos metadados alterados ou a uma base física diferente.

Com o filtro da folha (mask=0x1ff e k u8), só k=0..7 pode produzir a store.
Os 880 casos aceitos dos 88 perfis têm o bloco inteiro de 72 bytes dentro
do payload e de uma linha de 18 u32. k=6/7 pode escolher linha 0/1 da coluna
7; no ramo baixo usa a linha k da coluna 6. Os 36 pares distintos chave/linha
apontam a bytes originais com bit1 ligado: a alteração equivale a limpar
**bit9 do primeiro u32 little endian da linha**. O JSON conserva cada
offset/valor anterior e posterior, sob preservação da cópia do payload.
Isso não dá nome físico ao bit ou comprova a alteração no aparelho.

Para k u8 mais amplo, há 31504 casos comprimidos em que a cópia de B fica
fora do payload selecionado. São entradas de modelo, não caminhos físicos
demonstrados. A cópia antecede o teste do slot38, e seu retorno -1 não
aborta o wrapper; portanto esse teste não é uma proteção geral das cópias.
Também não se atribui validade de A/C a partir da validade de B.

## Ordem de cópia, uso e restauração

| Backup | Restauração | Origem/destino fora da pilha | Backup na pilha | Comprimento |
|---|---|---|---|---|
| `0x224f4` | `0x2258c` | A | F+96 | 160 |
| `0x22504` | `0x2259c` | B | F+256 | 72 |
| `0x22518` | `0x225b0` | C | F+328 | 4×N, relido em cada etapa |

N é o byte nominal `0x31688`, alimentado por columns do descritor da coluna
8 em `0x2d5d8/0x2d5dc`. Nos perfis completos, vale 16 ou 17; o último backup
termina em F+392 ou F+396, dentro dos 448 bytes. Um byte arbitrário maior
não herda esse limite. A releitura de N não prova que ele ficou igual.

O helper `0x1fcc4` copia byte a byte **para a frente**. Seu guard usa a
diferença W32 com comparação signed; os tamanhos 160/72/64/68 copiam esses
comprimentos. Sobreposição não ganha semântica memmove e uma falha posterior
não desfaz stores anteriores. Os nove opcodes reais e a preservação dos
registradores usados pelo wrapper foram conferidos.

As chamadas entre os backups e as restaurações são:

- `0x22538`: slot19 nominal, incluindo a edição condicionada do slot38.
- `0x22558` e `0x2257c`: célula `0x31048`, com W0=4 e W1=0/bit salvo.
- `0x2256c`: slot20 da tabela A (`0x314a8`), W0=k, W1=0.

Sob retorno normal, bases estáveis, backup/frame privado preservado, N
compatível e ausência de escritor posterior, a restauração repõe os bytes
anteriores de B, inclusive o bit alterado. Os testes refutam essa conclusão
quando o backup é alterado, B aliasa sua cópia na pilha, não há retorno ou
o tamanho restaurado usa bytes que não foram salvos. Não se provou que os
callees satisfazem essas condições no aparelho.

O slot20 inicial aponta a `0x2f488`. Seu BLR `0x2f498` usa
`M64[M64[nominal(0x31998)]+56]` com k/0; depois há BR por `0x31040` com W0=4.
A [análise do método +56](newtime-method56-hzc2.md) resolve condicionalmente
o provedor inicial para um pedido comando6 e uma espera por resposta. O dado
low24 é obtido de uma raiz runtime, sem ligação direta demonstrada a B.
Restaurar RAM não prova desfazer o que o destinatário possa ter consumido.

## Reprodução e limites

```sh
python3 scripts/inspect_newtime_slot38_buffers_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_slot38_buffers_hzc2.py),
[32 testes novos](../scripts/test_newtime_slot38_buffers.py),
[JSON](references/newtime-slot38-buffers-hzc2.json) e
[validação](references/newtime-slot38-buffers-validation-20261028.json).
GNU: 193 palavras, 15 alvos relativos e 94 operandos selecionados.
Os modelos são de host e seus budgets/bounds não são guards do firmware.
Gates, valores físicos, preservação, aliases transitivos, consumo do pedido
+56, seu BR posterior e despacho/X0 do slot47 continuam sem resolução.
