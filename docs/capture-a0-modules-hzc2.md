# A0 HZC2 — módulos stock e requisitos de CRC

Rodada de 01/11/2026, base `d7938fa`, após PR #77. Continuação do
[A0](capture-a0-hzc2.md) e da [análise KMI](capture-a0-kmi-hzc2.md).
**O conjunto de módulos do vendor ramdisk foi identificado; A0 permanece
aberto para build candidato e comparação.** Nenhuma operação no telefone.

## Insumo concreto recuperado

O `vendor_boot.img` original fixado nos [pins A0](references/capture-a0-pins-hzc2.json)
contém um ramdisk gzip de SHA-256
`2d926b819764ff7c985db7dc75d7a46152dc14ee3189f2c13c91123b5c807857`.
O CPIO descomprimido tem 55168256 bytes e SHA-256
`bd15253d911a94726950045075c55851158ea723d0396c964f8931392c025175`.
O parser lê o arquivo em memória, sem extrair caminhos ou seguir links.

| Observação no vendor ramdisk | Resultado |
|---|---:|
| Entradas CPIO, excluído o trailer | 296 |
| Arquivos `.ko` AArch64 ET_REL | **274** |
| Entradas de `modules.load` | 274; conjunto igual aos arquivos |
| Entradas de `modules.dep` | 274; todas as referências presentes |
| Registros de `__versions` | **13995** |
| Nomes distintos com CRC exigido | **2763** |
| Nomes com CRCs conflitantes entre consumidores | **0** |
| Consumidores de `module_layout` | 274; CRC `0x1e5b7ab7` |

Todos os módulos declaram o mesmo vermagic:

```text
5.4.242-30958140-abG998BXXSJHZC2 SMP preempt mod_unload modversions aarch64
```

Isso identifica arquivos reais do firmware, incluindo `ufs-exynos-core.ko`,
`dhd.ko`, `mali_kbase.ko` e `fimc-is.ko`. **Não é uma lista observada de
módulos carregados no aparelho.** A presença nas listas não prova execução,
ordem efetiva, resolução de símbolos ou sucesso de inicialização. O escopo
é esse vendor ramdisk, sem declarar inventariados outros módulos possíveis
em super/vendor, recovery ou outras partições.

## Origem e significado dos CRCs

O arquivo Samsung `Kernel.tar.gz` foi novamente conferido contra o hash
fixado. O relatório registra os hashes de cinco fontes utilizadas:

- `include/linux/module.h`, linhas 34–39: `modversion_info` contém CRC
  `unsigned long` e nome de tamanho `MODULE_NAME_LEN`.
- `include/linux/moduleparam.h`, linha 21: tamanho do nome é 64 menos o
  tamanho de `unsigned long`. No ELF64 AArch64 observado são registros de
  64 bytes: oito para o CRC e 56 para o nome. Os CRCs encontrados cabem em
  32 bits; não são hashes do arquivo `.ko`.
- `scripts/mod/modpost.c`, linhas 2315–2355: o gerador monta `__versions`
  a partir dos símbolos externos que têm fornecedor e CRC conhecido.
- `kernel/module.c`, linhas 1315–1394: o carregador compara a versão
  encontrada e trata `module_layout` separadamente. Há exceções e ramos de
  ausência de CRC; este inventário não simula o carregador completo.
- `include/linux/vermagic.h`, linhas 37–42: composição do vermagic.

Os 13995 registros são **requisitos embutidos nos consumidores stock**,
não CRCs recém-calculados de uma compilação candidata. A união de 2763
nomes não é um censo de todos os imports ELF, nem somente de símbolos
fornecidos por vmlinux: há dependências entre módulos. Não se transforma
ausência na whitelist KMI em incompatibilidade automaticamente.

GNU `readelf` 2.42, com `-x __versions`, recuperou os mesmos bytes de seção
nos 274 arquivos, independentemente do leitor ELF Python. Isso confirma a
extração; não compara os CRCs contra um kernel candidato.

O [relatório](references/capture-a0-modules-hzc2.json) publica hashes e
metadados por módulo, contagem/hash de sua seção de versões e a união dos
CRCs com número de consumidores. Não publica os módulos, ramdisk ou fontes
Samsung completos. Autores e outros campos livres de `.modinfo` não são
incluídos.

## Comparador para o próximo build

O [leitor](../scripts/capture_a0_modules.py) inclui uma comparação com
`Module.symvers`: nomes ausentes, CRCs diferentes e conflitos stock fazem
o critério de cobertura de CRC reprovar. Nomes duplicados ou linhas
malformadas no arquivo candidato são recusados; não há escolha silenciosa
de um fornecedor. A quarta coluna identifica o tipo de export; a quinta,
quando presente, é aceita como namespace, sem validar sua política.

É necessário fornecer o conjunto de exports correspondente à combinação
de kernel e módulos pretendida. Um arquivo contendo só exports de vmlinux
pode estar incompleto para os requisitos entre módulos. O comparador não
resolve fornecedores, permissões GPL/namespaces, CFI, relocação, assinatura
ou comportamento. **Mesmo cobertura de CRC completa não aprova ABI, boot
ou A0.** Neste relatório, nenhum `Module.symvers` candidato foi fornecido.

```sh
python3 scripts/test_capture_a0_modules.py
python3 scripts/check_capture_a0_modules.py \
  --vendor-boot /caminho/vendor_boot.img \
  --source /caminho/Kernel.tar.gz \
  --output build/modules-stock.json
```

Use o vendor_boot original descomprimido, não o repack reprovado. O runner
confere imagem e arquivo Samsung por tamanho/hash antes da análise; a
saída deve ser nova. Para comparar um build, acrescente
`--symvers /caminho/Module.symvers`. Retorno **2** indica comparação ausente
ou cobertura de CRC reprovada; **1**, erro/recusa; **0**, somente cobertura
de CRC aprovada, mantendo `a0_complete=false`.

O relatório foi reproduzido byte a byte. Os 25 testes novos incluem gzip
truncado/concatenado/expansão excessiva, caminhos/links CPIO, limites ELF,
CRC inválido/conflitante, listas e comparações sintéticas positivas e
negativas. Passaram junto dos 67 testes A0 anteriores e estão na CI.
[Validação da rodada](references/capture-a0-modules-validation-20261101.json).

## Próximo passo delimitado

O bloqueio já não é desconhecer os requisitos de versão desse conjunto
stock. Falta produzir o build p3s com o perfil completo, resolver os insumos
KMI pendentes e obter seus exports/Module.symvers para comparar estes CRCs.
LTO/CFI/compat32, interfaces e política de módulos continuam requisitos
separados. O [problema de contêiner](capture-a0-repack-extent-hzc2.md) também
permanece aberto para payload modificado. A1 não foi iniciado.
