# Firmware stock G998BXXSJHZC2: conferência das imagens recebidas

Data: 2026-10-20. O usuário identificou as três imagens como originais da mesma compilação usada no aparelho. A string interna do kernel confirma o identificador HZC2, versão e data abaixo. Não foi feita verificação criptográfica da assinatura de fábrica/AVB.

## Identificação do kernel

```
Linux version 5.4.242-30958140-abG998BXXSJHZC2
#1 SMP PREEMPT Mon Mar 9 19:18:41 KST 2026
Android clang 11.0.1 / r383902; LLD 11.0.1
```

## Imagens e cabeçalhos

| Campo | Valor extraído |
|---|---|
| boot.img | Android boot header v3; partição de 64 MiB |
| Kernel em boot.img | 29.469.184 bytes; Image AArch64, sem gzip externo |
| Ramdisk em boot.img | 701.558 bytes |
| Image.text_offset | 0x80000 |
| Image.image_size (inclui memória além do conteúdo carregado) | 0x2067000 |
| vendor_boot.img | Vendor boot header v3, páginas de 4096 bytes; 64 MiB |
| vendor_ramdisk_size | 12.017.257 bytes |
| vendor header kernel_addr | 0x80008000 — campo do cabeçalho, não prova do PC final |
| vendor header ramdisk_addr | 0x84000000 |
| vendor header dtb_addr | 0x81f00000 |
| Região DTB no vendor_boot | Offset 0xb77000, com tabela Android de 64 bytes antes do FDT |
| FDT base | Offset 0xb77040; 389.876 bytes; FDT v17 |
| dtbo.img | Partição de 8 MiB; tabela com 8 overlays |

O boot header anuncia OS 11.0.0 e patch 2026-01; isso é metadado do cabeçalho e não determina sozinho a versão Android instalada. Os cabeçalhos boot/vendor_boot contêm `androidboot.selinux=permissive loop.max_part=7`; isso também não prova o estado SELinux efetivo após o boot.

## Recursos confirmados no DTB

| Recurso | Valor |
|---|---|
| Células raiz | #address-cells=2, #size-cells=1 |
| GIC Distributor | 0x10200000, tamanho 0x10000 |
| GIC Redistributor | 0x10240000, região de 0x200000; sem redistributor-stride explícito |
| CPU MPIDRs | 0x000, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700 |
| PSCI | arm,psci-1.0; method=smc |
| Timer | arm,armv8-timer, use-physical-timer, 26 MHz |
| Timer físico NS | PPI 14: INTID 30 |
| UART1 | 0x10840000, tamanho 0x100; samsung,exynos-uart / USI v2 |
| UART1 IRQ | SPI 533: INTID 565 (533+32), não INTID 533 |

Todos os MPIDRs descritos têm Aff0=0. O índice lógico não pode ser obtido apenas de Aff0; isso invalida a antiga tabela SMP 0..7 e a seleção de secundárias por Aff0. A etapa atual em uma CPU já não usa esse critério na entrada primária ou na descoberta do GICR; o caminho SMP dormente ainda exige correção própria.

A UART está disabled no FDT base, mas os oito overlays foram aplicados individualmente com fdtoverlay e todos a tornam okay. Suas revisões cobrem 0x02..0x0f, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15 e 0x16..0x20. A classificação da revisão real ainda depende do aparelho. Nenhum desses overlays altera as regiões GIC ou os MPIDRs. `okay` não comprova clock/pinmux/USI inicializados no instante de entrada no payload.

## O que ainda depende do estado de execução

Nem o FDT base nem os oito FDTs resultantes têm nó device_type=memory. Existem reserved-memory, inclusive reservas acima de 4 GiB; não se deve deduzir que toda a RAM é baixa, contígua ou livre. O bootloader precisa fornecer/completar a descrição em execução. Os dados de memória não podem ser inventados a partir de /chosen.

Essas imagens não provam o EL de entrada, estado SCTLR/caches/GIC, acesso ao timer, registros de Harx ou o FDT efetivamente entregue após os ajustes do bootloader. O DTB ativo continua sendo a fonte para esse estado descritivo final. Não houve flash ou execução no telefone.

Platform.tar.gz foi inventariado: 12.274 arquivos, principalmente external/libcore/vendor/art/system. É fonte de plataforma; não fornece por si só o contrato de entrada do bootloader.

## SHA-256 das entradas e imagens descompactadas

| Imagem | SHA-256 LZ4 recebido | SHA-256 descompactado |
|---|---|
| `boot.img` | `cb5f76269c71f5d643afdcda57ff1561b708b9fcb724876b59b0d407abb3477e` | `28818995d6c3060df19602a0104c2c7dac9861f31f2620f9dab8466e6cdf51a1` |
| `vendor_boot.img` | `179c36e8fbcd9163f800dd9ab5a169cbbed702f1390bd45f05ed602b3916e736` | `f5b18d6b18230702cef98d80f4543a0f452cddb5829310b3acdafd6d600a60b5` |
| `dtbo.img` | `d2887b046ae6d533a8be830f30a483b6bc80cde772a07623573f6582ce24b672` | `f7c96bf0fb7dc67c82c05c7ed02cc74aa40e5f1f8ae68f2b6b47cc38e556dd34` |

A descompressão usou liblz4/LZ4F com verificação de erros e consumo completo do frame. Cabeçalhos Android foram interpretados conforme sua versão; a região DTB foi separada da tabela que a encapsula. Os resultados acima substituem afirmações conflitantes da documentação antiga, especialmente kernel ausente, UART sempre disabled, MPIDR 0..7 e IRQ UART 533 como INTID.
