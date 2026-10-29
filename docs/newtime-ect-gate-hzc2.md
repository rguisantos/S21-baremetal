# HZC2: gate ECT, retorno sem parser e reserva corrigida

Auditoria estática de 2026-10-29 (Campo Grande), base remota `45f316f`.
O JSON recebido do GLM tem a árvore principal compatível com o código.
Esta revisão delimita os efeitos, a continuidade e o cursor do parser;
não reproduz a suíte de52 testes ou as185 verificações anunciadas, cujos
fontes não vieram no anexo. As44 palavras fornecidas foram conferidas.

Mesmo sboot de4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs/células são offsets de arquivo; tradução BL2 nominal `0x020ea000`.
Sem execução de firmware Samsung, monitor ou ampliação QEMU.

## Decisão e contratos dos helpers

O caminho normal da main chama `0x1ca44` em `0x160a0`. O ramo PMU0xbad
salta de `0x16084` para `0x16124`, sem esse BL. O scan de B/BL alinhado
confere esses PCs, sem demonstrar exclusividade frente a entradas indiretas.

`0x1654c` fornece X0=-233/X1=0 ao helper `0x16428`, que zera X2, faz SMC
e move X2 para X0. X3 não é normalizado por esse wrapper. Seja R esse
retorno opaco; o gate calcula em W:

`N=(u32(R) >> ((4*(u32(R)&15))&31))&15`.

O contador do LSR W é mascarado em cinco bits. O nibble baixo escolhe um
dos oito nibbles; seletores0/8 escolhem a si próprios. Há226 pares
seletor/valor representáveis na construção independente dos testes.

Sob retorno normal das chamadas, acesso à memória e preservação dos
registradores/frame e instruções selecionados:

| Condição | Próxima aresta | Efeitos diretos selecionados |
|---|---|---|
| N=4 ou5 | publica origem e salta para parser | duas stores em31c08/31c10; sem leitura do gate MMIO |
| N diferente, bit0 MMIO=0, assinatura coincide | parser | RMW relê MMIO e faz OR1; SMC244 variantes0/2 |
| N diferente, bit0 MMIO=0, assinatura difere | parser | sem store MMIO nesse ramo; SMC244 variantes0/1 |
| N diferente, bit0 MMIO=1, primeiro retorno X64 não zero | retorno1caf0 | sem store global direta selecionada |
| Mesmo bit0=1, primeiro retorno0, segundo retorno X64 não zero | retorno1caf0 | sem store global direta selecionada |
| Mesmo bit0=1, ambos retornos X64 zero | parser | duas stores em31c08/31c10 |

O MMIO é AP0x1586081c. Variante0/1/2 significa argumento X2, não código
retornado. Os wrappers -244 conservam o retorno X0 do monitor; X1 recebe
W0 estendido com zeros e X3=0. Na segunda chamada `0x1cae4`, W0=0 decorre
do teste anterior de **X0 inteiro igual a zero**, mesmo sem MOV adicional.
O ramo bit0=0 não usa os retornos desses SMCs para decidir a aresta parser.
Os resultados físicos continuam desconhecidos; a tabela não afirma que
SMCs retornem, sejam aceitos ou preservem memória/registros no aparelho.

## Assinatura, publicação e continuidade

O helper `0x1c9f4` compara os quatro primeiros bytes SRAM com a constante
PARA e os três seguintes com **os bytes atuais ECT+4..6**. PARA007 é o caso
com a origem ECT preservada. Por exemplo, SRAM=PARAabc e ECT=XXXXabc
satisfazem esse helper, mas não validam o prefixo do parser posteriormente.
O oitavo byte da assinatura não é comparado nesse helper.

O caminho parser guarda0x02153000 nas células31c08/31c10 e faz B1c87c.
Isso não demonstra validação do cabeçalho, despacho de callbacks ou sucesso.
No retorno que pula o parser não há store global direta selecionada, mas
há save/restore de pilha e chamadas ao monitor: **não se provou preservar
as células ou o MMIO por toda a cadeia**. All-ones no arquivo não estabelece
RAM residual, zeramento de BSS, valor ativo ou validade de ponteiros.

A main não testa o retorno do gate: sua instrução seguinte é BL161d8.
Cópia ECT em16114 e finalize em16120 estão depois na ordem do programa,
com várias chamadas/polls intermediários. Sua execução depende de que
essas etapas retornem. O blob de arquivo36000 copiado para SRAM em16118
não é amostra do conteúdo SRAM lido anteriormente pelo gate.

## Correção da reserva ASV/GEN

A [auditoria ASV/GEN anterior](newtime-asv-gen-hzc2.md) classificava
O+total+4 como a reserva inteira. Isso estava errado: o parser chama
`alloc(16)` em1c8b0 e avança/alinha o cursor **antes** de somar total+4.
Depois alinha novamente e só então valida o prefixo PARA em1c920.

| Limite, equivalente de arquivo sob o mapeamento selecionado | Valor |
|---|---|
| Origem O | 0x69000 |
| Cursor após descritor16/alinhamento | 0x69010 |
| O+header_total, campo bruto | 0x7a0c4 |
| O+header_total+4, soma bruta | 0x7a0c8 |
| Cursor real após incremento/alinhamento | **0x7a0d8** |
| Fim da origem copiada | 0x7d000 |

Os onze candidatos INTSCI0x7a0c4..0x7a0ce continuam **fora da matriz e do
intervalo indicado pelo campo total**, mas dentro da reserva bump maior
nesse caminho. Quatro também ficam antes da soma bruta O+total+4; esse
número não é uma classificação de sete acessos além da reserva.
Nenhum desses limites é guard de leitura ou prova de OOB físico.
O extrator e o JSON ASV/GEN foram regenerados com os dois limites separados.

## Finalize e efeitos posteriores

`0x1cb04` faz nova chamada -233 e pode escolher outro nibble, independentemente
da amostra usada pelo gate. A tabela em2fdf8 dá modos0/20/32/64. O modo64
pula SMC-237; os demais não. O helper230 em1643c faz stores em0xe7ffe000
antes do SMC, incluindo base/tamanho/parâmetros do estágio seguinte.
Modos64 e20 não sobrescrevem todos os campos de cauda desse registro.

Após SMC-230, `0x1cb58` testa **W0**: bits superiores sozinhos não impedem
o BL1caf4. Este faz STR WZR e zera **a palavra MMIO inteira**, incluindo
outros bits. Retorno W0 não zero leva ao laço1cb5c antes desse clear.
Depois SMC-231 tem outro teste W32 e pode ficar em1cb70 após o clear.
Essa diferença W/X impede reutilizar a interpretação X64 dos ramos do gate.

## Reprodução

```sh
python3 scripts/inspect_newtime_ect_gate_hzc2.py /caminho/sboot.bin
python3 scripts/inspect_newtime_asv_gen_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator independente](../scripts/inspect_newtime_ect_gate_hzc2.py),
[24 testes do gate](../scripts/test_newtime_ect_gate.py),
[JSON](references/newtime-ect-gate-hzc2.json) e
[validação/proveniência](references/newtime-ect-gate-validation-20261029.json).
Mais três regressões de reserva estão na suíte ASV/GEN. O comparador externo
não substitui o extrator ausente do GLM. Retornos físicos, efeitos do
monitor, aliases, alcance real dos callbacks e slot47/X0 continuam abertos.
