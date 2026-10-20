# FDT: recursos e política inicial de memória

O código em `r8/r10_payload/fdt.c` substitui a antiga checagem apenas do magic/total. É um subconjunto limitado do [formato FDT](https://devicetree-specification.readthedocs.io/en/stable/flattened-format.html) e das propriedades padrão; não implementa todos os bindings ou traduções de barramentos.

## O que é interpretado

- Cabeçalho v17 compatível, blocos dentro de totalsize, offsets/alinhamento, tokens e strings limitados, nesting e lista de reservas terminada. Campos relevantes duplicados ou estruturas truncadas são recusados.
- Memória na raiz com `device_type=memory`, `reg` com uma ou duas células por endereço/tamanho, inclusive endereços acima de 4 GiB. RAM sobreposta é recusada.
- Reservas `/memreserve/` e `/reserved-memory`, além do initrd em `/chosen`. Reservas dinâmicas com apenas `size` e agrupamentos aninhados não resolvidos impedem certificar RAM utilizável.
- CPUs em `/cpus`, por MPIDR completo. Nós desabilitados e descendentes não contam como recursos ativos.
- GICv3 na raiz com `interrupt-controller` e `#interrupt-cells=3`, duas primeiras regiões `reg`, phandle e stride opcional; uma região de redistributors. Timer `arm,armv8-timer` na raiz, segunda interrupção na ordem do binding (físico NS) e seu interrupt-parent. O timer deve declarar disparo por nível, alto ou baixo, compatível com a configuração da PPI.

Não há alocação, escrita no DTB ou acesso MMIO dentro do parser. Os limites são 2 MiB por DTB, profundidade 32, 64 intervalos RAM, 128 reservas e 32 CPUs; exceder capacidade provoca erro, nunca truncamento silencioso. A pilha de travessia é estática: chamar antes de liberar IRQs/SMP. A saída só é válida quando o parser retorna zero.

## Política de boot

`r10_fdt_check_boot()` exige o intervalo `[__payload_start, __payload_end)` inteiro dentro de um intervalo RAM e fora de reservas, initrd e do próprio DTB. Também exige a CPU atual na topologia, GIC e timer ligados pelo mesmo phandle e INTID 30. Regiões GIC não podem se sobrepor entre si, ao DTB ou à RAM declarada. O driver descobre em seguida o redistributor e confere o estado herdado do firmware.

Não há escolha automática de endereço, união de bancos adjacentes, tradução genérica de `ranges`, autenticação do DTB ou reconstrução de reservas do bootloader. Reservas aninhadas são mantidas para inspeção, mas a descrição é marcada incompleta porque seu significado não é garantido por um binding genérico. A política é deliberadamente conservadora; o DTB ativo ainda pode exigir suporte adicional a bindings Samsung.

Resultados negativos distinguem formato inválido (-1), capacidade (-2), binding não suportado (-3), ausência de RAM (-4), reservas incompletas (-5), conflito de intervalos (-6) e recursos ausentes/incompatíveis (-7). A main guarda o resultado em `r10_boot_status` e para. Erros posteriores do GIC/timer usam -100/-101; estado pronto é 1. UART pode estar desativada, portanto ausência de texto não prova sucesso.

## Responsabilidade do carregador

BSS e pilhas iniciais são escritos antes da validação em C. O carregador deve reservar os segmentos ELF pelo **p_memsz**, incluindo todas as pilhas, e garantir que sua carga não destrua firmware, DTB, initrd ou reservas. O linker agora inclui `.stacks` no segmento data PT_LOAD e expõe os limites completos da imagem. `0x80080000` continua sendo apenas o endereço padrão de linkedição.

x0 deve apontar para um FDT bruto, alinhado a 8 bytes, legível integralmente com a MMU desligada. `available` é o limite fornecido pelo chamador, não uma prova de mapeamento; na main o teto de 2 MiB depende dessa garantia externa de legibilidade. Leituras de endereços inacessíveis continuam fatais. Também faltam validar o EL de entrada real, manutenção de cache até PoC/coerência de instruções e acesso ICC/timer.

Dados FDT têm alinhamento de quatro bytes, inclusive propriedades de 64 bits. O parser AArch64 é compilado com `-mstrict-align`: sem isso, GCC pode fundir leituras byte a byte em um LDR desalinhado, que falha com o regime inicial de memória do payload. A integração QEMU detectou esse caso em uma propriedade de afinidade.

## Testes e DTBs recebidos

```bash
python3 scripts/test_fdt.py
python3 scripts/test_fdt.py --inspect /caminho/base.dtb /caminho/merged.dtb
bash scripts/test_r10_stage.sh
```

As fixtures Python codificam o formato independentemente do parser C e verificam sucesso/erro sob ASan/UBSan. Cobrem células de 32/64 bits, RAM alta, reservas/initrd/DTB, bancos, afinidades, recursos ausentes, nós desabilitados, capacidade e corrupção/truncamento. A integração executa o parser AArch64 e a política reais antes do GIC e de cinco IRQs de timer.

O FDT base HZC2 e cada um dos oito resultados com overlays passaram no parsing, confirmaram GIC/CPU/timer e tiveram boot recusado com -4: nenhum descreve RAM. Reservas dinâmicas/aninhadas também foram detectadas. O DTB do TWRP indicado teve o mesmo resultado após retirar sua tabela Android de 64 bytes. Isso é inspeção estática, sem equivalência ao FDT final entregue pelo bootloader.
