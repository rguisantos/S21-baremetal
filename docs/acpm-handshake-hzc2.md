# HZC2: publicação ACPM e destino condicional NEWTIME

Continuação de **2026-10-24 (Campo Grande)** do
[rastreio NEWTIME](boot-metadata-hzc2.md). O sboot continua fixado em
4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets de código nesta página são de arquivo; endereços AP e locais ao
núcleo ACPM são indicados separadamente.

**Existe um produtor Thumb do valor 0x38e00, que satisfaz o critério de
alias NEWTIME encontrado na etapa anterior.** A rotina escreve esse valor
no endereço local **0xa5900108**, espera zero e depois configura um
ponteiro local **0x3a600**. O BL2 lê **0x15900108**, constrói a configuração
e zera o registrador. A correspondência entre essas visões de hardware e
a execução/preservação da cadeia seguem condicionais.

## Anotação pelo DTS público

Fonte fixada em
[xfwdrev, commit 756951a, exynos2100.dts](https://github.com/xfwdrev/android_kernel_samsung_ex2100/blob/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0/arch/arm64/boot/dts/exynos/exynos2100.dts),
501932 bytes, SHA-256
`a92a3c3a2dcba40460d51343a23590d5f48c0ad3330ba33864e77aa446859f4e`.
O inspetor exige esse arquivo exato e confere os campos do nó `acpm_ipc`:

| Campo | Conteúdo da fonte |
|---|---|
| compatible | samsung,exynos-acpm-ipc |
| Primeiro recurso reg | AP 0x15900000, extensão 0x1000 |
| Segundo recurso reg | AP 0x02039000, extensão 0x41000 |
| initdata-base | Offset 0x8000 |

Assim, o endereço lido pelo BL2 pertence ao recurso IPC nomeado nessa
fonte, e a base somada pelo BL2 coincide com o recurso SRAM. Isso não
comprova que o kernel público corresponde ao firmware em execução nem
documenta, por si, o alias local **0xa5900108 ↔ AP 0x15900108**.

## Dois payloads e a inicialização selecionada

Os loops AArch64 0x16228 e 0x16250 têm parâmetros literais e cópias de
16 bytes. Aplicando o delta nominal BL2 **0x020ea000** às suas origens:

| Intervalo do arquivo | Destino AP da cópia | Intervalo local se zero local = AP 0x02039000 |
|---|---|---|
| [0x38000, 0x3d000) | [0x0203d000, 0x02042000) | [0x4000, 0x9000) |
| [0x3d000, 0x67000) | [0x02048800, 0x02072800) | [0xf800, 0x39800) |

A primeira origem contém vetor com SP **0xf800** e reset Thumb
**0x4261**. Sob esse mapeamento, reset é arquivo **0x38260**, cuja chamada
em **0x3826e** chega a **0x38c90**. São testemunhos de imagem e código,
sem observação da colocação, reset ou das cópias no aparelho.

No caminho selecionado, a tabela local **0x7960** aponta para os helpers
de inicialização. **0x39b48** configura a base local dos descritores em
**0x7150** e contagem 13. **0x3998c**, chamado em **0x38e5a**, preenche o
callback do descritor **7**: base+0x150+4 recebe **0x29601**. O bit Thumb
é um; o destino nominal do segundo payload é arquivo **0x56e00**.
O descritor inicial tem identificador 7 e byte +32 igual a 1.

O laço **0x38e6a–0x38ebe** testa o byte +32, lê o callback +4 e o chama
em **0x38e90**, avançando 48 bytes por descritor. A função **0x56e00**
contém BL em **0x56e1e → 0x56ee0**. Chamadas intermediárias, preservação
dos campos e passagem efetiva pelos gates não foram comprovadas.

## Publicação e confirmação selecionadas

| Lado | Testemunho do código |
|---|---|
| Thumb 0x56eee/0x56ef0 | LDRs relativos ao PC leem literais 0xa5900108 e 0x38e00 em 0x56fd8/0x56fdc |
| Thumb 0x56ef2 | STR de 32 bits: publica 0x38e00 no endereço local 0xa5900108 |
| Thumb 0x56ef6–0x56efa | Lê o mesmo endereço e repete enquanto diferente de zero |
| Thumb 0x56f00/0x56f0a | Após sair, guarda 0x38e00 em célula local 0x2fbf4 e 0x3a600 em 0x2fd98 |
| BL2 0x17eb0 | Chama função 0x17974 |
| BL2 0x179a8 | Zera AP 0x15900108 antes da configuração selecionada |
| BL2 0x179e4–0x179f0 | Lê AP 0x15900108 e repete enquanto zero |
| BL2 0x179f8–0x17a0c | Faz **nova leitura**, soma 0x02039000 em W e guarda X estendido com zeros em estado 0x31a48 |
| BL2 0x17a50 | Zera AP 0x15900108 após chamadas e outras escritas |
| BL2 0x17fe8 | Atualiza o ponteiro NEWTIME em 0x30520 com estado 0x31a48 + 0x1800 |

Os dois polls selecionados não contêm timeout. A amostra que encerra o
poll BL2 e a leitura posterior não são necessariamente iguais. O inspetor
não fornece valores simulados de MMIO e não executa nenhum dos polls.

Se as visões de hardware forem aliases, o consumidor receber a publicação
e o estado for preservado até a atualização, o destino calculado é:

```text
((0x38e00 + 0x02039000) & 0xffffffff) + 0x1800 = 0x02073600
```

Portanto o valor exigido na etapa anterior agora tem um **produtor
estático correspondente**. Isso ainda não comprova a escrita física do
callback NEWTIME em 0x19694: seu frame+136, lookup/linha e ponteiro ativo
continuam dependentes da execução e das chamadas.

## Consumidor DRAM no payload Thumb

Em **0x3f558–0x3f588**, dois produtores MOVW/MOVT endereçam locais
**0x3a600** e **0x3a604**. Dois LDRs de 32 bits leem baixo/alto e os
comparam com **0x60000110** e **0x00010008**. A assinatura combinada é
**0x0001000860000110**, igual à comparada no BL2 e no
[consumidor público devfreq](bl2-kernel-consumers-hzc2.md).

Sob o alias SRAM, local 0x3a600 corresponde a AP **0x02073600**.
Esse local fica **fora** do intervalo inicializado pela segunda cópia,
que termina em 0x39800 local. Não converter essa leitura em offset de
arquivo, conteúdo inicial, amostra atômica ou geometria observada.

## Validação e próximo passo

```bash
python3 scripts/inspect_acpm_handshake_hzc2.py /caminho/sboot.bin /caminho/exynos2100.dts
python3 scripts/check_acpm_handshake_gnu.py /caminho/sboot.bin /caminho/exynos2100.dts
python3 -m unittest discover -s scripts -p 'test_bl2*.py' -v
```

[Relatório estático](references/acpm-handshake-hzc2.json) e
[GNU 2.44](references/acpm-handshake-gnu-hzc2.json): **100 palavras
AArch64, 141 instruções Thumb/168 halfwords**, 10+14 alvos relativos,
15 referências Thumb a literais, 34 operandos selecionados e 22 spans de
literais. Ambos reproduzidos byte a byte. **70 regressões BL2 passaram**;
[12 recusas CLI](references/acpm-handshake-validation.json) cobrem imagem
e DTS curtos, longos e alterados nos dois comandos, exit 2 sem JSON parcial.

Próximo: seguir lookup/linha NEWTIME e preservação do argumento/célula de
destino; corroborar os aliases por uma fonte correspondente ou observação
verificável. Demais escritores/slots, registros reais, RAM/reservas/FDT e
contrato de entrada permanecem abertos. Sem novo QEMU, kernel completo,
execução de firmware ou operação no telefone.
