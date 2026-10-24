# Referências a BL2 no kernel e cruzamento com HZC2

Investigação de **2026-10-24 (Campo Grande)**, após o usuário esclarecer
que indicou o repositório pelas menções a BL2. Fonte pública fixada em
[756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0](https://github.com/xfwdrev/android_kernel_samsung_ex2100/tree/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0),
branch `rebased-11`. A análise anterior de build/DTS é
[uma frente separada](xfwdrev-kernel-reference.md).

**Há consumidores de informação anterior ao kernel que ajudam o rastreio.**
O vínculo mais concreto é uma leitura de `0x02073600`, endereço do
[registro de geometria BL2](bl2-geometry-record-hzc2.md), e uma constante
de comparação compartilhada. Isso não recupera o produtor do registro.
[Relatório com hashes de 12 arquivos e testemunhos binários](references/bl2-kernel-consumers-hzc2.json).

## Menções e significado

A busca indexada por `bl2`/`BL2` retornou 75 caminhos na revisão indicada;
a busca não é um censo completo dos fontes. Foram seguidas as referências
Samsung relevantes e feitas buscas pelos endereços já conhecidos.

| Referência | O que o código faz | Utilidade / limite |
|---|---|---|
| `drivers/samsung/sec_bootstat.c` | Consome parâmetros de tempo BL1/BL2/BL3 e oferece estatísticas de boot | Pode ajudar a correlacionar estágios; não contém a inicialização BL2 |
| `drivers/gpu/arm/exynos/include/gpex_clock.h` | Descreve o limite de clock GPU como vindo de CAL/BL2 | É comentário sobre procedência; seguir implementação e alterações posteriores |
| `drivers/devfreq/exynos/exynos-devfreq.c` | Lê a primeira palavra de `0x02073600` como `dram_type` | Novo consumidor concreto do mesmo endereço do registro BL2 |
| `include/dt-bindings/soc/samsung,sysmmu-v8.h` | Define BL2 como codificação de tamanho de fetch em TLB_CFG | Nome sem relação com estágio de boot |
| `include/linux/bio.h` | Usa `bl2` para a segunda lista de bio | Variável sem relação com bootloader |

## Registro DRAM: consumidor Linux e constante comum

Em [exynos-devfreq.c](https://github.com/xfwdrev/android_kernel_samsung_ex2100/blob/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0/drivers/devfreq/exynos/exynos-devfreq.c),
função `exynos_init_freq_table`, o ramo `DEVFREQ_MIF` mapeia **1024 bytes
em 0x02073600**. Faz duas leituras de 32 bits: primeiro `+4`, deslocado
32 bits, depois `+0`, combinado por OR. Não é uma leitura atômica de u64
comprovada. O resultado é impresso como **`DEVFREQ : dram: %llx`**.

Se a palavra for **`0x0001000860000110`**, o ramo identifica o caso como
`dram d1z` e chama `dev_pm_opp_disable` com os argumentos literais
2288000, 2535000 e 2730000. Isso é uma política de frequência MIF para
esse valor, sem um decodificador geral dos campos ou da capacidade RAM.

No sboot HZC2 de SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`:

- Em `0x2f4dc/0x2f4e4`, ADRP/ADD produzem o estado relativo `0x31688`.
- MOVZ/MOVK em `0x2f4e0/0x2f4f0/0x2f4f8/0x2f500` produzem a mesma constante.
- `0x2f4fc` lê u64 de estado+752, célula relativa **0x31978**.
- `0x2f504` compara a palavra com a constante; `0x2f50c` segue para
  `0x2f548` quando iguais.

Esse é o primeiro slot cujas duas recargas de `0x02073600` já foram
identificadas. As 14 palavras selecionadas foram conferidas por prefixo
exato e reconstrução com os helpers existentes. São offsets de arquivo e
estado nominal, sem execução física, identidade de placement ou prova de
preservação entre as etapas.

**Consequência prática:** a linha `DEVFREQ : dram:` é um candidato para
observar o conteúdo da primeira palavra a partir de logs já disponíveis.
Sua presença na fonte pública não prova que o binário HZC2 em execução
contenha o mesmo trecho, que o ramo tenha rodado ou que o log seja legível.
Nenhum valor real foi coletado. Não foram repetidas as leituras de logs
anteriormente bloqueadas pela coleta shell/Shizuku.

## O gate das bases é corroborado como revisão principal do SoC

O driver `exynos-chipid_v2.c`, variante `drv_data_exynos2100`, define
offset de revisão **0x10**, shift principal **20**, shift secundário
**16** e máscara **0xf** em `exynos-soc.h`. O nó
`chipid@10000000` do DTS fixado usa `samsung,exynos2100-chipid` e base
0x10000000. Portanto `main_rev` corresponde a **bits 20–23 de 0x10000010**.

Isso corrobora a identidade do campo usado pelo
[getter BL2 0x2e3d0](bl2-query-base-rewrite-hzc2.md): o gate nominal que
reescreve as cinco bases da consulta corresponde a **main_rev == 1**.
O binding de callback e a execução continuam condicionais; não foi
observada a revisão real nem escolhida uma tabela ativa para o aparelho.

## Bootstat: parâmetros compatíveis com strings do LK

`sec_bootstat.c` declara `boot_time_bl1`, `boot_time_bl2` e
`boot_time_bl3` como parâmetros de módulo com modo 0440. O init registra
`/proc/boot_stat` e `/proc/enhanced_boot_stat`; este último imprime os
tempos e diferenças entre estágios. A configuração pública consultada
declara **CONFIG_SEC_BOOTSTAT=m**: a presença da interface depende também
do carregamento e dos valores fornecidos ao módulo.

No sboot HZC2 existem estas strings exatas:

| Offset de arquivo | Formato |
|---|---|
| 0x23b200 | `sec_bootstat.boot_time_bl1=%d` |
| 0x23b220 | `sec_bootstat.boot_time_bl2=%d` |
| 0x23b240 | `sec_bootstat.boot_time_bl3=%d` |

São compatíveis com o contrato dos parâmetros; as referências às strings,
seus argumentos e o valor runtime não foram rastreados nesta entrega.
A linha que diz MCT inicializado em BL2 usa zeros literais no relatório
do kernel: o texto sozinho não é medição da execução BL2. O valor
`mct_start` é obtido separadamente de `exynos_get_mct_start`.

## GPU: seguir a implementação além do comentário

O getter de frontend retorna `gpu_max_clock_limit` em cache, abastecido
pelo backend. O backend consulta `cal_dfs_get_max_freq(cal_id)`, que chama
`vclk_get_max_freq`: este lê `vclk->max_freq` se houver nó e LUT.
Em `vclk.c`, `vclk_get_dfs_info` atribui valores vindos de ECT DVFS/GEN;
o caminho ASV também contém atribuições. O backend ainda pode elevar o
limite até `gpu_max_clock` do DT quando esse valor é maior.

Assim, o comentário oferece uma pista de procedência, mas não estabelece
um escritor BL2 único ou que o limite exposto seja o valor bruto entregue
pelo firmware. A fonte completa da configuração ECT/ASV ativa e os
bindings efetivos continuam abertos. Não ligar a tabela FVMAP de tensões
ao registro DRAM só por ambos aparecerem em uma camada Samsung.

## Próximos passos e reprodução

Priorizar uma observação verificável do primeiro u64, se houver log
correspondente disponível, e seguir seus produtores no BL2. Em paralelo,
seguir xrefs das três strings de bootstat para seus argumentos. Nenhuma
dessas pistas substitui bancos/reservas finais ou a entrada do diagnóstico.

Para repetir as buscas em um checkout externo na revisão fixada:

```bash
rg -n -i 'bl2' drivers/samsung drivers/gpu/arm/exynos include/dt-bindings/soc
rg -n '02073600|1000860000110' drivers/devfreq/exynos/exynos-devfreq.c
rg -n 'drv_data_exynos2100|main_rev_bit|rev_reg' drivers/soc/samsung/exynos-chipid_v2.c
rg -n 'gpex_clock_get_max_clock_limit|gpu_max_clock_limit' drivers/gpu/arm/exynos
rg -n 'cal_dfs_get_max_freq|vclk_get_max_freq|max_freq =' drivers/soc/samsung/cal-if
```

No S21-baremetal, os dois relatórios estáticos anteriores foram
reproduzidos sem alteração com `inspect_bl2_geometry_record.py` e
`inspect_bl2_query_base_rewrite.py`, usando o mesmo sboot. Não houve build
completo de kernel, novo QEMU, leitura MMIO ou operação no telefone.
