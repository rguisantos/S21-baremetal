# Wi-Fi do SM-G998B p3s no HZC2

## Identidade observada no Android ZTO

Na seção STA Chip Information do [dumpstate de 27/10](bugreport-boot-hzc2.md),
linhas 994065–994070 do membro principal (LF), o próprio diagnóstico Wi-Fi
informa CID `semco_sem_e53_es40`, DHD 101.18.65, firmware 20.80.87.4
(r1074309, C1, FWID 01-3fe70789), NVRAM SEMCO SWB-E53(4389c1) ES4.0
module_201116 e CLM Samsung.P3LSI240816. A identificação se aplica ao
aparelho coletado. Outras revisões de módulo requerem sua própria seleção.

## Arquivos correspondentes em vendor

Na [imagem HZC2 XEO de referência](a0-vendor-modules-hzc2.md), os arquivos
abaixo ficam em /vendor/firmware/wifi. A tabela bcm4389_naming_table do
dhd_custom_cis.c Samsung associa e53_es40 aos sufixos _ES40_semco_c1 e _c1.
O diretório contém três firmwares STA. Lendo o campo FW-TAG, o arquivo sem
sufixo identifica 4389b0 (20.30.5), _c0 identifica 4389c0 (20.80.56.2) e
_c1 contém o FWID, a revisão e a versão do diagnóstico. O comentário do
arquivo NVRAM coincide com Nv_info. O CLM contém os textos Samsung.P3LSI
e V26_201030(240816). Os hashes fixam os arquivos da imagem XEO. O Android
ZTO reporta os identificadores de execução, sem fornecer hashes dos arquivos.

| Nome | Bytes | SHA-256 |
|---|---:|---|
| bcmdhd_sta.bin_c1 | 1528114 | 234e3abe763343689ca8026003b87c80565cca7d08be56850d723b34a60f7e71 |
| nvram.txt_ES40_semco_c1 | 18005 | bb111969049ad8a4243cbac88d36748a645d6fea2ce813dd607cfbae1ffde071 |
| bcmdhd_clm.blob | 57440 | d52bc311084ebfbfaf45ee2d483bf9de43438f6ef89e2cb43afa7d9d2300ce4c |

## Correção reproduzida no host

Na base do fork `1af89756d50efc5d82dd27e6bca830508745494f`, a função
brcmf_nvram calculava o padding contando um NUL adicional que não gravava.
O corpo terminava sempre com tamanho congruente a 3 módulo 4. Com a NVRAM
acima, retornava 13955 bytes incluindo o token. O corpo tinha 13951 bytes,
mas o contador descrevia 3487 palavras, ou 13948 bytes.

O [patch 0004](../lab/s21xnu-p3s/fork/0004-mkpayload-align-nvram.patch)
termina a última entrada e a lista, completa até quatro bytes e usa a
contagem exata de palavras no token little-endian. O mesmo arquivo produz
412 entradas, 13952 bytes no corpo e 13956 ao todo, com token 0xf25f0da0.
SHA-256 da saída: b527cf42f2af44b1c84af93e9c53e238633df2e2dba7f1db14dcb081a96f8b34.
O teste cobre as quatro posições possíveis do último terminador e a recusa
de contagem que não cabe em 16 bits. É o caminho de mkpayload para segmentos
Wi-Fi opcionais. O driver integrado por 0142 também descreve obtenção de
arquivos a partir do sistema de arquivos. A correção do empacotador, sozinha,
não comprova uso desses segmentos pelo candidato.

Para reproduzir, aplicar a série ao upstream fixado, executar
`python3 tools/test_mkpayload_nvram.py` e fornecer os bytes da NVRAM acima
a `tools/mkpayload.py:brcmf_nvram` em host. O verificador da série executa
o teste no clone temporário após git am.

## Limite atual do driver

O [contrato entre placas](xnu-s21xnu-p3s.md) identifica PCIe canal 0,
Gen2 no p3s. O driver Samsung compilado para o HZC2 é bcmdhd_101_18. Em
include/bcmdevs.h os valores são 0x4389 para o chip e 0x4441 para o
dispositivo PCI D11AX. Em dhd_pcie.c o ramo BCM4389 com núcleo CA7 usa
CA7_4389_RAM_BASE (0x200000 em include/sbchipc.h). Fonte Kernel.tar.gz
SHA-256 c5ad9994240e67ebdc40878c191be040bf30db398bc8513ea1f156eaebd86bf2.

No [0142 do fork](https://github.com/rguisantos/s21xnu/blob/1af89756d50efc5d82dd27e6bca830508745494f/xnu/patches/0142-s21-wifi.sh),
a identificação PCI exige 14e4:4475 e a rotina do chip é redwood_bcm4375_run.
O [0111](https://github.com/rguisantos/s21xnu/blob/1af89756d50efc5d82dd27e6bca830508745494f/xnu/patches/0111-sweet-pcie-wifi-firmware.patch)
também trata CR4 com base 0x170000. A primeira etapa verificável de um
driver p3s é distinguir o endpoint do p3s do 4375 na enumeração, antes
de qualquer carga de firmware. O ID esperado vem da fonte Samsung.
O XNU candidato ainda não enumerou o chip no S21 Ultra.

## Enumeração no XNU: patch 0149

O [0149](../lab/s21xnu-p3s/xnu/0149-s21-p3s-wifi-enumerate.patch) altera
o `bsd/dev/sweet_wifi.c` que o 0142 escreve. Os pinos não mudam: no DTS
r17 do p3s, `cfg_wlanen` é gpp12-2 (saída, sem pull, drive 3), host wake
é gpa0-7 e o PCIe canal 0 tem `ep-device-name = "WIFI"`, como no t2s. O
p3s declara `max-link-speed = <2>`; o 0142 já força Gen1 x1. O índice
S2MPU `PCIE_GEN2` = 7 vem do exynos2100.dts comum.

Com `sweetwifi=N` nos boot-args:
- **N ≥ 2:** liga WLAN_REG_ON, sobe o enlace e lê o ID. 14e4:4475 (S21/S21+)
  segue o caminho antigo. 14e4:4441 (p3s) é aceito; qualquer outro ID
  falha como antes.
- **N ≥ 3 no p3s:** grava BAR0 = 0x20000000, janela BAR0 (config 0x80)
  na base de enumeração 0x18000000, habilita memória e lê o chipid da
  ChipCommon. Loga `W2b PASS` se o chip for 0x4389, com a revisão.
- **p3s, qualquer nível:** `W4 SKIP` e retorno antes do pool DMA e de
  `redwood_bcm4375_run`, que só conhece o BCM4375.

A base 0x18000000 é a usual dos chips Broadcom AXI e não foi conferida
para o 4389 neste repositório; um `W2b FAIL` com o valor lido é o
diagnóstico. As linhas aparecem no log persistente `wifi:` do s21xnu.

[`verify_wifi_0149.py`](../lab/s21xnu-p3s/xnu/verify_wifi_0149.py), no
CI, lê o heredoc do 0142 como texto (o script baixa código e não é
executado), aplica o 0149 e confere:
- a ordem enlace → ramo p3s → pool → driver;
- a saída do p3s antes do pool e do driver;
- o chipid só com N ≥ 3, sem escrita no BAR mapeado;
- a chamada do driver 4375 preservada;
- num teste de host, a classificação de 7 IDs (inclusive bytes trocados e
  vizinhos) e a decodificação do chipid.

17 de 17 checagens passam; com o ID trocado no patch, o teste de host
falha. [Evidência](references/s21xnu-p3s-wifi-0149-20261126.json).

No fork, `715d738` e run
[45898493855](https://github.com/rguisantos/s21xnu/actions/runs/45898493855):
sucesso, 0149 aplicado, nenhum aviso novo em `sweet_wifi.c` (os restantes
são das classes que já existiam: casts de `rd`/`wr` e de inicialização de
locks). Novo `xnu-kernel` de 61.319.441 bytes; é o kernel candidato.

No aparelho, com `sweetwifi=3`, o esperado é: `endpoint 14e4:4441`,
`W2 PASS` com os tamanhos dos BARs, `W2b PASS: chipid … chip 4389`, e
`W4 SKIP`. Próximo marco: carregar o firmware `_c1` no BCM4389 (núcleo CA7,
RAM em 0x200000 segundo a fonte Samsung), que o redwood_bcm4375 não faz.
