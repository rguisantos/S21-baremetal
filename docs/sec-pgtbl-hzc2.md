# SEC_PGTBL: respostas e checagem de tamanho no LK

Análise de 2026-10-21 em Campo Grande, correspondente a 2026-10-22 UTC.
Usa apenas o BL HZC2 recebido; não repete a coleta Harx bloqueada e não
executa serviços no telefone. Os offsets abaixo são de arquivo.

O tratamento de **0x82002060** no LK foi isolado, modelado e conferido pela
execução das instruções originais em Unicorn, com respostas fornecidas
explicitamente. Há um achado local: a instrução associada à
checagem de alinhamento do tamanho usa **a base em X21**, já normalizada,
em vez do tamanho retornado. Assim, esse caminho não verifica o alinhamento
do tamanho. Isso não demonstra que o serviço retorne um valor inválido no
aparelho; seu conteúdo efetivo continua desconhecido.

## Identidade e limite do LDFW

O membro exato `ldfw.img.lz4` foi lido do pacote BL e descomprimido com consumo
completo do frame, sem extrair caminhos arbitrários. A identidade bruta bate
com o inventário anterior:

| Campo | Valor |
|---|---|
| Tamanho raw | 8.388.608 bytes |
| SHA-256 | 9d52a013bffde6f3d734e02a359ce9323a7db75878fce60569f5989b63e057fd |
| Marcador em 0x30 | CryptoManagerV50 |
| Nome em 0x3fc09c | ldfw.img |

O hash confirma a identidade dos bytes; não demonstra assinatura válida,
código em claro ou um endereço de execução. A inspeção ampliada encontrou
um contêiner proprietário de registros concatenados, sem ELF embutido.

### Registros e cabeçalho

Cada registro começa com `0x10adab1e`. O campo u32 em +0x4 dá o tamanho do
registro inteiro, incluindo padding. O percurso pelos tamanhos, sem procurar
magics no corpo, produz os seis registros abaixo. Fins são exclusivos.

| Registro | Início | Fim | start_smc_id | Palavra em +0x28 |
|---|---|---|---|---:|
| CryptoManagerV50 | 0x0 | 0x211000 | 0x82001000 | 1 |
| fmp_fw_V20 | 0x211000 | 0x228000 | 0x82001800 | 1 |
| drm_fw | 0x228000 | 0x389000 | 0x82002000 | 1 |
| srpmb_fw | 0x389000 | 0x3da000 | 0x82003800 | 1 |
| hdcp_fw | 0x3da000 | 0x3fb000 | 0x82004000 | 1 |
| tail_fw | 0x3fb000 | 0x3fc000 | 0x82001800 | 0 |

O [U-Boot, arquivo fixado por commit](https://github.com/u-boot/u-boot/blob/3d9115a045d2d48c28019b3d6673ab30271819f5/board/samsung/e850-96/fw.c),
define esse cabeçalho comum: entradas em +0x8/+0xc/+0x10/+0x14/+0x20,
start_smc_id em +0x18, versão em +0x1c e nome de 16 bytes em +0x30.
É referência de outra placa, não o carregador usado pelo HZC2. Os campos
magic/tamanho/versão/nome são corroborados diretamente pelo LK recebido.
Os demais valores de entrada ficam registrados como metadados, sem declarar
uma base física ou virtual validada para este firmware.

O LK em **0xf65f8** percorre o contêiner: 0xf6680 lê +0x4, 0xf6684 avança
o ponteiro, 0xf6688 soma o tamanho e 0xf668c–0xf6694 verifica a próxima magic.
Em 0xf66a8/0xf66ac/0xf66b0 passa o prefixo de **0x3fc000** bytes, no buffer
Normal World **0xfa000000**, ao wrapper 0xf60e8. Este põe X0=-0x500,
X1=buffer, X2=tamanho, X3=0 e executa SMC #0 em **0xf60fc**. Isso identifica
a entrega ao monitor, sem recuperar sua rotina de decriptação/dispatch.
`SignerVer03`, a partir de 0x3fc000, está fora desse prefixo. Seu rótulo HZC2
é metadado do arquivo; nenhuma assinatura foi verificada.

### Bloqueio no DRM e código em claro no tail

O [parser/decryptor publicado para Exynos9830](https://github.com/halal-beef/Exynos9830-Firmware-Decryptor/blob/5142272e65b8525647643131c42a0f495f60898c/decrypt-ldfws.py)
interpreta +0x28 como flag de cifragem e +0x44/+0x48 como início/fim exclusivo
do intervalo cifrado. Aplicado **somente como descrição de formato**, indica
cinco módulos marcados como cifrados. No DRM, o intervalo relativo é
**0x150–0x125b0**, ou **0x228150–0x23a5b0** no arquivo, com **74.848 bytes**.
O segundo campo é fim, não comprimento. O relatório guarda limites e hashes
de cada registro e de cada intervalo, sem publicar seus corpos.

A [apresentação original sobre o S21](https://www.offensivecon.org/speakers/2022/federico-menarini-and-martijn-bogaard.html)
corrobora a existência de LDFWs cifrados nessa arquitetura. Isso não fornece
as chaves do HZC2. O autor do decryptor restringe suas chaves ao Exynos9830.
Um ensaio offline limitado da hipótese desse formato/chave no intervalo DRM
não produziu plaintext validado nos pontos de entrada candidatos; não foi
gravada uma imagem modificada. Esse ensaio não valida chaves, IV, modo AES
ou decriptação para Exynos2100 e não integra a ferramenta publicada.

O tail, com flag zero, contém código AArch64 legível. Foram conferidos cinco
leaves `MOV W0,#0; RET` em **0x3fb0b8/0x3fb0c0/0x3fb0c8/0x3fb0d0/0x3fb0d8**.
O zero é resultado local dessas funções; não é resposta SEC_PGTBL. O tail
também contém wrappers com SMC, sem ligação comprovada com esse serviço.

O start_smc_id **0x82002000** torna `drm_fw` candidato para **0x82002060**
(diferença 0x60), reforçando as mensagens de erro do LK. A proximidade dos
identificadores não prova limites da faixa, índice de tabela ou endereço do
handler. O dispatch e o handler SEC_PGTBL **continuam não recuperados**.

## Chamadas e largura dos retornos

| Etapa no sboot | Efeito |
|---|---|
| 0xfae2c–0xfae40 | x0=0x82002060, x1=1, x2/x3=0; BL → 0xf6088, SMC #0/RET |
| 0xfae44 | preserva o retorno X0 em X21 como candidato de base |
| 0xfae48–0xfae78 | trata 0, 3, -1 de 64 bits e alinhamento da base a 1 MiB |
| 0xfae7c–0xfae90 | mesmo serviço, x1=2 para tamanho |
| 0xfae94 | MOV W20,W0: conserva somente os 32 bits baixos do tamanho |
| 0xfae98–0xfaea8 | trata 0, 3 e 0xffffffff em W0 |
| 0xfaeac | AND X1,X21,#0xfffff: testa novamente a base |
| 0xfaeb4 | conserva o tamanho em X2 por máscara 0xffffffff |
| 0xfaec4 | X27 = X21 + X2, sem checagem de overflow nesse trecho |

As mensagens referenciadas são SEC_PGTBL_BASE e SEC_PGTBL_SIZE, incluindo
Invalid type, serviço não suportado, LDFW não inicializado e alinhamento.
Essa identificação vem de chamadas, argumentos e strings, não de símbolos
ELF ou de um retorno observado.

### Classificação do retorno da base

| X0 fornecido | Base normalizada | W22 |
|---|---|---:|
| 0 | 0 | 0 |
| 3 | 0 | 0 |
| 0xffffffffffffffff | 0 | 0 |
| outro valor com bits 19:0 não zero | 0 | 0 |
| outro valor alinhado a 1 MiB | mantém X0 | 1 |

A comparação de -1 é em X0. O valor 0x00000000ffffffff não corresponde
a esse -1 de 64 bits e cai na classificação de base desalinhada. Não foi
presumido qual forma o provedor realmente retorna.

### Classificação do retorno do tamanho

As comparações são em W0, portanto ignoram a metade superior de X0. Valores
baixos 0, 3 e 0xffffffff desabilitam W22 e levam tamanho zero a X2. Os demais
valores são mantidos em 32 bits sem uma checagem independente de alinhamento.

No caminho seguido desde 0xfae44, a base que chega a 0xfaeac já é alinhada
ou foi zerada. Se o SMC e as chamadas de impressão preservarem X21/W22 como
o LK espera, seu AND com 0xfffff dará zero. Portanto, a mensagem
SEC_PGTBL_SIZE de desalinhamento não valida o tamanho nesse caminho.
O modelo torna explícita essa hipótese de preservação. A emulação abaixo
confere esse trecho; não reproduz o provedor ou todo o firmware.

## Efeito sobre os bancos e guarda adicional

W22 não zero seleciona o ramo 0xfb670. O construtor 0xf1570 recebe uma faixa
até a base SEC_PGTBL, e as seguintes começam após o fim X27, com outros
ramos condicionados ao tamanho total de RAM. Os comprimentos de nós também
usam aritmética W. Não se reconstruiu toda a lista de bancos neste modelo.

Uma resposta sintética com base 0xe0000000 e tamanho 0x1000 mantém W22=1,
embora o tamanho não seja múltiplo de 1 MiB. O inspetor reproduz isso como
comportamento do LK e, separadamente, reprova uma **guarda de aritmética do
host** que exige flag, tamanho não zero/alinhado e soma sem wrap de 64 bits.
Essa guarda é adicional: não deve ser atribuída ao binário Samsung.

Mesmo uma guarda aprovada não comprova autenticidade da resposta, posse de
memória, ausência de outras reservas ou adequação ao R10. O resultado sempre
mantém `runtime_observed=false`, `memory_map_verified=false` e
`range_is_free=false`. Não se alteraram drivers ou o payload a partir desses
cenários, nem se corrigiu o firmware proprietário.

## Emulação do chamador, com serviços substituídos

`emulate_sec_pgtbl_hzc2.py` usa Unicorn **2.1.4** para executar o trecho
original **0xfae2c–0xfaec8**, seus ramos de erro e o RET do wrapper SMC.
O SMC é interceptado: somente os dois X0 fornecidos são usados como respostas;
X1..X3 recebem valores sem utilidade para o chamador. A impressão é omitida,
envenenando X0..X18 e preservando os registradores que o chamador espera.

Há apenas três páginas de instruções, com leitura/execução, sem mapeamento
de MMIO ou dados do aparelho. Cada cenário tem limite de 256 visitas a
instruções e um segundo de emulação. Saídas, argumentos do SMC e chamadas
omitidas são conferidos; execução ou acesso inesperado provoca erro. Os PCs
usam offsets de arquivo como endereços artificiais, sem alegar base runtime.

A matriz reproduzível tem **144 cenários**: 80 combinações explícitas e 64
pares pseudoaleatórios com seed fixa. Todos coincidiram com o modelo para
X21, W20, W22 e X27, cobrindo sentinelas, truncamento e wrap. O ramo do erro
de alinhamento do tamanho não foi visitado. O exemplo base=0xe0000000,
tamanho=0x1000 manteve W22=1 e X27=0xe0001000. É uma confirmação executável
do comportamento local sob as hipóteses, não uma resposta observada.

O [relatório da matriz](references/sec-pgtbl-unicorn-hzc2.json) identifica
versão do emulador, hashes, entradas, registradores e PCs cobertos.
`provider_executed`, `runtime_observed`, `memory_map_verified` e
`range_is_free` permanecem falsos.

## Reprodução

```bash
# Somente evidências dos dois arquivos originais, sem cenário presumido.
python3 scripts/inspect_sec_pgtbl_hzc2.py /caminho/sboot.bin /caminho/ldfw.img

# Exemplo fictício de retorno; não são valores medidos no telefone.
python3 scripts/inspect_sec_pgtbl_hzc2.py /caminho/sboot.bin /caminho/ldfw.img \
  --base-result 0xe0000000 --size-result 0x1000

python3 -m unittest discover -s scripts -p 'test_sec_pgtbl_hzc2.py' -v

# Dependência opcional, fora do repositório; o inspetor/modelo usam stdlib.
python3 -m venv /tmp/s21-unicorn-env
/tmp/s21-unicorn-env/bin/python -m pip install unicorn==2.1.4
/tmp/s21-unicorn-env/bin/python scripts/emulate_sec_pgtbl_hzc2.py \
  /caminho/sboot.bin /caminho/ldfw.img --self-check

/tmp/s21-unicorn-env/bin/python scripts/emulate_sec_pgtbl_hzc2.py \
  /caminho/sboot.bin /caminho/ldfw.img \
  --base-result 0xe0000000 --size-result 0x1000
```

A CLI exige os hashes e tamanhos exatos dos dois binários antes de emitir
evidências ou cenário. As duas respostas são opcionais, mas devem ser dadas
juntas como valores brutos unsigned de 64 bits; não há respostas padrão.
O relatório sem cenário está em [sec-pgtbl-hzc2.json](references/sec-pgtbl-hzc2.json),
somente com metadados, palavras de instrução e strings.

**14 testes de host passaram**, incluindo os sete anteriores de respostas
e mais sete de limites do contêiner/recusa do emulador: tamanhos inválidos,
truncamento, intervalos cifrados, nomes, flag desconhecida, término e limite
de registros. As CLIs foram executadas nas imagens originais e a matriz
Unicorn passou em 144/144 cenários. As suítes R8/R9/R10 anteriores não foram
reexecutadas; seus arquivos não mudaram.

## O que falta para recuperar o handler

Para continuar **especificamente dentro do provedor SEC_PGTBL**, falta código
em claro do DRM HZC2 com origem verificável, ou sua implementação fonte
correspondente. Outro exemplar do mesmo `ldfw.img` cifrado e os READMEs de
compilação do kernel não fecham essa lacuna. Ainda é possível continuar a
análise dos chamadores e de outros trechos em claro com o material recebido.

Unicorn/Qiling não removem a cifragem. Angr precisa de instruções e estados
de entrada definidos; executar ciphertext ou substituir respostas por
constantes não enumera retornos reais. Mesmo com plaintext, será necessário
reconstruir o dispatch, a inicialização e as dependências do handler antes
de atribuir significado às suas saídas. Retorno local e resposta que chega
ao LK também podem passar por adaptações de contexto do monitor.

Tracing do kernel exigiria um canal de observação que não existe na sessão
rish atual. As recusas já recebidas continuam válidas; não se repetiram
coletas, não se pediu root e não se provocaram falhas no telefone. As
respostas efetivas soc_info/SEC_PGTBL e o estado final de boot seguem abertos.
