# HZC2: origem nominal dos buffers de canal e descritores de cópia

Análise **estática, 2026-10-27 (Campo Grande)**, base `68eacaa`, após PR #46.
**Foi encontrado um escritor concreto das quatro células de canal:**
`0x2d468` publica bases fixas de `0x02075a00` a `0x02078910`, com passo
de 4016 bytes, e uma quinta base para o buffer de configuração. A rotina
`0x2f724` contém uma chamada nominal para esse inicializador.

Os intervalos selecionados não contêm a célula `0x31580` no mapeamento
adotado, **se os bindings e ponteiros publicados forem preservados**.
Não foi provada ausência global de transporte, outros escritores ou aliases.
O despacho e X0 do slot 47 continuam abertos. Não houve execução Samsung
ou ampliação do [escopo QEMU](newtime-gate-observation-scope-hzc2.md).

## Identidade e reprodução

Mesmo sboot HZC2 de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs e células da imagem são offsets de arquivo. A tradução nominal usa
`0x020ea000`; os endereços AP abaixo são literais reconstruídos do código,
não leituras do aparelho. S corresponde à âncora nominal `0x31688`.

```bash
python3 scripts/inspect_newtime_channel_origins_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
python3 scripts/validate_baseline.py
```

O [analisador](../scripts/inspect_newtime_channel_origins_hzc2.py) exige o
hash exato e confere **428 palavras, 70 alvos relativos e 64 operandos**
no GNU. O [JSON](references/newtime-channel-origins-hzc2.json) registra
instruções, hashes dos intervalos, referências diretas e condições.
Os modelos de diretório são deduções aritméticas de host, não execuções
das rotinas originais nem capturas de metadados.

## Escritor e chamada nominal

`0x2d468` usa ADRP+ADD para S e MOV/MOVK para `0x02075a00`.
Cada STR X abaixo escreve oito bytes; os ADD intermediários somam `0xfb0`:

| STR | Célula de arquivo | Base publicada | Uso selecionado |
|---|---|---|---|
| `0x2d478` | `0x31908` | `0x02075a00` | Canal 0 |
| `0x2d480` | `0x31910` | `0x020769b0` | Canal 1 |
| `0x2d488` | `0x31918` | `0x02077960` | Canal 2 |
| `0x2d490` | `0x31920` | `0x02078910` | Canal 3 |
| `0x2d498` | `0x31928` | `0x020798c0` | Buffer de configuração; extensão própria não derivada aqui |

O ponteiro nominal para `0x2d468` aparece em `0x31498`, índice **18** da
tabela `0x31408`. Em `0x2f730`, o código lê essa célula por base `0x31000`
mais 1176, e o BLR de `0x2f73c` a chama. Isso liga a chamada ao inicializador
sob preservação do slot, sem confundi-lo com o slot 47 da mesma tabela.
A entrada `0x2f724` tem seu próprio ponteiro nominal em `0x31488`, slot 16;
seu chamador efetivo não foi resolvido nesta entrega.

Depois vem `0x2f740 → 0x2e4fc`, mantida opaca nesta análise. Se W0=0, o
laço `0x2f7d0–0x2f7f0` relê as quatro células e zera 4016 bytes em cada
buffer. Se W0 não é zero, pula esse ramo. A publicação antecede a consulta,
mas a preservação da memória por ela continua sendo condição; a ABI de
registradores não garante preservação das células globais.

Os quatro intervalos nominais são adjacentes, com união
`[0x02075a00,0x020798c0)`. Nenhum intersecta os oito bytes de
`0x0211b580`, endereço nominal da célula investigada. Isso delimita as
quatro cópias de 4016 bytes de `0x22148/58/68/78` **nesse binding**.
Não demonstra que os valores estejam ativos no boot observado.

## Diretório que registra e recupera os buffers

A célula `0x30b78` contém inicialmente `0x0223f000`. As rotinas a recarregam;
seu conteúdo em runtime e todas as escritas por alias não foram determinados.
Com essa base preservada, o layout usado pelo código é:

| Endereço relativo à base | Campo |
|---|---|
| `+0x2c` | Cursor u32 para próxima área de dados |
| `+0x30` | Contagem u32 de registros |
| `+0x34+24*i` | Nome: cópia de até 16 bytes |
| `+0x44+24*i` | Origem/endereço u32 do registro |
| `+0x48+24*i` | Comprimento u32 |

`0x21ec8` escreve o cabeçalho, zera a contagem, põe o cursor em
`0x0223f000` e registra `header` com tamanho **416 bytes**. O cabeçalho
é registrado na própria base; essa etapa não copia um segundo buffer para lá.
Em `0x22120`, os quatro nomes `phy_trn_ch0` a `phy_trn_ch3` são registrados
e copiados por `0x21f84`, usando as bases de canal e 4016 bytes cada.
A chamada de `0x1f420` é condicionada ao retorno não zero de `0x21b78`,
campo `[M64(S+616)+32]` não zero e byte S+739 zero. Não se atribui a esses
testes um estado de boot físico nesta entrega.

A recuperação `0x22098 → 0x21ff8 → 0x21d3c` procura os mesmos nomes e
usa os ponteiros de canal como destinos. O lookup percorre **15 posições,
independentemente da contagem atual**. Ao encontrar o nome, retorna seu
endereço; `0x22004` carrega origem/tamanho por LDP W1/W2 em +16/+20.
A origem é u32 estendida por zero, não um offset a somar à imagem.
Um nome encontrado não certifica frescor, integridade ou origem dos metadados.

## Dois exemplos condicionais de diretório novo

Sob inicialização completa, chamadas normais, nomes distintos, bindings
preservados e nenhuma edição/registro intermediário, o código permite as
seguintes deduções. `0x220e8` pode acrescentar `charac_lvcc` de 52 bytes
antes dos canais; a condição desse ramo não foi medida.

| Perfil de host | Primeiro registro de canal, nominal | Cursor após quatro canais | Contagem final |
|---|---|---|---:|
| Apenas header antes dos canais | `0x0223f1a0` | `0x02243060` | 5 |
| Header + charac_lvcc antes dos canais | `0x0223f1d4` | `0x02243094` | 6 |

Os endereços de todos os registros estão no JSON. Nenhuma origem de
recuperação desses exemplos inclui a célula do slot 47. Diretório
preexistente, outros registros ou metadados alterados não são esses perfis;
seus valores continuam abertos. Os modelos não fornecem valores para
continuar a execução além do gate NEWTIME.

## Ordem das verificações e limites do modelo

Em `0x21dc0`, a verificação de nomes duplicados antecede a cópia do nome.
Depois, **origem/tamanho e novo cursor/contagem são gravados antes** das
comparações contra `0x02257fdf` e contagem 15. Esses testes são unsigned,
e a soma do cursor usa W, com wrap de 32 bits. Não são prova geral de
ausência de overflow, acesso válido ou ausência de edições parciais.

O modelo termina na primeira solicitação de erro desses limites e não
executa `0x1fdb8`. Embora o handler contenha WFI, existe um RET sintático
posterior: não foi tratado como uma função comprovadamente sem retorno.
Os exemplos novos passam pelos limites aritméticos sob suas condições;
isso não valida endereços ou execução no Samsung.

Passaram **95 testes NEWTIME**, incluindo 11 novos de limites/ordem/layout,
reprodução byte a byte, recusas de firmware curto/longo/alterado e baseline
completo de código próprio. [Validação](references/newtime-channel-origins-validation-20261027.json).

A origem nominal das quatro células e a produção selecionada de descritores
agora têm arestas concretas. Preservação posterior e metadados efetivos
seguem abertos. A próxima frente pode seguir o argumento X5 do slot 20
da outra tabela e o despacho que fornece X0 ao slot 47; nenhuma ligação
entre eles foi demonstrada por esta análise.

Continuação: [chamadores do slot 20 e origem de X5](newtime-slot20-hzc2.md)
liga oito cargas a nove chamadas nominais: sete X5 zero e duas com buffer
local calculado, sem ligação demonstrada ao slot 47. A busca adicional
de endereços preserva o limite das formas aceitas.
