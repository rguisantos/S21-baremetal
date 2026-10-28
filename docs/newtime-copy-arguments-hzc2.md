# HZC2: argumentos das 47 referências ao helper de cópia

Análise **estática, 2026-10-27 (Campo Grande)**, base `5b3ef6a`, após PR #45.
**Não foi encontrado transporte comprovado da célula `0x31580`; o despacho
do slot 47 e seu argumento X0 continuam abertos.** A investigação anterior
examinara três referências. Esta entrega revisa as outras 44, organiza as
47 por fluxo de argumentos e segue referências diretas de seus wrappers.
Revisar um local não significa resolver seus ponteiros recebidos ou aliases.

Não houve execução de instruções Samsung, resposta MMIO/SMC ou mudança no
runner QEMU. O baseline executado separadamente usa somente código próprio
em ambiente sintético. A [observação antes do gate](newtime-gate-observation-scope-hzc2.md)
e suas fronteiras permanecem iguais.

## Identidade e método

Sboot HZC2: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets são de arquivo. `nominal(p)` significa `p+0x020ea000`, sem afirmar
que esses bytes estejam preservados ou sequer mapeados assim no aparelho.
S é a âncora nominal correspondente a `0x31688`.

A célula contém oito bytes em `0x31580`, endereço nominal `0x0211b580`;
a janela da tabela nominal é `[0x0211b408,0x0211b588)`. O scan de 219136
palavras alinhadas em `[0x16000,0xec000)` reencontra **46 BL e um B** para
`0x1fcc4`. Isso enumera codificações candidatas; não prova alcançabilidade
nem cobre chamadas indiretas, outros helpers ou outras imagens.

O [analisador](../scripts/inspect_newtime_copy_arguments_hzc2.py) associa
deduções manuais a instruções testemunhas e exige o hash exato. Não é um
executor simbólico geral. O GNU confere **1320 palavras, 231 alvos relativos
e 46 operandos selecionados**, incluindo larguras e extensões de sinal.
O [JSON](references/newtime-copy-arguments-hzc2.json) contém cada PC,
expressões de X0/X1/W2, limites, intervalos com hash e instruções conferidas.

## Semântica do helper e grupos revisados

`0x1fcc4` começa com X3=0; a cada iteração compara `signed32(W2-W3)` com
zero, lê um byte de `[X1+X3]` e grava em `[X0+X3]`. Se os acessos forem
válidos, copia `max(signed32(W2),0)` bytes para frente. Um W2 com bit 31
ligado não significa uma cópia positiva de mais de 2 GiB.

| Grupo | Referências | Origem e limite |
|---|---:|---|
| Strings com endereço nominal fixo | 24 | Nomes de arquivos/funções; comprimento vem de `strlen`, sobre memória mutável |
| Salvamento/restauração por campos AP | 6 | Ponteiros derivados de cabeçalhos e SP; 160, 72 ou quatro vezes um byte recarregado |
| Salvamento/restauração por canal | 5 | Ponteiros de `0x31908+8*i` e SP; 160/200 bytes, quatro canais no laço selecionado |
| Buffer de configuração | 2 | `0x31630` e `0x31668`, destino recebido pela célula S+672 |
| Índice com extensão de sinal | 2 | `0x31630+4*signed32(W3)` e `0x31668+32*signed32(W3)` |
| Wrappers de registro/recuperação | 2 | Entrada recebida ou metadados localizados por nome; ponteiros efetivos abertos |
| Buffer recebido por `0x1ff50` | 1 | Origem da entrada X0 e tamanho `u8(W1)`; oito referências diretas ao wrapper |
| Buffer opcional recebido por `0x2b498` | 1 | X5 não zero, 64 bytes para SP+0x70; origem ainda aberta |
| Cópias de seis bytes | 2 | SP para campos de canal; não transportam oito bytes inteiros em uma chamada |
| Scratch para a pilha | 1 | `0x31f30`, 108 bytes, em `0x26f1c` |
| Origem literal externa | 1 | `0x021ab6a4`, 52 bytes, em `0x2e8b8` |

Total: 47 referências. As sete cópias fixas de outro mecanismo continuam
com o resultado próprio do [relatório anterior](newtime-transports-hzc2.md);
não fazem parte dessa soma.

## Exclusões locais e suas condições

As origens fixas de `0x1db58`, `0x26f1c` e `0x2e8b8`, com comprimentos
32/108/52, não intersectam a célula. Em `0x1db2c`, a origem fixa também
fica depois da célula. O laço em `0x1dabc–0x1dadc` deixa W19=4 sob
preservação de X19 pelas chamadas intermediárias. Essa é uma dedução do
código, não o valor capturado no aparelho.

As 24 cópias de strings apontam para nove origens nominais. Os bytes
iniciais do arquivo terminam em NUL antes da célula. Por exemplo,
`0x241f8/0x24268` usam `0x30438`, nome `src/common/training/training.c`;
isso vem dos dois ADD `0x24178/0x24180`, não de uma suposição pelo contexto.
O comprimento efetivo é obtido de `0x1fce8`. Alteração dos bytes, aliases
ou um comprimento diferente no aparelho não foram excluídos. A projeção
dos bytes iniciais fica separada da conclusão de runtime no JSON.

`0x26950/0x26978` copiam seis bytes por chamada. Isso exclui somente o
transporte da célula inteira por **uma** dessas cópias. Não exclui leituras
parciais, combinação de resultados ou sobrescrita por um destino alias.
Da mesma forma, SP relativo não demonstra uma origem fora da tabela sem
um contrato para a pilha efetiva.

## Índices: o chamador importa

`0x25400` não impõe localmente um índice W3 não negativo. A primeira rota
usa ADD com `sxtw #2`; a segunda usa SBFIZ em X3, com campo de 32 bits e
deslocamento 5.
Não se pode interpretar esses índices como unsigned para afastar a tabela.

O scan encontra **uma referência direta** à entrada: `0x25a58`, no laço de
`0x259f4`. X20 começa em zero; a chamada ocorre somente enquanto
`signed32(W20) < signed32(W24)`, recebe W3=W20 e depois incrementa X20.
Sob entrada normal e preservação de X20/X24 pelas chamadas, o índice da
chamada é não negativo, no máximo `0x7ffffffe`. Nessa rota, as duas origens
ficam acima da célula e seus intervalos não dão wrap.

Isso afasta ler a célula por **esse caminho selecionado**. Não restringe
chamadores indiretos, entradas internas ou uma violação das condições de
preservação. Também não resolve o destino `M64[S+672]` nem exclui que ele
sobrescreva a tabela.

## Wrappers: próxima fronteira concreta

`0x21f84` conserva a origem da entrada X1 e o tamanho W2, chama `0x21dc0`
para registrar uma área e passa a origem ao helper em `0x21fe4`.
As seis referências diretas ao wrapper estão no JSON. Quatro delas,
`0x22148/58/68/78`, carregam origens de `0x31908/10/18/20`, com **4016
bytes** cada. Essas quatro células são zero no arquivo; seus valores em
runtime não foram reconstruídos nesta entrega.

Uma outra rota concreta é `0x25ee8 → 0x22014 → 0x21f84`. O argumento de
origem é o **endereço de `0x31c30`**, guardado em `[SP+128]` e recarregado
em `0x25ed8`, e não o ponteiro armazenado nessa célula. O tamanho é
`162*u8(objeto_atual+12)`, até 41310 bytes. A origem fica acima de
`0x31580` e a cópia para frente não inclui essa célula nesse mapeamento.
Isso não estabelece endereço final, preservação ou sucesso das chamadas.

No sentido inverso, `0x21ff8` chama `0x21d3c` para localizar um nome num
diretório com passo de 24 bytes. O lookup retorna o endereço do campo de
nome; o LDP **W1/W2** em `0x22004` lê origem e tamanho em +16/+20. A
origem é estendida de 32 para 64 bits, não calculada como offset do sboot.
O destino é a entrada X1 de `0x21ff8`. As cinco referências diretas estão
inventariadas, mas nenhum descritor efetivo foi capturado. A existência do
wrapper não demonstra que algum registro contenha a tabela investigada.

Por fim, o buffer opcional de `0x2b504` recebe X5 de `0x2b498`. Não há
referência B/BL direta à entrada no intervalo pesquisado. Seu ponteiro
nominal aparece em `0x31088`, índice **20 de `0x30fe8`**. Essa tabela é
distinta de `0x31408`, cujo slot 47 estamos investigando. O ponteiro inicial
não resolve o despacho indireto nem o argumento X5.

## Reprodução e validação

```bash
python3 scripts/inspect_newtime_copy_arguments_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
python3 scripts/validate_baseline.py
```

O relatório foi reproduzido byte a byte. Arquivos curto, longo e alterado
foram recusados antes de emitir JSON. Passaram **84 testes NEWTIME**, dez
novos para limites de comprimento/sinal/interseção, e o baseline completo:
43/60/17 casos de host, diagnóstico 12, loader 1+5 e leitor 17.
[Evidência da validação](references/newtime-copy-arguments-validation-20261027.json).

O inventário dos argumentos diretos está revisado. A próxima etapa útil é
seguir os escritores das quatro células de canal e os descritores que o
lookup pode recuperar; para o buffer opcional, resolver os despachos do
slot 20 com o argumento X5. Transporte, escrita sobre a célula e uso do
valor como ponteiro de função continuam perguntas diferentes. O leitor de
AP0x0207365c, o significado físico das colunas e a origem do X0 do slot 47
permanecem abertos.

Continuação de 27/10: [origens dos canais e descritores](newtime-channel-origins-hzc2.md)
liga o escritor `0x2d468` às quatro bases fixas e uma chamada nominal,
delimita o diretório e dois perfis novos condicionais. Isso avança as
origens selecionadas acima sem comprovar preservação ou transporte do slot 47.
