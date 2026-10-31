# LK HZC2: registro scsirpmb e callbacks SCSI/UFS

A ligação antes pendente no [backend RPMB](lk-rpmb-hzc2.md) está resolvida
**nominalmente no caminho de inicialização selecionado**: o construtor
forma `scsirpmb`, inicializa/registra o objeto e instala os callbacks que
montam SCSI Security Protocol IN/OUT. O despacho seguinte entra no
transporte UFS. Isso não mede a instalação ativa, a resposta do dispositivo
ou a persistência de um contador.

Base main `8fe014ead19d431912a9feb349723939c9415072`, após PR #65.
`sboot.bin` HZC2:4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo. Endereços relativos seguem o delta nominal
VA−arquivo `0xe7f14000`, sem identificar memória física livre. Etapa
inteiramente estática: nenhuma instrução Samsung, SMC ou I/O executado.

## Nome, objeto e publicação

O trecho chamador `0x10eae8..0x10eb0c` passa a `0x10c3c8`:

| Argumento | Valor no trecho selecionado |
|---|---|
| X0 | Objeto no endereço relativo `0x8a7400` |
| W1 | 68 (`0x44`) |
| W2 | 0 |
| X3 | Callback `0x10e758`, preparado em X20 antes das chamadas |
| X4 | String `rpmb`, em `0x226b90` |
| W5 | 128 |
| X6 | Contexto/lista preparado pelo chamador |

O construtor calcula o limite69 para a iteração iniciada em68 e usa
`scsi%s` (`0x226b20`) com `rpmb`, produzindo `scsirpmb` no buffer de16
bytes. O ramo com início0 usa outro formato, `scsi%u`; não se confunde
com o nome de RPMB. Chamadas anteriores/preparação de contexto continuam
condicionadas a retorno normal e preservação de registradores.

`0x10c300` solicita identificação/configuração por `0x10c188` e `0x10c210`.
Erro −2 pula o objeto; outro resultado negativo sai do construtor. No
ramo não negativo selecionado, comparação exata do sufixo com `rpmb`
seleciona unidade512, em vez da unidade4096 dos demais sufixos. O
inicializador `0x18f380` recebe também W3=`0xffffffff` e flags0.

| Offset do objeto | Campo/valor preparado no caminho selecionado |
|---|---|
| +24 | Nome duplicado pelo helper `0x1b2588` |
| +40 u64 | Unidade512 bytes |
| +56 u32 | `0xffffffff`, valor preparado; sem medição de capacidade |
| +60 u32 | Limite128 em unidades de512 bytes |
| +64 | Ponteiro para o próprio objeto |
| +96 u32 | Flags0 |
| +144/+152 | Wrappers genéricos de leitura/escrita |
| +192/+200 | Callbacks SCSI IN/OUT |
| +368 | Callback de transporte `0x10e758` |

Após instalar os métodos, `0x18f4a8` incrementa a referência e encadeia o
objeto na lista relativa `0x31ff78`. `0x18eb08`, já chamado pelo dispatcher
RPMB com `scsirpmb`, percorre essa mesma raiz, compara nomes integralmente
e incrementa a referência do objeto encontrado; ausência retorna NULL.
O extrator confere a igualdade das raízes e os slots instalados/consumidos.
Não foram provados alocação do nome, exclusividade, preservação ou presença
desse objeto em uma execução real.

## Cadeia de métodos

| Operação | Slot do objeto → wrapper | Slot seguinte → SCSI |
|---|---|---|
| Leitura | +144 → `0x18e8a8` | +192 → `0x10c018` |
| Escrita | +152 → `0x18e650` | +200 → `0x10c0d0` |

Os wrappers têm caminhos de alinhamento, blocos parciais e divisão em
lotes. Sob unidade512, flags0 e um frame, o caminho selecionado chega ao
callback correspondente com quantidade1. O limite128 permite esse pedido
sem divisão adicional. Status não zero do callback vira −1 no wrapper;
o dispatcher RPMB acima tem seu [tratamento separado](lk-rpmb-hzc2.md)
e não testa todos os retornos desses I/Os.

Isso é uma redução condicional do caminho de um frame, sem certificar
aritmética, limites de buffer ou geometria para todas as entradas. Os
corpos completos dos dois wrappers estão na cobertura GNU.

## CDB e workspace compartilhado

As rotinas `0x10c018`/`0x10c0d0` preparam o mesmo workspace relativo
`0x8a7380`. Zeram os16 bytes iniciais do CDB, colocam ponteiro de dados
em+24, comprimento u32 em+16 e ponteiro do objeto pai em+104. O pai vem
de objeto+64; no caminho selecionado é o próprio objeto.

| Campo do CDB | Valor preparado |
|---|---|
| byte0 | `0xa2` leitura / `0xb5` escrita |
| byte1 | `0xec` |
| bytes2..3 | `0x0001` |
| bytes6..9 | `u32(quantidade <<9)`, em big-endian |
| byte9 | Explicitamente0, compatível com comprimento múltiplo de512 |

Os opcodes/protocolo são extraídos dos MOVN/MOVZ e truncados somente
pelos stores de byte. O comprimento de payload em+16 é calculado como
u32(quantidade×unidade do objeto), enquanto o CDB usa shift9. As fórmulas
coincidem sob a unidade512 selecionada; não se presume essa igualdade
para objetos arbitrários. O argumento original W2 de índice não é
codificado no CDB dessas rotinas: os campos RPMB pertinentes estão no
frame, conforme a [análise de pacotes](lk-rpmb-hzc2.md).

O callback é carregado de pai+368 e invocado com o workspace. Retorno
não zero é devolvido diretamente. Retorno zero leva a `0x10bea8`, que lê
workspace+96 como byte e chama `0x10b9c0`. A tabela de65 bytes signed×4
em `0x226954` resolve os diagnósticos SCSI: low8 zero retorna0; qualquer
outro low8 retorna low32 `0xffffffd5` (−43), inclusive índices>64.
A origem/frescura desse byte de resposta ainda depende das rotinas UFS
posteriores; o memset inicial de16 bytes não o inicializa.

O formato é coerente com o transporte no [FlopKernel](flop-kernel-reference.md),
mas isso não demonstra fonte idêntica nem igualdade de serviços seguros.
O valor68 do seletor LK não é uma identificação já provada do encoding
WLUN `0xc4` usado pela referência Linux.

## Entrada no transporte UFS e limite desta etapa

`0x10e758` recebe o workspace; NULL retorna−7. Para pedido não nulo,
lê índice signed da célula relativa `0x8a7710`, seleciona ponteiro na
tabela relativa `0x8a7718` e passa host/pedido a `0x10e568`. Host nulo
imprime diagnóstico e é recarregado/reutilizado, sem guard local de
retorno; não se classifica esse ramo como falha segura garantida.

O corpo local `0x10e568..0x10e758` chama preparação de descritor
`0x10c7f8`, montagem `0x10cab8`, publica registradores MMIO, chama espera
`0x10cfb0` e processamento de resposta `0x10c888`. Há retries condicionais
e tratamento de sense, mas esses callees e a configuração ativa do host
não foram fechados. Não se demonstra ACK, DMA concluído, origem do byte
de status ou leitura/escrita física. O compartilhamento do workspace
também exige posse e preservação ainda não medidas.

Próximo: descritores e resposta/completion UFS, origem do host/índice e
dos gates RPMB. O [serviço seguro MAC/nonce](lk-rpmb-hzc2.md) permanece
outra fronteira; o contrato de carga/memória/captura do diagnóstico físico
continua pendente.

## Verificação e reprodução

`inspect_lk_rpmb_transport.py` recusa tamanho/SHA divergentes antes de
invocar GNU. Confere992 palavras,133 destinos relativos,194 operandos,
13 literais e16 grafos. O relatório compacto conserva índice por hash,
testemunhos, bindings e65 destinos do classificador SCSI. Grafos mantêm
continuações condicionais normais dos callees e não avaliam valores ou
viabilidade dos caminhos; BRs indiretos permanecem fronteiras locais.

```sh
python3 scripts/test_lk_rpmb_transport.py -v
python3 scripts/inspect_lk_rpmb_transport.py /private/path/sboot.bin > /tmp/lk-rpmb-transport.json
cmp /tmp/lk-rpmb-transport.json docs/references/lk-rpmb-transport-hzc2.json
python3 scripts/test_lk_rpmb.py
python3 scripts/test_rpmb_frame.py
python3 scripts/test_flop_reference.py
python3 scripts/validate_baseline.py --output-dir build/baseline-rpmb-transport
```

Os16 testes novos alteram registros, offsets, raízes e larguras para
conferir recusas e exercitam constantes MOVN/STRB. Não executam firmware.
[Relatório](references/lk-rpmb-transport-hzc2.json) e
[validação](references/lk-rpmb-transport-validation-20261030.json).

Continuação: a [conclusão UFS](lk-ufs-completion-hzc2.md) fecha o caminho local de descritores/espera/resposta e a conversão LUN68→0xc4. O byte SCSI é publicado antes da checagem OCS; origem nominal não estabelece frescura física.
