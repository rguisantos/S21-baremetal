# HZC2: geometria que substitui o marcador no estado BL2

Continuação do [registro anterior](bl2-geometry-record-hzc2.md) e do
[tratamento de erro NEWTIME](newtime-error-hzc2.md), sobre o mesmo sboot
de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets são de arquivo. A tradução de ponteiros usa o delta nominal
0x020ea000; bindings em execução não foram observados.

**A recarga não garante a substituição de 0xcafe. Um produtor posterior
zera os quatro slots e empacota resultados de consultas.** Foi conferida
a transformação condicional de respostas fornecidas até a folha de tamanho,
sem executar consultas de hardware ou recuperar a geometria do telefone.
O registro AP 0x02073600 e os slots relativos de estado são destinos distintos.

## Ordem selecionada, sem presumir execução física

| Ponto | Ação / alvo nominal | O que se pode concluir |
|---|---|---|
| 0x1e2c4 | Grava 0xcafe em 0x31978 | Marcador no primeiro slot de estado |
| 0x1e2d0, célula 0x31510 | Wrapper 0x2f6c0 e callback NEWTIME | Sob os bindings anteriores, o callback pode gravar o próprio marcador no primeiro u64 de R |
| 0x1e2e0, célula 0x314c8 | 0x2d568 com W0=W1=12 | Se alcançar 0x2d7e0, recarrega AP0x02073600 para 0x31978; a leitura pode continuar sendo o marcador |
| 0x1e85c | Chama 0x1d830, depois de outras fases | A ordem dos offsets não prova que todas as chamadas anteriores retornaram ou preservaram o estado |
| 0x1d840, célula 0x31500 | Empacotador 0x2f130 | Zera e reconstrói os quatro slots a partir das consultas |
| 0x1d848, célula 0x31558 | 0x2fa98, com retorno do empacotador em W0 | Callback intermediário não executado neste ensaio |
| 0x1d864, célula 0x31358 | Tail branch para 0x2caec | Folha de tamanho; há teste/possível chamada de erro antes desse salto |

0x2d568 tem um teste anterior à recarga, incluindo adição e comparação
signed em W; pode chamar 0x1fdb8. Seus efeitos e a inicialização maior não
foram executados aqui. A fase intermediária e os callbacks impedem declarar
um percurso físico completo a partir dessa ligação nominal.

## Escritas do empacotador

0x2f130 percorre slots 0..3. Antes de consultar cada um, **0x2f168 grava
XZR** em 0x31978+8×slot. O marcador e quaisquer bits anteriores são
descartados nesse slot quando essa instrução é alcançada. O corpo grava
estado relativo e pilha; não tem store direto no endereço AP fixo do
registro. Efeitos dos callbacks, aliases e escritores posteriores ficam abertos.

Para cada slot, consulta termos **1 e 2**, começando pelo seletor **5**.
Se a resposta W inteira é zero, não pede seletores 6/7/8 desse termo e
seus campos temporários ficam zero. Um W não zero cujo byte baixo é zero
continua ativo: o teste não é apenas sobre o byte que será empacotado.
As respostas W completas ficam nos arrays de estado base+32/64/96/128,
com stride de oito bytes por slot e quatro por termo.

| Bits do u64 reconstruído | Origem |
|---|---|
| 4–7 | 3 se termo 2 ativo; senão 1 se termo 1 ativo; senão 0 |
| 8–15 | Seletor 5, termo 1, byte baixo |
| 16–19 | Seletor 8, termo 2, bits 6–7 zero-estendidos |
| 20–23 | Seletor 8, termo 2, bits 2–5 |
| 24–27 | Seletor 8, termo 1, bits 6–7 zero-estendidos |
| 28–31 | Seletor 8, termo 1, bits 2–5 |
| 32–39 | Seletor 6, termo 1, byte baixo |
| 40–47 | Seletor 7, termo 1, byte baixo |
| 48–51 | Helper 0x2e3d0: bits 20–23 da leitura de 0x10000010 |

Os bits baixos 0–3, 52–55 e 60–63 permanecem zero sob o contrato dos
blocos analisados. Seletores 6/7 do termo 2 são lidos quando habilitados
e ficam nos arrays, mas não alimentam esses campos do u64.

O acesso nominal da consulta foi ligado anteriormente a **0x28480**:
controle u32, disparo e resposta u32 em base ativa+12, com tabelas de
bases mutáveis. Esses retornos e o valor de 0x10000010 não foram medidos.
Não se atribuíram nomes JEDEC, canal/rank ou capacidade física aos campos.

## Extensão seletiva nos bits 56–59

Depois de inserir a revisão, três comparações exatas podem solicitar
**seletor 0x31 (49), termo 3**, para o mesmo slot:

| u64 antes da extensão | Linha do seletor na NEWTIME embutida | Resposta 49, nibble baixo |
|---|---|---|
| 0x0001000860000110 | 10 | 0..3 são apagados; 4..15 preservados |
| 0x0001000850500130 | 15 | 0..3 são apagados; 4..15 preservados |
| 0x0001000860600130 | 12 | 0..15 preservados |

O código insere somente quatro bits da resposta em 56–59. Depois mascara
os 52 bits baixos para comparar com a terceira constante; se não coincidem
e o nibble é ≤3, apaga o nibble. Uma quase coincidência ou revisão diferente
não entra nessa consulta. As linhas são correlações no bloco embutido,
não seleções observadas no telefone.

Ao terminar, **0x2f46c** grava W21 em **0x31939** e W0 retorna o mesmo
modo: o do **slot 3**, processado por último. Já a folha de tamanho lê o
nibble 4–7 do **slot 0** para escolher um ou dois termos globais. Casos
sintéticos com modos diferentes confirmam essa distinção; não demonstram
que ela ocorra fisicamente ou seja um defeito.

## Execução de blocos originais com retornos fornecidos

[QEMU](references/bl2-geometry-packing-qemu-hzc2.json): **100 cenários**,
50 vetores em cada delta RAM 0x40000000/0x40200000. Cada cenário executa
os blocos originais do empacotador e depois a folha original de tamanho,
com os quatro slots resultantes. São **100 execuções adicionais da folha**,
sem o callback de validação intermediário.

O harness para **antes de cada BLR** de preparação/consulta e do
**BL 0x2e3d0**. Não executa essas instruções nem seus alvos: fornece X0,
ajusta LR/PC ao sucessor e preserva os demais registradores/memória.
Esse é o contrato explícito das arestas fornecidas. Não é execução integral
da função física, emulação de controlador ou prova de efeitos dos callees.

Foram comparados argumentos e ordem de todas as consultas, zeros anteriores
às consultas, os **784 bytes** do estado selecionado, campos temporários,
quatro u64, byte/retorno de modo, resultado da folha, ABI/SP, guardas,
instruções, tabela de densidades e dois slots de callbacks. Um registro
separado em RAM, de 0x2400 bytes, mantém 0xcafe e permanece intacto no
ensaio. Isso demonstra a separação no laboratório; não prova o alias ou
a preservação do registro AP no percurso físico completo.

Os vetores incluem marcador versus estado anterior de todos os bits ligados,
gates zero/full-W, termos isolados, todos os 16 índices, revisões extremas,
as três constantes e o limiar da extensão, modos diferentes entre slots
e oito matrizes determinísticas da seed 0x2f130. Entradas e resultados
numéricos do runner são sintéticos; não identificam os 12 GB do aparelho.

## Reprodução e próximos passos

```bash
python3 scripts/inspect_bl2_geometry_packing.py /caminho/sboot.bin
python3 scripts/check_bl2_geometry_packing_gnu.py /caminho/sboot.bin
python3 scripts/emulate_bl2_geometry_packing_qemu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
python3 -m unittest discover -s scripts -p 'test_newtime*.py' -v
```

[Estático](references/bl2-geometry-packing-hzc2.json) e
[GNU 2.44](references/bl2-geometry-packing-gnu-hzc2.json): **386 palavras,
27 alvos relativos, 33 operandos e sete ponteiros nominais**. Índice SHA-256
`8f76fc88d790dd7a6b0b39a904a3d690655457129eedf27da49e07deccdf1313`.
**Dez testes novos e 101 anteriores passaram**; nove recusas CLI exigem a
imagem exata antes de GNU/QEMU. Relatórios estático/GNU reproduzidos byte a
byte, Python compilado e links conferidos.
[Validação](references/bl2-geometry-packing-validation-hzc2.json).

A [segunda publicação NEWTIME](bl2-geometry-publication-hzc2.md) foi ligada
ao primeiro slot e ao ponteiro ativo, com chamadas originais e MMU sintética
no laboratório. Próximo: seguir os efeitos posteriores e callbacks
intermediários, mantendo respostas e aliases físicos desconhecidos.
Para fechar RAM física ainda faltam valores reais, demais bindings, limite
LK e bancos/reservas/FDT final. O empacotamento conferido não fornece esses dados.
