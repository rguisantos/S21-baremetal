# FlopKernel Exynos 2100: utilidade para o projeto e referência RPMB

O repositório indicado pelo usuário é útil como referência de drivers e
placas do Exynos2100, incluindo `p3s`/S21 Ultra. O cruzamento desta etapa
confirma o layout RPMB usado para interpretar o [backend do LK](lk-rpmb-hzc2.md)
e entrega um leitor offline de um frame. Não identifica os callbacks do
LK nem fornece a implementação segura de MAC/nonce.

Revisão em30/10/2026, base do projeto `d60ea14d567a2fa34a2d0c66061511e6b0ed5895`
(PR #64). Fonte externa fixada em
[`4553117a5014928dff55595f46627e0d77bcf133`](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/tree/4553117a5014928dff55595f46627e0d77bcf133),
head de `floppy-main` no momento da consulta. A avaliação cobre os arquivos
listados, sem auditoria integral ou ensaio de boot desse kernel.

## O que a árvore oferece

| Área | Evidência na revisão fixada | Aplicação e limite |
|---|---|---|
| Versão | Makefile declara5.4.304 | Diferente do5.4.242 informado pelo aparelho e pelo pacote Samsung consultado anteriormente |
| Placa p3s | Makefile de overlays inclui r02,r16–r22; `build/dtconfigs/p3s.cfg` associa custom0/custom1 | Referência de seleção; não identifica o overlay ativo no telefone |
| Build principal | `do_build.sh` chama `build/ckbuild.sh`, cujo padrão é `exynos2100-unified_defconfig` | Esse caminho é distinto do `build_kernel.sh` auxiliar, que usa r9s |
| Armazenamento | `scsi_srpmb.c/.h` e UFS Exynos | Fornece layout, montagem do transporte e fronteira WSM/IRQ |
| Configuração | unified: `UFS_SRPMB=m`, `SCSI_UFS_EXYNOS=m`, `SCSI_UFS_EXYNOS_SRPMB=y` | Valores no defconfig consultado, sem inferir configuração final ou módulos carregados |
| Console/PSCI | `SERIAL_SAMSUNG=y`, `SERIAL_SAMSUNG_CONSOLE=y`, `ARM_PSCI_FW=y` | Presença de suporte; clocks, pinmux, método PSCI final e acesso físico seguem dependentes do contexto |

Fontes de placa/build: [overlays p3s](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/arch/arm64/boot/dts/exynos/samsung/p3s/Makefile),
[seleção p3s](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/build/dtconfigs/p3s.cfg),
[ckbuild](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/build/ckbuild.sh)
e [unified_defconfig](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/arch/arm64/configs/exynos2100-unified_defconfig).
O build principal também encadeia dependências, imagens, empacotamento e
upload. Os scripts foram lidos, sem execução. Sua existência não comprova
compatibilidade com a instalação HZC2 deste aparelho.

Os anexos README_Kernel/Platform foram relidos: o primeiro descreve
`exynos2100-p3sxxx_defconfig` com variáveis Android11/r; o segundo trata
módulos de plataforma Android15. Não equivalem ao fluxo unified do Flop.
Identidades e limites anteriores permanecem na [referência Samsung](samsung-reference.md).

## Layout confirmado com o compilador C do host

O [header RPMB](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/scsi_srpmb.h)
declara `struct rpmb_packet` com tipos u8/u16/u32. O probe compila apenas
essa declaração, com typedefs de largura fixa, e mede `sizeof`/`offsetof`:
512 bytes, com os intervalos abaixo. O
[driver](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/drivers/scsi/scsi_srpmb.c)
usa `swap_packet` para reverter todos os bytes. O LK HZC2 já tinha esse
mesmo padrão de reversão delimitado por GNU.

| Campo | Offset local | Bytes | Offset no frame transmitido |
|---|---:|---:|---:|
| request | 0 | 2 | 510 |
| result | 2 | 2 | 508 |
| count | 4 | 2 | 506 |
| address | 6 | 2 | 504 |
| write_counter | 8 | 4 | 500 |
| nonce | 12 | 16 | 484 |
| data | 28 | 256 | 228 |
| Key_MAC | 284 | 32 | 196 |
| stuff | 316 | 196 | 0 |

Intervalo invertido: início wire=512−offset_local−tamanho. Os escalares
locais little-endian tornam-se big-endian no frame; **as sequências de
bytes dos arrays também são invertidas**. O leitor conserva os hashes
na ordem transmitida para evitar atribuir aos arrays a ordem local.
Os284 bytes autenticados pelo helper do LK começam em228 e terminam
no fim do frame; os32 bytes de MAC estão fora desse intervalo, em196.

O frontend LK usa+28/+32 como ponteiro/quantidade antes de materializar
dados. Portanto, uma estrutura de512 bytes ainda contendo esses placeholders
não é automaticamente um frame recebido ou autenticado. A igualdade de
layout não demonstra que o LK e Linux usem a mesma implementação.

## Transporte Linux e monitor: fronteiras separadas

O `init_wsm` do driver Linux aloca memória coerente, obtém uma IRQ do DT,
prepara workqueue/handler e registra endereço DMA e hwirq com
SMC `0x82003811`. A IRQ marca `0xdcdc` e agenda o worker. O worker obtém
o dispositivo SCSI a partir de sda, seleciona o RPMB WLUN e monta CDBs
Security Protocol IN/OUT, protocolo `0xec`, específico1, comprimento em
bytes nos campos6..9. O [cabeçalho SCSI](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/include/scsi/scsi_proto.h)
define opcodes `0xa2`/`0xb5`.

O [DTS Exynos2100](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/arch/arm64/boot/dts/exynos/exynos2100.dts)
(blob `7d387b91fdfa3be7bc1b64b182fc86bc63392f3b`) contém UFS em
`0x13100000`, com tupla de IRQ `<0 0x10e 4>`, e `ufs-srpmb` com
compatible `samsung,ufs-srpmb` e IRQ `<0 0xe1 4>`. São propriedades da
fonte consultada, não uma leitura do FDT final do aparelho. Não usar
esses números como IRQ Linux já mapeada ou prova de acesso MMIO livre.

| Namespace | Valores na fonte/caminho selecionado |
|---|---|
| `Rpmb_Req.type` do worker Linux | 1 contador,2 escrita,3 leitura |
| `Rpmb_Req.cmd` do transporte Linux | 7 IN,8 OUT |
| Comando local do dispatcher LK | 2 contador,3 escrita,4 leitura;1 tem outro ramo |
| Frame de consulta de resultado | 5, preparado pelo worker e pelo LK em seus respectivos caminhos |
| Registro WSM Linux | SMC `0x82003811` |
| RNG no header Linux | SMC `0x82001012` |
| MAC/nonce selecionados no LK | SMC `0xc2001018`/`0xc200101c` |

As constantes de SMC vêm do
[header Exynos](https://github.com/FlopKernel-Series/flop_exynos2100_kernel/blob/4553117a5014928dff55595f46627e0d77bcf133/include/soc/samsung/exynos-smc.h).
Não se substituem IDs entre esses namespaces. Essa interface kernel não
revela o serviço MAC do LK nem seu fornecedor de chave.

Nos três ramos do worker, resultado RPMB não zero pode ser apenas
registrado antes de publicar `RPMB_PASSED`=`0xbaba`. Os testes de I/O
selecionados são `ret<0`, não `ret!=0`; o helper devolve o resultado SCSI.
Não se interpreta `0xbaba` como autenticação ou sucesso de toda operação.
O worker selecionado não calcula/compara HMAC; isso deixa a autenticação
fora desse corpo, sem identificar seu responsável seguro.

## Ferramentas entregues e reprodução

`inspect_rpmb_frame.py` aceita **um arquivo regular com exatamente512 bytes**.
Recusa bytes extras, FIFO e diretório; limita a leitura a513 bytes. Saída:
escalares, hashes de arrays/intervalo autenticado e flags de ausência de
autenticação, procedência, I/O e persistência comprovadas. Não contém
operações de dispositivo, chaves ou agregação de múltiplos frames.

```sh
python3 scripts/inspect_rpmb_frame.py /path/to/offline-frame.bin
python3 scripts/inspect_rpmb_frame.py /path/to/materialized-packet.bin --input-order local-materialized
python3 scripts/test_rpmb_frame.py -v
python3 scripts/test_flop_reference.py -v
```

O padrão é `wire`; a ordem não é detectada automaticamente. O modo
`local-materialized` é uma declaração do chamador, sem verificar a
história do buffer. Resultado u16 zero também não autoriza marcar
autenticação como comprovada.

`inspect_flop_reference.py` exige os19 arquivos do
[manifesto](references/flop-kernel-source-4553117.json), no mesmo layout
de diretórios da revisão fixada. Confere tamanho, SHA-256 e SHA-1 Git de
todos antes do probe C, lê constantes literais/configuração e compara
offsets do C com o leitor offline. Não executa Makefile, scripts de build
nem kernel. O parser de declaração/defines suporta só a gramática
delimitada; expressões, ponteiros e aliases não são avaliados.

```sh
python3 scripts/inspect_flop_reference.py /path/to/pinned-source > /tmp/flop-reference.json
cmp /tmp/flop-reference.json docs/references/flop-kernel-rpmb-4553117.json
```

A [fixture sintética](references/rpmb-frame-synthetic.json) conserva a comparação entre as duas ordens, sem captura de aparelho. São14 testes do leitor e12 da referência/probe, incluídos no CI. Há casos
de endianness, ordem dos arrays, limites, resultado zero sem autenticação,
recusa de fontes divergentes e alteração de largura rejeitada pelo C.
[Relatório reproduzido](references/flop-kernel-rpmb-4553117.json) e
[validação](references/flop-kernel-validation-20261030.json) registram a etapa.

O próximo trabalho no LK continua sendo ligar o registro de `scsirpmb`
aos métodos concretos e à origem dos gates. A referência Linux reduz a
ambiguidade de formato/transporte, sem fechar essa ligação. O projeto
segue sem contêiner aceito, memória de entrada/captura comprovada ou
diagnóstico executado no S21.
