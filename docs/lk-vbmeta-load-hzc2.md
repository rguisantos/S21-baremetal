# HZC2: leitura do vbmeta, tabela de partições e fallback para boot

Continuação offline de 04/11/2026 (Campo Grande), base 09b1b4d do PR #91.
O usuário propôs seguir os callbacks e fallbacks do bootloader fixado.
Mantida a validação offline adicional; PR #91 aberto, sem merge, main e
PRs anteriores preservados. Conferência externa não é substituída por outra
execução do mesmo assistente.

**Achado:** o caminho selecionado pede vbmeta na tabela AVB, normaliza o nome
para VBMETA e procura uma entrada na tabela de partições em memória. Na
ausência dessa entrada, existe um fallback condicionado para carregar o AVB
do footer de boot. Nenhuma dessas observações identifica os bytes instalados
no aparelho ou demonstra que um dos caminhos foi executado nele.

## Identidade e método

Sboot HZC2: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Foi novamente obtido do membro sboot.bin.lz4 do
[BL fixado](references/capture-a0-parent-pins-hzc2.json): membro de 1963522
bytes, SHA-256
`7d07b1d85b746c073c51278a5102ff4edd8fd73a4e9fcadceb1f269ede000bd1`.
Arquivo e membro foram consumidos em buffers conferidos. Não se executou
nenhuma instrução Samsung, serviço seguro ou operação no aparelho.

O [extrator](../scripts/inspect_lk_vbmeta_load.py) valida a identidade do
buffer antes de analisar e fornece os mesmos bytes ao GNU por memfd selado.
Não verifica um caminho para depois reabri-lo no disassembler. Confere todas
as palavras dos blocos, destinos relativos, operandos e literais selecionados,
além de decodificar o vínculo entre instalador, slots e chamadas indiretas.

O [relatório](references/lk-vbmeta-load-hzc2.json) registra 971 palavras,
184 destinos relativos e 102 operandos. PCs são offsets de arquivo; endereços
da tabela são relativos ao modelo LK já usado pelo projeto. Não são nova
medição de endereço físico, RAM ou preservação em execução.

## Pedido inicial e origem dos bytes

| Etapa | Evidência no código selecionado |
|---|---|
| Caller | 0xfbc58/0xfbc64 forma X0=0x28ef80; o byte nesse objeto do arquivo é NUL, formando suffix vazio |
| Wrapper | 0x17f608 salva X0; 0x17f6a4 entrega o suffix como X2 a 0x1244b0; W3 vem do byte de desbloqueio e W4=0 |
| Slot normal | Com flag bit2 limpo, 0x1246f8/0x1246fc forma o literal vbmeta; 0x12473c chama 0x122498 com W6=0 |
| Loader | 0x122524 compara o prefixo vbmeta; 0x1225e0 concatena nome e suffix pelo helper 0x1253e0 |
| Leitura raiz | Prefixo igual seleciona offset 0 e pedido de 65536 bytes em 0x122748..0x1227cc |
| Criptografia | Após o retorno da leitura e testes locais, 0x1227f4 chama 0x1262b0 |

O suffix vazio é uma evidência do objeto no arquivo e do caller selecionado;
não se certifica que memória, argumentos ou tabela permaneçam inalterados
durante um boot real. Há outros modos e entradas indiretas fora deste recorte.

O instalador 0x180de8 escreve no objeto relativo 0xd05900:

| Slot | Callback instalado | Uso selecionado |
|---|---|---|
| +24 | 0x180448, leitura | LDR/BLR em 0x1225f4/0x122610 e 0x1227b4/0x1227cc |
| +88 | 0x17fcb8, tamanho | Chamada direta em 0x1806b4 para resolver offset negativo |

O callback de leitura copia o nome, chama 0x125a68 para converter apenas
ASCII a..z em A..Z e chama 0x14a1b0. Este busca o nome com o comparador
0x1b2538 na tabela relativa 0xcd36b8: contador u32 em +4, nomes em
+0x40+i*0x84 e ponteiro retornado em +0x1c+i*0x84. Não há conteúdo dessa
tabela no arquivo analisado que permita determinar o registro ativo.

O corpo do callback usa campos do registro retornado: LE32 em +20 na
aritmética do endereço de setor e LE32 em +28 na seleção do backend. O nome
BOOTLOADER é um caso local que usa seletor 1. O helper de tamanho calcula
LE32(record+24)<<9. Há pedidos de 512 bytes para 0x11b258; esse dispatcher
lê uma função em device+168 e salta indiretamente. O alvo ativo desse salto
continua uma fronteira. Essas fórmulas não autorizam atribuir unidades aos
campos da transcrição PIT sem demonstrar a ligação entre os registros.

Consulta sem registro devolve W0=3; falha de alocação local devolve W0=1.
Nos caminhos normais selecionados, os retornos das chamadas de backend não
são testados antes de cópias e publicação de out_num_read=comprimento
solicitado, W0=0. Tudo isso depende dos callees retornarem normalmente e
preservarem o estado necessário; não demonstra sucesso físico da leitura,
geometria válida ou conteúdo inicializado em todas as condições.

## Fallback: condição e alcance

O ramo 0x122b10..0x122b30 seleciona 0x123030 somente quando o retorno da
leitura inicial é 3, a comparação do prefixo vbmeta deu zero, o flag bit2
está limpo e o parâmetro de localização encadeada é zero. O modelo de host
no extrator reproduz apenas esse predicado local, sem executar firmware.

0x123034/0x123060 escolhe o literal boot; 0x1230b0 chama novamente 0x122498.
Boot não coincide com o prefixo vbmeta: o loader pede 64 bytes no offset
−64, valida o footer e usa o offset/tamanho nele decodificados. O tamanho
de metadados é limitado a 65536 nesse caminho. O callback resolve um offset
negativo somando o tamanho obtido por 0x17fcb8.

Falha de RSA ou header não é a condição desse ramo de fallback: ele testa
o retorno da leitura antes da chamada criptográfica. Não se afirma ausência
de outros tratamentos em todo o bootloader. O fallback não prova aceitação
de imagem sem assinatura, desbloqueio ou retirada de verificações posteriores.

VBMETA_SAMSUNG e VBMETA_SYSTEM existem como strings no arquivo. Nos corpos
selecionados de leitura/tamanho não há troca automática de vbmeta por esses
nomes. Presença de strings não estabelece fallback; isso também não é uma
busca exaustiva de todos os modos e chamadores do bootloader.

## Relação com o pai candidato e a confiança

A [comparação anterior](capture-a0-parent-hzc2.md) demonstrou que o pai
extraído do BL satisfaz os dois arquivos stock e não satisfaz B inalterado.
Este caminho estático agora liga o pedido nominal à busca de VBMETA, nome
presente no [PIT transcrito](download-pit-observation-hzc2.md) e no mapa
[by-name registrado](runtime-collection.md). Isso é correspondência de rota
e nome, sem identificar o registro ativo ou os bytes instalados.

A [consulta de confiança](lk-avb-key-trust-hzc2.md) é outra operação: o
callback 0x180d50 pede material de chave ao monitor usando o rótulo vbmeta.
Esse rótulo não é prova de leitura do arquivo vbmeta.img nem determina a
partição que forneceu os metadados. A chave ativa não foi observada; RSA
coerente com a chave embutida continua sem estabelecer confiança Samsung.

Para demonstrar uso efetivo, seria necessária uma evidência já existente e
confiável que vinculasse os bytes de partição ao aparelho, a identidade do
bootloader e a seleção efetiva da rota/tabela naquele boot, ou uma medição
autenticada equivalente com cobertura conhecida. Um dump identificado
comprovaria conteúdo naquele instante; sozinho não prova consumo no boot.
Build string, green, PIT/by-name e arquivos do mesmo pacote não substituem
esse vínculo. A análise estática de mais constantes não produz essa medição.

Não há nova coleta solicitada ou executada. Na ausência dessa evidência,
o vínculo físico fica **não demonstrado**, com critério de parada explícito;
não se abre busca indefinida por SMC ou fallback com base somente em strings.
Aceitação pela cadeia travada permanece bloqueada, não convertida em risco
residual ou em autorização de A1. SignerVer03, KMI/política runtime e causa
produtora da diferença da Image continuam nos respectivos estados abertos.

## Reprodução e validação

```sh
python3 scripts/inspect_lk_vbmeta_load.py /insumos/sboot.bin \
  --output build/vbmeta-load-novo.json
python3 scripts/test_lk_vbmeta_load.py
python3 -m unittest discover -s scripts -p 'test_lk_avb*.py'
python3 scripts/validate_baseline.py --output-dir build/baseline-vbmeta-novo
```

O relatório de destino deve ser novo. Identidade, limites, bindings ou
operandos divergentes e falhas/timeout do GNU causam recusa; firmware não
é executado. Os 25 testes sintéticos cobrem slots, registradores, destinos,
predicado de fallback, normalização, recusa antes do GNU e imutabilidade
do buffer fornecido ao processo nativo. As 48 regressões AVB e o baseline
obrigatório 9/9 passaram. São 73 testes de host nesta rodada, separados
dos 378 A0 anteriores, que não foram reclassificados como testes novos.
[Validação textual](references/lk-vbmeta-load-validation-20261104.json).

O PR permanece aberto. A1 não começou; nenhuma decisão OEM, gravação,
reboot, leitura de partição ou outra ação no aparelho foi realizada.
