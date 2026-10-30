# HZC2: chave pública AVB embutida na entrada nominal de SHA

Análise de **2026-10-30 (Campo Grande)**, base main `cd7f304` após PR #57.
Sboot: 4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets são de arquivo. Nenhuma instrução Samsung ou serviço seguro foi
executado; nenhum comando ou alteração no telefone participou desta entrega.

**Conclusão:** os bytes originais usados pela referência nominal do
[pedido de SHA anterior à cópia](lk-precopy-measurement-hzc2.md) estão no
próprio LK: um objeto de chave pública RSA-4096 no formato serializado AVB,
com 1.032 bytes. A identificação combina layout, largura do módulo e duas
relações matemáticas, não apenas uma sequência que parece um cabeçalho.
O vínculo até a execução continua condicionado à preservação desses bytes.

## Instruções que escolhem a entrada

O analisador decodifica ADRP/ADD e ADRP/LDR W diretamente das palavras e
confere as nove instruções do recorte com GNU. Não usa um endereço físico
suposto para procurar os dados:

| Consumidor | Resultado relativo aos bytes do arquivo |
|---|---|
| ADRP X0 em `0x151a80`, ADD em `0x151a90` | Ponteiro para `0x31d740` |
| ADRP X1 em `0x151a74`, LDR W1 em `0x151a8c` | u32 little-endian em `0x31d738` |
| Valor de quatro bytes `08 04 00 00` | Comprimento 1.032 (`0x408`) |
| BL em `0x151a94` | Chama `0x17dae8` |

O objeto ocupa `[0x31d740,0x31db48)`, dentro do intervalo LK identificado
`[0xec000,0x36c000)`. A instrução lê **quatro bytes** de comprimento; não
agrega a palavra vizinha em `0x31d73c`. O consumidor anterior já fornece
modo W2=1 e saída relativa `0xcd6250`; não reclassificamos esse modo como
SHA-256 nem tratamos a manutenção de 64 bytes de cache como tamanho de digest.

Essa relação PC-relativa é a do modelo de arquivo. Não estabelece posse de
RAM livre, base física observada ou disponibilidade de um leitor no telefone.
Não foi necessário encontrar uma rotina que produza esses bytes em execução
para reconhecer a inicialização embutida; outros escritores e aliases seguem
fora desta conclusão.

## Layout e conferência matemática

A referência é o [header AVB do Android Open Source Project](https://github.com/AndroidBootloader/platform_external_avb/blob/b27a9aa53d2db7720e4d88d6950dcd979da97de3/libavb/avb_crypto.h),
fixado em `b27a9aa53d2db7720e4d88d6950dcd979da97de3` no mirror
AndroidBootloader. O SHA-256 dos 6.279 bytes consultados é
`5aa8c148e0951a241080446456ff8ed32364918273f8b771683dcad51519c07a`.
É referência de serialização, **não o fonte correspondente do fork Samsung**.

| Offset no objeto | Bytes | Interpretação conferida |
|---|---:|---|
| +0 | 4 | `key_num_bits=4096`, big-endian |
| +4 | 4 | `n0inv=0x41f3e7a3`, big-endian |
| +8 | 512 | Módulo n, big-endian, ímpar e com 4.096 bits |
| +520 | 512 | Valor rr, big-endian |

O tamanho é `8 + 2*(4096/8) = 1032`. Com os valores completos extraídos,
`n*n0inv mod 2^32 = 0xffffffff` e `rr = 2^8192 mod n`. Ambos passaram.
O expoente 65537 é implícito nessa interpretação AVB: não há um campo de
expoente medido separadamente no objeto.

O SHA-256 **calculado no host sobre o objeto serializado** é
`d185cb2fb075fdc3b128836be117bd44851aabacce2ebffd285cf4e2b3aa54e6`.
Esse hash identifica os bytes recebidos. Não é uma captura do monitor,
assinatura verificada ou prova de que a chave seja confiável para algum
vbmeta ativo. Não foi comparada a uma nova imagem vbmeta nesta etapa.

O parser é conservador: aceita larguras 2048/4096/8192, exige extensão exata,
largura completa do módulo, paridade e os dois parâmetros coerentes. Isso
é política do analisador offline, não reprodução de todos os critérios do LK.
Não verifica fatoração do módulo, posse de chave privada ou uma assinatura.

## O que muda na investigação

A origem **inicial** do ponteiro/comprimento deixou de ser uma lacuna:
há uma chave serializada e um comprimento embutidos, consumidos pelo recorte
identificado. A hipótese de que esse par simplesmente nomeie os bytes da
Image não descreve o conteúdo inicial encontrado no arquivo.

Ainda não se pode afirmar qual entrada o monitor recebeu em um boot real.
Também não foi demonstrado que este objeto seja a raiz de confiança usada
por um validador de vbmeta, nem que o serviço aceite o pedido ou execute um
algoritmo específico. A semântica criptográfica do monitor e o percurso de
autenticação/carga da Image continuam separados dessa identificação.

O próximo alvo é ligar a chave ao consumidor de verificação que decide a
aceitação do contêiner e delimitar suas políticas. A preservação do objeto
até a chamada também precisa de prova própria. O Marco A continua exigindo
carga compatível, região própria/coerente, entrada e aquisição dos 128 bytes;
desbloquear o aparelho não resolve automaticamente esses requisitos.

## Reprodução e testes

```bash
python3 scripts/inspect_lk_embedded_key.py /caminho/sboot.bin
python3 scripts/test_lk_embedded_key.py -v
python3 scripts/test_lk_precopy_measurement.py
```

O [relatório](references/lk-embedded-avb-key-hzc2.json) guarda offsets,
comprimento, metadados e hashes, nove palavras GNU, um alvo relativo e nove
operandos conferidos. O arquivo completo é identificado por tamanho/SHA
antes do objdump; nenhum firmware, chave bruta ou dump pessoal é publicado.

**17 testes novos passaram**, sem firmware Samsung: fixture matemática
construída independentemente para as três larguras, truncamentos/excesso,
endianness, módulo par ou curto, parâmetros alterados, campos trocados,
ADRP com deslocamento negativo, registradores/formas de instrução incorretos,
ADD com shift e recusa de imagem incorreta antes do GNU. A fixture sintética
tem `n=2^(bits-1)+3`, `n0inv=0x55555555`, `rr=36`; ela não declara uma chave
RSA de produção nem simula o monitor. As 12 regressões do verificador da
PR #57 também passaram. O CI executa os testes novos antes do baseline R10.

[Validação local](references/lk-embedded-avb-key-validation-20261030.json): relatório reproduzido byte a byte, 17 testes novos e 12 regressões aprovados, baseline de nove etapas aprovado e links de arquivos conferidos.
