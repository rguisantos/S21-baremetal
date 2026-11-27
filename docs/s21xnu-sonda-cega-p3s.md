# Sonda cega do shim s21xnu no p3s (27/11)

## Por que

No primeiro teste no aparelho (27/11, [evidência](references/aparelho-p3s-20261127.json))
a sonda com tela não mostrou nada. O logo "Samsung Galaxy" ficou na tela por
mais de 2 minutos, e o aparelho não reiniciou sozinho nem depois dos 40 s
programados. Isso é compatível com quatro hipóteses, e só a primeira e a
última já estavam documentadas como risco:

1. o S-Boot não executou o boot.img;
2. o shim travou antes do reset (por exemplo, na pausa que depende do
   `CNTPCT_EL0`);
3. o reset por PSCI, que o shim faz com `hvc #0`, não funciona nesse boot;
4. o DECON está em modo comando (`psr_mode=2`) e as escritas em 0xfa000000
   não aparecem no painel.

O log do S-Boot é o único canal que já se lê no aparelho, pela Fox em
`/proc/last_kmsg`. Em cada boot ele imprime `show_reset_reason_rawdata:
rst_stat: …, inform2: …, inform3: …`.

## O que o patch 0003 faz

[`0003-probe-blind-pmu-marks.patch`](../lab/s21xnu-p3s/0003-probe-blind-pmu-marks.patch)
é aplicado depois do 0001 e do 0002, só com `prepare_first_boot.py --cega`.
Sem a opção, o kit da sonda com tela não muda. Os endereços são os do FDT
stock do p3s (`sec-reboot` e `exynos-reboot`), os mesmos que o kernel
Samsung usa a partir de EL1:

| Registrador | Endereço | Valor escrito | Uso no kernel stock |
|---|---|---|---|
| INFORM2 (magic-inform) | 0x15860808 | `0x51nn`, bits 31..16 em zero | bits 23..16 com 0x4E no reboot normal |
| INFORM3 (panic-inform) | 0x1586080c | `0x12345604` | `SEC_RESET_REASON_RECOVERY` (`reboot recovery`) |
| SYSIP_DAT0 | 0x15860810 | `0xff` | `REBOOT_MODE_RECOVERY` |
| reboot-offset | 0x15863c00 | `2` | reset por software (`exynos-reboot.c`) |

Os bits 31..16 de INFORM2 ficam em zero, como no log depois de um reset
manual (`inform2: 0x0`), que já bootou normalmente. Fontes:
`drivers/samsung/sec_reboot.c` e `drivers/power/reset/exynos-reboot.c` do
FlopKernel `dc17ad0`, e os nós `sec-reboot` e `exynos-reboot` do `p3s.dtb`.

- `--cega entrada` (`SHIM_BLIND=1`): na primeira instrução depois do
  handoff, grava o pedido de recovery e `0x5101`, e reinicia pelo PMU. Não
  usa pilha, timer, framebuffer nem PSCI.
- `--cega etapas` (`SHIM_BLIND=2`): grava o pedido de recovery na entrada e
  uma marca por etapa, com a pausa reduzida a 2 s. Reinicia pelo PMU no fim e
  também em qualquer exceção (`0x5S8X`: S = última etapa, X = slot do vetor).

| inform2 | Última etapa alcançada |
|---|---|
| `0x5101` | entrada (primeira instrução) |
| `0x5102` | `shim_main` |
| `0x5103` | framebuffer pintado |
| `0x5104` | loader leu o ramdisk |
| `0x5105` | linhas do handoff, FDT lido |
| `0x5106` | pausa de 2 s: o contador anda |
| `0x5107` / `0x510E` | MMU ligada / falhou |
| `0x5108` | antes do PSCI (`hvc`) |
| `0x5109` | PSCI respondeu |
| `0x510A` | teste do GIC concluído |
| `0x510F` | reset pedido no fim |
| `0x5S8X` | exceção no slot X do vetor, depois da etapa S |
| `0x0` | nenhuma marca: o shim não rodou, ou o S-Boot zerou o PMU no reset manual |

Leitura esperada: com a variante entrada, voltar sozinho à Fox com
`inform2: 0x5101` separa a hipótese 1 das outras. Com a variante etapas, a
última marca aponta a etapa em que parou. Nos dois casos, a volta automática
à Fox também mostra que o reset pelo PMU e o pedido de recovery funcionam
desse ponto.

## Validação

[`qemu/blind_marks.py`](../lab/s21xnu-p3s/qemu/blind_marks.py) compila as
três variantes com o PMU redirecionado para RAM (`BLIND_PMU=0xBF000000`),
carrega a sonda pelo handoff LK modelado e lê os registradores pelo monitor
do QEMU ([resultado](references/s21xnu-sonda-cega-qemu-20261127.json)):

- `SHIM_BLIND=0` não escreve nada;
- `SHIM_BLIND=1` para em `0x5101`;
- `SHIM_BLIND=2` passa por todas as etapas até `0x510F`;
- as duas variantes cegas escrevem só os quatro registradores, com
  `0x12345604`, `0xff` e `2`.

Roda também no CI. Os testes de `prepare_first_boot.py` cobrem o roteiro
das variantes cegas.

O QEMU não é o Exynos. Continua sem verificação no aparelho:
- se o S-Boot preserva INFORM2 num reset por software ou num reset manual;
- se o S-Boot obedece ao pedido de recovery;
- se a escrita no PMU a partir de EL1 passa pelo hipervisor (uH) nesse boot.

O caminho de exceção da variante etapas não foi exercitado no QEMU.
