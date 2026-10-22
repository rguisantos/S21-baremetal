# SEC_PGTBL: respostas e checagem de tamanho no LK

Análise de 2026-10-21 em Campo Grande, correspondente a 2026-10-22 UTC.
Usa apenas o BL HZC2 recebido; não repete a coleta Harx bloqueada e não
executa serviços no telefone. Os offsets abaixo são de arquivo.

O tratamento de **0x82002060** no LK foi isolado e modelado com respostas
fornecidas explicitamente. Há um achado local: a instrução associada à
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

O inspetor registra também palavras little-endian do início, como visão de
bytes. Não atribui semântica de endereço de carga a esses campos, não
identifica algoritmo/chave pelo marcador e não valida assinaturas. O handler
SEC_PGTBL e o dispatch do provedor **não foram recuperados** dessa imagem.
As mensagens do LK citam LDFW não inicializado, o que sustenta uma dependência,
sem provar onde todo o atendimento desse serviço está implementado.

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
O modelo torna explícita essa hipótese de preservação; não é uma emulação
de todos os registradores ou do firmware.

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

## Reprodução

```bash
# Somente evidências dos dois arquivos originais, sem cenário presumido.
python3 scripts/inspect_sec_pgtbl_hzc2.py /caminho/sboot.bin /caminho/ldfw.img

# Exemplo fictício de retorno; não são valores medidos no telefone.
python3 scripts/inspect_sec_pgtbl_hzc2.py /caminho/sboot.bin /caminho/ldfw.img \
  --base-result 0xe0000000 --size-result 0x1000

python3 -m unittest discover -s scripts -p 'test_sec_pgtbl_hzc2.py' -v
```

A CLI exige os hashes e tamanhos exatos dos dois binários antes de emitir
evidências ou cenário. As duas respostas são opcionais, mas devem ser dadas
juntas como valores brutos unsigned de 64 bits; não há respostas padrão.
O relatório sem cenário está em [sec-pgtbl-hzc2.json](references/sec-pgtbl-hzc2.json),
somente com metadados, palavras de instrução e strings.

Sete testes novos passaram, cobrindo sentinelas, larguras X/W, perda de bits
superiores do tamanho, desalinhamento, wrap e recusa de identidade incorreta.
A CLI foi executada nos arquivos originais e no exemplo sintético acima.
A validação desta etapa se limita à ferramenta nova; as suítes anteriores
não foram reexecutadas e não houve mudança em seus arquivos.

O avanço fecha a classificação dos retornos no chamador e identifica uma
checagem insuficiente. Permanecem abertos o dispatch do provedor, as respostas
soc_info/SEC_PGTBL efetivas e o estado final de boot. O material recebido
basta para continuar; não é necessário outro arquivo do aparelho neste marco.
