# s21xnu no S21 Ultra (p3s): contrato de hardware e perfil de painel

Rodadas de 25 e 26/11/2026 (Campo Grande). Análise estática das fontes e builds de
host. **Nada foi executado no aparelho; o bootloader continua informado como
travado.**

## Ponto de partida

O repositório público [jimmycarles9991-glitch/s21xnu](https://github.com/jimmycarles9991-glitch/s21xnu),
fixado em `a128f07b04987e60f5e13e2ce67b19ae009672cd`, é o port ios-sweet do
XNU `xnu-8796` (iOS 16) para o Galaxy S21+ SM-G996B (`t2s`), mesmo SoC Exynos
2100 do nosso SM-G998B (`p3s`). Segundo o README e as notas dele (não
reproduzido aqui), o kernel sobe nos oito núcleos, monta a raiz HFS+ por um
arquivo dentro de `userdata` com UFS somente leitura, tem touch e chegou à
tela de bloqueio/início com renderização por software em 31/10. O handoff
mais recente registra um panic precoce com a raiz completa de 16 GiB, então o
estado não é estável.

Caminho de carga dele: Linux 7.3.0-rc5 no próprio telefone (DTS
`exynos2100-t2s-firstlight-v32.dts`, não publicado) executa `kexec` do shim
(`shim/`, Image arm64) com o payload XNU como initrd. Isso exige bootloader
desbloqueado.

## Método

O verificador [`scripts/s21xnu_board_contract.py`](../scripts/s21xnu_board_contract.py)
compila com `dtc` a base `exynos2100.dts` e os overlays de placa do
FlopKernel (`dc17ad08a8b4f7fcabd3f949d9c83ff11c5f80ee`), mescla com
`fdtoverlay` e compara os recursos que o s21xnu fixa em código. Revisão
`r17` nas duas placas, porque o DTS HZC2 recebido tem `board_rev=0x11`
([registro](dts-source-roundtrip.md)). Hashes das fontes e dos FDT mesclados
estão no [relatório](references/s21xnu-board-contract-p3s-t2s-20261125.json).
Duas execuções produziram JSON idêntico.

```bash
python3 scripts/s21xnu_board_contract.py \
  --flop-dts FLOP/arch/arm64/boot/dts/exynos --json saida.json
```

O FDT base do FlopKernel não é o DTB stock HZC2 (398496 contra 389876
bytes). As placas foram comparadas entre si na mesma fonte; isso não substitui
o FDT final entregue pelo LK.

## Resultado: 21 itens iguais, 5 diferentes

| Recurso usado pelo s21xnu | p3s | t2s | Situação |
|---|---|---|---|
| Touch (0094): barramento, endereço, pinos | hsi2c@105D0000, 0x48, gpp4-0/1, ATTN gpa1-0 | igual | reaproveitável |
| Alimentação do touch (0094/0107) | S2DOS05 LDO2 tsp_io 1,8 V e LDO3 tsp_avdd 3,0 V | igual | reaproveitável |
| Coordenadas do touch | `sec,max_coords` 4096×4096 | igual | normalizadas, ver painel |
| Firmware do touch | `y792_p3.bin` | `y792_t2.bin` | mesma família slsi_ts; o s21xnu não grava firmware |
| PMIC S2DOS05 (0094) | hsi2c@10560000, 0x60, gpp0-2/3 | igual | reaproveitável |
| MAX77705 (0123) | hsi2c@10570000, 0x66, gpp1-0/1 | igual | reaproveitável |
| Teclas (0125) | gpa0-3/4, códigos 114/115 | igual | reaproveitável |
| GIC, Mali, UFS, MPIDR | 0x10200000/0x10240000, 0x18500000, 0x13100000, 0x000–0x700 | igual | reaproveitável |
| Reservas fixas na janela XNU 0x8c0000000–0x940000000 | nenhuma | nenhuma | janela utilizável nas duas placas |
| **Painel** | modos até **1440x3200** (S6E3HAD) | 1080x2400 (S6E3FAB) | **muda** |
| **Wi-Fi PCIe ch0** | `ep-ver` **0x4389**, Gen2 | 0x4375, Gen1 | **muda** |

As alimentações S2DOS05 também servem ao painel nas duas placas. O
power-cycle de LDO2/LDO3 que o s21xnu faz por padrão tem o mesmo risco nos
dois aparelhos.

### Painel

O LK HZC2 reserva `bootloader_fb` em `0xfa000000` com `0x1194000` bytes
([escritores condicionais](lk-dynamic-fdt.md)), exatamente 1440 × 3200 × 4.
Isso é coerente com scanout WQHD+ a 32 bpp, mas formato e stride vivos não
foram medidos. 1440x3200 é exatamente 4/3 de 1080x2400, com a mesma proporção
9:20.

A maior parte do XNU do s21xnu lê a geometria do ADT ou de `boot_args.Video`
(0003, 0046, 0112). Ficam fixos em 1080x2400:

| Local | Efeito no p3s |
|---|---|
| `shim/console.h`, `tools/mkadt.py` | geometria anunciada ao XNU, **corrigida pelo perfil abaixo** |
| 0010/0012/0106: depuração precoce com stride 4320 | marcas em posição errada; só diagnóstico |
| 0061: apresentação iPhone X 1125x2436 centrada em 1080x2400 | offsets ficam errados em 1440x3200 |
| 0094 linha 366, 0139: touch 0..4095 → 1080x2400 | no modo janela o toque sai a 3/4 da posição |
| 0058/0061: normalização HID por 1080/2400 | segue a mesma conversão |

### Wi-Fi

O BCM4389 do p3s é outro chip, com firmware, NVRAM e CLM próprios. O s21xnu
carrega BCM4375 (0109/0111/0142, `mkpayload.py --wifi-*`). No p3s, manter
`sweetpcie` no nível sem firmware até um port próprio.

## Perfil p3s para o s21xnu

[`lab/s21xnu-p3s/0001-board-p3s-framebuffer.patch`](../lab/s21xnu-p3s/0001-board-p3s-framebuffer.patch)
(compatível com `git apply` e `patch -p1` sobre `a128f07`) adiciona
`BOARD=` ao `shim/build-s21.sh` e `--board=` ao `tools/mkadt.py`:

| Perfil | FB_W × FB_H | Stride | Uso |
|---|---|---|---|
| `t2s` (padrão) | 1080 × 2400 | 4320 | S21+, byte a byte igual ao original |
| `p3s` | 1440 × 3200 | 5760 | tela cheia; exige ajustar 0061/0094/0058 |
| `p3s-window` | 1080 × 2400 | 5760 | janela no canto superior esquerdo; XNU sem mudança de geometria, toque desalinhado (3/4) sem ajuste em 0094 |

O [verificador](../lab/s21xnu-p3s/verify_p3s_profile.py) copia o clone
fixado, aplica o patch, compila o shim nos três perfis e gera o ADT com semente
fixa. 20/20 critérios: t2s idêntico ao original (shim `e91caec6…`, ADT
`4a4155f4…`), geometria do nó `sweet-fbcon` e dos macros que alimentam
`boot_args.Video`, base/tamanho do framebuffer preservados, padrão = t2s e
recusa de placa desconhecida
([resultado](references/s21xnu-p3s-profile-validation-20261125.json)). O XNU
não foi compilado; isso exige o runner macOS do workflow dele.

## Caminho de carga no p3s

O s21xnu depende de um Linux com `kexec` no telefone. Para o p3s há três
opções, todas após o desbloqueio OEM:

1. **Shim direto pelo S-Boot** (detalhado abaixo): shim como kernel e
   payload como ramdisk do `boot.img`, sem Linux. Cada teste é um flash via
   Odin.
2. **Kernel Android com `CONFIG_KEXEC`.** O `kernel.config` publicado pelo
   port MonsterROM (Floppy 5.4.304) tem `KEXEC` e `KEXEC_FILE` desligados.
   Um build próprio (o A0 já reproduz 5.4.242 com os 274 módulos) poderia
   ligar a opção e usar o Android rooteado como lançador.
3. **Linux mainline como no t2s.** Exige DTS p3s para Linux 7.x, que não
   existe publicado.

## Carga direta pelo S-Boot (26/11)

Contrato de entrada do shim (`a128f07`) contra o modelo do LK HZC2 já
documentado neste repositório:

| Exigência do shim | LK HZC2 (modelo estático) | Situação |
|---|---|---|
| Image arm64, código sem relocação absoluta (o build recusa ABS64) | copia para 0x80080000 + KASLR (0..0x1f8000, passo 0x8000) ([produtor](bootloader-hzc2.md)) | compatível; Image p3s 249.856 bytes |
| Entrada em EL1, MMU/caches desligados, x0 = FDT | X0 = 0x8b080000; helper desce EL2→EL1 ([granule](lk-entry-granule-hzc2.md), [cache](lk-cache-handoff.md)) | compatível no modelo |
| `/chosen` `linux,initrd-start/end` de 4 ou 8 bytes | LK grava células u32: 0x84080000 e +vendor+boot ([FDT dinâmico](lk-dynamic-fdt.md)) | compatível (`fdt_chosen_u64` aceita 4 bytes) |
| Procura SWEETXNU de 4 em 4 bytes desde initrd-start | ramdisk vendor em 0x84080000, ramdisk de boot logo após, **sem padding** ([cópias v3](lk-v3-layout.md)) | exige padding, ver abaixo |
| Header do payload alinhado a 8 (`copy64` em memória Device) | vendor ramdisk stock tem 12.017.257 bytes: o ramdisk de boot começa em **0x84bf5e69** | **7 bytes de padding** |
| PSCI por HVC | LK edita smc→hvc ([PSCI](lk-psci-final-edit-hzc2.md)) | coerente |

Sem o padding, o header fica em endereço ímpar. O shim não o acha, ou recusa
o header, e o XNU nunca recebe o controle. No caminho kexec do t2s o Linux
coloca o initrd alinhado a página, por isso o problema não aparece lá.

[`lab/s21xnu-p3s/mk_sboot_bootimg.py`](../lab/s21xnu-p3s/mk_sboot_bootimg.py)
monta o `boot.img` v3 a partir do `boot.img`/`vendor_boot.img` stock (mantém
os_version e cmdline do header), do `Image` do shim e do payload. O padding
sai do tamanho real do ramdisk vendor. O script recusa a montagem quando:
- o kernel com o maior KASLR alcança 0x84080000;
- o initrd passa do FDT do LK ou do staging 0x94000000;
- o ramdisk vendor contém SWEETXNU num endereço que o scan veria;
- a janela ou as escritas do payload (segmentos, ADT, boot_args) caem sobre
  o initrd, o FDT ou as reservas fixas do LK (uH, sboot, fb, kaslr, mz);
- a imagem excede a partição de 64 MiB.

Sem `--payload`, gera a **sonda**: o shim mostra `no SWEETXNU payload` em
vermelho, segue para o diagnóstico na tela (DTB, MMU, PSCI, GIC) e chama
PSCI SYSTEM_RESET após 40 s. A sonda não toca armazenamento: o teste UFS
do shim (`test_ufs`, só leitura) nem é chamado por `shim_main`. Como reinicia no mesmo
`boot.img`, sair do ciclo exige entrar no modo download e regravar o boot
stock.

### Execução no QEMU

[`lab/s21xnu-p3s/qemu/run_handoff.py`](../lab/s21xnu-p3s/qemu/run_handoff.py)
compila o shim `BOARD=p3s` e um kernel falso e monta o `boot.img` com um
ramdisk vendor sintético de 12.017.257 bytes. Depois reproduz o LK no QEMU
virt: Image em 0x80080000+KASLR, initrd vendor+boot em 0x84080000, FDT com
células u32 em 0x8b080000 e salto em EL1 com x0=FDT. O kernel falso imprime
`boot_args` na PL011.

Resultado: **57/57**
([JSON](references/s21xnu-sboot-handoff-qemu-20261126.json)).
- Nos KASLR 0, 0x8000 e 0x1f8000, o kernel falso recebeu o controle em EL1
  com Revision/Version 2, framebuffer 0xfa000000 1440×3200 stride 5760,
  ADT copiado e cmdline correta, e boot_args dentro da janela.
- O controle negativo, com o mesmo payload sem padding (header em
  0x84bf5e69, resto 1 mod 8), não chega ao kernel falso.
- Duas execuções deram o mesmo `boot.img` (SHA-256 `06f34148…`).

O QEMU virt não é o Exynos. O teste não cobre DECON/painel, uH, PSCI real,
UFS ou o FDT final do aparelho.

### Antes de um teste no aparelho

- Desbloqueio OEM. O port MonsterROM também regrava o vbmeta. Este repo
  não verificou como o LK desbloqueado trata o boot sem footer AVB; os docs
  de AVB do LK cobrem o estado travado.
- O DECON 0 está em modo comando com disparo por hardware (`psr_mode=2`,
  `trig_mode=0`), igual no t2s, onde o framebuffer do S-Boot já é usado pelo
  s21xnu. Que escrever em 0xfa000000 apareça na tela do p3s continua não
  observado.
- Recuperação: modo download e Odin com o boot stock.

## Coerências com este repositório

- PSCI por **HVC** observado pelo s21xnu bate com a
  [edição smc→hvc do LK](lk-psci-final-edit-hzc2.md).
- GICD/GICR, MPIDR e UFS conferem com [EXYNOS2100_HARDWARE.md](../EXYNOS2100_HARDWARE.md).
- O s21xnu usa o timer **virtual** (INTID 27). Nossa tabela registra o físico
  NS (INTID 30). Os dois PPIs existem; não é contradição.

## Correção paralela

`scripts/parse_fdt.py` (legado) tinha `FDT_PROP`/`FDT_END_NODE` trocados e lia
`off_mem_rsvmap` como versão: abortava em qualquer FDT real. Agora segue a
especificação e decodifica `reg` com as células do nó pai. Continua marcado
como leitor legado.

## Testes

`scripts/test_s21xnu_board_contract.py`: 11 testes com FDT sintéticos
(recusas de magic/truncamento/estrutura, células do pai, placas iguais,
diferenças estilo p3s, pinos de touch movidos, reserva invadindo a janela
XNU, recurso ausente, CLI/JSON e regressão do `parse_fdt.py`, que falha sem a
correção).

## Pendências

- Decisão sobre desbloqueio OEM: nenhuma opção de carga existe sem ela.
- Montar a sonda com o `boot.img`/`vendor_boot.img` stock reais (não estão
  neste ambiente) e conferir o relatório antes de qualquer flash.
- Ajuste de toque em 0094 (boot-arg com a geometria do painel) e da
  apresentação em 0061 para `p3s`; exigem o build XNU do workflow s21xnu.
- Port BCM4389 ou Wi-Fi desligado.
- Conferir no aparelho o FDT final do LK e o scanout do `bootloader_fb`.
