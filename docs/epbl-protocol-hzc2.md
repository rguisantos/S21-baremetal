# HZC2: buffers, MMIO e resultados da preparação EPBL

Continuação de **2026-10-23 (Campo Grande)**, sobre a main `ff90d419`.
Entrada: sboot original de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets de código são no arquivo. A tradução por delta `0x02024000`
continua hipótese nominal, como no [inventário anterior](epbl-frontier-hzc2.md).

**Resultado:** o percurso legível liga uma primeira saída de **48 bytes**
a dois campos da operação seguinte: **32 bytes de material e 16 bytes de IV**.
A segunda operação pede origem=destino e 46816 bytes, produzindo **32 bytes**
para comparação com o registro candidato EBHS. Foram inventariados **177
acessos MMIO** e conferidas **1095 instruções/114 destinos relativos**.
Não foi obtido plaintext verificado nem ligado um vetor ou handler SMC.

## Primeira etapa: entrada externa e produção de 48 bytes

O marcador/gate da [preparação anterior](epbl-preparation-hzc2.md) pode
pular o corpo. A sequência abaixo descreve o ramo que prossegue, sob
retorno normal das chamadas; não é execução medida no telefone.

| Transferência | Origem / instruções | Destino e extensão |
|---|---|---|
| Limpar scratch | `0x31bc–0x31c8`, stores W em passos de quatro | frame principal `[+0x88,+0x108)`, 128 bytes |
| Copiar semente | célula `0xfdf0` → nominal `0x02028698`, loop acrescenta **2** | candidato de arquivo `[0x469a,0x46ba)`, 32 bytes → início do scratch |
| Enviar scratch | 32 grupos LDR W/STR W, `0x3284–0x3480` | MMIO `+0x1100…+0x117c`, 128 bytes: 32 da semente e 96 zeros |
| Ler resultado | 12 grupos em `0x3574–0x3630` | MMIO `+0x11c0…+0x11ec` → frame `[+0x58,+0x88)`, **48 bytes** |
| Limpar registradores de semente | 32 stores após a leitura | MMIO `+0x1100…+0x117c`, 128 bytes zerados |

A semente fica **antes do EBHS**, não no EBRS. Seu hash está no relatório;
seus bytes não são interpretados como chave final ou resposta do hardware.

Configuração literal observada, na base **`0x18330000`**:

| Offset | Valor preparado | Limite de interpretação |
|---|---|---|
| `+0x100c` | `0xf` | configuração sem importar nomes de outra variante |
| `+0x14` | valor lido AND `0xfffffffc` | leitura real desconhecida |
| `+0x1008` | `1` | configuração |
| `+0x1020 / +0x1024` | `0x3fc / 0` | extensão da mensagem sob interpretação HASH candidata |
| `+0x1030 / +0x1034` | `0 / 0` | estado anterior preparado |
| `+0x1000` | `0x19` | seletor exato; algoritmo HZC2 não estabelecido |
| `+0x2c` | `0x40` | configuração do percurso de dados |
| `+0x40 / +0x44 / +0x48` | **`0 / 0x1fc00 / 0x3fc`** | três palavras de DMA, discutidas abaixo |

### Endereço e tamanho: não transportar o layout antigo

No consumidor posterior, as instruções demonstram pares de 64 bits:

| Campo carregado | Palavra baixa | Alta após LSR X,#32 | Extensão W |
|---|---|---|---|
| request `+0x58`, origem X | MMIO `+0x24` | `+0x20` | `+0x28`, request `+0x60` |
| request `+0x68`, destino X | MMIO `+0x154` | `+0x150` | `+0x158`, request `+0x70` |

O mesmo espaçamento **alto/baixo/tamanho**, aplicado a `+0x40/+0x44/+0x48`,
indica a entrada candidata **`[0x1fc00,0x1fffc)`**, com **1020 bytes**.
É inferência de layout sustentada pelo mesmo prefixo; faltam especificação
HZC2 e mapeamento/conteúdo dessa entrada. Não se declarou que esses bytes
sejam ROM, fusíveis ou RAM, nem que estejam contidos no sboot recebido.

Interpretar `+0x40` como endereço de 32 bits e `+0x44` como tamanho daria
“endereço zero, tamanho 0x1fc00”. A referência SSS antiga não autoriza essa
transposição. O relatório conserva palavras brutas e hipótese separadas.

## Segunda etapa: descritor e ligação dos buffers

O request começa em frame principal `+0x88`. Em `0x3838–0x3848`, os primeiros
32 bytes da saída anterior vão ao request `+0x00`. Em `0x3850–0x3868`, os
16 seguintes vão ao request `+0x44`.

| Campo relativo ao request | Valor/origem no chamador |
|---|---|
| `+0x00…+0x1f` | saída anterior `[0,32)` → oito registradores `+0x480…+0x49c` |
| `+0x40` | tamanho do material: **32** |
| `+0x44…+0x53` | saída anterior `[32,48)` → `+0x430…+0x43c` no modo 1 |
| `+0x58 / +0x60` | origem `0x02028700`, extensão `0xb6e0` |
| `+0x68 / +0x70` | destino `0x02028700`, capacidade `0xb6e0` |
| `+0x74` | zero preparado pelo chamador |
| `+0x78 / +0x7c / +0x80` | modo **1**, direção **1**, campo extra **0** |

O pedido cobre nominalmente `[0x4700,0xfde0)` no arquivo. Igualdade dos
ponteiros não comprova transformação ou posse física da região.

A tabela `03 00 00 02` e os seletores produzem controle **`0xfab`** para
esse chamador: base `0xf88`, direção 1, modo 1 acrescenta 2 e material de
32 bytes acrescenta `0x20`. Modo 2 também acrescenta 2 neste consumidor;
não foi renomeado por suposição.

Os bits AES da fonte primária SSS fixada abaixo descrevem decriptação,
CBC, chave de 256 bits e opções de troca de bytes. Isso sustenta a
**inferência AES-256-CBC**, sem provar binding HZC2 ou fornecer os 48 bytes
que o hardware produz antes.

### Wrapper e resultado comparado

`0x4248` cria contexto local; o inicializador `0x422c` zera **somente** os
contadores `+0x40/+0x44`. Seus primeiros 32 bytes não são inicializados
pelo helper. Neste chamador, contadores zero evitam lê-los como estado
HASH herdado. O argumento original de saída passa em X2 ao consumidor,
selecionando o ramo final.

Nesse ramo, `0xb6e0` vai a MMIO `+0x1020`, contexto `+0x44` a `+0x1030`
e contexto `+0x40` a `+0x1034`. A continuação com fonte ACE identifica a
ordem baixa/alta nessa referência; a descrição anterior os nomeava ao
contrário, sem alterar as instruções ou a execução. Com ambos zero, o controle HASH preparado é `0x14`, sem
restaurar os oito words de estado do contexto.

Depois dos polls, **oito** leituras `+0x11c0…+0x11dc` vão ao buffer do
chamador, frame principal `+0x38`: **32 bytes**, distintos dos 48 anteriores.
O código reconstrói oito u32 little-endian do registro apontado por
`0xfe30`: candidato EBHS em `0x46bc`, conteúdo comparado `[0x46c0,0x46e0)`.
Divergência prepara **`0x1109`**.

Tamanho 32 e controle `0x14` são compatíveis com a referência SHA-256, mas
os offsets HASH antigos não coincidem integralmente com este prefixo: o
algoritmo HZC2 permanece hipótese. Tampouco se atribui SHA-384 à primeira
etapa apenas porque ela lê 48 bytes.

No epílogo comum, o scratch local do material de 32 bytes e IV de 16 bytes
é zerado. Não há limpeza explícita dos registradores de material da segunda
etapa nesse recorte; isso não garante eliminação de cópias/cache/estado interno.

## Falhas, polling e progresso

O JSON vincula **21 testemunhos de produção de status** às instruções.
São resultados internos do consumidor/wrapper/preparação, sem equivalência
presumida aos retornos SMC ou ao enum DRM.

| Status | Condição no recorte |
|---|---|
| `0x1001 / 0x1002` | request nulo; ponteiro/tamanho ausente |
| `0x1003 / 0x1008 / 0x1009` | campo extra não zero; direção >1; capacidade insuficiente |
| `0x1004 / 0x100a / 0x100b / 0xfdaa0500` | testes separados dos bits MMIO no relatório |
| `0x1005 / 0x1006` | modo >3; tamanho fora de 16/24/32 |
| `0x1007` | bit de conclusão DMA ausente na releitura final |
| `0x1106 / 0x1107` | polls da primeira etapa esgotados |
| `0x110c / 0x110d / 0x110e` | polls final/parciais esgotados |
| `0x1110 / 0x1111 / 0x1112` | saída nula; contexto nulo; máscara `0x50` no ramo guardado |
| `0x1109` | comparação final de 32 bytes divergente |

Cinco loops conferidos usam contador zero, incremento W e
`CMP #0x100000 / B.LS`: se todas as leituras falharem, são **0x100001**
leituras antes da saída por limite. O loop DMA usa **0x10000000**, depois
faz **uma releitura adicional**, que ainda pode observar sucesso.
São limites de iteração condicionais, não tempos em milissegundos nem
prova de progresso de MMIO ou ausência de traps.

## Fontes correspondentes: alcance da busca

- [s5p-sss.c, Exynos-2100, commit 37c14d8](https://github.com/Exynos-2100/android_kernel_samsung_universal2100/blob/37c14d86996a49edbea8953f2523b202546b8958/drivers/crypto/s5p-sss.c): blob e SHA-256 recalculados. A listagem `drivers/crypto` desse commit foi consultada; não é busca universal por código ausente. AES corrobora a inferência; diferenças DMA/HASH impedem importar o protocolo inteiro.
- [decrypt-epbl.py original, commit 404785e](https://github.com/halal-beef/Exynos9830-Firmware-Decryptor/blob/404785e78056a3b69bac1f96a9c7ca96427d1099/decrypt-epbl.py): implementação primária Exynos9830, com endereço/slots diferentes. Fonte lida, não executada como programa. Um único ensaio AES-256-CBC com sua chave/IV públicos sobre o candidato HZC2 não coincidiu com EBHS sob hipótese SHA-256. Não validou plaintext e não exclui outros algoritmos/chaves. Nenhum binário foi alterado ou publicado.

As fontes e esse resultado estritamente negativo estão em
[epbl-protocol-sources.json](references/epbl-protocol-sources.json). Não foi
encontrada aqui implementação que estabeleça a preparação completa HZC2.

## Reprodução e validação

```sh
python3 scripts/inspect_epbl_protocol.py /caminho/sboot.bin
python3 scripts/check_epbl_protocol_gnu.py /caminho/sboot.bin
(cd scripts && python3 -m unittest test_epbl_protocol test_epbl_frontier test_epbl_preparation -v)
```

O inspetor exige tamanho/SHA-256 exatos. Usa stdlib, recortes limitados e
templates. O inventário é **lexical**: não prova que os 177 acessos ocorram
numa mesma execução. Dados não resolvidos continuam desconhecidos; branches
cortam o rastreio de literais. Um salto que possa pular o construtor de
endereço impede sua reutilização.

**Na entrega inicial: 33 testes novos + 36 regressões = 69 PASS.** Cobrem limites, larguras X/W,
endereço alto/baixo, desconhecidos, saltos no meio de builders, polling
inclusivo, seletores e recusa de firmware errado.

GNU objdump 2.44 coincide nas **1095 palavras**, nos **114 destinos relativos**
e nos **177 endereços/larguras/operações MMIO**: 38 leituras e 139 escritas.
O conferidor MMIO independente interpreta texto GNU de MOV/MOVK/load/store,
sem reutilizar o decodificador binário de endereços. Não executa o fluxo de
buffers, nem valida respostas ou memória no aparelho.

A [continuação de proveniência HASH](epbl-hash-provenance-hzc2.md) acrescenta
dois testes de ligação dos contadores e 12 de fontes: 83 no conjunto atual.
Os 69 anteriores continuam preservados como evidência histórica; o relatório
de protocolo foi reemitido com os dois vínculos de contador explícitos.

- [Relatório de protocolo](references/epbl-protocol-hzc2.json)
- [Conferência GNU](references/epbl-protocol-validation.json) e [linhas do recorte](references/epbl-protocol-gnu.txt)
- [Saída dos testes](references/epbl-protocol-host-tests.txt)

**Próxima evidência útil:** confirmar binding e bytes da entrada candidata
`[0x1fc00,0x1fffc)`, a semântica de `0x19` ou a saída real de 48 bytes, por
implementação correspondente ou observação verificável. Depois, validar
transformação e ligar vetores/tabelas ao dispatcher. Material inventado ou
chave importada de outro SoC não substitui essa evidência. Carregamento,
coerência e leitura do diagnóstico seguem no [roadmap físico](roadmap.md).
R10/shim/firmware não foram alterados; nenhum novo ensaio QEMU/S21 foi feito.
