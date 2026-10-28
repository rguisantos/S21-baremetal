# HZC2: resultado secundário de 0x1a804 e identidade Q=B

Análise estática de 2026-10-28 (Campo Grande), complementar ao PR #50.
O helper antes opaco em `0x1a804` tem dois retornos possíveis: o buffer
original B ou o resultado de uma nova alocação. **Q=B é um caminho explícito,
não apenas uma hipótese de colisão de alocador.** Isso permite conferir as
duas stores de correção da continuação sem supor buffers distintos.

## Escopo e argumentos

Mesmo sboot HZC2, 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets são de arquivo; delta BL2 nominal `0x020ea000`. A análise é estática,
sem acesso ao hardware ou execução de firmware no aparelho; o escopo QEMU
foi preservado.

O grafo sintático `[0x1a804,0x1aab4)` tem 172 PCs, RET em `0x1aab0` e
três BLs: alocador `0x1a854 → 0x18068`, setup numérico `0x1a9c4 → 0x1a294`
e amostra numérica `0x1aa34 → 0x1a294`. Continuar após BL exige retorno normal.
Um scan B/BL em `[0x16000,0x2fd00)` encontra o chamador `0x1b354`; não é
uma prova de exclusividade global ou de ausência de entradas alternativas.

| Argumento recebido | Papel local |
|---|---|
| W0 | seletor original, conservado em W28; não é o seletor packed W21 |
| X1/X2 | A, quatro pontos; Y, quatro amostras modificáveis |
| X3 | D, descritor dinâmico |
| W4/W5 | chave de registro e coluna |
| X6 | B, buffer original, conservado inicialmente em X20 |

O helper captura n=u32([D+16]), ou zero se D for nulo, e pede u32(4*n)
ao alocador **antes de testar seletor/gate**. O alocador aplica SXTW e
retorna o cursor antigo Qnew, conforme a
[análise da continuação](newtime-common-continuation-hzc2.md). Wrap e
pedido negativo continuam possíveis no modelo; não há prova de bounds.
Mesmo nos caminhos que retornam B, a chamada de alocação já ocorreu.

## Células e escolha de retorno

| Célula no arquivo | Uso nominal |
|---|---|
| `0x31a60` | raiz R, lida em `0x1a840` e recarregada antes das stores relativas |
| `0x31a68` | ponteiro P, cujos bytes +6/+7 escolhem o caminho |
| `0x31b60` | ponteiro Z para bytes usados nos campos de ajuste |

As três células contêm inicialmente `0xffffffffffffffff` no arquivo. Isso
não estabelece seu conteúdo runtime ou a validade dos ponteiros. Há uma
publicação selecionada de R em `0x19084`, com o retorno do alocador após
pedido de 1508 bytes. Não foi provado que seja o único escritor ou que
essa publicação ocorra antes desta chamada no aparelho.

| W0 recebido | Gate | Retorno | Store de metadado |
|---|---|---|---|
| 2 | P[6]=0 | B | u16 em Rentry+0x420 |
| 2 | P[6]!=0 | Qnew | u16 em Rentry+0x420 |
| 3 | P[7]=0 | B | u16 em Rentry+0x422 |
| 3 | P[7]!=0 | Qnew | u16 em Rentry+0x422 |
| outros | não consultado nesse teste | Qnew | nenhuma dessas stores |

O valor armazenado é **low16(ponteiro_retornado − Rlate)**. O destino usa
a raiz capturada na entrada; o subtraendo vem da raiz recarregada depois.
Não se presume que Rentry=Rlate diante de aliases/escritas externas.
O campo de 16 bits não basta para reconstruir o ponteiro inteiro sem
condições adicionais de intervalo/base.

Quando o gate é zero, os caminhos `0x1a880/0x1a92c → 0x1a930` retornam B
sem passar pelos BLs numéricos. Quando é não zero, quatro stores ajustam
Y, mesmo se n=0:

| Seletor | Campos de dois bits subtraídos de Y[0..3], multiplicados por 6250 |
|---|---|
| 2 | Z[3][3:2], Z[3][5:4], Z[3][7:6], Z[3][7:6] |
| 3 | Z[2][5:4], Z[2][7:6], Z[3][1:0], Z[3][1:0] |

As subtrações são u32. Os ponteiros/bytes são recarregados entre stores;
usar uma única amostra no modelo pressupõe que os aliases não os alterem.
Não há interpretação física de unidade ou significado dos bits nesta entrega.

## Construção de Qnew

O caminho geral faz setup em `0x1a294`. Se D é nulo, retorna Qnew depois
desse setup. Com D presente, busca registros de passo 48 usando
**UMULL(u32([D+20]),48)** e comparação X por igualdade. A contagem é unsigned,
diferentemente das buscas signed da continuação comum. `0xffffffff`
representa um span de 206158430160 bytes no modelo, sem demonstrar validade.

A busca conserva o primeiro registro coincidente ou o último examinado.
Não há fallback para o primeiro. Contagem zero deixa X14=0; se n>0 e os
acessos/chamadas anteriores retornarem normalmente, `0x1aa38` lê endereço
zero. Isso não comprova fault, mapeamento ou alcance no aparelho.

Para cada nível i, o BL numérico recebe A,Y,level[i],1. Se a chave coincide,
um byte do registro corrige o resultado usando v para v<=160 e 160-v para
v>=161. A palavra final, sob campos conservados, é:

`(low8(resultado_numérico + correção_opcional)<<24) | (u32(level[i]*1000)&0x00fffff8)`.

O cálculo FP e os efeitos de memória de `0x1a294` permanecem opacos.
Seu corpo selecionado não referencia os GPRs X13..X28, sustentando os
ponteiros/contadores transportados pelo chamador sem presumir preservação
ABI dos registradores voláteis X13/X14/X15/X18.

## Tag, gate e duas adições no mesmo byte

Antes da continuação, o caso original 2 copia Z[2].bit3 para **W27 e P[6]**
em `0x1ae60/0x1ae64`; o caso original 3 copia Z[2].bit2 para **W27 e P[7]**
em `0x1ae9c/0x1aea0`. Logo, nessas duas cadeias preservadas, tag/gate têm
o mesmo valor 0 ou 1. Os helpers packed/numérico selecionados conservam W27.
O próprio `0x1a804` usa W27=1000 internamente, mas salva X27 em `0x1a824`
e o restaura em `0x1aaa8` no epílogo único. Assim, o teste da continuação
recebe a tag original após um retorno normal.

Se o caminho habilitado chega ao BL `0x1b354` com gate/tag zero, o helper
retorna B. A continuação então executa:

1. `0x1b110`: soma o byte de E ao byte B+4*i+3.
2. W27=0 não satisfaz o teste 255 que pularia a segunda store.
3. `0x1b134`: recarrega o byte Q+4*i+3 e soma o byte de E novamente.

Com **Q=B**, E estável e o laço executado, o mesmo byte recebe duas
adições, módulo 256. Exemplo de host: byte inicial 10, margem 3 → 16.
Com buffers disjuntos, cada byte recebe uma adição. Se a margem é zero,
duas stores não implicam diferença no valor final.

Esse é um efeito condicional da ordem das stores. Não demonstra valor
não zero de E, viabilidade conjunta das condições no boot real, significado
físico incorreto ou vulnerabilidade. Nos caminhos Qnew, uma nova chamada
de alocação também não prova disjunção física dos buffers.

## Reprodução

```sh
python3 scripts/inspect_newtime_secondary_result_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_secondary_result_hzc2.py),
[testes](../scripts/test_newtime_secondary_result.py),
[JSON](references/newtime-secondary-result-hzc2.json) e
[validação](references/newtime-secondary-result-validation-20261028.json).
GNU: 482 palavras, 47 alvos relativos e 91 operandos selecionados.
Os modelos cobrem gates, campos repetidos, wrap W, offset u16, contagem
unsigned, composição de palavra e ordem de stores com/sem alias exato.

Permanecem abertos MARGIN, as origens efetivas de P/Z, aliases, resultados
FP e as condições reais de execução. O slot 47 e seu X0 não foram resolvidos.
