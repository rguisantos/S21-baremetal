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

- `--cega relogio` (`SHIM_BLIND=3`): depois da entrada, espera 30 s pelo
  contador (supondo 26 MHz) e chama PSCI `SYSTEM_RESET`. Marca `0x5110` ou
  `0x5111` (CNTFRQ_EL0 zero ou não), `0x5112` antes do PSCI e `0x5113` se ele
  voltar; nesse caso reinicia pelo PMU. A duração se mede de fora, pelos
  tempos de `USB disconnect` e reconexão no `dmesg` do PC.

- `--cega tela` (`SHIM_BLIND=4`): lê `TRIG_CON` (0x19F00030) e
  `GLOBAL_CON` (0x19F00020) do DECON0 como o S-Boot deixou e grava um
  resumo em INFORM2 (`0x6TTG`). Depois tira a máscara do trigger por
  hardware (`HW_TRIG_EN`, limpa `HW_TRIG_MASK_DECON`), pede atualização das
  shadow (`SHD_REG_UP_REQ` bit 31) e pinta vermelho com texto por 15 s e
  verde por 15 s. A base vem do nó `decon_0@0x19F00000` do FDT p3s; os
  registradores vêm de `cal_2100/regs-decon.h` e de
  `decon_reg_set_trigger()` no FlopKernel `dc17ad0`. O driver Samsung
  mascara o trigger entre os frames no modo comando com trigger por hardware.
  A hipótese é que o S-Boot deixa o trigger mascarado depois do logo.

O pedido de recovery usa só o INFORM3. A primeira versão escrevia também
`SYSIP_DAT0` (0x15860810) = 0xff, que não era necessário: o S-Boot já
obedece ao INFORM3. Agora não escreve mais.

## Resultado no aparelho (27/11)

O log se lê em `/proc/sec_log` na Fox: ele tem o S-Boot do boot anterior e
do atual. O `/proc/last_kmsg` tem só o anterior.

| Kit | Linha do S-Boot no boot seguinte | Leitura |
|---|---|---|
| entrada (`ed8342f4…`) | `PINFORM = 12345604 … REBOOT_MODE to 4`, `inform2: 0x5101` | o S-Boot executou o boot.img e o shim rodou desde a primeira instrução |
| etapas (`ed5787aa…`) | `PINFORM = 12345604 … REBOOT_MODE to 4`, `inform2: 0x510F` | todas as etapas, sem exceção; reset pelo PMU |
| relogio | `PINFORM = 12345604 … REBOOT_MODE to 4`, `inform2: 0x5113` | o PSCI `SYSTEM_RESET` (hvc) **voltou sem reiniciar**; o reset veio do PMU |
| tela (`09f266e7…`) | `inform2: 0x6C5F`; o usuário **viu vermelho e depois verde** | `TRIG_CON` = 0x31 (trigger ligado, mascarado para DECON e SLAVE0), `GLOBAL_CON` = 0x1F (modo comando, rodando, em repouso); desmascarar o DECON liga a tela |

Ao carregar a sonda, o S-Boot registrou `Verify_Signature_Ecdsa … failed`
para a BOOT e `set_ddi_kernel_type: BOOT, 0x2` e seguiu até `Starting
kernel...`. O ciclo da variante etapas levou ~29 s do `USB disconnect` à
reconexão da Fox. O `inform3` aparece zerado na linha `show_reset_reason`
porque o S-Boot já o consumiu na linha `PINFORM`. Se a tela mudou durante a
variante etapas, o usuário não percebeu.

Com isso a hipótese 1 está descartada. A sonda com tela roda o mesmo código e
difere em duas coisas: espera 25 s em vez de 2 e reinicia por PSCI (`hvc`)
depois de 40 s. A variante relogio respondeu as duas:
- **O PSCI `SYSTEM_RESET` volta sem reiniciar** (`0x5113`). O kernel Samsung
  faz o mesmo: no log do Android, `psci_sys_reset` é chamado e volta, e quem
  reinicia é o `exynos_restart_handler` pelo PMU. Isso explica a sonda com
  tela, que depois do PSCI fica parada num `wfe`.
- **O contador anda a 26 MHz.** O ciclo levou 57,0 s (USB 98914,9 → 98971,9)
  contra 29 s na variante etapas: os 28 s a mais batem com a diferença de
  espera.

Conclusão: a sonda com tela deve ter rodado o diagnóstico inteiro, num
framebuffer que o painel não mostra (hipótese 4), e travado no reset
(hipótese 3). A variante tela ataca a hipótese 4. O reset do shim e do XNU no
p3s precisa ir pelo PMU (0x15863c00 = 2).

## A tela do p3s: patch 0004

Com o resultado da variante tela, o
[`0004-p3s-decon-trigger-and-pmu-reset.patch`](../lab/s21xnu-p3s/0004-p3s-decon-trigger-and-pmu-reset.patch)
põe as duas correções no shim do p3s (`BOARD=p3s` e `p3s-window`):
- `p3s_display_on()` roda antes do loader: liga `HW_TRIG_EN`, limpa
  `HW_TRIG_MASK_DECON` e pede `SHD_REG_UP_REQ` global. Com o trigger
  desmascarado, o painel continua atualizando a cada TE depois que o shim
  salta para o XNU.
- `reset()` vai pelo PMU (`0x15863c00` = 2), com o pedido de recovery
  (INFORM3 = `0x12345604`). A sonda e o painel de exceção voltam sozinhos à
  recovery.

O 0004 entra na sonda padrão de `prepare_first_boot.py` (as variantes cegas
continuam só com o 0003) e no shim de `prepare_xnu_boot.py`, depois da série
do fork. Validação: `blind_marks.py` confere no QEMU, com DECON0 e PMU falsos
via `P3S_MMIO_CFLAGS`, o trigger desmascarado na entrada e o reset pelo PMU
no fim (6 checagens). `probe_screenshot.py` (7 linhas) e `run_handoff.py`
(handoff do XNU falso) passam com o 0004 aplicado. No aparelho, o 0004 ainda
não rodou; o próximo teste é a sonda padrão, com as linhas legíveis na tela.

## Efeitos colaterais observados (27/11)

- **Android em loop para a recovery depois do vbmeta desativado.** O `init`
  pede `reboot recovery` aos 10,5 s:
  `KeyStorage: decryptWithKeystoreKey fail` (`fbe.fail_cause M02R`), depois
  `fs_mgr_mount_all suggested recovery, so wiping data`. A chave do `/data`
  está presa ao estado de verificação. Resolve com Format Data na Fox. Não
  tem relação com a sonda: o Android não ligou desde a gravação do vbmeta.
- **A Fox recompacta a BOOT a cada entrada** (sempre `9d405a0c…` a partir do
  stock). O autor da ROM descreve no XDA um "script herdado que reempacotava
  o boot stock", que ele tirou da recovery que usava. O `to-android
  --no-reboot` regrava o stock conferido; o reinício para os testes é feito
  por `sysrq` (`echo b > /proc/sysrq-trigger`).
- O log de cada boot se lê em `/proc/sec_log` (S-Boot do boot anterior e do
  atual).

## Validação

[`qemu/blind_marks.py`](../lab/s21xnu-p3s/qemu/blind_marks.py) compila as
três variantes com o PMU redirecionado para RAM (`BLIND_PMU=0xBF000000`),
carrega a sonda pelo handoff LK modelado e lê os registradores pelo monitor
do QEMU ([resultado](references/s21xnu-sonda-cega-qemu-20261127.json)):

- `SHIM_BLIND=0` não escreve nada;
- `SHIM_BLIND=1` para em `0x5101`;
- `SHIM_BLIND=2` passa por todas as etapas até `0x510F`;
- as variantes entrada e etapas escrevem só três registradores (INFORM2,
  INFORM3 = `0x12345604` e reboot-offset = `2`) e não tocam no DECON;
- `SHIM_BLIND=3` marca `0x5111` durante a espera e o PSCI `SYSTEM_RESET`
  encerra o QEMU (`-no-reboot`);
- `SHIM_BLIND=4`, com um DECON0 falso em RAM semeado com `TRIG_CON=0x11` e
  `GLOBAL_CON=0x113`, grava `0x644F`, deixa `TRIG_CON=0x01` e liga o bit 31
  de `SHD_REG_UP_REQ`.

Roda também no CI. Os testes de `prepare_first_boot.py` cobrem o roteiro
das variantes cegas.

O QEMU não é o Exynos. No aparelho, as variantes entrada e etapas já mostraram
que o INFORM2 sobrevive ao reset por software, que o S-Boot obedece ao pedido
de recovery e que a escrita no PMU a partir de EL1 funciona. Continua sem
verificação se o INFORM2 sobrevive a um reset manual.

O caminho de exceção da variante etapas não foi exercitado no QEMU.
