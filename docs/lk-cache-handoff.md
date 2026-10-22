# Cache/MMU e argumentos do trecho final LK HZC2

Auditoria de **2026-10-22 (Campo Grande)** do sboot recebido, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets são de arquivo. A transformação de registradores e os operandos de
manutenção foram conferidos em **352 cenários** com as instruções originais.
Os acessos a registradores de sistema foram fornecidos/registrados; não se
simularam tradução, conteúdo de cache ou efeitos físicos das barreiras.

**Resultado:** o helper condiciona a manutenção a SCTLR.M, limpa M/C somente
no EL atual e preserva I. O caminho M=0/C=1 conserva C=1. Há chamadas e
callbacks depois desse helper, portanto seu retorno não comprova o estado
na entrada da Image. R10 e diagnóstico permanecem sem alteração.

## Caminho ligado no binário

| Offset / trecho | Comportamento conferido |
|---|---|
| `0xfbdd0 → 0xf6088` | SMC anterior, X0=-0x3ff e X1–X3=0; semântica não determinada; fora da execução do harness |
| `0xfbdd4` | DAIFSet #2: força somente o mascaramento IRQ |
| `0xfbdd8 → 0xee658` | Preparação da interrupção 30; chamada omitida no harness |
| `0xfbddc → 0x18a3a8` | Seleção por CurrentEL e teste do bit M do SCTLR correspondente |
| `0x18a410 → 0x18997c` | Se M=1, percorre caches de dados por CLIDR/CCSIDR |
| `0x1899bc → 0x189848` | Seleciona nível em CSSELR; emite DC CISW por set/way |
| `0x18a41c → 0x189db8` | Tail branch limpa M e C no SCTLR do EL atual e emite ISB |
| `0xfbde4 / 0xfbdf0` | Chamadas posteriores para modo/saída e printf |
| `0xfbdf4–0xfbe14` | Reconstrói argumentos, lê deslocamento de 32 bits e faz BLR X4 |

No retorno normal do helper, sem traps ou alteração de comportamento dos
registradores de sistema, a tabela é:

| M/C iniciais no EL atual | Manutenção DC | M/C após helper |
|---|---|---|
| 0/0 | Não | 0/0 |
| 0/1 | Não | **0/1** |
| 1/0 | Sim | 0/0 |
| 1/1 | Sim | 0/0 |

O bit I e os demais bits do SCTLR são preservados. SCTLR dos outros ELs
não é alterado. Nenhum ERET/SMC/HVC aparece nos caminhos suportados desse
helper; ele não muda o nível de exceção por si. Isso não demonstra o EL ou
os registradores herdados em toda a cadeia Samsung.

## Percurso set/way e barreiras

`0x18997c` guarda DAIF, mascara IRQ, emite ISB/DSB SY e lê CLIDR_EL1.
Usa LoC, bits 26:24, e percorre os níveis de zero até LoC-1; cache type
menor que 2 é pulado. O helper de nível usa a codificação **legada**:

| Campo usado | Derivação observada |
|---|---|
| CSSELR | nível × 2, seleção de dados |
| Deslocamento do set | CCSIDR[2:0] + 4 |
| Maior way | CCSIDR[12:3] |
| Maior set | CCSIDR[27:13] |
| Deslocamento do way | CLZ de 32 bits do maior way |

Os sets descem até zero; para cada set, os ways também descem até zero.
O operando combina nível, set e way em aritmética W antes de DC CISW X7.
Cache diretamente mapeada também foi conferida: CLZ(0)=32 e o way zero
mantém o campo zerado. As geometrias usadas são pequenas e sintéticas,
incluindo buracos, níveis só de instruções e um nível de índice 6.
Não são a geometria medida dos A55/A78/X1. CCIDX não é tratado por esse modelo.

Depois do percurso, CSSELR recebe zero, há DSB SY/ISB e DAIF é restaurado
antes de ISB. A rotina seguinte limpa M/C e emite ISB. Mesmo com LoC=0,
o caminho M=1 conserva essa sequência de conclusão/reset de seletor.
O caminho M=0 não entra nela. O mascaramento externo garante apenas IRQ;
os demais bits DAIF seguem o estado fornecido, sob as hipóteses do harness.

## Fronteira antes do salto

O harness executa o BLR real, parando no destino sintético antes de executar
uma instrução de payload. Sob preservação de estado pelas chamadas omitidas:

| Item | Valor reconstruído |
|---|---|
| X0 | `0x8b080000`, sem ler/certificar o FDT nesse endereço |
| X1/X2/X3 | zero |
| X4 / destino | `0x80080000 + zero_extend(deslocamento_u32)` |
| X5 | deslocamento lido, de 32 bits |
| X30 | `0xfbe18`, retorno produzido pelo BLR |

Os 64 deslocamentos do perfil HZC2 foram cobertos. Os registradores voláteis
são envenenados nas três substituições, verificando que os argumentos são
reconstruídos depois delas. A pilha e X19 são restaurados pelo helper.

Essa conclusão é **condicional**: `0xf29a0` ainda chama formatador/printf,
faz chamadas ao helper `0xff5f0` e stores associados às mensagens de modo.
O corpo direto escreve `0x15868500` ou `0x1586c500` e `0xf0000180`; isso não
atribui significado de hardware a esses registradores. Não há execução dessas
escritas no harness.

Na saída, `0x20c618` lê uma tabela de operações e faz BR X3 em `0x20c624`.
O handler inicial `0x20c478` percorre a lista de callbacks e faz BLR X3 em
`0x20c4dc`. Ponteiros e lista são mutáveis. As evidências iniciais estão no
[console LK](lk-console-handoff.md); não se provou que as chamadas posteriores
conservem o estado de cache/EL no aparelho. Também falta fechar a semântica
do SMC anterior -0x3ff. Esses são limites concretos da auditoria final.

## Referências e coerência física

O `Documentation/arm64/booting.rst` recebido no Kernel.tar.gz foi lido:
11898 bytes, SHA-256
`bf8bf8030e23f05f0c45949c28a729ffe9ddce87e6c16ee724dbea8abedfe24c`.
O protocolo pede MMU desligada e a imagem limpa até PoC, admitindo I-cache
ligada. Também distingue cache de sistema e outros agentes coerentes.
Logo, preservar I não é por si um defeito; observar DC CISW e os bits M/C
não comprova a coerência da imagem nesse SoC.

[TF-A v1.5 cache_helpers.S](https://github.com/ARM-software/arm-trusted-firmware/blob/v1.5/lib/aarch64/cache_helpers.S)
foi consultado como referência primária de CLIDR/CCSIDR, operações DC e
barreiras. Não é fonte correspondente nem implementação idêntica do LK
Samsung. Identidades dos trechos e referências estão no relatório estático.

## Reprodução e resultado

```bash
python3 scripts/check_lk_cache_handoff.py /caminho/sboot.bin
python3 scripts/check_lk_cache_handoff.py /caminho/sboot.bin --scenario /caminho/cenario.json
python3 scripts/emulate_lk_cache_handoff.py /caminho/sboot.bin --scenario /caminho/cenario.json
python3 scripts/emulate_lk_cache_handoff.py /caminho/sboot.bin --self-check
python3 -m unittest discover -s scripts -p 'test_lk_cache_handoff.py' -v
```

O emulador usa Unicorn 2.1.4 opcional. O cenário exige nove campos explícitos:
`current_el` (1, 2 ou 3), `sctlr_el1`, `sctlr_el2`, `sctlr_el3`, `daif`,
`clidr_el1`, `csselr_el1`, `ccsidr_by_level` (chaves string 0–6) e
`kernel_offset`. O JSON é limitado a 8192 bytes; inteiros podem ser números
sem sinal ou strings numéricas. Só geometrias legadas resolvidas, com no
máximo 4096 operandos DC, são representadas. São guardas do host, não do LK.

São mapeadas três páginas RX originais, uma página RX de parada sintética,
8 KiB de pilha RW e uma página RW para o deslocamento fornecido. Os acessos
a SCTLR/CurrentEL/DAIF/CLIDR/CCSIDR/CSSELR são substituídos ou registrados,
assim como DC/DSB/ISB. Limites: 50000 visitas/1 segundo por caso, guardas de
PC e recusa de instrução de sistema não modelada. Não há MMIO físico,
cache suja, tradução, traps, errata ou semântica RES1/RAO/WI simulados.

**352/352 cenários coincidiram:** 288 de matriz e 64 da seed `0x18a3a8`;
174 passaram pela manutenção e 178 a pularam. Máximos de 2370 visitas e
266 operandos DC por caso. **14 testes novos de host passaram**, incluindo
gates M/C/I, EL ativo, DAIF, operandos, limites JSON e identidade da imagem.

[Relatório estático e exemplo artificial](references/lk-cache-handoff-hzc2.json)
e [relatório Unicorn](references/lk-cache-handoff-unicorn-hzc2.json) foram
versionados. O exemplo EL2/M=0/C=1 conserva C e deixa SCTLR_EL1 inalterado;
não é um estado observado no S21. Sem mudança no payload ou suas exigências,
sem nova regressão R8/R9/R10, coleta bloqueada ou teste físico.
