# Kernel Exynos 2100: branch pública rebased-11

Repositório indicado pelo usuário, consultado em **2026-10-24 (Campo Grande)**:
[xfwdrev/android_kernel_samsung_ex2100, rebased-11](https://github.com/xfwdrev/android_kernel_samsung_ex2100/tree/rebased-11).
Revisão fixada **756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0**, de
2026-10-19 UTC; árvore `3cb6380ea1348c26fc4eeea0d4562dedba88e0e0`.
Foram lidos 15 arquivos selecionados, sem executar os scripts de build.
[Hashes, configurações e resultados do host](references/xfwdrev-rebased-11-20261024.json).

## O que esta branch oferece

O [Makefile fixado](https://github.com/xfwdrev/android_kernel_samsung_ex2100/blob/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0/Makefile)
declara **Linux 5.4.304-openela**. A configuração base usa o nome
`-ChicletKernel`; `p3s.config` acrescenta `CONFIG_MODEL_P3S=y` e recursos do
Galaxy S21 Ultra. O nome `rebased-11` não identifica sozinho a versão
Android compatível, e essa árvore modificada não foi identificada como o
kernel stock HZC2 5.4.242.

O [build.sh](https://github.com/xfwdrev/android_kernel_samsung_ex2100/blob/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0/build.sh)
seleciona `p3s` e combina `exynos2100_defconfig` com `p3s.config` e
fragmentos opcionais de recovery/KernelSU/SuSFS. Configura Clang r614150,
LLVM/IAS, saída em `out`, DTB/DTBO e boot/vendor_boot header v3. O fluxo
declara OS_VERSION 16.0.0 e patch level 2025-11: são metadados do
empacotamento, sem ensaio de compatibilidade Android 15/16 nesta análise.
Há submódulos para mkbootimg e KernelSU-Next. Compilação completa,
dependências e imagens resultantes continuam sem validação nesta etapa.

O outro script, `build_kernel.sh`, ainda chama
`exynos2100-t2sxxx_defconfig`, ausente na listagem fixada de configs; não
é o fluxo p3s usado por `build.sh`. O README_Kernel recebido menciona um
defconfig p3sxxx e toolchains antigos, enquanto README_Platform trata de
módulos Android 15. Não aplicar essas instruções automaticamente à árvore
reorganizada. Ambos os anexos foram relidos, preservando os originais.

## Comparação com a referência Samsung recebida

Os hashes anteriores vêm de [samsung-reference](samsung-reference.md) e
[dts-source-roundtrip](dts-source-roundtrip.md). O TAR completo não precisou
ser recuperado novamente. A comparação é byte a byte por SHA-256, sem
atribuir equivalência funcional aos arquivos que diferem.

| Arquivo | Resultado na branch pública | Implicação |
|---|---|---|
| `exynos_tty.c` | Idêntico ao recebido | Confirma a mesma implementação UART já analisada; não revela novo roteamento físico |
| `exynos2100-universal2100_rev11.dts` | Idêntico ao recebido | Conserva a referência genérica, distinta dos overlays p3s |
| `exynos2100.dts` | Diferente: 501932 bytes contra 495720 | A base pública modificada não substitui a base stock comprovada |
| `irq-gic-v3.c`, `exynos_mct.c` e `Makefile` | Diferentes | Registrar a revisão ao consultar drivers; sem auditoria completa desses diffs nesta entrega |

As três listas `/ems/pe-list/list@{0,1,2}/cpus` já usam strings separadas
sem os escapes octais ambíguos encontrados no pacote recebido. Não foi
necessário editar nenhum dos DTS consultados para as compilações abaixo.

## DTS compilados e overlays aplicados no host

DTC **1.7.2**, `-a 4`; aplicação com fdtoverlay **1.7.2** e leitura pelo
parser estrito existente `scripts/inspect_proton.py:fdt_nodes`.
Os três DTS compilaram e as duas aplicações de overlay passaram. Há
avisos herdados de bindings/phandles, contados por categoria no JSON;
compilação bem-sucedida não significa validação de todos os bindings.

| Artefato do host | Bytes | Nós | UART0 | UART1 | Nós RAM |
|---|---:|---:|---|---|---:|
| Base pública | 393452 | 2292 | disabled | disabled | 0 |
| Base + UNIVERSAL2100 rev11 | 545541 | 3354 | okay | disabled | 0 |
| Base + P3S EUR r22 | 637728 | 3830 | okay | okay | 0 |

A base compilada tem SHA-256
`15ee3a4771ede368d9b5aee1ab40f587f59c413ddfd41e70247f5f2801eb37c1`;
difere da base HZC2 de 389876 bytes, SHA-256
`d75cd25518112ec3a64235497b33f2caf84d60e8080b92c17ef98774c439aa2d`.
O overlay genérico, compilado aqui também com `-a 4`, tem um byte extra de
padding em relação à compilação anterior com alinhamento padrão; sua fonte
é idêntica. Não comparar esses hashes como se as opções fossem iguais.

O `p3s_eur_openx_w01_r22.dts` declara faixa DTBO **0x16–0x20**,
também presente no `build/dtconfigs/p3s.cfg`. Isso não identifica a revisão
física do aparelho. GICD/GICR continuam em 0x10200000/0x10240000, timer
arquitetural mantém o PPI físico NS 14 (INTID 30), PSCI usa `smc` e UART0
continua declarada em 0x10540000, debug 115200/8.

Ambos os merges conservam chosen initrd 0x84000000–0x841fffff e não
produzem nós `device_type=memory`. Reservas estáticas e alocações por
`size` continuam sendo declarações, sem provar bancos, RAM livre ou o FDT
final após os ajustes do LK. O overlay aplicado no host não executa a
UFDT Samsung, o kernel ou a inicialização de clocks/pads.

## Utilidade para a próxima etapa

Na configuração base consultada, `CONFIG_KEXEC`, `CONFIG_KEXEC_FILE`,
`CONFIG_CRASH_DUMP` e `CONFIG_DEVMEM` estão desativados.
`CONFIG_SERIAL_SAMSUNG_CONSOLE`, `CONFIG_PSTORE`, `CONFIG_PSTORE_RAM` e
`CONFIG_DEBUG_SNAPSHOT_BUILT_IN` estão ativos; DEBUG_SNAPSHOT e TZDEV são
módulos. Esses valores são declarações da fonte, sem `.config` gerada ou
imagem executada conferida. `CONFIG_UH` desativado nessa configuração não
prova controle de EL2 nem desativação do Harx/monitor no firmware.

**Aplicação proposta:** usar a árvore fixada como candidata para um kernel
Android de diagnóstico que registre o FDT recebido e as faixas/reservas
efetivas, após validar o build p3s e seu caminho de instalação/recuperação.
Isso pode alimentar as lacunas do contrato físico com observações. A
persistência e a leitura por pstore/debug-snapshot ainda precisam de
ensaio próprio; não são um canal já demonstrado pelo simples config.
O estado EL observado por Linux não substitui o registro da entrada de um
payload posterior nem garante passagem EL2 por kexec.

Na frente bare-metal, permanecem os próximos passos do
[roadmap](roadmap.md): produtores reais do registro BL2 em 0x02073600,
FDT final, propriedade/coerência da imagem e recuperação do primeiro
diagnóstico. Esta consulta não recuperou o produtor BL2 ou o handler SVC.
Nenhum kernel completo, firmware ou payload foi executado no telefone.

## Reprodução mínima

Com um checkout externo na revisão fixada e DTC/fdtoverlay 1.7.2 no PATH,
na raiz desse checkout, use um diretório de saída separado:

```bash
XFWDREV_AUDIT_DIR=$(mktemp -d)
dtc -I dts -O dtb -a 4 -o "$XFWDREV_AUDIT_DIR/base.dtb" \
  arch/arm64/boot/dts/exynos/exynos2100.dts
dtc -I dts -O dtb -a 4 -o "$XFWDREV_AUDIT_DIR/generic.dtbo" \
  arch/arm64/boot/dts/exynos/exynos2100-universal2100_rev11.dts
dtc -I dts -O dtb -a 4 -o "$XFWDREV_AUDIT_DIR/p3s-r22.dtbo" \
  arch/arm64/boot/dts/samsung/p3s/p3s_eur_openx_w01_r22.dts
fdtoverlay -i "$XFWDREV_AUDIT_DIR/base.dtb" \
  -o "$XFWDREV_AUDIT_DIR/merged-generic.dtb" "$XFWDREV_AUDIT_DIR/generic.dtbo"
fdtoverlay -i "$XFWDREV_AUDIT_DIR/base.dtb" \
  -o "$XFWDREV_AUDIT_DIR/merged-p3s-r22.dtb" "$XFWDREV_AUDIT_DIR/p3s-r22.dtbo"
sha256sum "$XFWDREV_AUDIT_DIR/"*.dtb "$XFWDREV_AUDIT_DIR/"*.dtbo
```

Os pacotes DTC/libfdt/libc já disponíveis foram extraídos fora do checkout
e invocados por seu loader. Não se alteraram dependências versionadas.
As fontes externas e DTBs gerados também ficaram fora do Git; o relatório
preserva tamanho, SHA-256, identidade de blob Git e propriedades selecionadas.
