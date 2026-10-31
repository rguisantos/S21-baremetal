# LK HZC2: descritores, espera e resposta UFS

A [ligação RPMB→SCSI→UFS](lk-rpmb-transport-hzc2.md) agora tem a sequência
local de preparação, polling e resposta delimitada. A espera aceita uma
combinação de registradores; a resposta publica o byte SCSI antes de
testar OCS. Esses resultados são separados das verificações RPMB de
resultado, nonce e MAC, e não comprovam persistência física.

Base main `f1e6f7199a00c076cd067beb32ba0c908492aa67`, após PR #66.
`sboot.bin` HZC2:4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo. Endereços relativos usam o delta nominal
VA−arquivo `0xe7f14000`. Nenhum firmware, MMIO, DMA, SMC ou pedido ao
telefone foi executado nesta etapa.

## Pedido, LUN e descritores

`0x10c7f8` associa o pedido a host+96 e pedido+32 a host+128. Para os
opcodes selecionados `0xa2`/`0xb5`, lê o pai em pedido+104 e seu campo LU
em+280. LU68 (`0x44`) é traduzido para `0xc4`, guardado em host+120.
Isso fecha a conversão antes pendente no caminho RPMB; não generaliza
o mapeamento para todos os comandos/objetos ou para o estado vivo.

`0x10cab8` recebe host, encontra o pedido em host+96 e o descritor de
comando em host+144. Para payload não zero:

| Local | Preparação observada para IN/OUT |
|---|---|
| Descritor de comando+0 | Tipo1 |
| +1 | Flags `0x40` IN / `0x20` OUT |
| +2 | LUN `0xc4` no caminho selecionado |
| +12..15 | Comprimento do payload em big-endian |
| +16..31 | Cópia dos16 bytes do CDB |
| +2048 em diante | Entradas PRD com stride16 |
| Descritor de transferência+0..3 | Bytes `00 00 00 05` IN / `00 00 00 03` OUT |
| +8..11 | Palavra inicial OCS15, little-endian |
| +28..29 | Campo bruto `((n &0xfff)<<4)` little-endian |
| +30..31 | Bytes `00 08` |

A nomenclatura de descritores/registradores é cruzada com o
[ufshci.h fixado](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/ufs/ufshci.h).
O relatório conserva offsets/bytes; não presume que todo campo tenha a
mesma unidade ou configuração de uma implementação genérica Linux.
Hashes dos dois headers consultados estão na
[referência de fontes](references/lk-ufs-completion-source-reference.json).

O número de entradas escritas é `n=u32(comprimento+4095)>>12`. Cada
entrada recebe endereço avançado em4096 e tamanho codificado4095, mesmo
para um frame de512 bytes. Não há redução da última entrada ao resto
do payload nesse trecho. O descritor também carrega o comprimento
esperado; não se conclui daí quantos bytes o hardware transferiria ou
que houve overrun físico.

A aritmética W32 importa: de `0xfffff001` a `0xffffffff`, a soma arredondada
pode envolver e produzir n0. O campo codificado conserva apenas12 bits
de n, enquanto o laço usa o n inteiro calculado. Não se demonstraram
guards completos de capacidade/intervalos. Para o caso selecionado512:
n1, campo16, uma entrada de segmento4096. Os modelos não alocam payloads
ou descritores e não executam instruções Samsung.

## Espera: o que o zero local significa

O executor `0x10e568` publica o pedido e chama `0x10cfb0` com modo1.
Esse wrapper escolhe o orçamento e chama repetidamente `0x10cda0` com
**modo interno0**, enquanto o retorno for3. Para esse modo, a rotina
usa MMIO pela base em host+24:

| Condição na amostra selecionada | Retorno do polling |
|---|---:|
| IS em+0x20 contém algum bit de `0x30880` | 2 |
| Sem esses bits, IS bit0 ligado e doorbell em+0x58 bit0 limpo | 0 |
| Ainda pendente e orçamento anterior não zero | 3 |
| Ainda pendente e orçamento anterior zero | 1 |

A máscara inclui `0x80/0x800/0x10000/0x20000`; os nomes no header de
referência são link lost/device fatal/controller fatal/system bus fatal.
Ela não equivale a todos os bits de erro conhecidos do header: UIC `0x4`
e crypto fatal `0x40000`, por exemplo, não pertencem à máscara desse
teste. Não se amplia o teste do firmware para cobrir esses bits.

No ramo pendente, o contador em host+204 é decrementado **antes** de
testar seu valor anterior. Zero é armazenado como `0xffffffff` e então
seleciona timeout1. Com valor anterior não zero, solicita helper de delay
com argumento1 e retorna3. O zero de conclusão ou erro2 não consome o
contador nesse ramo. Não se assume estabilidade entre amostras MMIO.

| Modo externo de `0x10cfb0` | Orçamento inicial extraído |
|---|---:|
| 1, opcode diferente de4 (inclui A2/B5) | 10.000.000 |
| 1, opcode4 | 600.000.000 |
| 0 | 30.000 |
| 22 | 1.500.000 |

São contadores de tentativas, sem conversão estabelecida para segundos.
O helper de delay e seu retorno/preservação permanecem opacos; retries
do executor também não foram convertidos em prazo físico. Há outros
ramos de polling para comandos UIC, incluídos na cobertura GNU, mas os
modelos de amostra desta entrega exercitam somente o modo interno0.

## OCS, byte SCSI e retorno do executor

`0x10c888` encontra o pedido em host+96 e descritores por host+144/+152.
Se o pedido é não nulo, copia byte do descritor de comando+`0x407` para
pedido+96 **antes** de testar a palavra OCS. O endereço nominal do
consumidor SCSI, relativo `0x8a73e0`, corresponde ao workspace RPMB+96;
os registradores, offsets e stores foram conferidos mecanicamente.

A palavra de quatro bytes em descritor de transferência+8 é reconstruída
como little-endian. O firmware compara a palavra inteira, sem aplicar
a máscara low4 do header Linux:

- OCS32 zero retorna0 nesse helper sem testar ali o tipo de transação ou
  exigir byte SCSI zero. O classificador SCSI posterior continua separado.
- OCS32 não zero entra em diagnósticos e seleciona retorno local−1 sob
  a hipótese de chamadas diagnósticas retornarem normalmente. O byte
  SCSI já foi publicado, mesmo com esse erro.

No ramo de erro com tipo de resposta `0x21`, copia18 bytes de resposta+34
para pedido+32 antes da checagem posterior do ponteiro. Esse ramo não
certifica segurança de memória para pedido nulo; o caminho RPMB
selecionado fornece pedido não nulo. Outros diagnósticos e seus efeitos
transitivos permanecem fronteiras.

O executor chama o parser depois que a espera retorna0. Se o parser
retorna0, seleciona saída local0; se falha, há tratamento de sense/retry
e retorno separado. Acima dele, ainda existem o classificador SCSI, o
resultado do pacote RPMB e as verificações de nonce/MAC. Não se promove
o zero de uma camada a sucesso das seguintes.

A origem nominal do byte está ligada; sua frescura física ainda exige
descritores válidos, posse do workspace, coerência, DMA e resposta do
dispositivo. O executor solicita zerar4096 bytes do descritor de comando
a cada tentativa, incluindo a posição desse byte; o zero inicial não
comprova uma escrita nova do dispositivo. Não houve aquisição dessas condições. O foco seguinte é
origem/configuração ativa do host e dos buffers, além dos gates RPMB e
da [implementação segura](lk-rpmb-hzc2.md).

## Verificação e reprodução

`inspect_lk_ufs_completion.py` exige tamanho/SHA antes de GNU. Confere635
palavras,121 destinos relativos,135 operandos,8 literais e8 grafos,
além do binding do produtor/consumidor de status. Modelos sintéticos
resumem uma amostra de polling, a aritmética de comprimentos e a
publicação de status; não substituem execução do firmware ou captura.
Grafos mantêm continuações condicionais de chamadas opacas e não
avaliam viabilidade ou preservação runtime.

```sh
python3 scripts/test_lk_ufs_completion.py -v
python3 scripts/inspect_lk_ufs_completion.py /private/path/sboot.bin > /tmp/lk-ufs-completion.json
cmp /tmp/lk-ufs-completion.json docs/references/lk-ufs-completion-hzc2.json
python3 scripts/test_lk_rpmb_transport.py
python3 scripts/test_lk_rpmb.py
python3 scripts/test_rpmb_frame.py
python3 scripts/validate_baseline.py --output-dir build/baseline-ufs-completion
```

São21 testes novos, incluindo bits de máscara, prioridade de erros,
wrap do orçamento/arredondamento, status publicado com OCS não zero,
larguras de acesso e mutações de bindings. Evidências:
[relatório](references/lk-ufs-completion-hzc2.json) e
[validação](references/lk-ufs-completion-validation-20261030.json).

Continuação: [origem do host e buffers](lk-ufs-host-memory-hzc2.md) liga alocações, tabelas e stores de bases. A [referência Exynos ampliada](flop-ufs-dma-reference.md) sustenta a interpretação PRDT em bytes, mantendo tamanho de entrada e configuração separados do estado físico.
