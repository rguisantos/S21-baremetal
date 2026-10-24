# HZC2: arquivo TZAR e fronteira das bibliotecas criptográficas

Continuação de **2026-10-24 (Campo Grande)**, sobre a main `65040a6`, após
a revisão e o merge do PR #6. Investigação estática do mesmo pacote BL
recebido; os [READMEs de build](stock-firmware-hzc2.md) não fornecem a
implementação HASH do firmware.

**Resultado:** o primeiro bloco interno de `tzar.img` foi descomprimido e
seus **44 registros** foram percorridos integralmente. As bibliotecas HZC2
permitem localizar uma fronteira concreta entre EVP e `/dev/crypto`, mas
não identificam o seletor MMIO `0x19` ou os bytes DMA usados pelo EPBL.
Essa análise usa componentes HZC2, sem importar uma resposta de outro SoC.

## Identidade e formato observado

O componente vem do membro `tzar.img.lz4` do [BL inventariado](bootloader-hzc2.md):

| Entrada/intervalo | Tamanho | SHA-256 |
|---|---:|---|
| `tzar.img` depois do LZ4 externo | 7340816 | `791c8818555e64d0e060c406e68748e869c7d53fbc9c9bbc893a1dd4f65a2077` |
| Primeiro bloco interno descomprimido | 6159648 | `5b98e0ad1d493cf5e9d792ca607e8c05a0f4dbc019b9263806fe68541edbd97d` |
| Cauda a partir de `0x2b4ddc` | 4502836 | `fcea9f41db1b6f0caee96984d8ef320feee38f0474b97a44ffb735304ace67ac` |

O prefixo tem três u32 little-endian: tamanho descomprimido `0x5dfd20`,
magic legado LZ4 `0x184c2102` e tamanho comprimido `0x2b4dd0`. O bloco começa
em `0xc` e termina em `0x2b4ddc`. O leitor trata esse bloco observado;
não presume que ele descreva toda a imagem ou uma especificação genérica.
A cauda permanece contabilizada por tamanho/hash, sem interpretação no relatório.

O resultado começa com `7f a5 54 41 00 00 00 01`, seguido de tamanho total
e contagem 44. Cada registro tem tamanho do nome, tamanho do conteúdo,
nome ASCII terminado em NUL e conteúdo. Todos os bytes desse arquivo
interno foram consumidos; dois registros têm conteúdo vazio.

Os conteúdos não estão necessariamente alinhados a quatro bytes no arquivo
interno. Por exemplo, `/lib64/libscrypto.so` começa em `0x2f8482`.
Portanto, uma busca de instruções no contêiner comprimido ou alinhada apenas
ao offset externo não equivale a examinar o código ELF dessas bibliotecas.
O leitor usa os segmentos ELF para traduzir endereços virtuais em bytes do
arquivo correspondente. Isso não determina endereços físicos no S21.

## Bibliotecas identificadas

| Arquivo dentro do primeiro TZAR | Bytes | SHA-256 |
|---|---:|---|
| `/lib32/libscrypto.so` | 1081864 | `9f148111c474f8109e91e8c99d8fb85289c258bb3cf9c0cbd21c3d5064c03775` |
| `/lib64/libscrypto.so` | 1184808 | `53a65d95d602cadfd690be31f9181af5128b240a11e9a4a3007bfe01504317cc` |
| `/lib64/libteesl.so` | 345744 | `354d68d5936e11258f8c6a27828a4f7389045da57bdfa9bfc255603a46f77895` |

O manifesto inclui os nomes, offsets, tamanhos e hashes dos 44 registros.
A análise de instruções desta entrega seleciona somente as duas bibliotecas
de 64 bits acima; não declara auditoria completa de todos os módulos.

## Fronteira encontrada no código HZC2

Endereços abaixo são virtuais do ELF ligado, não offsets de `tzar.img`.
Os offsets de arquivo correspondentes constam no JSON.

| Evidência | Endereço / comportamento no recorte |
|---|---|
| `SHA384_Update` em `libscrypto` | `0xa7a9c`: BL para `SHA512_Update`, `0xa7ab0` |
| `SHA384_Final` em `libscrypto` | `0xa7aac`: B para `SHA512_Final`, `0xa7bac` |
| Caminho de dispositivo em `libteesl` | `0x2a804/0x2a808`: referência a `/dev/crypto` em `0x43670`; BL `open@plt` em `0x2a80c` |
| Preparação do pedido | buffer de `0x6c` bytes; tradução em `0x281f8–0x282e0`; resultado gravado no primeiro word |
| Alocação no dispositivo | `0x2a87c`: request 7; `0x2a894`: BL `ioctl@plt` |
| Atualização no dispositivo | `0x2c838–0x2c860`: buffer de `0x28` bytes, ponteiro e extensão preparados; request 1 para `ioctl@plt` |
| Atualização pelo EVP | `0x2c89c–0x2c8b0`: contexto em operação `+0x40`, buffer/extensão e BL `EVP_DigestUpdate@plt` |

Em `TEE_DigestUpdate`, os seletores `0x500000d2`, `0x500000d4` e `0x500000d6`
selecionam o caminho de dispositivo. O intervalo `0x50000001…0x50000006`
segue o caminho EVP. A seleção vem das comparações e branches no recorte,
sob as validações anteriores da função; não foi executada uma chamada TEE.

Esses números são seletores da API da biblioteca. Os requests `7` e `1`
são argumentos de `ioctl`. **Nenhum deles é o seletor MMIO HASH `0x19`.**
O helper fornece a tradução abaixo, derivada dos MOV/MOVK, comparações e
branches do recorte; não são respostas medidas do dispositivo:

| Seletor de entrada W0 | Código base produzido em W2 |
|---|---|
| `0x500000d2` | `0x02010000` |
| `0x500000d4` | `0x02030000` |
| `0x500000d6` | `0x02040000` |

O epílogo `0x28298–0x282a4` acrescenta por OR o bit 0 exatamente quando
o argumento W1 é 1. No chamador, esse argumento vem da operação `+0x08`;
o valor real não foi observado. A implementação que consome os pedidos
no dispositivo permanece aberta; não foi atribuída semântica SSS aos códigos.
Os símbolos SHA384/HMAC existentes no pacote tampouco ligam automaticamente
o EPBL a esses algoritmos.

## Implementação, reprodução e validação

O [inspetor](../scripts/inspect_tzar_hzc2.py) exige tamanho e SHA-256 exatos
antes da descompressão. Usa `liblz4` do host via `LZ4_decompress_safe`,
com limites de entrada/saída de 8 MiB e tamanho final obrigatório; confere
também o hash interno. O parser recusa nomes não canônicos/duplicados,
contagens, comprimentos, truncamentos e bytes sobrando. Não grava os caminhos
do arquivo. O leitor ELF restringe o formato a ELF64 LE AArch64 ET_DYN,
com limites de tabelas e nomes, segmentos respaldados pelo arquivo e tradução
única de endereços.

```sh
python3 scripts/inspect_tzar_hzc2.py /caminho/tzar.img
python3 scripts/check_tzar_crypto_gnu.py /caminho/tzar.img
python3 -m unittest discover -s scripts -p test_tzar_hzc2.py -v
```

O segundo comando usa o binutils do repositório e cria duas cópias temporárias
com nomes fixos para `readelf`/`objdump`; são removidas ao terminar. Não executa
ELFs, firmware, `/dev/crypto`, SMC ou MMIO.

**15 testes passaram**, incluindo LZ4 com cauda, entrada não alinhada, arquivo
vazio, corrupção de nomes/tamanhos/tabelas ELF, exclusão de BSS e segmentos
ambíguos, e recusa de firmware errado sem JSON parcial. O ensaio real confirmou
os 44 registros. GNU binutils 2.44 coincide em **15 símbolos dinâmicos,
127 palavras de instrução e 34 destinos relativos** dos recortes selecionados,
incluindo as 59 instruções do helper de tradução.
O aviso preexistente do `readelf` sobre o símbolo local 3 após `sh_info` na
`.dynsym` de `libteesl` está preservado; não houve erro de leitura ou divergência
nesses símbolos/instruções. Isso não valida o fluxo inteiro ou o ELF em execução.

- [Manifesto e recortes](references/tzar-crypto-hzc2.json)
- [Conferência GNU e aviso](references/tzar-crypto-gnu.json)
- [Saída dos testes](references/tzar-crypto-host-tests.txt)

O próximo rastreio está agora localizado na implementação correspondente
ao dispositivo que recebe esses códigos, antes de tentar relacionar
seus códigos com o [protocolo EPBL](epbl-protocol-hzc2.md). Continuam necessários
conteúdo verificável de `[0x1fc00,0x1fffc)`, implementação HZC2 de `0x19` ou
saída observada de 48 bytes. Não houve nova tentativa de chave, plaintext
validado ou execução física/QEMU nesta entrega. Entrada, coerência e leitura
do diagnóstico no telefone permanecem no [roadmap](roadmap.md).
