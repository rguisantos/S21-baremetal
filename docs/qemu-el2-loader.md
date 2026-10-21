# Contêiner → EL2 → main R10 em uma CPU

Marco validado em 2026-10-20 (America/Campo_Grande). Agora existe um teste que materializa o S21R10 e inicia a **main de produção** do R10. Ele usa firmware sintético QEMU, não o shim Samsung legado.

## Reprodução

```bash
python3 scripts/test_payload_stage.py
python3 scripts/test_payload_loader.py
```

Requer Linux, Python 3, cc/readelf e o toolchain/QEMU usados pelo kit. O segundo script faz um build isolado e inicia efetivamente QEMU virt com GICv3, uma CPU e virtualização habilitada. A observação GDB usa stdin/stdout por pipes; não exige sockets locais, servidor TCP ou pacote GDB externo. A UART do emulador fica em arquivo separado.

Assinaturas observadas:

```text
EL2 MATERIALIZE PASS: exact PT_LOADs, BSS, stacks, FDT and guards
R10 CONTAINER HANDOFF PASS: production main at EL1, raw FDT, ... timer IRQs
EL2 REJECT PASS: bad-magic, destination untouched
EL2 REJECT PASS: protected-destination, destination untouched
EL2 REJECT PASS: different-fdt, destination untouched
EL2 REJECT PASS: reserved-ram, destination untouched
EL1 ENTRY REJECT PASS: before BSS clear, destination untouched
PAYLOAD LOADER QEMU PASS: 1 production handoff + 5 refusal cases, one CPU
```

O número exato de IRQs varia; o teste exige pelo menos cinco. As execuções observadas receberam aproximadamente 24–25 IRQs antes da pausa de inspeção. Não há inferência de sucesso apenas por timeout ou mensagem de boot.

## Caminho exercitado

1. Um ELF de firmware de teste é carregado pelo QEMU em 0x44000000. Seu PT_LOAD inclui BSS, workspace e pilha de 16 KiB. A entrada assembly exige EL2 e MMU/D-cache de EL2/EL1 desligadas antes de BSS/pilha; instala vetores EL2 de parada.
2. Esse firmware contém uma cópia própria do FDT de teste e uma cópia separada do contêiner. O FDT confiável não é obtido aceitando a declaração do próprio payload. O fixture descreve uma CPU, RAM QEMU de 128 MiB, GIC/timer do emulador e reserva uma página em 0x47f00000 para testes de rejeição.
3. `payload_stage()` valida o formato, exige igualdade do FDT empacotado com o FDT confiável e confere toda a janela de destino contra RAM, reservas/initrd, fonte, FDT original e intervalos protegidos. A região do firmware inclui código, dados, contêiner e pilha. A cópia recebe uma janela explicitamente possuída pelo chamador.
4. Somente após essas verificações, a etapa zera a janela inteira (BSS, pilhas, buracos e padding), copia os bytes exatos de cada segmento e copia o FDT para kernel_end. Contagens não são arredondadas para acessos de 64 bits.
5. O firmware faz limpeza por VA até PoC, DSB, invalidação de I-cache e ISB; configura apenas o GIC sintético que ele possui e transfere controle ainda em EL2, com x0=FDT físico e x1..x3=0.
6. A entrada **real** `_start_r10` faz o caminho EL2→EL1 e chama `r10_el1_entry` de produção. Parser, política FDT, GIC, timer e dispatcher também são os de produção. Somente o backend UART foi substituído por PL011 QEMU, com um registrador de observação de CurrentEL; secundárias ficam estacionadas.

O ELF R10 de teste é linkado em 0x40080000 e empacotado por tools/mkpayload.py; não se copia o arquivo ELF bruto como código. O shim padrão continua em quarentena e loader_boot permanece desativado.

## O que é conferido por fora do payload

O harness GDB pausa em loader_enter antes da primeira instrução R10. Compara **todos os bytes da janela** contra uma reconstrução independente dos PT_LOAD do ELF e do FDT, incluindo BSS/pilhas zeradas, e verifica canários imediatamente antes/depois. Depois libera a CPU e lê os símbolos de memória:

- loader_observed_el=8 (CurrentEL de EL2);
- r10_boot_status=1;
- g_fdt igual ao endereço onde o FDT foi copiado;
- r10_qemu_observed_el=4 (CurrentEL de EL1, observado pelo backend UART);
- r10_timer_ticks ≥ 5 pelo dispatcher/IRQ reais.

Para entradas inválidas, toda a janela é inicialmente preenchida com 0xa5 pelo harness. Depois da recusa, ele compara a janela inteira e os canários. Para entrada por EL1, QEMU é iniciado sem EL2, e um marcador na BSS do carregador comprova que o clear não ocorreu antes da recusa.

## API da etapa de cópia

`shim/payload_stage.h` descreve a API. O chamador fornece FDT e intervalos protegidos confiáveis, MPIDR, posição física da fonte e um mapeamento de destino com capacidade explícita. Deve possuir a janela inteira e manter contexto/workspace fora dela. A API é single-thread e exige execução antes de IRQs/SMP. Ela não configura hardware, faz manutenção de cache ou executa a imagem; essas tarefas pertencem ao chamador. No momento, só é ligada ao firmware de teste QEMU.

`test_payload_stage.py` exercita a implementação C com ASan/UBSan: **17 casos PASS**, incluindo cópias/tails não múltiplos de oito, guards, fonte/destino sobrepostos, destino protegido, RAM reservada/ausente/incompleta, FDT divergente, capacidade curta e saída aliased. Entradas recusadas não alteram a janela ou a fonte. Uma saída aliased é recusada sem invalidá-la por escrita.

## Limites

O sucesso cobre uma CPU e o modelo QEMU. Cache maintenance emitida/executada no emulador não comprova coerência de caches do Exynos. O teste não usa sboot, Harx, USI ou um caminho Android/fastboot; não valida firmware Samsung, EL de entrada real, bancos/reservas do telefone, SMP ou display. O protocolo v1 continua sem autenticação e sem flags de permissões no wire; o produtor verifica permissões no ELF, mas o consumidor não pode recuperá-las do contêiner.

O próximo trabalho para o aparelho é fechar seu contrato de entrada/memória e canal de diagnóstico. O caminho de firmware real precisa fornecer as garantias que aqui são explícitas e controladas. Não foi habilitado flash ou chainload no S21.
