# HZC2: marcador antes da cópia e pedido de SHA ao monitor

Análise estática de **2026-10-30 (Campo Grande)**, sobre main `dcba0d3`.
Sboot: 4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; endereços de dados são relativos ao modelo LK,
sem medição dos seus conteúdos no aparelho. Nenhuma instrução Samsung,
SMC, manutenção de cache ou operação no telefone foi executada.

**Conclusão:** o helper `0x151a10`, chamado pelos caminhos v2/v3 antes das
cópias rastreadas, compara 16 bytes com `SEANDROIDENFORCE` e consulta uma
política para encaminhar um pedido nominal de SHA ou de apagamento de chave
pública. Uma diferença no marcador imprime falha, mas também chega à consulta
dessa política. Esse bloco não fornece um certificado de autenticação da Image.
Os chamadores selecionados não testam seu retorno antes de sobrescrever W0.

## Entrada e localização do marcador

Os dois chamadores empacotam palavras de 32 bits em memória little-endian,
carregam o par como X0 e chamam o helper:

| Caminho | Preparação e chamada | Metade alta do argumento X0 |
|---|---|---|
| v2 | `0x12e2b8..0x12e2cc` | W20 no instante do STP |
| v3 | `0x12e6f8..0x12e70c` | W21 no instante do STP |

O helper salva X0 em `frame+16`, mas lê **u32 de `frame+20`**, a metade
alta, para somar a `0x94000000`. Não usa a metade baixa como deslocamento
do marcador. Esta entrega não amplia o recorte dos produtores W20/W21 para
uma validação de todos os tamanhos dos contêineres.

O bit 19 das flags de `0x147ed8` escolhe a string de partição: `RECOVERY`
(8 bytes) ou `BOOT` (4 bytes). O copiador `0x1b2688` guarda o nome no frame.
**Isso não troca a base fixa `0x94000000` por outro endereço.** Os dois ramos
passam ao comparador `0x1b26b0` o endereço staging mais a metade alta de X0,
a literal em `0x242ad8` e comprimento 16. São os 16 caracteres do marcador,
sem exigir o NUL seguinte.

## Política e continuação local

O getter `0x14da90` lê um byte relativo em `0xcd563c` e retorna se é diferente
de zero. A origem e o valor ativo desse byte permanecem abertos; não foi
identificado aqui como sinônimo de estado OEM, FRP, KG ou Knox.

| Comparação | Byte de política | Continuação, se os helpers retornarem normalmente |
|---|---:|---|
| Igual | zero | Imprime `SEANDROID ENFORCING` e encaminha pedido de SHA |
| Igual | não zero | Imprime `SEANDROID ENFORCING` e encaminha pedido nominal de apagar chave pública |
| Diferente | zero | Relê flags, imprime falha boot/recovery e encaminha pedido de SHA |
| Diferente | não zero | Relê flags, imprime falha boot/recovery e encaminha pedido nominal de apagar chave pública |

O caminho de SHA chama `0x17dae8` em `0x151a94`, com estes argumentos:

| Registrador | Valor nominal |
|---|---|
| X0 | Ponteiro relativo `0x31d740` |
| W1 | u32 carregado de `0x31d738` |
| W2 | 1 |
| X3 | Ponteiro relativo `0xcd6250` |

**Não foi demonstrado que esse buffer seja a Image bruta ou o contêiner
boot inteiro.** Os produtores do buffer e do comprimento são uma próxima
fronteira concreta. Encontrar o marcador não estabelece essa igualdade.

## Wrapper SHA e efeitos ainda externos

A literal ligada ao ramo de erro é `[ERROR] SHA input size is limited 60MB`.
`0x17dae8` compara X1 unsigned com `0x3c00000`; tamanho maior imprime essa
mensagem e retorna W0=`0xffffffff`. O zero não é recusado por esse teste local.
O nome SHA vem dessa evidência estática, sem execução do algoritmo ou captura
de um digest. O argumento de modo 1 não foi convertido em um algoritmo específico.

No outro ramo, monta um pedido alinhado a 128 bytes na pilha:

| Offset no pedido | Store observado |
|---|---|
| +0 | Ponteiro de entrada, u64 |
| +8 | Ponteiro de saída, u64 |
| +16 | Comprimento, u32 |
| +28 | Modo, u32 |

Os demais bytes não foram demonstrados inicializados pelo wrapper; não se
reconstrói um pedido completo para executar no aparelho a partir desse quadro.
O código solicita limpeza de cache do pedido `[P,P+0x40)`, entrada `[I,I+N)`
e saída `[O,O+0x40)`, depois usa `0xf6088`, que contém `SMC #0; RET`:
X0=`0xffffffffffffff0f`, X1=P, X2=0, X3=4. As rotinas de cache alinham o
início para baixo e executam pelo menos uma operação mesmo se o intervalo
for vazio; os intervalos são argumentos nominais, não uma política validada
de acesso a memória livre.

Após retorno normal do monitor, invalida a saída por `0x189a40` e devolve
os 32 bits baixos do X0 recebido. O helper `0x151a10` não testa esse resultado.
A extensão de 64 bytes usada na manutenção de cache e o modo não estabelecem
um tamanho de digest. Traps, coerência efetiva, implementação segura e efeitos sobre os buffers
continuam desconhecidos.

No ramo alternativo, `0xf6ac0` usa a string `erase public_key` e solicita
SMC `0xc200101d`, X1=5, X2=X3=0. Isso identifica um pedido potencialmente
mutável, **não uma consulta para executar no celular**. Se a SMC retomar e
o helper retornar, o handler descarta seu resultado e impõe W0=0. Não houve
apagamento observado ou instrução de como provocar esse caminho.

## Retorno não certifica aceitação

No retorno de `0x151a10`, o caminho v2 carrega bytes e sobrescreve W0 em
`0x12e2d4`; o v3 faz isso em `0x12e720`. Não há teste do resultado entre as
chamadas e essas sobrescritas. Isso vale para os blocos selecionados e sob
retorno normal dos callees. Não exclui verificações em outra etapa, efeitos
do monitor ou interrupção de execução por uma chamada opaca.

Acrescentar `SEANDROIDENFORCE`, obter zero local ou desbloquear o bootloader
não constitui, com essa evidência, um percurso demonstrado para a sonda.
A [matriz Samsung](samsung-diagnostic-contract.md) continua exigindo carga
aceita, região própria/coerente, entrada compatível e aquisição do registro.
O telefone informado é de uso pessoal; o desenvolvimento desta etapa foi
inteiramente offline e não altera esse estado.

## Reprodução e validação

```bash
python3 scripts/inspect_lk_precopy_measurement.py /caminho/sboot.bin
python3 scripts/test_lk_precopy_measurement.py -v
```

O [relatório](references/lk-precopy-measurement-hzc2.json) confere **261
palavras GNU, 47 destinos relativos, 41 operandos selecionados e nove
literais** contra o arquivo identificado. Os 11 grafos são locais: ramos
condicionais mantêm ambos os lados e chamadas opacas só admitem continuação
condicionada ao retorno. A SMC inline do pedido de apagar chave é uma
fronteira explícita; seu epílogo textual não prova que essa fronteira retorne.

Doze testes sem firmware verificam cobertura incompleta/excedente, limites,
sobreposição, palavra divergente, alvo relativo errado, instrução sem decode,
operandos divergentes, PC duplicado e recusa de arquivo não identificado.
O CI executa esses testes antes do baseline R10. Eles validam o verificador,
não simulam a política Samsung ou a execução do monitor.

Próximo: localizar a produção de `0x31d738`/`0x31d740` e separar essa medição
nominal dos validadores de imagem chamados em outra etapa. A implementação
segura permanece uma fronteira; não é necessário repetir leituras ADB negadas
nem mudar o bloqueio do aparelho para continuar a análise.

[Registro da validação local](references/lk-precopy-measurement-validation-20261030.json): 12 testes novos, regressões de grafos 14/15, baseline de nove etapas aprovado e links de arquivos conferidos. Nenhum teste executou firmware Samsung.
