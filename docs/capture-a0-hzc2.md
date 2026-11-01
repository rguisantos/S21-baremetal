# A0 HZC2: fonte candidata e integridade do contêiner stock

Rodada de 31/10/2026, Campo Grande, base `ce93eb1` após PR #74.
Continuação offline da [proposta cooperativa](marco-a-carga-captura-recuperacao.md).
**A0 parcial e bloqueado; A1 não iniciado e nenhum pacote para o telefone.**

A fonte Samsung recuperada declara Linux **5.4.242** e o defconfig p3s
difere da configuração embutida no kernel stock em apenas dois campos.
O Clang **11.0.1/r383902, build 6443078** correspondente foi identificado,
fixado e executado no host. Isso seleciona uma candidata concreta, sem provar
equivalência binária ou compatibilidade de módulos.

O ensaio de pacote encontrou um bloqueio: **magiskboot v30.7 reprova o
round-trip sem alterações** de boot e vendor_boot. Os componentes principais
ficam iguais, mas bytes opacos e rodapés mudam; os hashes AVB deixam de conferir.
Não se aceita esse resultado como pacote compatível, mesmo com OEM desbloqueado.

## Insumos e proveniência

Os [pins completos](references/capture-a0-pins-hzc2.json) registram tamanhos,
SHA-256, revisões e nove membros selecionados do arquivo Samsung. Firmware,
ramdisks, configuração com caminhos do host de build e dependências binárias
permanecem fora do Git. O [inventário anterior](stock-firmware-hzc2.md) fornece
o contexto dos arquivos stock; esta rodada verifica novamente seus hashes.

| Insumo | Identidade fixada |
|---|---|
| Firmware | G998BXXSJHZC2, boot/vendor_boot de 64 MiB e dtbo de 8 MiB após descompressão |
| Fonte Samsung recebida | `Kernel.tar.gz`, 209261574 bytes, SHA-256 `c5ad9994240e67ebdc40878c191be040bf30db398bc8513ea1f156eaebd86bf2` |
| Configuração candidata | `arch/arm64/configs/exynos2100-p3sxxx_defconfig`, SHA-256 `e0d7cfe4c8fceb31a5e44a9ba916c00338834a58011a44494e15120efe76c4fd` |
| Configuração stock extraída por IKCONFIG | 203018 bytes, SHA-256 `55dde3bb7c52e99eccdb82b925a4b831c03fd32a19a2b64bdf7bda993e92a2e1` |
| Toolchain AOSP | commit `f71cc7fa68ac644595257d6fdebc2e543cb7041c`, diretório `clang-r383902`, árvore `34feae7abc38fffe258af1842a4c19746368cec6` |
| Magisk | tag v30.7, commit `e8a58776f1d7bdf852072ad0baa6eceb9a1e4aac`, asset oficial `app-debug.apk`; executável x86_64 conferido contra o APK |

A identidade do APK local coincide com o digest do asset na
[release oficial](https://github.com/topjohnwu/Magisk/releases/tag/v30.7).
O binário host é `lib/x86_64/libmagiskboot.so` dentro desse APK, com SHA-256
`39c5278f3e8dcac26a507f37c1a8db02c53472bc4702411dc455d67332763946`.
Não se executam instaladores Android, scripts de flash ou scripts legados de demo.
Em particular, `scripts/magiskboot/boot.img` é uma fixture sintética de 8192 bytes,
não a imagem stock desta rodada.

O [commit oficial do Clang](https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+/f71cc7fa68ac644595257d6fdebc2e543cb7041c)
identifica o build 6443078. O arquivo baixado e `clang`, `clang.real`, `ld.lld`
têm hashes registrados. `clang --version` corresponde ao texto de compilador
da configuração stock; um C freestanding produziu ELF AArch64 no host.
Esse smoke test não compila o kernel nem demonstra LTO/CFI/módulos funcionais.

## Fonte, configuração e perfil de build ainda incompleto

O Makefile do arquivo Samsung declara 5.4.242. A configuração stock foi
extraída do payload real do boot, validando os limites dos marcadores e gzip.
A comparação por chave CONFIG tem exatamente estas diferenças:

| Chave | Diferença observada | Consequência |
|---|---|---|
| `CONFIG_UNUSED_KSYMS_WHITELIST` | Caminho relativo na fonte; caminho absoluto de build no stock, com o mesmo sufixo `gki/abi_symbollist.raw` | Resolver o arquivo por conteúdo/hash, sem copiar o caminho privado |
| `CONFIG_KMI_SYMBOL_LISTS` | Presente no stock, ausente no defconfig recebido | Dependência real do perfil KMI; não presumir equivalência de exports/módulos |

O relatório publica nomes e hashes dos valores divergentes, sem os caminhos
do host de build. O arquivo `gki/abi_symbollist.raw` também foi recuperado e
fixado. LTO/CFI Clang, MODVERSIONS, TRIM_UNUSED_KSYMS e COMPAT_VDSO estão ativos.
Isso torna insuficiente substituir o compilador por qualquer GCC disponível
ou reaproveitar módulos stock apenas porque a versão nominal coincide.

O Makefile aponta para Clang r383902 e ferramentas GNU Android AArch64 4.9;
o perfil também precisa resolver a construção compat de 32 bits. O README
Samsung recebido prescreve `PLATFORM_VERSION=11`, `ANDROID_MAJOR_VERSION=r`
e `ARCH=arm64`. São instruções de fonte, sem prova de correspondência de
todo o build ao Android HZC2 instalado. A seleção completa de binutils,
ferramentas compat, KMI e módulos continua aberta. Não há `vmlinux` p3s novo.

O [FlopKernel fixado](flop-kernel-reference.md) continua referência auxiliar:
seu Makefile declara 5.4.304 e seu perfil usa Clang 23, diferentes desta
candidata Samsung. Nenhum build script Flop, downloader, opcional SU ou upload
foi executado. Não se promove essa árvore a reprodução do kernel HZC2.

## Continuação KMI — 01/11/2026

A [conferência das duas diferenças](capture-a0-kmi-hzc2.md) localizou o
consumidor da whitelist e delimitou a string KMI na árvore recebida. Duas
listas citadas no IKCONFIG não estão no arquivo; a união das 17 disponíveis
contém 4990 dos 5000 símbolos da whitelist candidata. Seis controles do gerador
original separam caminho, conteúdo, exports e layout de uma fixture host.
CRCs, estruturas reais e módulos p3s não foram comparados; a compatibilidade
não foi promovida. O bloqueio de contêiner descrito abaixo permanece.

## Entrada e prova de linker exigida antes de A1

Na fonte Samsung fixada, `arch/arm64/kernel/head.S` contém:

- Cabeçalho EFI nas linhas 73–74: `add x13,x18,#0x16` produz o opcode MZ;
  depois `b stext`. EFI está habilitado no config stock.
- `ENTRY(stext)` na linha 113; `bl preserve_boot_args` na 114;
  `bl el2_setup` na 115. O extrator confere esses anchors dentro da função
  primária, sem confundi-los com chamadas da entrada secundária.

Isso dá um candidato de inserção: redirecionar o branch primário do header
para instrumentação e continuar por branch no `stext` original, antes dessas
chamadas. **É um desenho futuro**, sem patch e sem endereço numérico final.
O ADD EFI já terá alterado X13; não se promete observar todos os registradores
como estavam antes do primeiro opcode da Image. Entradas secundárias/resume
não são incluídas por associação. Deslocamento ARM64, alcance dos branches,
relocações, CFI e continuação precisam de disassembly do artefato final.

O linker desta fonte delimita `__init_begin`/`__init_end`, dados retidos,
`.mmuoff.data.write/read`, `_edata`, `BSS_SECTION` e `_end`.
Esses símbolos orientam o desenho, mas **não comprovam a cápsula**.
O teste automatizado de A1 deverá abrir o ELF final e exigir:

1. Símbolo/tamanho da cápsula S21COOP1, seção carregada `SHT_PROGBITS`,
   flags e alinhamento exigidos, bytes iniciais efetivamente presentes na Image.
2. Ausência de sobreposição com BSS, init descartável e demais intervalos de
   zeragem/cópia; correspondência dos offsets entre ELF, mapa e Image emitida.
3. Retenção pelo linker, cobertura da extensão carregada e conservação ou
   migração demonstrada na relocação/KASLR; inicializar zero em C não basta.
4. Branches reais header→produtor→continuação e captura anterior à primeira
   mudança de EL/MMU/cache do caminho escolhido, além de preservação de estado.

Esses testes ainda não existem porque o produtor/ELF instrumentado não existe.
O relatório mantém `final_elf_checked=false` e `capture_implemented=false`.

## Round-trip real e controle de inventário

O [runner offline](../scripts/check_capture_a0.py) verifica todos os inputs
privados antes de executar o host tool, cria diretório novo e usa ambiente
reduzido a PATH/LC_ALL. Não habilita `PATCHVBMETAFLAG`. Faz `unpack -n -h`
e `repack -n`; o retorno 3 de unpack vendor é sucesso na versão fixada.

O parser independente cobre todos os bytes: headers, payloads, alinhamentos,
extensões opacas, vbmeta e rodapé. Confere os hash descriptors AVB como
hash de `salt || imagem[0:image_size]`, com bounds e extents separados.
O layout segue o
[AvbHashDescriptor oficial](https://android.googlesource.com/platform/external/avb/+/761178607206f4cb2af79ed9eec52d8cbd814adb/libavb/avb_hash_descriptor.h).
**Não verifica assinatura RSA, confiança da chave ou aceitação de boot.**

| Resultado sem trocar payload | boot | vendor_boot |
|---|---:|---:|
| Header e payloads idênticos | sim | sim |
| Blob vbmeta idêntico | sim | sim |
| Bytes diferentes no arquivo | 586 | 3474 |
| `original_image_size` antes→depois | 30180128→30179344 | 12415760→12414976 |
| Offset vbmeta antes→depois | 30183424→30183424 | 12419072→12414976 |
| Hash descriptor confere antes→depois | sim→não | sim→não |
| Gate de round-trip magiskboot | **FAIL** | **FAIL** |

O código fixado de [repack](https://github.com/topjohnwu/Magisk/blob/e8a58776f1d7bdf852072ad0baa6eceb9a1e4aac/native/src/boot/bootimg.cpp)
copia vbmeta e recalcula campos do footer, sem recomputar esses descriptors.
O ensaio também observa perda de bytes da extensão; não diz que o blob
vbmeta foi refeito/assinado. Em vendor_boot, o extent original do descriptor
passa a sobrepor o vbmeta movido. Desbloquear não torna esse resultado uma
reprodução íntegra do stock nem resolve a compatibilidade por si só.

Um controle separado reconstrói boot/vendor_boot/dtbo de todos os spans
inventariados, substituindo os payloads de boot/vendor pelos bytes de unpack
conferidos. Os três arquivos voltam **byte a byte iguais** aos originais,
com hashes AVB ainda válidos. Esse controle conserva explicitamente bytes
opacos: não é o repack Magisk aprovado, não aceita payload modificado e
não fornece um packer de kernel próprio. DTBO foi inventariado/reconstituído;
não foi submetido a `magiskboot repack`.

## Reprodução e próximo limite

Com os inputs locais correspondentes aos pins:

```sh
python3 scripts/test_capture_a0.py
python3 scripts/check_capture_a0.py \
  --stock-dir /caminho/stock \
  --source /caminho/Kernel.tar.gz \
  --magisk-apk /caminho/app-debug.apk \
  --output-dir build/capture-a0-novo
```

O segundo comando gera logs privados/imagens somente no diretório novo.
Retorna **2** quando a análise termina e o round-trip reprova; 1 significa
recusa/erro de análise. Não tratar o 2 esperado desta evidência como aprovação.
O [JSON publicado](references/capture-a0-stock-hzc2.json) foi reproduzido
byte a byte numa segunda execução. Os 32 testes sintéticos estão na CI;
a [validação da rodada](references/capture-a0-validation-20261031.json)
registra também a baseline de nove etapas e o smoke test do Clang.

A próxima entrega continua em **A0**: fechar o perfil de build/KMI/módulos
e uma estratégia de contêiner que passe o controle sem alterações antes
de admitir um payload modificado. A1 só avança com esses pré-requisitos;
o ELF final será seu próprio gate. Ramdisk/política e instalação/restauração
continuam pendentes; recovery/vbmeta stock separados não foram resolvidos
nesta rodada. Nenhum acesso negado no shell foi repetido. A decisão OEM e
as operações no aparelho continuam fora desta execução offline.

## Continuação — repetibilidade e cobertura AVB, 01/11/2026

A [análise delimitada do repack](capture-a0-repack-extent-hzc2.md) reproduziu saídas idênticas em três processos por imagem, alterando os mtimes dos arquivos extraídos. A extensão omitida está dentro do hash, mas o rodapé AVB está fora. As diferenças internas são 584 bytes em boot e 651 em vendor_boot; os demais bytes alterados ficam fora. O controle sem alterações exige preservação integral; payload modificado exige metadados coerentes e rota de aceitação demonstrada. A0 continua aberto.
