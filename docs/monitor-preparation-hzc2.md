# Preparação do monitor e mutações da lista LK HZC2

Auditoria estática de **2026-10-23**, continuação das
[fronteiras finais do LK](lk-final-edges.md). Imagem recebida: sboot de
4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Todos os endereços abaixo são offsets no arquivo, exceto os valores dos
registradores e ponteiros explicitamente identificados.

**Resultado:** foi localizado um pedido BL2 cujos argumentos se correlacionam
com o contêiner candidato do monitor; a busca de saltos B também encontrou
um segundo objeto de callback, com inserção/remoção desativadas pelo código
desta imagem. A operação segura, a completude da lista em execução e o estado
de entrada físico continuam sem comprovação. Não foi executado serviço seguro,
alterado firmware ou acessado o telefone.

## Pedido BL2 relacionado ao contêiner candidato

O wrapper `0x16500–0x16534` e sua cópia `0x36218–0x3624c` têm os mesmos
52 bytes. Ambos constroem os argumentos abaixo e chamam um veneer de duas
instruções, `SMC #0; RET`, em `0x16420` e `0x36138`, respectivamente.
O inspetor reconstrói os argumentos até esse limite, sem executar o SMC.

| Entrada W0 fornecida | X0, ID com sinal | X1 | X2 | X3 |
|---|---|---|---|---|
| `0` | `-0xe7` | `0x1b61` | `0x40000` | `0xe8000000` |
| `0x20` | `-0xe7` | `0x36c` | `0x40000` | `0xe8000000` |
| Outros valores W0 | `-0xe7` | `0` | `0x40000` | `0xe8000000` |

X0 contém exatamente `0xffffffffffffff19`. W0 é uma entrada explícita do
modelo, não o modo medido no aparelho. O chamador `0x1cb04–0x1cb80` obtém
um valor de outro serviço, deriva um índice e consulta bytes em `0x2fdf8`;
a chamada ao wrapper está em `0x1cb68`. Essa origem não fornece o valor
efetivo sem a resposta externa. Antes dela há outras preparações e testes.

Depois do SMC, `0x1cb6c` testa **W0**: zero continua em `0x1cb74`; valor
não zero fica no laço `0x1cb70`. Isso identifica o teste do chamador, sem
demonstrar retorno real zero ou classificar todos os possíveis valores X0.

Há três correlações aritméticas verificáveis:

- `0x36c × 4096 = 0x36c000`;
- `0x1b61 × 512 = 0x36c200`;
- `0x40000` é o tamanho do intervalo candidato `[0x36c000, 0x3ac000)`.

**As unidades de X1, a função de X3 e a operação do serviço não foram
identificadas.** Essas igualdades não provam leitura por setor, cópia,
verificação ou decriptação; tampouco demonstram onde o monitor executa.

Um wrapper posterior, `0x16534–0x1654c`, recebe um salto B de `0x1612c`
e prepara outro pedido: X0=`-0xe8`, X1=X2=0, X3=`0xbffff000`, seguindo ao
mesmo veneer. Sua semântica e o papel de X3 também estão abertos.

No candidato de cabeçalho há as palavras brutas abaixo. Elas são preservadas
como dados, sem atribuir-lhes tipos de campo ou um contrato de carregamento.

| Offset | Palavra little-endian |
|---|---|
| `0x36c310` | `00010000` |
| `0x36c314` | `bff80000` |
| `0x36c318` | `bff80000` |
| `0x36c31c` | `bff80500` |
| `0x36c320` | `bff9aac0` |

Literais nominais não estabelecem posse de RAM, reservas ou o estado após
o bootloader. Endereços de outra geração Exynos não preenchem essa lacuna.
O ID **-0xe7** não é o **-0x3ff** anterior ao salto final do LK.

## Segundo objeto: por que contar BL era insuficiente

A busca de palavras alinhadas no intervalo LK `[0xec000, 0x20c630)` agora
inclui tanto chamadas BL como saltos B para os helpers de lista:

| Local | Transferência | Objeto / condição |
|---|---|---|
| `0xff948` | BL `0x20c578`, inserir | Objeto conhecido `0x2ef138`, callback inicial `0xff6c8` |
| `0x16f6e4` | B `0x20c578`, inserir | Objeto adicional `0x31e5c8`, condicionado |
| `0x16f714` | B `0x20c5c8`, remover | Mesmo caminho adicional, condicionado |

Os dois últimos são transferências de cauda: não aparecem num censo restrito
a BL. O ponteiro no objeto adicional, em `E+16`, é `0xe8083018`, equivalente
ao offset `0x16f018` sob o delta LK já documentado `0xe7f14000`. Seus primeiros
dois ponteiros iniciais são `0xe82325c8`, apontando para o próprio objeto sob
esse delta. Isso descreve os bytes iniciais, não uma leitura da lista viva.

Os wrappers de inserção e remoção chamam `0x170750`, que contém exatamente
`MOV W0,#0; RET`. Depois de UXTB W0,W0, cada um usa CBNZ W0 para entrar
no ramo de alteração. O corpo do próprio callback também consulta esse gate:

| Chamada ao gate | Teste | Próximo PC com retorno zero |
|---|---|---|
| `0x16f6c0` | CBNZ em `0x16f6c8` | `0x16f6cc`: restaura e retorna, sem inserir |
| `0x16f6f0` | CBNZ em `0x16f6f8` | `0x16f6fc`: restaura e retorna, sem remover |
| `0x16f030` | CBZ em `0x16f038` | `0x16f0a4`: restaura e retorna, sem executar o corpo de log |

Isso vale sob instruções inalteradas, chamadas/retornos normais e ausência
de traps. **O objeto adicional existe no arquivo, mas esses caminhos não o
ativam nesta compilação.** Não é atestado de execução nem prova contra
inserções por outros caminhos, aliases, chamadas indiretas ou alteração de
código/dados. A expansão histórica de 1834 instruções permanece uma expansão
dos bindings declarados, sem alegação de completude.

## O que os helpers realmente escrevem

Seja H a cabeça em `0x3218c0`, E o nó fornecido e T o antigo `[H+8]`.
A inserção grava `E[0]=H`, `E[8]=T`, `T[0]=E` e `H[8]=E`, nos stores
`0x20c590`, `0x20c598` e `0x20c59c`. Existe um segundo percurso equivalente
em `0x20c5b4/0x20c5bc/0x20c5c0`, selecionado pela máscara IRQ herdada.

A remoção lê E0=`[E+0]` e E8=`[E+8]`; grava `E8[0]=E0`, `E0[8]=E8` e
zera E[0]/E[8] em `0x20c5d8/0x20c5e0/0x20c5e4`. O segundo percurso usa
`0x20c5f4/0x20c5fc/0x20c600`. A implementação relê alguns campos durante
essas operações; as expressões resumem o percurso normal, sem concorrência
ou aliases que mudem os campos entre acessos.

Esses helpers não escrevem o ponteiro de callback em E+16. Isso restringe
os efeitos desses corpos; não prova validação geral de ponteiros, segurança
da lista, imutabilidade da tabela de operações ou ausência de outros
escritores. O censo B/BL é de candidatos alinhados, não análise completa de
fluxo de ponteiros de todo o firmware.

## A impressão de informações do monitor é outra consulta

Em `0xf9844`, o LK chama `0xf6178` com buffer em `X29+0x28` e tamanho
`0xb4` (180 bytes). O wrapper prepara X0=`-0x12d`, X1=buffer, W2=tamanho,
X3=0 e executa SMC em `0xf6188`. Depois imprime
`EL3 Monitor information:` e o buffer como string.

Esse chamador solicita metadados. Ele não demonstra um dump do código do
monitor, a recuperação do handler de **-0x3ff** ou seus retornos reais.
Os quatro IDs **-0xe7, -0xe8, -0x12d e -0x3ff** permanecem contratos
distintos. Nenhuma resposta segura foi fornecida ou executada nesta etapa.

## Reprodução e validação

```sh
python3 scripts/inspect_monitor_preparation.py /caminho/sboot.bin
(cd scripts && python3 -m unittest test_monitor_preparation test_lk_final_edges -v)
```

O inspetor usa stdlib, leitura limitada e recusa qualquer tamanho/hash
diferente. Há **14 testes novos** de argumentos X/W, modos, gates, limites,
saltos B/BL e adulterações; com as **15 regressões do grafo final**, foram
**29 PASS**. Não são os mesmos 29 testes da entrega anterior (15 do grafo
mais 14 do helper de cache), nem execução dos handlers originais.

A conferência independente com GNU aarch64 objdump **2.44** coincidiu nas
**160 palavras de instrução e 31 destinos relativos** dos blocos de código
selecionados. Tabela de modos e palavras do cabeçalho foram excluídas dessa
contagem. O ELF de inspeção foi criado a partir do binário sem modificar
seus bytes; os comandos são os da auditoria final anterior, incluindo o
intervalo BL2 `0x16000–0xec000`. O JSON abaixo conserva cada linha decodificada.

- [Pedidos, gates, objetos e hashes dos blocos](references/monitor-preparation-hzc2.json)
- [Conferência GNU por instrução](references/monitor-preparation-validation.json)
- [Saída dos testes de host](references/monitor-preparation-host-tests.txt)

Próximo limite concreto: identificar a implementação dos serviços seguros
ou sua preparação verificável e limitar os escritores indiretos da tabela
de operações/lista. O material recebido basta para continuar a investigação
estática; não é necessário reenviar firmware. Carregamento Samsung, posse e
coerência da Image, estado efetivo e leitura dos 128 bytes do diagnóstico
continuam necessários para o Marco A. Não houve nova validação física.

A [continuação da cadeia BL2](bl2-service-chain-hzc2.md) identifica a resposta X2 do getter -0xe9, o seletor W e os campos herdados no pedido anterior -0xe6. As correlações aritméticas acima continuam sem atribuição de unidades ou operação do provedor seguro.
