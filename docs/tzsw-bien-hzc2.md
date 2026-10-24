# HZC2: envelope BiEn e validação de candidatos TZSW

Continuação de **2026-10-24 (Campo Grande)**, sobre main `cd8b512`.
A revisão automática do PR #8 terminou sem achados. O [rastreio anterior](teegris-ioctl-boundary-hzc2.md)
chegou ao SVC do wrapper; esta etapa investiga a imagem candidata a conter
seu consumidor, sem presumir que os bytes recebidos sejam código em claro.

**Resultado:** o envelope BiEn foi delimitado e um ensaio com parâmetros
públicos da referência Exynos9830 foi reproduzido por duas implementações
AES. O resultado **não coincide com o digest candidato do cabeçalho** e não
foi aceito ou salvo como plaintext. O handler SVC permanece sem identificação.
Uma nova validação verifica futuros candidatos contra o original, recusando
inclusive a substituição do digest pelo próprio candidato.

## Identidade e campos observados

`tzsw.img`: 1572864 bytes, SHA-256
`83eedef172714cc2e24624a12e77ab7e7a2e04891fe98366f653b3e3a6c533c0`,
do mesmo [pacote BL HZC2](bootloader-hzc2.md) já recebido. O inspetor exige
essa identidade antes de ler referências ou processar um candidato.

| Campo/recorte | Valor observado / interpretação limitada |
|---|---|
| `0x10…0x13` | `BiEn` |
| `0x14…0x17` | bytes `19 09 19 20`; sem atribuir uma semântica de versão |
| `0x18…0x1f` | `teegris` terminado em NUL |
| u32 em `0x20 / 0x24` | `1 / 0x834`, mantidos como palavras brutas |
| u32 em `0x28 / 0x2c` | `0x1000 / 0x9d8f0`, início/fim segundo a referência |
| u32 em `0x30 / 0x34` | ambos `0x9c8f0`, iguais à diferença fim-início |
| Recorte candidato | `[0x1000,0x9d8f0)`, **641264 bytes**, múltiplo de 16 |
| Material de cabeçalho na referência | `[0x40,0x70)`, 48 bytes |
| Digest na referência | `[0x70,0x90)`, 32 bytes |

Os nomes ligados à transformação vêm da referência de implementação abaixo.
Não foi ligado o parser/carregador HZC2 a esses campos, nem comprovado o
algoritmo ou a chave usados no aparelho. A presença de BiEn não transforma
esse intervalo em código AArch64 pronto para rastrear o dispatcher.

## Referência fixada e ensaio estritamente negativo

Fontes primárias em [Creeeeger/CreckerROM, commit bc9aa70](https://github.com/Creeeeger/CreckerROM/tree/bc9aa7039a6cd5f8cfcfd803ac74f37161fe94a3/scripts/samsung_signing):
`tzsw_crypt_tool.py`, `aes_cbc.py`, `binary_io.py` e `soc_data.py`. Os quatro
arquivos foram lidos e conferidos por SHA-256 e blob Git. O manifesto tem
URLs e hashes completos. Nenhum arquivo externo foi importado ou executado.

O utilitário se declara Exynos9830. Sua tabela de SoCs não contém Exynos2100.
Ele lê inteiros little-endian, propõe AES-256-CBC para os 48 bytes do
cabeçalho e usa os 32+16 bytes resultantes na transformação do payload.
Compara SHA-256 desse intervalo ao campo de 32 bytes e procura o marcador
`ub_tzar_walk_cb`. Isso descreve a implementação consultada, não a do HZC2.

Um único conjunto de parâmetros dessa fonte foi avaliado em memória,
independentemente por `cryptography` 50.0.2 e OpenSSL 3.0.13. Os resultados
do bundle e do payload coincidem byte a byte entre as implementações:

| Evidência | SHA-256 / resultado |
|---|---|
| Intervalo bruto recebido | `e7854e8566fd12fcd8f887f6ba10709cc3f74f68a3af9441b202aa1c86637099` |
| Campo de digest no original | `b24b95f1cc9b7a3df61844c886c6310facb7e37d53817e188dffb8f7f53cfd66` |
| Saída da hipótese, nos dois backends | `e5440865f72d323677fbd2ce691596053390afc55936c25a42b1e95b896178ee` |
| Digest coincide / marcador encontrado | **não / não** |

Não houve busca de chaves ou variações por tentativa. O resultado recusa
esse conjunto de parâmetros e interpretação como plaintext validado; não
exclui outro algoritmo, layout ou material correspondente ao HZC2. Nenhum
byte dessa saída foi desassemblado como handler ou publicado como firmware.

## Validação de um futuro candidato

O [inspetor](../scripts/inspect_tzsw_bien.py) lê um candidato completo, com
limite de tamanho, e usa somente os campos do original identificado:

1. Exige o mesmo tamanho da imagem.
2. Exige identidade de todos os bytes fora da região candidata, incluindo
   cabeçalho, digest e cauda.
3. Compara SHA-256 da região candidata com o digest do original.

Trocar o digest no candidato não o torna aceitável. Coincidência futura
significaria correspondência com esse digest sob a hipótese declarada;
assinaturas Samsung, carregamento físico e comportamento de execução ainda
precisariam de validação própria. O marcador é somente informativo.

O modo padrão usa stdlib. A opção de ensaio requer as quatro fontes exatas,
`cryptography` e OpenSSL, lê constantes por AST restrita e não executa suas
funções. Nenhum modo grava firmware/plaintext ou emite chave/IV derivados.

```sh
python3 scripts/inspect_tzsw_bien.py /caminho/tzsw.img
python3 scripts/inspect_tzsw_bien.py /caminho/tzsw.img \
  --probe-reference-dir /refs/creckerrom-bc9aa70
python3 scripts/inspect_tzsw_bien.py /caminho/tzsw.img --candidate /caminho/candidato.img
python3 -m unittest discover -s scripts -p test_tzsw_bien.py -v
```

`--candidate` inválido produz JSON com `accepted=false` e **exit 1**.
Erros de identidade/formato/referência produzem **exit 2**, sem relatório
parcial. A inspeção e o ensaio negativo de referência usam exit 0 quando
concluídos; isso não significa que a hipótese criptográfica passou.

**15 testes passaram**, incluindo candidato sintético válido, corrupção
do payload, alteração fora dele, substituição de digest, tamanhos, limites,
constantes malformadas, fonte alterada e recusa do firmware errado. O positivo
é sintético; não representa plaintext HZC2 recuperado. No ensaio real, o
próprio arquivo bruto também foi recusado como candidato com exit 1. O hash
do original permaneceu intacto.

- [Envelope, fontes, versões e ensaios](references/tzsw-bien-hzc2.json)
- [Saída dos testes](references/tzsw-bien-host-tests.txt)

Esta ramificação do SVC depende agora de código em claro com origem e
correspondência verificáveis, ou implementação HZC2 equivalente. As
bibliotecas do TZAR não substituem o kernel consumidor. Não há novo
diagnóstico/QEMU/S21 executado. Entrada, memória e canal de leitura do
diagnóstico físico permanecem frentes paralelas no [roadmap](roadmap.md).
A recuperação desse consumidor não é requisito universal do diagnóstico mínimo;
é a dependência específica deste rastreio do SVC.
