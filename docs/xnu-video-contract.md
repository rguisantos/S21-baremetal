# XNU com vídeo: contrato e reserva do framebuffer no QEMU

Em **2026-10-23**, o loader do laboratório entregou vídeo ao XNU e a
execução completou PID 1/UID 0, leitura APFS, timer e retorno normal.
Foram **25 critérios positivos com vídeo**, **22 sem display**, três
recusas antes da cópia do kernel e **62 testes de host**. O kernel é o
prebuilt HackiOS identificado por hash; o EFI e o init são compilados.

O ensaio anterior de [ramfb](xnu-ramfb-audit.md) desenhava um padrão no EFI
e estacionava antes do kernel. Este ensaio captura o contrato já na entrada
`arm_init` do XNU, depois retoma a execução e observa o driver do kernel.
Não inclui userland iOS, SpringBoard, input ou execução no S21.

## Contrato observado

A captura por GDB foi somente leitura, com breakpoint em
`0xfffffff007453994` do kernel fixado. Foram lidos os registradores, os
736 bytes apontados por x0 e a árvore Apple completa, reemitidos sem
alteração. O formato LP64 de seis campos segue o
[header Apple já conferido](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/pexpert/pexpert/arm64/boot.h).

| Campo/intervalo | Valor observado |
|---|---|
| `v_baseAddr` | `0x1bdced000` |
| `v_display` | 1, modo gráfico |
| `v_rowBytes` | 4500 |
| `v_width`, `v_height` | 1125, 2436 |
| `v_depth` | 32 |
| Formato configurado no ramfb | XR24, bytes B/G/R/ignorado |
| Bytes de pixels | 10.962.000 |
| Reserva arredondada a páginas UEFI de 4096 bytes | 10.964.992 (`0xa75000`) |
| Janela XNU, fim exclusivo | `[0xf4000000, 0x1bc000000)` |
| Payload de entrada | `[0xf0000000, 0xf4000000)` |

Depois da retomada, o próprio kernel registrou:

```text
MiniIOMobileFramebuffer: display 1125x2436 on a panel of 1125x2436 (4500 bytes per row)
```

O screendump PNG em `arm_init` tem as mesmas dimensões. Ele é preto:
o ensaio usa modo gráfico e nosso init de testes, sem compositor iOS.
A captura não foi apresentada como tela de bloqueio ou app.

## Como a memória é conferida

O binding do framebuffer é registrado imediatamente após a conclusão
bem-sucedida do ramfb, conservando endereço e tamanho da alocação EFI.
O guard nativo exige a geometria fixa do perfil e a igualdade desse
binding com `SCREEN`. Antes da cópia e no mapa final usado no handoff,
exige cobertura integral como `EfiLoaderData`, atributos permitidos e
separação do payload/janela do kernel. Os seis campos de `boot_args`
também são conferidos antes do salto.

O verificador Python independente cruza o binding, os argumentos
capturados e **todos os quatro mapas completos**: o framebuffer já estava
alocado antes do primeiro deles e continua coberto nos demais. Inclui a
última página arredondada, não apenas o intervalo dos pixels. A janela
XNU é selecionada em memória convencional, portanto essa reserva limita
seu tamanho em comparação com o laboratório sem vídeo.

Isso comprova consistência e propriedade reportada pela UEFI nesse
ensaio. Não demonstra acesso de um display físico, coerência de caches
Samsung, preservação antes da entrada no EFI ou memória após reset.
A UEFI continua residente; não há `ExitBootServices`.

O perfil sem display continua sendo o padrão de
`boot_contract.validate_profile`: vídeo não zerado exige uma declaração
explícita. O caminho de memória só fornece essa declaração após conferir
os mapas. Não foram liberados modos arbitrários, GOP de fallback, rotação,
scale, profundidades alternativas ou `-v`.

## Controles e arquivos

| Cenário | Resultado |
|---|---|
| Vídeo correto | Captura em EL1, 25 critérios, driver framebuffer, init/APFS/timer/retorno |
| Sem display | Mesmo builder, 22 critérios; vídeo zerado preservado |
| Stride incrementado em um byte | Recusa no estágio anterior à cópia |
| `SCREEN.base` substituída pelo endereço do payload | Recusa por contrato/binding inválido, antes da cópia |
| Uma página do framebuffer devolvida e reservada como BootServicesData | API UEFI real retorna sucesso; ownership recusado antes da cópia |

As injeções usam builds separados `S21_VIDEO_TEST=1/2/3`; o normal usa 0.
Os 12 testes novos confrontam o C ligado ao EFI com o decoder Python e
exercitam geometria, limites, overflow, modos, arredondamento, mapas,
atributos, sobreposição e a exigência explícita de vídeo. Reexecutados os
28 testes do contrato e os 22 de memória; estes últimos incluem o guard de
memória C com ASan/UBSan.

Uma tentativa anterior encerrou após o banner UEFI, sem chegar ao loader,
mesmo com saída de processo 0. O harness a recusou por ausência da alocação;
[o log incompleto](references/xnu-video-incomplete-startup-20261023.txt)
foi preservado. A causa não foi estabelecida. Os cinco cenários finais
foram executados em invocações separadas, com ESP/NVRAM novas e evidência
completa. Não há retry automático que converta uma inicialização vazia em PASS.
Dois logs de controles paralelos também divergiram dos hashes registrados;
foram descartados como evidência e os controles repetidos sequencialmente.
Os hashes dos arquivos publicados e dos mapas reconstruídos foram conferidos.

- [Manifesto com comandos, builds, hashes e resultados](references/xnu-video-20261023.json).
- [Serial positivo completo, incluindo os quatro mapas](references/xnu-video-positive-20261023.txt).
- [boot_args capturados](references/xnu-video-boot-args-20261023.bin) e
  [árvore Apple capturada](references/xnu-video-apple-tree-20261023.bin).
- [PNG real em arm_init](references/xnu-video-arm-init-20261023.png).
- [Saída dos testes de host](references/xnu-video-host-tests-20261023.txt).

## Reprodução e próximo marco

Usar as fontes fixadas, baseline positivo e dependências do
[laboratório EFI](xnu-efi-adapter-lab.md). Não é necessário IPSW para estes
casos. O positivo usa GDB stdio e QMP por named pipes; não precisa de
socket/rede do host. Cada invocação aceita um único cenário:

```sh
python3 scripts/test_xnu_video.py
for scenario in positive headless stride input-overlap page-busy; do
  python3 scripts/run_xnu_video_lab.py \
    --case "$scenario" \
    --kernel-tree /caminho/hackios-xnu-kernel \
    --llvm-root /caminho/llvm-extraido \
    --lab-run /caminho/baseline-positivo \
    --efi-code /caminho/AAVMF_CODE.no-secboot.fd \
    --efi-vars /caminho/AAVMF_VARS.fd \
    --out "/caminho/nova-execucao-$scenario" || break
done
```

O marco gráfico seguinte foi [reproduzido no laboratório de referência](hackios-userland-qemu.md):
launchd → backboardd → SpringBoard, com Ajustes/Geral/Sobre respondendo a
toques e capturas nativas. Esse ensaio usa o ABI upstream da imagem de
sistema residente; a [integração ao consumidor EFI restrito](xnu-resident-contract.md)
agora cobre uma imagem residente de 4 MiB, reservas e recusas com init
próprio. O [perfil de userland completo](xnu-guarded-userland.md) também foi
executado, com mapas/boot_args conferidos e interação gráfica em uma CPU. O port
Exynos e a escolha Android/XNU no telefone dependem dos marcos físicos.
