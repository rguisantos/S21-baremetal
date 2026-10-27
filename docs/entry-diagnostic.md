# Diagnóstico de entrada EL1/EL2

Implementado e testado em QEMU em 2026-10-21. **Não executado no telefone.**

A análise estática do [LK HZC2](sboot-layout-hzc2.md) mostra uma normalização
para EL1h na entrada do LK; isso não mede o EL do salto final para o kernel.
O R10 de produção continua exigindo EL2. Este diagnóstico separado permite
observar uma entrada em EL1 ou EL2 sem antecipar a decisão de adaptar o R10.

## Comportamento

`r8/entry_diag/start.S` é independente de R10 e do shim. Produz um Image ARM64
com cabeçalho de 64 bytes, `text_offset=0x80000`, tamanho completo incluindo
registro, little-endian, página não especificada e bit de posicionamento 3.
Não tem stub EFI, contêiner Android, assinatura Samsung ou suporte Odin.
Referência do cabeçalho e contrato genérico:
[Booting AArch64 Linux](https://www.kernel.org/doc/html/latest/arch/arm64/booting.html).
Esse contrato admite EL1 ou EL2; ele não demonstra o comportamento Samsung.

O código lê CurrentEL e DAIF, mascara interrupções, seleciona SCTLR_EL1 ou
SCTLR_EL2 e recusa a gravação se M ou C estiver ligado. EL diferente de 1/2
também estaciona sem gravar. Na recusa, x4 conserva CurrentEL, x5 o DAIF
original e, para EL1/EL2, x6 o SCTLR consultado, visíveis por debugger.
Não instala VBAR nem trata traps impostos por firmware em nível superior.

Na entrada aceita, registra o estado em 128 bytes **dentro da própria imagem**
e estaciona em WFE. Não usa pilha, limpa BSS, troca EL, modifica MMU/cache,
dereferencia FDT, faz SMC/HVC ou acessa UART/GIC/timer. Não chama o R10.
Requer uma CPU, RAM gravável pertencente à imagem inteira e código coerente
fornecido pelo carregador. Não descobre nem valida RAM livre no aparelho.

## Registro v1

Todos os valores são little-endian. `diag_record` é relativo à imagem e
alinhado a 64 bytes; sua posição exata vem do ELF da mesma compilação.

| Offset | Tamanho | Campo |
|---|---:|---|
| 0 | 8 | `S21ENTRY`, marcador escrito por último após DSB |
| 8 | 4 | Versão: 1 |
| 12 | 4 | Tamanho: 128 |
| 16–47 | 4 × 8 | x0, x1, x2, x3 recebidos |
| 48 | 8 | CurrentEL bruto (4 = EL1, 8 = EL2) |
| 56 | 8 | DAIF antes do mascaramento |
| 64 | 8 | SCTLR do EL de entrada |
| 72 | 8 | MPIDR_EL1 |
| 80 | 8 | SPSel |
| 88 | 8 | SP recebido, sem utilizá-lo |
| 96 | 8 | Endereço efetivo do início do Image |
| 104 | 8 | Endereço efetivo do registro |
| 112–127 | 16 | Reservado, zero |

x0 é apenas um valor registrado: não é certificado como FDT válido.
O marcador não é prova de persistência após reinício nem autenticação.

O [contrato consolidado Samsung](samsung-diagnostic-contract.md) agora reúne
percurso de carga, posse/coerência, recuperação e bloqueios do último estado
informado. Inclui o leitor offline dos 128 bytes e capturas completas QEMU;
consistência de bytes não comprova origem ou frescor do registro.

## Reprodução e evidência

```bash
python3 scripts/test_entry_diag.py
make -C r8 build/entry_diag.elf build/entry_diag.Image
```

O teste usa QEMU 10.0.13 `virt`, uma CPU e GDB por stdio. QEMU carrega o
**Image bruto**, não o ELF, e seu stub chega à entrada em EL1
(`virtualization=off`) ou EL2 (`on`). O debugger então fornece argumentos
distintos e um SP deliberadamente inadequado para uso como pilha.

Matriz executada: EL1/EL2 × deslocamentos 0, 0x8000, 0x1f8000: **6/6 PASS**.
Nos casos deslocados o debugger copia a mesma imagem e altera PC; isso testa
independência de endereço do código, não relocação pelo LK. Os deslocamentos
correspondem a exemplos da faixa encontrada na análise HZC2, aplicados à RAM
QEMU. Não são uma afirmação de conformidade desses endereços com a regra
genérica de base alinhada a 2 MiB do protocolo Linux.

São conferidos argumentos completos, EL, DAIF, M/C desligados, SPSel, SP,
endereços efetivos, versão/tamanho, campos reservados, código intacto e
sentinelas antes/depois da imagem. O ponteiro x0 inválido verifica que não há
leitura do FDT. MPIDR é capturado, mas sua topologia não é validada neste teste.
A matriz original não exercitava as recusas. A recusa por C ligado foi
coberta na atualização abaixo; M ligado foi coberto na atualização de MMU abaixo; EL não suportado continua sem teste. Não há teste SMP, Samsung ou preservação após reset.

## Próximo bloqueio concreto

O registro permanece apenas na RAM; não há transporte funcional de saída no
telefone. Antes de qualquer execução física, faltam um caminho de carregamento
Samsung verificado, propriedade da região da imagem e um canal para recuperar
o registro sem depender da UART USI ainda não inicializada. Não existe comando
de flash/chainload autorizado tecnicamente por este teste.

Nenhum novo arquivo é necessário para continuar a análise estática: BL e
fontes já recebidos bastam para seguir o caminho de preparação/salto. Um FDT
**dinâmico** e uma captura real do estado de entrada continuam evidências
pendentes; Shizuku sem root não superou as permissões do aparelho, portanto
não repetir a mesma coleta como se ela pudesse fornecê-las.

## Cobertura ampliada dos deslocamentos HZC2

`python3 scripts/test_entry_diag.py --all-offsets` executou **128/128 PASS**,
EL1/EL2 e todos os 64 offsets de 32 KiB. O modo padrão continua com seis casos.
As mesmas limitações da injeção por GDB se aplicam; a evidência de ligação
entre cópia e salto está em [lk-kernel-copy.md](lk-kernel-copy.md).

## Recusa com SCTLR.C ligado — teste adicionado

O harness agora compila `r8/tests/entry_diag_state.S` (nome atual da fixture ampliada) como fixture independente.
Após o stub Linux do QEMU chegar à entrada, GDB coloca essa fixture numa área
separada de RAM e aponta PC para ela. A fixture lê o SCTLR correspondente ao
CurrentEL, liga C com MRS/ORR/MSR, executa ISB e salta para a Image via x17.
Ela não usa a pilha nem grava na Image. x0–x3 continuam intactos.

A mesma Image de diagnóstico de produção foi testada nos dois níveis:
**EL1 e EL2 recusaram a entrada**, chegando a `diag_refused`. O harness
confere x4=CurrentEL, x5=DAIF original e x6 com C=1/M=0, os argumentos,
SP, DAIF mascarado, registro inteiro ainda preenchido com 0xa5, código e
sentinelas. Isso verifica que a recusa ocorre antes de qualquer gravação
no registro; não é uma simulação de retorno injetado em x6.

O bit C fica ligado com MMU desligada. Esse cenário testa a condição de
entrada e não cria nem comprova linhas sujas de cache ou manutenção correta
de cache herdado. Naquele teste de cache, MMU ligada, entrada EL3 e traps de firmware superior
ficavam fora da cobertura; a atualização seguinte cobre MMU ligada. Não houve execução no telefone.

Reprodução padrão: `python3 scripts/test_entry_diag.py` — seis entradas
aceitas e duas recusas PASS. O modo `--all-offsets` mantém as 128 entradas
aceitas e acrescenta duas recusas. Não houve alteração no contrato EL2 do R10
nem na lógica da Image; a mudança está na fixture e na verificação.

## MMU ligada — etapa 1 do roadmap

A fixture `entry_diag_state.S` agora recebe os bits M/C em x16 e o destino
em x17. Para M=1, configura MAIR, TCR e TTBR0 do EL atual, barreiras e TLBI,
e liga a tradução com MSR/ISB. Não usa pilha ou periféricos. O harness grava
as tabelas antes de iniciar a fixture, em RAM separada da Image:

| Estrutura | Local e conteúdo relevante |
|---|---|
| L0 | 0x40040000; entrada 0 → tabela em 0x40041000 |
| L1 | 0x40041000; entrada 1 → bloco 0x40000000 de 1 GiB |
| Bloco | AF=1, Inner Shareable, Attr0 normal WB, EL atual read-only, executável |
| TCR | VA 48 bits, granule 4 KiB, PA 40 bits; EPD1 em EL1, RES1 corretos em EL2 |

Só [0x40000000,0x80000000) é mapeado, por identidade. A fixture e a Image
ficam dentro desse bloco. O SP deliberadamente inadequado continua sem uso.
A configuração é somente do QEMU, sem relação presumida com RAM livre Samsung.

Antes do salto, AT S1E1R/S1E2R confirma a tradução de leitura do destino;
AT S1E1W/S1E2W confirma a falha de escrita pelo AP read-only
(FST=0x0d, permission fault no nível 1). Os dois PAR
são preservados em x12/x13 até o breakpoint de recusa e conferidos pelo
harness. Isso verifica a tradução real, além de observar SCTLR.M ligado.

Executado `python3 scripts/test_entry_diag.py`: **12 casos PASS** — seis
entradas aceitas, mais C, M e M|C em cada EL (seis recusas). Em todas as
recusas: registro 0xa5 intacto, código/sentinelas/argumentos/SP preservados,
CurrentEL e DAIF conferidos. Nos casos M, tabelas intactas, leitura traduzida
para o PA esperado e escrita recusada. A fixture foi ampliada; a Image de
produção não mudou.

O modo `--all-offsets` passa a combinar 128 entradas aceitas com essas seis
recusas. A execução desta atualização usou o modo padrão; as 128 entradas
aceitas foram verificadas na etapa anterior, sem claim de nova execução completa.

Limites: entrada EL3 não exercitada; EL0 não é uma entrada suportada e pode
trapear antes de ler CurrentEL. Traps de firmware superior, stage-2, linhas
sujas de cache herdadas e perda de energia não são simulados. Recusar antes
de escrever não estabelece por si só um carregamento Samsung funcional.

As constantes de TCR foram conferidas nos arquivos do Kernel.tar.gz recebido:
`arch/arm64/include/asm/kvm_arm.h` (TCR_EL2_RES1, PS_40B) e
`arch/arm64/include/asm/pgtable-hwdef.h` (EPD1, granularidade e cacheability).
