# A0: tamanho da Image e dos ramdisks com os 274 módulos

Rodada de 02/11/2026, Campo Grande, continuação do PR #85 / `a773381`.
A restrição do [montador de geometria fixa](capture-a0-container-hzc2.md)
foi confrontada com bytes reais do [build alinhado](capture-a0-aligned-full-hzc2.md).
**Não há crescimento da Image; o ramdisk como saiu do build excede o
contêiner stock. Cópias com --strip-debug ficam menores que o payload stock,
mas ambos os payloads menores continuam recusados pela exigência de igualdade.**

## Medidas observadas

| Payload/perfil | Stock, bytes | Candidato, bytes | Diferença | Igualdade exigida pelo montador |
|---|---:|---:|---:|---|
| Image, receita da fonte sobre vmlinux preservado | 29469184 | 29403648 | -65536 | Não |
| Vendor ramdisk gzip-9, módulos como saíram do build | 12017257 | 103744124 | +91726867 | Não |
| Vendor ramdisk gzip-9, cópias com --strip-debug | 12017257 | 11774882 | -242375 | Não |

Os 103744124 bytes do ramdisk sem strip excedem até os 67108864 bytes
do **arquivo vendor_boot stock inteiro**, antes de considerar header/DTB/AVB.
Isso não é uma medição da capacidade física da partição, nem autorização
para reparticionamento. O perfil medido não cabe na geometria desse arquivo.

No perfil com strip, Image e ramdisk cabem em capacidade nos comprimentos
dos payloads stock, mas não têm comprimentos iguais. O montador atual
recusa tanto crescimento quanto redução. Nenhum byte de preenchimento,
extensão gzip ou nova geometria foi implementado/adotado nesta rodada.
Os 65536 bytes mencionados como padding no relatório são somente a diferença
aritmética da Image; zero_padding_applied permanece falso.

## Como a Image foi obtida

O vmlinux vem do pacote alinhado com SHA
d649de92e904eff21fd0cf40af0d10b5a10b67a54de54b5b6f234df628e10015.
Seu hash é 0355418bebc35257984558d234d61af4d6b71a312c8089b760fda7c1b3405eeb.
Não foi recompilado o kernel. A fonte Samsung fixada determina em
arch/arm64/boot/Makefile:

```text
OBJCOPYFLAGS_Image :=-O binary -R .note -R .note.gnu.build-id -R .comment -S
```

A receita foi executada com GNU objcopy 2.44, ferramenta de medição cujo
hash/versão estão no relatório. Não se apresenta essa versão como o binutils
original do build Samsung. Um leitor independente mapeou as 29 seções
alocadas com bytes em arquivo por seus LMAs e reproduziu **todos os bytes**
da saída, incluindo lacunas zeradas, sem emitir BSS ou as seções removidas.
O LMA é uma coordenada do ELF, não uma medição de endereço físico no telefone.

SHA-256 da Image: 9614f9a0ec8e83177ccb2010a585a128fd11f028cb46c417f2c1dbed2c2fd571.
O header ARM64 foi conferido: text_offset=524288, flags=10 e extensão
runtime declarada de 33910784 bytes; no stock essa extensão é 33976320.
O comprimento do arquivo e a reserva runtime são medidas distintas. Não se
atribui a diferença de 64 KiB a uma opção ou causa sem rastreio adicional.
Essa conferência não implementa a cápsula/exportador de A1 nem mede o handoff.

## Os dois perfis do ramdisk

O vendor ramdisk stock contém 296 entradas, das quais 274 são módulos.
O [runner](../scripts/check_capture_a0_sizes.py) usa exatamente os 274 nomes
e o mapeamento source -> lib/modules do relatório do PR #84. Os dois módulos
adicionais do build continuam fora da seleção. A montagem é um **protótipo
de dimensionamento com dados reais**, não um vendor_boot ou pacote de boot.

| Perfil | Soma dos módulos | CPIO completo | Gzip completo |
|---|---:|---:|---:|
| Stock original | 53963656 | 55168256 | 12017257 |
| Stock recompresso pelo mesmo gzip-9 de medição | 53963656 | 55168256 | 11882154 |
| Recompilados como preservados | 404465432 | 405670400 | 103744124 |
| Cópias recompiladas com --strip-debug | 53191272 | 54395904 | 11774882 |

A recompressão stock retém o CPIO original byte a byte e mostra que o perfil
gzip também altera o tamanho: 135103 bytes menores que o gzip recebido.
O perfil recompilado com strip fica 107272 bytes menor que esse controle
de mesma compressão. Não se atribui toda a folga de 242375 bytes ao strip.

A fonte permite INSTALL_MOD_STRIP=1 em Makefile e usa --strip-debug na
instalação em scripts/Makefile.modinst. O ensaio executou essa opção somente
em cópias. Em cada um dos 274 módulos foram comparados nome, imports,
exports/CRCs, versões, dependências, licenças, namespaces, vermagic e bytes/
tamanhos/atributos das seções alocadas. Esses dados permaneceram iguais.
Isso não valida ABI, relocations, CFI/RKP ou carregamento em execução.
A opção é um perfil de medição; não foi adotada como política do pacote final.

A montagem preserva nomes/ordem, headers newc (exceto filesize dos módulos)
e os dados das entradas não substituídas, incluindo modules.load e
modules.dep. O último não foi regenerado. Para os candidatos, o fim do CPIO
é alinhado a 512 com zeros. A compressão usa gzip.GzipFile, nível 9, mtime 0
e filename vazio; Python/zlib estão registrados. Não se afirma reproduzir
o compressor ou a política de instalação que gerou o stock.

Cada saída foi descomprimida e todas as 296 entradas foram conferidas em
stream, por metadados e SHA, sem extração dos caminhos. A medição admite
explicitamente CPIO de até 512 MiB em stream; os leitores normais continuam
limitados a 128 MiB. Não se mudou um limite global para acomodar o protótipo.

## Recusa observada e validação

Uma repetição foi recusada por GNU strip ao consumir mali_kbase.ko: a cópia
local tinha 26214400 bytes, contra 30998000 no artefato preservado, com
hash divergente. A origem dessa diferença não foi identificada. A tentativa
não gerou relatório de sucesso e não é uma falha de compilação do kernel.
O runner passou a conferir a cópia por tamanho/SHA imediatamente antes
do strip e conferir novamente o hash depois. A regressão cobre truncamento
e alteração de mesmo tamanho. As execuções completas em diretórios novos
reproduziram tamanhos e hashes da Image, CPIO/gzip e módulos tratados.

Código: [leitores/montagem](../scripts/capture_a0_sizes.py),
[runner](../scripts/check_capture_a0_sizes.py) e
[24 controles sintéticos](../scripts/test_capture_a0_sizes.py).
Evidência: [relatório](references/capture-a0-payload-sizes-hzc2.json) e
[validação](references/capture-a0-payload-sizes-validation-20261102.json).
Os 251 testes A0 e o baseline obrigatório 9/9 passaram; a CI inclui o conjunto.
Fonte, arquivos stock e pacote alinhado foram conferidos pelos pins anteriores.
Os 275 payloads selecionados são vmlinux e os 274 módulos, não uma nova
conferência independente externa dos 2133 arquivos do pacote inteiro.

```sh
python3 scripts/test_capture_a0_sizes.py
python3 scripts/check_capture_a0_sizes.py \
  --stock-dir /insumos/stock-raw \
  --candidate-artifacts /insumos/S21-HZC2-alinhado-completo-20261102.tar.gz \
  --source /insumos/Kernel.tar.gz --tools-root tools/root \
  --output-dir /saida/dimensionamento-novo
```

Retorno 2 indica medição concluída, com A0 aberto; 1 indica recusa/erro.
Nenhum firmware, Image, módulo ou ramdisk foi adicionado ao Git.

## Consequência para A0

Há uma barreira de capacidade para o perfil sem strip. O perfil com strip
mostra uma alternativa sem crescimento dos payloads, mas exige decidir e
validar como obter os comprimentos exatos, ou implementar outra geometria.
Essa adaptação não foi escondida em padding automático. Ainda faltam a
política do pacote/dependências, assinatura/aceitação Samsung (SignerVer03,
chave e vbmeta pai), KMI e política runtime. A0 permanece aberto; A1 não
começou e nenhuma operação foi feita no aparelho.
