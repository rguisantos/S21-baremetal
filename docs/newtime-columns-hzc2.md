# HZC2: colunas 1 e 12, consumidores e parada antes do gate

Executado em **2026-10-24 (Campo Grande)** sobre main após o PR #24,
`0191d5607077678e01c411b271c1c35cc0849f5c`. Sboot exato: 4194304 bytes,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
O plano recebido foi confrontado com o código e executado até seu primeiro
limite de memória. Não houve acesso ao telefone, MMIO, resposta SMC, valor
artificial de gate ou mudança de PC para contornar o gate.

**As colunas são chaves de subtabelas.** O ensaio contínuo copia os valores,
mas para antes de consumi-los depois da cópia, na carga de AP0x158609bc.
A análise estática identifica esses consumidores e parte dos leitores
posteriores. O significado físico de timing continua aberto.

## Diferenças e formatos

A tabela tem 22 linhas de 17 u64 em 0x706c8, passo 0x88. A numeração de
colunas inclui a chave em zero. Só diferem as colunas abaixo:

| Coluna | Linha 10 | Linha 15 | Papel no código |
|---|---|---|---|
| 0 | 0001000860000110 | 0001000850500130 | Seletor da linha |
| 1 | 0x12b | 0x11b | Chave da primeira subtabela, índice de laço 0 |
| 12 | 0x71 | 0x73 | Chave da décima segunda subtabela, índice de laço 11 |

A palavra impressa no log corresponde à chave da linha 15. O log não
mostra o callback selecionar ou publicar essa linha no aparelho.

Há três formatos distintos: **entradas dos metadados parseados de 32 bytes**,
**scratch de 144 bytes** para copiar os 16 u64 posteriores à chave e
**descritores de saída de 16 bytes**. O callback não copia a linha inteira
para um único descritor de 32 bytes. Layout e fluxo já delimitados em
[registro NEWTIME](newtime-record-hzc2.md).

## Quem lê as chaves depois da cópia

| PC de arquivo | Ação estática |
|---|---|
| 0x19774 | Lê AP0x158609bc, antes de cada iteração |
| 0x197a4 / 0x197d4 / 0x19804 | Lê/modifica a chave no scratch quando o gate seleciona transformação nos índices 0 a 8 |
| 0x19820 | Lê `scratch[index]` como chave u64 |
| 0x1982c → 0x1c83c | Procura a subtabela pela chave |
| 0x1988c / 0x19890 | Relê a chave e grava seus 32 bits baixos no descritor de saída |
| 0x19964 / 0x19968 | Copia cada célula u32 da subtabela para seu payload |

Para a coluna 1, o gate pode trocar 0x12b/0x11b por 0x128/0x118,
respectivamente. A transformação é menos 3, pois o nibble baixo é 0xb.
A coluna 12 tem índice 11, fora do intervalo transformado: permanece
0x71/0x73. Isso depende de ramos reais ainda não observados.

| Chave | Dados no sboot | Forma | Bytes |
|---|---|---|---|
| 0x12b | 0x713ec | 15 × 1 u32 | 60 |
| 0x11b | 0x7135c | 15 × 1 u32 | 60 |
| 0x128 | 0x713a4 | 15 × 1 u32 | 60 |
| 0x118 | 0x71314 | 15 × 1 u32 | 60 |
| 0x71 | 0x77390 | 44 × 1 u32 | 176 |
| 0x73 | 0x7745c | 41 × 1 u32 | 164 |

Modelos com a mesma sequência de ramos mostram uma diferença de 12 bytes
no tamanho final: máscara zero, 0x22dc contra 0x22d0; máscara 0x1ff,
0x1e4c contra 0x1e40. São planos condicionais, não execuções deste novo
ensaio. Mudanças de tamanho deslocam também os payloads posteriores.
[Dados, hashes e planos](references/newtime-columns-hzc2.json).

## Leitores posteriores: primeira coluna parcialmente seguida

Se a construção completar e R corresponder ao registro fixo AP0x02073600:

- A coluna 1 ocupa o descritor em R+0x1a0. Em **0x2d5f8**, o código lê
  seu offset em AP0x020737a4, soma a base fixa e grava o ponteiro no global
  relativo **0x31758** em **0x2d774**.
- **0x2e4b4** carrega esse ponteiro em 0x2e4b8 e lê o segundo u32 do
  payload em **0x2e4bc**. Se bit 0 estiver ativo, procura o primeiro bit
  ativo entre 4 e 30, inclusive, e calcula índice+8. Sem habilitação ou
  sem bit nesse intervalo, calcula zero. **0x2e4f4** escreve o resultado
  no endereço fixo **AP0x0207365c**.
- Os payloads 0x12b/0x128 têm segundo u32 zero: resultado calculado **0**.
  Os payloads 0x11b/0x118 têm 0x00100001: resultado calculado **28**.
  Essa diferença tem consumidor concreto; ainda não nomeia um timing do
  controlador nem demonstra uma escrita nele.
- A coluna 12 ocupa R+0x250, nominalmente AP0x02073850. **0x2d5e8** lê
  a contagem de linhas e 0x2d5ec a armazena como byte no global relativo
  **0x31698**. **0x2d708** lê o offset do payload; **0x2d71c** grava seu
  ponteiro no global relativo **0x316a0**. O próximo leitor desse payload
  permanece por seguir.

O helper 0x2d568 tem testes e acessos anteriores, inclusive ao gate MMIO.
Esses leitores posteriores foram analisados estaticamente, **não executados**
neste trabalho, respeitando o limite de executar só o callback e sua cadeia.
Não foi comprovado o alias fixo no aparelho, a preservação posterior ou
que esses caminhos tenham sido alcançados. [GNU](references/newtime-columns-gnu-hzc2.json)
conferiu 188 novas palavras, 11 alvos e dez operandos, além da cobertura
anterior do callback.

## Execução contínua e rastreio de memória

O QEMU **10.0.13** do repositório funciona aqui pelo loader/bibliotecas
extraídos selecionados pelo [r8/Makefile](../r8/Makefile). `--version` e
o ensaio passaram; `-help` anuncia `-plugin`. Isso remove o bloqueio de
QEMU neste ambiente. Não foi diagnosticada a causa do aborto no outro
ambiente, nem executado um plugin nesta verificação.

O novo runner usa GDB para executar uma instrução por vez e conferir o
endereço e a largura de **cada load/store inteiro antes de executá-lo**.
Essa escolha fornece endereços e valores; `-d exec` isoladamente mostra
execução de blocos, sem fornecer toda essa informação de memória.
GNU fornece a instrução, com 466 palavras da cadeia conferidas contra os
bytes fixados. Formas de
memória não suportadas são recusadas. Código, ECT e metadados são protegidos
contra escritas pelo preflight; estado, pilha e destino são RAM laboratorial.

O limite declarado antes da execução é **20000 instruções por caso**.
PC fora da cadeia permitida, instrução de sistema, epílogo compartilhado,
acesso fora das regiões RAM permitidas ou esgotamento do limite interrompem
o rastreio. O label ERROR antigo aponta para o epílogo também usado pelo
retorno zero; o nome desse label sozinho não estabelece erro.

| Entrada | Colocações | Instruções por caso | Acessos de memória por caso | Parada |
|---|---|---:|---:|---|
| Linha 10 | 0x40000000 / 0x40200000 | 1355 | 580 | Antes do LDR em 0x19774 |
| Linha 15 | 0x40000000 / 0x40200000 | 1495 | 645 | Antes do LDR em 0x19774 |

Todos chegam com X0=0x158609bc; a carga não executa. A cópia da cauda,
primeiro u64 do destino, ponteiro do diretório, cursor, código, ECT,
metadados e guardas conferem. Por coluna, observam-se duas cargas u32 do
ECT em 0x1c54c/0x1c550 e um store u64 para scratch em 0x19600.
**Não há leitura posterior da cauda nem acesso ao diretório de saída
antes dessa parada.** Não houve retorno completo do callback.

[Resultado QEMU](references/newtime-columns-qemu-hzc2.json): PC, passo
baseado em zero, endereço, largura, bytes do valor em little endian e
coluna para os acessos observados; acessos do cabeçalho/diretório e hash
de cada trilha. O SHA cobre primeiro os pares PC normalizado/opcode LE
de todas as instruções executadas e depois o JSON canônico de todos os
eventos de memória (`sort_keys=True`, separadores compactos). A trilha
selecionada no JSON é menor que o conjunto coberto pelo hash, que o runner
reproduz. Metadados parseados e todos os bindings são fornecidos pelo host.

## Dados de kernel e aparelho: fronteiras preservadas

O pacote de kernel/driver de 2701 linhas e hash truncado f69a4077…662719,
o módulo carregado, frequências, propriedade DDR e novas restrições de
acesso são informações do plano recebido. Não foram reexecutadas aqui.
Essa fonte não foi confundida com o driver público fixado de 2702 linhas,
SHA-256 1133eb69…b2f7f6; defconfig e READMEs genéricos não provam a build
do binário stock.

Há uma ressalva à conclusão sobre OPPs: na mesma referência pública,
[devfreq.c, linha 1379](https://github.com/xfwdrev/android_kernel_samsung_ex2100/blob/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0/drivers/devfreq/devfreq.c#L1379),
`available_frequencies_show` percorre **profile->freq_table**. Esse caminho
não consulta se cada OPP está habilitada. Portanto ver as frequências nessa
lista, isoladamente, não prova que o ramo de disable não executou.
[Fonte e hash da conferência](references/devfreq-available-frequencies-reference.json).
Isso também não prova a implementação do atributo no stock.

Início tardio do dmesg torna a perda de mensagens iniciais uma hipótese
plausível, sem estabelecer sozinho o que o stock imprimiu. Loglevel de
console e conteúdo coletado do ring são questões distintas. Ausência de
DEVFREQ e leituras físicas continuam abertas. Não foram exportados novos
dados brutos ou identificadores pessoais.

## Reprodução e próxima fronteira

```bash
python3 scripts/inspect_newtime_columns_hzc2.py /caminho/sboot.bin
python3 scripts/inspect_newtime_columns_hzc2.py /caminho/sboot.bin --gnu
python3 scripts/trace_newtime_columns_qemu.py /caminho/sboot.bin
python3 scripts/trace_newtime_columns_qemu.py /caminho/sboot.bin --max-steps 1
python3 -m unittest discover -s scripts -p 'test_newtime_columns.py' -v
```

[Validação](references/newtime-columns-validation-hzc2.json).
Passaram 141 testes de host (13 novos), 12 recusas CLI com exit 2 e stdout
vazio, quatro controles com orçamento de uma instrução, quatro relatórios
reproduzidos byte a byte (incluindo QEMU e o GNU623 anterior), compilação
Python, 709 links locais e conferência de diff.
Próximo: seguir o leitor do payload apontado por 0x316a0 e a utilização
posterior de AP0x0207365c. Para o callback contínuo ultrapassar o gate,
é necessária evidência apropriada de seu estado ou outro ensaio com
hipóteses explicitamente diferentes; a execução atual preserva o requisito
de não fornecer respostas MMIO. Nem esta etapa nem os modelos condicionais
demonstram parâmetros físicos, boot Samsung ou o mapa final de RAM/FDT.


## Continuação estática de 2026-10-25

O [novo rastreio dos consumidores](newtime-consumers-hzc2.md) resolveu o
leitor de 0x316a0 em 0x2cdb8 e seguiu os argumentos até escritas nominais
em registradores. Também corrigiu a direção entre os registros de 108/162
bytes e delimitou o diretório de vddcal. Os resultados QEMU e as lacunas
físicas deste documento permanecem com o escopo original.
