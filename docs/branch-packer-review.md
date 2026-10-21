# Revisão do relatório S21R10 do branch kilo

Conferência em 2026-10-20 (America/Campo_Grande). Branch `kilo/slim-fjord-u2q` fixado em **9dca3969cc6e6ff571cbfd1cc440f7b27ac93143**; base main examinada **fd38e3c188b05dd82ad94aad040cd5faf1416001**. O relatório colado pelo usuário não representa o empacotador validado da main.

## Falhas reproduzidas

O [empacotador desse branch](https://github.com/rguisantos/S21-baremetal/blob/9dca3969cc6e6ff571cbfd1cc440f7b27ac93143/tools/mkpayload.py) foi executado isoladamente em diretório temporário, com o ELF R10 atual e DTB gerado pelas fixtures. Nenhum contêiner foi carregado em hardware.

| Achado | Resultado observado | Consequência |
|---|---|---|
| ELF tratado como imagem plana | Um segmento contém o arquivo ELF inteiro; bytes na entrada seriam 7f454c46 | O loader copiaria o cabeçalho ELF em vez das instruções dos PT_LOAD |
| kernel_end relativo | 0x18000, enquanto o ELF examinado termina em 0x800c4000 | Com phys_base=virt_base, o loader legado colocaria o DTB em 0x18000 |
| Extensão de memória incorreta | vmsize deriva do tamanho do arquivo ELF, não de p_memsz | Não representa corretamente BSS/pilhas nem os dois PT_LOAD do R10 atual |
| Memória presumida | mem_size=0x80000000 (2 GiB), fixo | Não corresponde a RAM/reservas comprovadas pelo DTB |
| Entrada fixa | entry_va=0x80080000, apesar de haver função read_elf_entry | Não usa de fato o entry point do ELF; alternativas de link não são respeitadas |

O tamanho do ELF dessa reprodução foi 97.680 bytes, e não os 93.096 do resumo; tamanhos variam entre revisões. O problema é a interpretação do formato, não a diferença de tamanho.

O [validador do branch](https://github.com/rguisantos/S21-baremetal/blob/9dca3969cc6e6ff571cbfd1cc440f7b27ac93143/tools/validate_payload.c), compilado nativamente com ASan/UBSan:

- Retornou exit 0 e imprimiu ALL CHECKS PASSED para o contêiner defeituoso acima.
- Com entrada de apenas quatro bytes, retornou erro com diagnóstico ASan heap-buffer-overflow. O código acessa o header antes de verificar o tamanho mínimo; também percorre segmentos sem limitar previamente a tabela e usa strlen sem comprovar terminação.

O consumidor da main recusou o mesmo artefato com exit 1, sem diagnóstico de sanitizer. A suíte ganhou um caso explícito para kernel_end relativo e passou em **60 casos**. As fixtures já verificam independentemente os bytes dos PT_LOAD e a extensão completa das pilhas do ELF real.

## O que realmente existe na main

- O ELF R10 atual tem dois PT_LOAD: código RX e memória RW com BSS/pilhas. O produtor lê program headers, preserva cada segmento e não grava o arquivo ELF bruto como código.
- A janela de destino é calculada da extensão da imagem mais FDT, sujeita a limites, sem assumir 2 GiB disponíveis.
- Não há página de boot_args XNU. Cmdline é metadado do contêiner; o futuro R10 precisa receber um FDT bruto em x0.
- O produtor está em tools/mkpayload.py; o consumidor real está em shim/payload.c e o CLI de teste em shim/tests/payload_probe.c. O tools/validate_payload.c citado pertence ao outro branch.
- O loader legado está desativado, e o shim padrão estaciona antes de BSS/pilha/MMIO.

Uso correto para a CLI atual, apenas para inspeção:

```bash
python3 tools/mkpayload.py r8/build/r10_payload.elf --dtb test.dtb -o payload.bin
python3 scripts/test_payload.py
```

O argumento ELF é posicional; `--kernel` pertence ao outro empacotador. O FDT precisa ser bruto e estruturalmente válido; o contêiner não corrige uma descrição incompleta de RAM.

## Comandos do relatório não demonstram SMP ou chainload

`make -C r8 run_r10 QEMU_ARGS='-smp 4'` foi conferido: o alvo apenas imprime uma mensagem sobre o ELF e não inicia QEMU. Isso também ocorre no Makefile do branch analisado. Logo, o comando não testa CPU_ON, SGIs/IPIs ou GIC por CPU.

Os PASS de R8/R9 demonstram seus próprios testes; não se transferem automaticamente ao shim, empacotador ou payload no telefone. Na revisão desse branch ainda faltava testar o carregador EL2. Esse teste foi posteriormente concluído em uma CPU, com main real e FDT bruto: [qemu-el2-loader.md](qemu-el2-loader.md). Isso não altera as falhas do branch nem prova SMP ou Samsung.

`fastboot boot shim/build/shim.elf` não é um caminho demonstrado neste Samsung; desbloqueio sozinho não fornece suporte a carregar esse ELF. A afirmação sobre DECON em 0x19050000 também não foi validada por esta análise e não foi incorporada como endereço confirmado.

Foram preservadas as correções da main, sem mesclar o estado anterior desse branch. Especificação e testes atuais: [payload-format.md](payload-format.md). Evidência do Proton Linux/EFI: [proton-binary.md](proton-binary.md). Nenhuma operação no telefone foi realizada.

## PR #4 resolvido — 2026-10-21 UTC

O PR #4 apresentou o mesmo head 9dca3969cc6e6ff571cbfd1cc440f7b27ac93143 aqui auditado. Revisado e encerrado como substituído pela implementação atual na main, sem merge; branch preservado. Confirmado novamente overflow com entrada de quatro bytes no validador antigo. A main passou em 60 casos de contêiner e na integração QEMU com um handoff e cinco recusas. Justificativa registrada no corpo do [PR](https://github.com/rguisantos/S21-baremetal/pull/4).

## Atualização do branch: f624360

Conferido em 2026-10-21: os commits f6556bb/f624360 após 9dca396 alteram somente README.md e EXYNOS2100_HARDWARE.md. Packer/validador e alvo run_r10 continuam iguais. O novo relatório “sboot analysis complete” contém afirmações e offsets incorretos; a revisão com o binário HZC2 está em [sboot-layout-hzc2.md](sboot-layout-hzc2.md). Não foi reaberto o PR #4 nem incorporada essa documentação como evidência confirmada.
