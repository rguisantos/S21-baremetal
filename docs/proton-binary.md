# ProtonPlus v6.1.0: inspeção do ZIP publicado

Inspeção realizada em 2026-10-20 (fuso America/Campo_Grande), após o ambiente de execução voltar. O ZIP foi baixado da [release pública v6.1.0](https://github.com/ProtonKernel/Proton/releases/tag/v6.1.0), sem executar seus arquivos. Não foi feita comparação byte a byte com o upload anterior, que não está no workspace reconstruído.

Arquivo: `ProtonPlus-v6.1.0-KSU-exynos2100-20260125-1906.zip`, **34.652.394 bytes**. SHA-256 **3b86a4f0ca1fcf8ac06372a2af27bb0b0b9ca413e3da3b0c055629b087e9c982**, igual ao digest informado pela API GitHub da release.

## Image é Linux com EFI stub

A Image contém simultaneamente o magic ARM64 `ARMd` no offset 0x38 e cabeçalho PE AArch64 (machine 0xaa64, subsystem 10/EFI Application), com assinatura MZ. A string incorporada identifica **Linux 5.4.302-ProtonPlus-v6.1.0**. Isso é uma Image Linux com suporte EFI; classificá-la como “Windows PE, portanto não Linux” está errado.

| Campo | Valor extraído |
|---|---|
| Tamanho em arquivo | 34.777.600 bytes |
| text_offset | 0x80000 |
| image_size | 0x2413000 |
| flags | 0xa |
| SHA-256 Image | 23f5332017f957689fbc944b0e048e941b5fdc253c281a1b5fcb6099ba484cb3 |

Header PE não comprova que o Samsung use UEFI para carregar essa imagem. Da mesma forma, a aceitação dessa Image não comprova que um ELF arbitrário ou o shim atual seja aceito.

## vendor_boot e FDT

| Campo | Valor extraído |
|---|---|
| vendor_boot.img | 15.443.968 bytes; header v3; páginas 2048 |
| kernel_addr do header | 0x10008000 |
| ramdisk_addr do header | 0x11000000 |
| dtb_addr do header | 0x11f00000 |
| Região DTB | 389.947 bytes; tabela Android de 64 bytes antes do FDT |
| FDT bruto | 389.883 bytes |
| SHA-256 vendor_boot | e397d4235f90b7ebd519780da678883de204eb22665d8d73ca70eb0875557234 |
| SHA-256 FDT | ef1d8bfe7a4c9639298e441c9b11dc65f45b48cb1797e92a09f7ebb697898be2 |

Esses campos do Proton correspondem aos defaults do mkbootimg consultado e diferem dos headers stock HZC2 já registrados. Continuam sendo campos do contêiner, não observações do PC ou ponteiro FDT final.

O parser C de produção aceitou esse DTB e identificou GICD=0x10200000, GICR=0x10240000 com tamanho 0x200000, MPIDRs 0x000..0x700 em passos de 0x100 e timer físico NS **PPI 14 = INTID 30**. “PPI 30” é nomenclatura incorreta: 30 é o INTID completo. UART1 está disabled no FDT base, SPI 533 = INTID 565; status pode ser alterado por overlays/firmware e não demonstra clocks ou USI prontos.

Não há nós memory. A política de boot retornou **-4/NO_RAM**, e o parser também marcou reservas não resolvidas. O DTB não autoriza declarar uma janela de 2 GB livre para o payload.

Em `/chosen`, initrd-start é 0x84000000 e initrd-end é **0x841fffff**. O [consumidor Linux](https://github.com/torvalds/linux/blob/v5.4/drivers/of/fdt.c) calcula phys_initrd_size=end-start, portanto initrd-end é exclusivo: a diferença é **0x1fffff bytes**, não exatamente 2 MiB. Não se deve corrigir silenciosamente esse valor ou inferir a posição real/tamanho do initrd final a partir do DTB estático. O tamanho do ramdisk vendor é outro campo, sem equivalência automática com esse intervalo escolhido.

Os bootargs incluem clocksource=arch_sys_counter e nr_cpus=8. São parâmetros Linux; eles não habilitam acesso CNTP, demonstram a topologia por si sós ou configuram o timer do R10. Endereços estáticos confirmados não fecham EL, caches, RAM, framebuffer ou handoff.

## Instalador incluído

anykernel.sh extraído tem 3.697 bytes e SHA-256 **5b1cc0ce1c06e5d90b5b7bd8411b52b9975fad5ad87f0a18b99961a72e5f493d**. Contém split_boot, flash_boot e flash_generic vendor_boot, coerente com a análise de fonte. Esse hash identifica os bytes do script; não atribui sozinho um SHA Git ao checkout AnyKernel usado no build.

## Reprodução sem instalar

```bash
python3 scripts/inspect_proton.py /caminho/ProtonPlus-v6.1.0-KSU-exynos2100-20260125-1906.zip
```

O script usa Python padrão, limita tamanhos e lê apenas Image/vendor_boot.img/anykernel.sh sem extrair caminhos do ZIP ou executar código do pacote. Produz JSON com hashes, headers e propriedades selecionadas do FDT. Os testes incluem uma fixture independente com os dois headers e rejeição de componentes truncados.

O relatório colado pelo usuário referencia o branch kilo/slim-fjord-u2q. Comparado com a main atual, esse branch parte de um estado anterior e omite correções e evidências posteriores. Suas conclusões de “pronto para chainload” e comandos fastboot/Odin não foram adotados. A integração preservou a main e corrigiu as evidências acima, sem mesclar regressões.

O empacotador e a quarentena do shim estão documentados em [payload-format.md](payload-format.md). Não houve flash, chamada ao bootloader do telefone ou teste de GPU nesta análise.
