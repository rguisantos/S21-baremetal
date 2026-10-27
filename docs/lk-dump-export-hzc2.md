# LK HZC2: perfis de dump e encaminhamento RDX

Análise estática de **2026-10-26 (Campo Grande)**, base `715a5e3` após
PR #34. Sboot descomprimido: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets de instrução são de arquivo. Endereços relativos usados pelo código
e endereços nominais das regiões não são leituras da RAM do aparelho.

**Existe encaminhamento nominal de bytes no código RDX, mas ainda não há
um canal de recuperação demonstrado para a Image de diagnóstico.** O perfil
fixo examinado não inclui sua janela candidata. Outros descritores são
acrescentados a partir de estado de execução que ainda não foi adquirido.
Não foi executado firmware Samsung, cliente USB, comando no telefone ou gravação.

Continuação após o PR #35: a [origem da tabela foi encontrada](lk-rdx-memory-origin-hzc2.md)
em `0xee370`. São bancos lógicos de 16 bytes, consumidos dois por iteração.
O primeiro par conservado cobre a janela candidata; o binding nominal USB
foi ligado ao DWC3. A cobertura nominal está resolvida, e a sonda atual
continua sem retorno cooperativo ao LK ou aquisição física demonstrada.

## Quatro regiões fixas do caminho iniciado pelo bootloader

A tabela em `0x245340` tem quatro entradas de 40 bytes: nome[16], início u64
em +16, tamanho u64 em +24 e flag u64 em +32. Em `0x15e6fc–0x15e710`, o código
copia 160 bytes para a pilha. O laço `0x15e734–0x15e754` encaminha cada nome,
início e tamanho ao construtor `0x12df68`. Isso liga os dados à construção
de descritores, sem demonstrar que o caminho foi percorrido no telefone.

| Entrada | Intervalo nominal, fim exclusivo | Tamanho | Sobrepõe a janela candidata do diagnóstico? |
|---|---|---:|---|
| `log` | `[0xf0010000,0xf0210000)` | 2 MiB | Não |
| `boot_ram` | `[0xe8000000,0xe8280000)` | 0x280000 | Não |
| `auto_comment` | `[0x91100000,0x91101000)` | 4096 | Não |
| `summary.html` | `[0x91101000,0x91121000)` | 0x20000 | Não |

A comparação usa apenas um envelope conservador: entradas candidatas
`0x80080000+0..0x1f8000` do [modelo LK](lk-kernel-copy.md) e extensão da
[Image atual](entry-diagnostic.md) menor que 1 MiB pelo limite ADR do linker.
Isso dá `[0x80080000,0x80378000)`, não uma reserva de memória ou posição
medida. A não sobreposição vale para essas quatro entradas e esse perfil.

`boot_ram` corresponde exatamente à janela nominal da imagem LK no arquivo:
`[0xec000,0x36c000)+delta 0xe7f14000`. Portanto o nome não deve ser interpretado
como a Image de kernel/diagnóstico. A conta pressupõe o mesmo delta corroborado
na [cadeia de console](lk-console-handoff.md); não inventaria toda a BSS do LK.

`log` também **não inclui o cabeçalho** `[0xf0000000,0xf0010000)`. O
[leitor debug-snapshot](lk-memory-log.md) exige 0x210000 bytes contíguos,
incluindo cursor/flag no cabeçalho. Os 2 MiB da entrada fixa, isoladamente,
não satisfazem esse contrato nem permitem deduzir a ordem do anel.

## Descritores de saída e memória acrescentada em execução

O formato produzido é diferente da tabela de entrada, apesar do mesmo passo:

| Campo de saída | Offset / operação |
|---|---|
| Habilitado | u32 em +0 recebe 1 |
| Nome | +4, cópia limitada a 15 bytes e terminador em+0x13 |
| Início | u64 em +24 |
| Fim inclusivo | u64 em +32, `início+tamanho−1` módulo 2^64 |
| Próximo descritor | endereço atual+40 |

`0x12df28` prepara o cabeçalho em endereço relativo `0xccf720` e retorna +16.
`0x12dfdc` publica o comprimento relativo nesse cabeçalho. O corpo do escritor
não rejeita tamanho zero/overflow: as validações de intervalos do extrator são
guardas do host, não uma política comprovada do firmware.

Depois das quatro entradas, `0x15e75c` chama `0x15e0e8`. Outro caminho chama
o mesmo helper em `0x15e320`, se o valor retornado por
`0x12dbc8(índice 0x11)` for 5. Não se confundem esse índice e os bits de flags
do dispatcher descrito abaixo.

O helper usa o endereço relativo `0xcd31d0`, retornado por `0x148030`.
Consome registros de 32 bytes, toma início de +0 e soma os u64 em +8/+24 como
tamanho, avançando o contador em 2. O limite vem de `0x11b6c0`: u32 em cache
ou `u64(AP0x02038848)>>29`, truncado a 32 bits. O ramo de preenchimento do
cache deriva unidades de 512 MiB, não uma contagem de nós FDT. Outros possíveis
escritores desse cache não foram inventariados nesta análise.

Não foram obtidas as entradas dessa tabela. Somar dois tamanhos não comprova
contiguidade, RAM acessível ou preservação. A ausência da Image nas quatro
entradas fixas **não a exclui** das entradas acrescentadas ou de outros perfis.
Os 12 GB observados no log não preenchem esses descritores.

## Encaminhamento RDX delimitado

| Etapa | Evidência estática |
|---|---|
| Registro | `0x15e34c → 0x116e88 → 0x17b8d0`; grava callbacks nominais `0x116d00` e `0x116cf8` no objeto relativo `0xd05198` |
| Recepção/seleção | Código em `0x116f18` contém referências a `process_rx`/`usbd3_rdx_process`; testa bits 17 e 16 do getter `0x147ed8` nos pontos selecionados |
| Flags | Getter lê u32 relativo `0xcd34ec`. Chamadas em `0x15e230` e `0x15e6d4` passam máscara 0x10000 e valor 1 ao setter `0x147ee8`, cujo ramo faz ORR; preservação posterior continua aberta |
| Dados | Recorte `0x11786c–0x1178f0` lê início/fim inclusivo relativos `0x8a78c8`/`0x8a78a0`, verifica ordem e limita o bloco a 0x80000 bytes |
| Envio nominal | `0x1178c4 → 0x112400 → 0x112338`; o ramo de envio chama `0x18c4c8` e depois `0x18c508`, sem reconstrução completa desse backend |
| Metadados | `0x117a7c–0x117ae0` copia o cabeçalho/descritores para um buffer, envia e compara os bytes; isso não autentica a sessão do aparelho |

No ramo de dados selecionado, o ponteiro inicial é encaminhado diretamente
se o contexto é nulo ou `u32(contexto+4)==0`. O outro ramo chama `0x162cc8`
com buffer/campos de contexto e está associado à string `handle_storage_dump`;
os efeitos desse helper não foram reconstruídos. O recorte também contém
um caso sentinela específico; os
controles existentes não foram tratados como um validador universal.
Não foi auditado o protocolo completo, a autorização de cada pedido ou o
backend USB a jusante. Não se conclui que uma leitura arbitrária esteja
disponível ao host ou ao shell. Nenhum cliente ou sequência de pacotes foi criado.

## Políticas e estado não se reduzem a um único flag

O ponto `0x159528` referencia `cmd_upload`. Ele chama `0x149a90` com 1;
retorno não zero chega à mensagem de recusa FMM em `0x159570` e retorna 0,
sem alcançar o salto para `0x15e210` daquele ramo.

Outro wrapper, em `0x15e7d0`, tem tratamento diferente: no caminho associado
à mensagem FMM, encaminha `fmm_lock_upload` ao helper `0x146ba0` e converge
para uma cauda que retorna 1. Os efeitos desse helper não foram reconstruídos;
não o descrevemos como escrita de um flag. Esses recortes não sustentam
uma regra universal de aceitação ou recusa.

FMM não foi medido e não é equiparado ao último estado informado do
bootloader/AVB. Também não foram medidos os flags 16/17, o índice 0x11,
bindings USB, tabela de memória, permissões ou progresso dos loops.

## Retenção e decisão para o diagnóstico

A Image atual registra 128 bytes e estaciona em WFE, sem driver USB ou retorno
automático ao LK. Usar RDX exigiria demonstrar como seu produtor volta a
executar e conserva a região do ensaio. Reset, nova inicialização de DRAM,
cópia de kernel ou carregamento de recursos podem alterar os bytes; esta
análise não mediu esses efeitos. A existência do código de envio não fecha
o [contrato de aquisição](samsung-diagnostic-contract.md).

Há ainda nomes de um caminho para armazenamento (`boot_ramdumps_to_bootdev`,
`dumpsink_bootdev`), distinto do envio direto. Sua implementação/gravação e
leitura posterior não foram reconstruídas aqui. Não foi chamado esse caminho.

A [continuação de origem e cobertura](lk-rdx-memory-origin-hzc2.md) fecha a
aresta `0xee370 → 0xcd31d0 → 0x15e0e8`, com binding nominal DWC3 e uma
conclusão específica para o laço WFE da sonda. O transporte físico e a
retenção ainda precisam ser comprovados juntos; não repetir leituras Shizuku
já negadas ou alterar políticas do aparelho.

## Reprodução e limites

```bash
python3 scripts/inspect_lk_dump_hzc2.py /caminho/sboot.bin
python3 scripts/test_lk_dump.py -v
```

O extrator exige o hash exato, usa GNU objdump do toolchain existente e
confere 488 palavras, 103 destinos relativos e 61 operandos selecionados.
[Relatório reproduzível](references/lk-dump-hzc2.json) e
[validação](references/lk-dump-validation-20261026.json). Quatorze testes novos
conferem layouts, limites, aritmética modular e recusas de firmware incorreto.
Capstone foi usado na exploração, não é dependência do extrator.
O levantamento é estático e limitado aos intervalos publicados, sem prova
de alcançabilidade completa, estado físico ou ampliação de escopo QEMU.
