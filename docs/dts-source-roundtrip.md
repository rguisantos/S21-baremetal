# DTS recebidos: recompilação e identidade com o DTB HZC2

Conferência concluída em **2026-10-22 (Campo Grande)**. Os dois DTS enviados
separadamente são idênticos aos membros correspondentes do `Kernel.tar.gz`
já recebido. Três listas de CPUs precisam de uma correção textual para
recompilação: escapes octais fundem o separador NUL com o primeiro dígito
da string seguinte. Com essas três alterações e DTC 1.7.2, alinhamento de
quatro bytes, o DTB base reproduz **todos os bytes do DTB stock HZC2**.

Isso fecha a identidade dessa base específica. Não identifica o FDT final
entregue pelo LK, a revisão física selecionada ou o mapa de RAM disponível.
Os anexos originais foram preservados; o patch se aplica a uma cópia.

## Origem e entradas

| Arquivo recebido | Bytes | SHA-256 |
|---|---:|---|
| `exynos2100.dts` | 495720 | `586ca56987bbaacce0a38ddaee8a852721caaaeb9096ada6bfde8bc8c0d88ca8` |
| `exynos2100-universal2100_rev11.dts` | 234843 | `e623b6edfe35d7714546f108cdd4ba6cea69d030bc087b7f9b2a32ea63afe43a` |

Ambos estão em `arch/arm64/boot/dts/exynos/` no pacote de SHA-256
`c5ad9994240e67ebdc40878c191be040bf30db398bc8513ea1f156eaebd86bf2`.
São representações DTS completas com phandles numéricos; a compilação
conferida não exigiu resolver includes de uma árvore kernel.

A referência binária é o DTB extraído de `vendor_boot.img`, offset
**0xb77040**. A imagem bruta recebida tem 67108864 bytes e SHA-256
`f5b18d6b18230702cef98d80f4543a0f452cddb5829310b3acdafd6d600a60b5`.
O transporte LZ4 foi consumido integralmente e a identidade bruta conferida.
Não se atribui por isso equivalência a todos os arquivos do pacote-fonte.

## Correção das três propriedades

Em `/ems/pe-list/list@0`, `list@1` e `list@2`, respectivamente, o original contém:

```dts
cpus = "0-3\04-6\07";
cpus = "4-6\07\00-3";
cpus = "7\04-6\00-3";
```

O compilador interpreta `\04` e `\07` como bytes octais, em vez de um NUL
seguido de `4` ou `7`. Na base stock, cada propriedade contém três strings
terminadas por NUL. A representação sem ambiguidade é:

```dts
cpus = "0-3", "4-6", "7";
cpus = "4-6", "7", "0-3";
cpus = "7", "4-6", "0-3";
```

O [patch](references/exynos2100-cpu-lists.patch) altera somente essas três
linhas. A árvore compilada sem correção tem os mesmos **2249 nós** da stock,
mas exatamente essas três propriedades diferem. A versão corrigida tem os
mesmos caminhos, propriedades e bytes completos, incluindo padding.
Não foi medido qualquer efeito no scheduler do telefone.

| Compilação com DTC 1.7.2 | Bytes | SHA-256 |
|---|---:|---|
| Base original, alinhamento padrão | 389863 | `ecf922db002ff7d546a33c0a0347c6f9bc33ce35d580a9377f695caff1dce4a4` |
| Base corrigida, `-a 4` | 389876 | `d75cd25518112ec3a64235497b33f2caf84d60e8080b92c17ef98774c439aa2d` |
| Base stock extraída | 389876 | `d75cd25518112ec3a64235497b33f2caf84d60e8080b92c17ef98774c439aa2d` |

### Reprodução a partir do anexo

Na raiz do S21-baremetal, com GNU patch e DTC **1.7.2** no PATH:

```bash
DTS_AUDIT_DIR=$(mktemp -d)
cp /caminho/exynos2100.dts "$DTS_AUDIT_DIR/exynos2100.dts"
patch -d "$DTS_AUDIT_DIR" -p1 \
  -i "$PWD/docs/references/exynos2100-cpu-lists.patch" \
  -o exynos2100-fixed.dts
dtc -I dts -O dtb -a 4 \
  -o "$DTS_AUDIT_DIR/exynos2100-fixed.dtb" \
  "$DTS_AUDIT_DIR/exynos2100-fixed.dts"
sha256sum "$DTS_AUDIT_DIR/exynos2100-fixed.dtb"
```

Os pacotes `device-tree-compiler_1.7.2-2+b1_amd64.deb`, `libfdt1` e `libc6`
já versionados em `tools/debs` permitem extrair as ferramentas sem root.
Nesta auditoria foram extraídos para um diretório separado, usando o loader
e as bibliotecas dessa extração; `libyaml` veio do host. Nenhum binário
versionado foi alterado. O parser estrito `inspect_proton.fdt_nodes` também
conferiu as árvores.

O compilador emite avisos herdados, incluindo clocks, endereços unitários e
phandles. A contagem por categoria consta no relatório. A identidade binária
da base não significa validação de todos os bindings ou ausência de avisos.

## UNIVERSAL2100 genérico e P3S são overlays diferentes

O segundo anexo declara `samsung,exynos2100`, `samsung,UNIVERSAL2100`,
`board_id=1` e `board_rev=0x11`. Esse valor é metadado do arquivo, não leitura
da revisão do aparelho. `__fixups__.serial_0` aponta a `fragment@24`, que
define `status=okay`; não há fixup `serial_1`. O fragmento de chosen acrescenta:

```text
console=ram androidboot.boot_devices=13100000.ufs pmic_info=0x3 ccic_info=0x1
```

Esse texto está em `bootargs_ext`. Aplicado à base stock com fdtoverlay
1.7.2, o overlay genérico habilita UART0 e conserva UART1 desabilitada.

Como referência de placa, também foi compilado o membro recebido
`arch/arm64/boot/dts/samsung/p3s/p3s_eur_openx_w01_r17.dts`
(373178 bytes, SHA-256
`85c8e16e77dc0a7c4f02407f5a2a01e52c467c34e1da73db8d7bcc6ae0ccb56a`).
Ele declara `SAMSUNG,P3S_EUR_OPENX`/`SAMSUNG,EXYNOS2100` e faixa de revisão
DTBO 0x11–0x11. A seleção efetiva pelo LK continua sem observação.

| Candidato aplicado à base stock no host | Nós | UART0 | UART1 | Nós de RAM |
|---|---:|---|---|---:|
| UNIVERSAL2100 rev11 do anexo | 3311 | okay | disabled | 0 |
| P3S r17 do pacote recebido | 3778 | okay | okay | 0 |

O genérico compilado tem 188467 bytes, SHA-256
`22d4c7ddf804377016e7aed0a65c768f14d290fda670502e7e2781f7d6923924`.
O P3S r17 compilado com `-a 4` tem 295844 bytes, SHA-256
`fd21d7c63617196ecc8e7ad2e12b12ea29ba3e6459981bfbc8f4ad4106303303`.
Este último **difere** do hash stock da entrada 2 de `dtbo.img`, de mesmo
tamanho: `6046fd7ea6b39824a217ea5696185002e8667130e765a21dbaf75d61a8924f2b`.
Essa referência vem do inventário binário já versionado; não foi feita nesta
etapa uma comparação das propriedades do overlay stock com o P3S-fonte.
Não estender a identidade comprovada da base ao overlay.

GIC, timer e método PSCI `smc` foram conservados nos candidatos. A aplicação
libfdt no host não executa a UFDT Samsung nem as escritas dinâmicas posteriores.
`status=okay` não demonstra clocks, pinmux ou acesso físico à UART.

## Reservas e initrd: por que ainda falta o FDT final

A base tem **46 descendentes** em `/reserved-memory`: 29 com `reg`, 16 com
`size` sem `reg` e um contêiner. Os dois candidatos aplicados continuam sem
nós RAM. O relatório conserva as propriedades em bytes, sem calcular uma
união de memória livre ou presumir endereços das alocações dinâmicas.

| Declaração na base | Valor |
|---|---|
| el3mon_reserve | base 0xbff80000, tamanho 0x80000 |
| s2mpu_table | base 0xc1800000, tamanho 0x800000 |
| seclog_mem | base 0xc3000000, tamanho 0x80000 |
| vfw_heap | tamanho 0x400000, alinhamento 0x10000; sem endereço `reg` |
| crypto_heap | tamanho 0x3000000, alinhamento 0x400000, `alloc-ranges` e `reusable`; sem `reg` |

Essas declarações não localizam código DRM descriptografado nem revelam os
retornos SEC_PGTBL. Nomes de heaps e lacunas entre reservas não autorizam o
endereço de carga do payload.

Os candidatos mantêm `/chosen` com initrd **0x84000000–0x841fffff**. O modelo
das cópias LK v3, aplicado às imagens stock com cenário de deslocamento zero,
produz **0x84080000–0x84ca12df**, com fim exclusivo. A checagem de chosen
recusou corretamente ambos os candidatos por esses valores antigos. Não se
editou o FDT para fazer a checagem passar: falta reproduzir/observar os ajustes
efetivos do carregador e os bancos RAM.

O [relatório JSON](references/dts-upload-hzc2.json) reúne hashes, diferenças,
avisos, reservas e as duas recusas esperadas. README, hardware, índice e
roadmap apontam para esta evidência. R8/R9/R10 não mudaram; suas suítes não
foram reexecutadas nesta etapa. Nenhum flash ou teste físico foi realizado.
