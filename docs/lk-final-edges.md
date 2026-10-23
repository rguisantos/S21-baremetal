# Fronteiras do trecho final LK HZC2

Auditoria estática de **2026-10-23 (Campo Grande)** do sboot recebido:
4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Continua o [helper de cache/MMU](lk-cache-handoff.md), sem executar firmware,
alterar payloads ou acessar o aparelho. Todos os endereços abaixo são offsets
no arquivo, salvo indicação explícita.

**Avanço:** o caminho direto e uma expansão explícita dos callbacks conhecidos
agora têm inventário reproduzível de controle e operações de sistema. Nesse
recorte expandido não há MSR na forma de registrador, SMC/HVC ou ERET depois
do helper. Há alterações de IRQ por MSR imediato, leituras de SCTLR_EL1,
espera por evento e um caminho DC ZVA. Isso reduz a lacuna dos corpos conhecidos;
**não comprova o estado final ou o progresso no telefone**.

## Recorte e expansão

A raiz é `0xfbde0`, logo após o helper; o inspetor para no BLR X4 em
`0xfbe14`, antes de executar o payload ou sua eventual continuação de retorno.
A chamada anterior de IRQ, `0xee658 → 0x101228 → 0x100df0`, é inventariada
separadamente. Não é uma nova validação do driver GIC.

| Grafo estático | Instruções inventariadas | Chamadas BL | Saídas indiretas |
|---|---:|---:|---:|
| Somente fluxo direto | 421 | 19 | 7 |
| Com expansões conhecidas | 1834 | 31 | 18 |
| Chamada IRQ anterior ao helper | 66 | 1 | 0 |

As duas alternativas dos ramos condicionais são exploradas. Não se executam
as instruções nem se provam viabilidade dos caminhos ou número de iterações.
O inventário tem limite de 8192 PCs únicos, recusa escapes do intervalo de
código e encodings de controle não suportados. Operações comuns de dados
não são interpretadas. O hash do índice ordenado PC/palavra e seus intervalos
permitem conferir o mesmo conjunto.

As 18 saídas indiretas do grafo expandido recebem tratamentos diferentes:

- **15 BLR X19 do formatador:** união dos callbacks produzidos pelos caminhos
  printf (`0x1b14e0`) e formatação para buffer (`0x1afcb0`). O produtor em
  `0x1b1658` e o adaptador em `0x1b10e8` fornecem esses valores. Não é análise
  geral de fluxo de registradores ou autorização para qualquer callback.
- **BR X0 em `0x1b0714`:** tabela em `0x26219c`, 91 halfwords com sinal,
  escala 4 e base `0x1b0718`; há 26 destinos distintos. O limite vem do
  teste de índice no próprio formatador. A tabela inteira é vinculada por hash.
- **BR X3 em `0x20c624`:** expandido pela tabela inicial do arquivo para
  `0x20c478`. A cadeia objeto/tabela continua mutável em execução.
- **BLR X3 em `0x20c4dc`:** expandido para o objeto conhecido registrado em
  `0xff948`, callback `0xff6c8`. Isso não prova que a lista contenha somente
  esse objeto ou que não seja alterada depois.

O delta LK `0xe7f14000`, corroborado na análise anterior, resolve os quatro
ponteiros iniciais. Ele não é uma nova medição de carregamento físico.
`runtime_graph_complete` permanece falso no relatório.

## Dependências posteriores ao helper

| Local | Instrução / condição | Implicação limitada |
|---|---|---|
| `0x12cee0` / `0x12cf1c` | MRS SCTLR_EL1; teste M | Dois helpers de sincronização pulam seus percursos quando M=0; um dos caminhos inclui SEVL/WFE e operações exclusivas |
| `0x1af608` | MRS SCTLR_EL1; teste M no preenchimento grande | O caminho de zeros pode chegar a DC ZVA em `0x1af664`; o código avança 64 bytes, sem medição de geometria nesta auditoria |
| `0x20c4a8–0x20c4f0` | Lê DAIF, pode DAIFSet #2 e DAIFClr #2 | O dispatcher evita limpar I quando já o recebeu mascarado; não muda D/A/F nesse corpo |
| `0xef4d4–0xef4d8` | Poll de `base+0x10`, bit 1 | Não há contador/timeout no laço; não está provado que a UART responderá após o helper |

Se o helper retornar normalmente em **EL1** com M=0 e ninguém mudar esse
estado, os três testes de SCTLR_EL1.M veem zero. Isso exclui os caminhos de
espera/zeragem condicionados a M=1 nesse cenário, não todos os motivos de
falha. Em **EL2**, limpar o SCTLR do EL atual não limpa SCTLR_EL1: os testes
posteriores podem tomar outros ramos. Não se troca EL2 por EL1 como premissa
ou se altera a entrada R10 com base nessa análise.

Na expansão examinada, as onze palavras de sistema são leituras de
CNTPCT_EL0, MPIDR_EL1, SCTLR_EL1 e DAIF, SEVL/WFE, DC ZVA e os dois MSRs
imediatos de IRQ. Não foi encontrada escrita na forma MSR registrador nem
ERET/SMC/HVC. O resultado vale para os nós enumerados e bindings declarados,
sem excluir traps, callbacks diferentes ou efeitos de MMIO no aparelho.

O [callback do log em memória](lk-memory-log.md) já tinha sido identificado;
a novidade aqui é incluí-lo no inventário condicional do trecho final.
Ele não oferece um canal de recuperação do registro do diagnóstico, não
reserva sua região para nós e não prova persistência após reset.

## SMC anterior: o que foi fechado e o que segue aberto

Em `0xfbdd0`, X0 recebe `0xfffffffffffffc01` (-0x3ff), X1/X2/X3 são zero,
e o destino `0xf6088` contém exatamente `SMC #0; RET`. O chamador não testa
o resultado antes das chamadas seguintes. Isso identifica o ponto de entrega,
sem demonstrar sucesso, efeitos de cache, retorno normal ou semântica do ID.

O veneer do monitor em `0x36c038` faz BL para `0x3813e4`; o ADR em
`0x36c044` aponta ao candidato de vetor `0x385000`. No arquivo recebido,
a primeira palavra daquele helper é `cbd452f0`, que o GNU objdump 2.44
apresenta como instrução indefinida. Os bytes do vetor tampouco foram
validados como código plaintext. Trechos, palavras e hashes foram preservados.
Não foi localizada uma ligação desse vetor ao handler de -0x3ff.

Isso é um limite da imagem em disco e da análise atual. Não se conclui uma
cifra específica por aparência/entropia, não se reinterpreta todo esse bloco
como código pronto e não se substitui a lacuna por um mock do serviço.
O carregamento/preparação do monitor continua uma investigação separada.

## Reprodução, testes e conferência independente

```sh
python3 scripts/inspect_lk_final_edges.py /caminho/sboot.bin
(cd scripts && python3 -m unittest test_lk_final_edges test_lk_cache_handoff -v)
```

A ferramenta só aceita o sboot exato, com leitura limitada antes da conferência
de tamanho/hash. Não depende de Capstone ou Unicorn. **29 testes passaram:**
15 novos de alvos relativos, chamadas/retornos, ciclos, limites, tabela com
sinal, encodings não suportados e rejeição de firmware, mais 14 do helper
anterior. Esses são testes do host, não novos cenários emulados de firmware.

Uma conferência separada usou GNU aarch64 objdump 2.44 sobre um ELF de
inspeção, criado sem mudar os bytes de sboot:

```sh
aarch64-linux-gnu-objcopy -I binary -O elf64-littleaarch64 -B aarch64 sboot.bin sboot.elf
aarch64-linux-gnu-objdump -D --start-address=0xec000 --stop-address=0x20c630 sboot.elf
```

Os PCs em `file_ranges` do JSON foram cruzados com as linhas do disassembler:
as 1834 palavras da expansão e seus 395 destinos relativos coincidiram;
nenhuma delas foi apresentada como `.inst`/UDF. Também passaram os recortes
direto (421 palavras/50 destinos) e IRQ (66/16). Os dados brutos do monitor
são uma consulta distinta e não foram incluídos nessa contagem de instruções
válidas do LK.

- [Grafo, tabelas, palavras e identidades](references/lk-final-edges-hzc2.json)
- [Conferência independente e operações de sistema decodificadas](references/lk-final-edges-validation.json)
- [Saída dos 29 testes](references/lk-final-edges-host-tests.txt)

A entrega fecha esse inventário sob as hipóteses declaradas. Para o Marco A
seguem pendentes o serviço seguro/estado efetivo, posse/coerência da imagem,
carregamento Samsung e leitura do registro de 128 bytes. Não há novo arquivo
solicitado nem razão para repetir as coletas Shizuku já bloqueadas.
