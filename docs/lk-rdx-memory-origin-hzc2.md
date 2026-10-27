# LK HZC2: origem da memória RDX e conclusão para a sonda

Análise estática de **2026-10-26 (Campo Grande)**, base `ce67fc5`, após o
PR #35. Sboot de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; globais são endereços relativos das instruções.
Nenhum firmware Samsung, MMIO, SMC, cliente USB ou telefone foi executado.

**A origem foi encontrada: `0xee370` constrói a tabela relativa `0xcd31d0`.
Com ao menos dois bancos produzidos e conservados, o primeiro descritor `ap`
do perfil que acrescenta RAM cobre `[0x80000000,0xc0000000)`, incluindo toda
a janela candidata da sonda. A sonda atual não oferece retorno cooperativo
ao LK; portanto essa cobertura não completa sua recuperação por RDX.**
Retenção após reset e disponibilidade física do transporte não podem ser
concluídas destes bytes estáticos. O resultado encerra a busca da origem e
da cobertura nominal; não declara uma captura do aparelho.

## Produtor e formato real da origem

`0xee380 → 0x147e88` retorna o objeto relativo `S = 0xcd31a8`; `0xee388`
guarda S em X19. `0x148030` devolve S+0x28, isto é, `0xcd31d0`.

| Operação do produtor `0xee370` | Evidência |
|---|---|
| Quantidade N | `0xee38c → 0x11b6c0`, preservada em W20 |
| Banco inicial | `0xee3d8`: par u64 `(0x80000000,0x20000000)` em S+0x28 |
| Bancos seguintes | `0xee3f0–0xee404`: início anterior+0x20000000, tamanho 0x20000000, passo 16 |
| Descontinuidade no índice 4 | `0xee3dc` monta `0x880000000`; `0xee41c` grava o par em S+0x68 |
| Inicialização normal selecionada | `0xfa9a0 → 0xee660 → 0xee66c → 0xee370` |
| Preparação do caminho de bootloader selecionado | `0x15e590 → 0x15e180 → 0x15e190 → 0xee370` |

Cada banco lógico tem **16 bytes: início u64 e tamanho u64**. O passo de 32
bytes visto pelo dump corresponde a dois bancos por iteração. Ele não define
um registro independente de geometria de 32 bytes. Este produtor constrói
endereços por aritmética; não importa os nós do FDT nem lê as regiões descritas.

As equações dos stores, para os pequenos N não negativos usados no modelo,
são:

| Índice i | Início | Tamanho |
|---|---|---|
| 0 a 3 | `0x80000000 + i × 0x20000000` | `0x20000000` |
| 4 em diante | `0x880000000 + (i−4) × 0x20000000` | `0x20000000` |

O primeiro par é escrito inclusive para N=0; o append, porém, não acrescenta
entradas se a quantidade retornada não for positiva. Os limites dos laços
usam comparações com sinal sobre W. A ferramenta aceita somente N de 0 a 64
por orçamento do host, sem atribuir esse limite ou capacidade de array ao LK.

## Quantidade, cache e ressalva dos 12 GB

`0x11b6c0` retorna o cache u32 relativo `0xaa7ea8`, se não zero. No outro
ramo lê u64 de AP`0x02038848`, guarda o total em `0xaa7e98`, desloca 29 bits
e publica os 32 bits baixos no cache. A unidade desse ramo é 512 MiB.

Há outros escritores conferidos: `0x11b6f0`, `0x11b758` e `0x11b798`.
Este último recebe uma quantidade em GiB, faz `<<30` e pode limitar o cache
ao valor solicitado, desde que não exceda o total lido do registrador.
O chamador `0x147310` passa os quatro bits baixos de X21. A análise não
inventaria todos os aliases/escritores nem observa a configuração ativa.

Logo, os **12.000000GB do log do bootloader continuam sendo uma observação
do log**, sem preencher AP`0x02038848`, N ou a tabela de execução. O exemplo
N=24 do extrator é um cenário explicitamente fornecido no host: produz 24
bancos de 512 MiB e 12 descritores de 1 GiB. Não é uma aquisição do S21.

## Ligação ao descritor e cobertura

`0x15e0e8` chama o getter da origem em `0x15e100` e o da quantidade em
`0x15e108`. Em cada iteração, lê o início em +0 e os tamanhos em +8 e +24,
soma os tamanhos e chama `0x12df68`. Avança 32 bytes e o contador em 2.
O nome fornecido em `0x245458` é `ap`.

Para os dois primeiros bancos desse produtor, sem alteração intermediária:

| Item | Intervalo, fim exclusivo |
|---|---|
| Banco 0 | `[0x80000000,0xa0000000)` |
| Banco 1 | `[0xa0000000,0xc0000000)` |
| Descritor `ap` resultante | `[0x80000000,0xc0000000)`; fim inclusivo `0xbfffffff` |
| Envelope candidato já usado no projeto | `[0x80080000,0x80378000)` |

O envelope está inteiramente contido no primeiro descritor. Isso vale se a
inicialização produziu ao menos dois bancos, eles foram conservados e o
perfil executa o append com quantidade positiva. O caminho de bootloader o chama em `0x15e75c`, após
as quatro entradas fixas; o caminho genérico o chama em `0x15e320` quando
`0x12dbc8(índice=0x11)` retorna 5. Não foi medido qual caminho está disponível.

O helper soma tamanhos sem conferir o início do segundo banco. A contiguidade
do par acima vem dos stores do produtor, não de uma guarda no append. Se N
for ímpar, a última iteração lê o tamanho do banco seguinte, que este produtor
não inicializou. O modelo conserva esse tamanho como desconhecido; não assume
uma cauda zerada. Alteração da tabela, wrap e contiguidade continuam distintos
de um intervalo de memória fisicamente disponível ou de RAM livre.

## Binding nominal do transporte

A cadeia de envio selecionada do [levantamento anterior](lk-dump-export-hzc2.md)
agora tem um produtor nominal para a tabela de operações do backend:

| Etapa | Ligação conferida |
|---|---|
| Registro de inicialização | Entrada de 24 bytes em `0x29b148`, nível `0x20000`, flags 1, função `0x113a60`, nome `dwc3_gadget_probe` |
| Publicação das operações | `0x113a60` calcula a tabela de arquivo `0x305530` e salta a `0x18d1b0`; o setter grava o ponteiro relativo `0xd060e0` |
| Criação do contexto | Entrada em `0x29b178`, nível `0x60002`, flags 1, função `0x18d210`, nome `usb_dev_gadget`; chama slot +0 e grava o retorno em `0xd060d8` no PC `0x18d27c` |
| Envio | `0x1178c4 → 0x112400 → 0x112338 → 0x18c4c8`; slot +0x38 da tabela inicial aponta a `0x114fe0`, que encaminha a `0x114eb8` |
| Finalização/consulta selecionada | `0x18c508` usa slot +0x48, alvo nominal `0x114c18 → 0x114b10` |
| Quantidade recebida | `0x18c570` usa slot +0x68, alvo nominal `0x113958` |

Os registros são consumidos pelo dispatcher `0xfa7b0`, que filtra nível e
flags e chama o ponteiro em +8 em `0xfa85c`. A sequência de inicialização
`0xfa948` chama a preparação `0xee660` antes da faixa `0x20000`, e chama a
faixa `0x60000–0x6ffff` depois. Isso estabelece uma ordem nominal selecionada,
dependente do percurso e do retorno dos helpers. Os ponteiros são mutáveis e
o contexto retornado, endpoints, controlador e progresso USB não foram observados.
Os corpos completos do driver e de sua configuração não foram auditados.

No leitor de entrada `0x111ef8`, a chamada `0x111f70` alcança `0x116f18`.
Seu ramo de memória exige entrada não vazia, bit 17 limpo e bit 16 definido.
Os estados selecionados usam o global relativo `0xaa7918`: seleção inicial/
metadados, fim e dados. Stores `0x117b0c` e `0x117a0c` alimentam início e fim
usados pelo envio; os blocos selecionados não confrontam esses valores com
os descritores publicados. Isso delimita uma aresta do código, sem provar
autorização completa, disponibilidade de leitura arbitrária ou aceitação de
entradas malformadas. Nenhum cliente ou sequência de pedidos foi criado.

## Conclusão de recuperação para a Image atual

Foi recompilada a mesma fonte `r8/entry_diag/start.S`, sem alterá-la. A Image
continua com 384 bytes, registro de 128 bytes no offset 0x100. O objdump
confere dois componentes fechados de controle normal:

| Caminho | Offset na Image | Instruções |
|---|---|---|
| Registro concluído | 0xd0–0xd8 | `wfe; b 0xd0` |
| Entrada recusada | 0xd8–0xe0 | `wfe; b 0xd8` |

A entrada mascara DAIF; o código da sonda não contém BL, BLR, BR, RET ou
ERET. Um evento que faça o WFE prosseguir encontra o salto de volta ao mesmo
laço. **Não há retorno cooperativo que retome o produtor RDX depois de gravar
o registro.** Isso não exclui reset, trap ou intervenção externa, cujos efeitos
não são modelados como um retorno normal.

RDX precisa de execução do LK e de bytes preservados no momento da leitura.
A cobertura nominal do endereço está resolvida. A Image atual não cumpre a
parte de retomada; os arquivos estáticos não comprovam retenção durante um
novo boot, disponibilidade USB/FMM ou aceitação de uma Image própria sob o
último estado informado, sem root e com bootloader travado.

A decisão técnica é **manter o ensaio físico bloqueado para esta combinação
de sonda e RDX**. Para mudar essa decisão é necessária uma rota compatível
de carregamento e uma destas evidências: aquisição independente enquanto a
sonda está parada, ou um mecanismo especificado e validado de retomada com
preservação. Um reset só serve depois de medir a retenção e a ausência de
sobrescrita. Não se troca o laço por `ret`: o estado de entrada e o contrato
de retorno do LK não foram validados para isso.

## Reprodução

```bash
python3 scripts/inspect_lk_rdx_memory_hzc2.py /caminho/sboot.bin
python3 scripts/test_lk_rdx_memory.py -v
make -C r8 build/entry_diag.elf build/entry_diag.Image
bash scripts/cross-run.sh tools/root tools/root/usr/bin/aarch64-linux-gnu-objdump -d r8/build/entry_diag.elf
```

[Relatório estático](references/lk-rdx-memory-hzc2.json): 839 palavras GNU,
202 destinos relativos e 85 operandos selecionados, mais ponteiros e registros
de inicialização conferidos. [Validação](references/lk-rdx-memory-validation-20261026.json):
16 testes novos, regressões, reprodução e conferência dos laços da Image.
Os exemplos são equações do host, sem emulação de firmware. O relatório também
lista candidatos B/BL alinhados no LK; essa busca não é um inventário completo
de aliases, chamadas indiretas ou alcançabilidade em execução.
