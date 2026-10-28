> Registro da integração anterior. As pendências de entrada/FDT, dispatcher
> e acessos GIC receberam correções posteriores; o estado atual está em
> [docs/r10-single-cpu.md](docs/r10-single-cpu.md).

# Integração das PRs #2 e #3 — 2026-10-20

A main recebe o histórico da branch kilo/slim-fjord-u2q (incluindo a PR #3)
e a PR #2. A resolução do conflito UART usa os offsets Samsung da PR #2,
acesso de byte a UTXH/URXH, TXFULL no bit 24 de UFSTAT, CR antes de LF,
limite de polling e buffer hexadecimal de 19 bytes.

A inicialização UART não programa clock, divisor, pinmux ou reset USI
presumidos. Por padrão não acessa MMIO. R10_UART_FIRMWARE_CONFIGURED só pode
ser definido quando um carregador tiver configurado e verificado essa
instância com FIFO habilitado. Isso é um pré-requisito externo, não uma
configuração que este código detecta automaticamente.

## Reprodução

- `make -C r8 BUILD=build-review all`: compila R8A, R8B, R8C, R9 e R10.
- `make -C r8 BUILD=build-review regress`: regressão QEMU R8A/B/C e R9.
- `bash scripts/test_pr_fixes.sh`: UART no host com ASan/UBSan, habilitada e
  desabilitada; primitivas atômicas reais da PR #3 em QEMU AArch64.
- `bash shim/build.sh`: compila o shim experimental.

O runtime do cross-binutils expõe somente suas bibliotecas específicas,
sem substituir a libc do host. O QEMU usa explicitamente seu loader e suas
bibliotecas. Caminhos fixos de outro workspace foram removidos. Há avisos
preexistentes de compilação; não é um build sem warnings.

## Limites da validação

O teste atômico é de uma CPU: verifica operandos, resultados, CAS bem e
malsucedido, test-and-set, ticket lock e exclusão reader/writer. Não prova
contenção entre CPUs nem o bring-up SMP do telefone. O QEMU virt não emula
o Exynos 2100. O shim compila, mas seu boot não foi validado.

Continuam pendentes: contrato de entrada EL2/EL1 e passagem FDT, topologia
MPIDR real, descoberta/configuração do GICR, auditoria do GIC (inclusive
endereços absolutos versus offsets), concorrência dos slots de chamadas
entre CPUs, tratamento de CPUs offline, clock/pinmux/USI e testes físicos.
A UART própria do shim também permanece experimental e não é coberta pelos
testes do driver R10. A integração na main não declara prontidão para
flash/chainload e não executa nenhuma operação no telefone.

## Resultado desta execução

- Build separado dos cinco ELFs: passou.
- Regressão: **4/4 PASS** (R8A, R8B, R8C, R9).
- Testes UART: **2/2 PASS** com AddressSanitizer/UBSan. LeakSanitizer
  desativado por limitação de `/proc` neste ambiente; não há alocações nos testes.
- Teste AArch64: **ATOMIC PASS**, encerrado pelo timeout esperado após park.
- Shim: ELF e binário compilados; execução não testada.

## PR #4 — substituído, não mergeado

Em 2026-10-21 UTC, revisado head 9dca3969cc6e6ff571cbfd1cc440f7b27ac93143. O packer/validador antigo e as afirmações sobre Proton já têm substitutos corrigidos na main. PR encerrado com justificativa, preservando o branch e evitando regressão. Evidências em [branch-packer-review](docs/branch-packer-review.md) e [continuação BL](docs/bootloader-hzc2.md).

## PR #5 — revisão e merge do protocolo EPBL

Revisado o head `636c56a4dc36f029afe966de4404aa8b7659c2d1`: revisão automática
concluída sem achados e sem threads pendentes; conferência do diff, dos
limites dos decodificadores e das evidências de 69 testes/GNU. Revisão registrada
no PR. Merge autorizado pelo usuário e executado em
`2df91f32fba86b6b8cb115146463da13661da4a4`; main local sincronizada.

A orientação permanente inclui concluir revisão, corrigir bloqueadores e
fazer o merge do head revisado, conforme [AGENTS.md](AGENTS.md). Não encerrar
uma entrega concluída apenas com PR aberto. A continuação técnica e a correção
dos nomes dos contadores estão em [proveniência HASH](docs/epbl-hash-provenance-hzc2.md).

## PR #6 — revisão e merge da proveniência HASH

Revisão própria registrada no head `c8f41e03781bf9aca19bf4f9684e5160f9f45bb1`,
com diff, limites das referências, 83 testes e evidência GNU conferidos. Sem
achados bloqueadores ou discussões pendentes no momento do merge. Nenhum
status CI configurado foi reportado. Merge em
`65040a6017280cb8c2bb4fac9808119f1bda0540`, main sincronizada antes da
continuação TZAR. Esta é revisão própria; não declara aprovação automática
externa do PR #6.

## PR #7 — revisão própria e merge do TZAR

Head `afec5aba6e4cf4b56064e226ace7bddc761ac116` conferido por revisão
própria registrada: 15 testes, GNU e os 14 blobs publicados coincidem com
a árvore validada. Sem threads ou status de falha reportados. A revisão
automática ainda informava running e não foi considerada aprovada.
Merge normal do head revisado em
`2f31df480b2e6731db38a002ab26ca4bc270a3d9`, sem contornar regras do GitHub.
Main local sincronizada e limpa. Na retomada desta continuação, a revisão
automática seguia pendente e não havia apontamentos ou threads adicionais.

## PR #8 — ligação ioctl e confirmação da revisão automática

Head `fd78916670c71263cb3e1d46f351c028dcb313cc`, revisão própria registrada,
30 testes e GNU conferidos. Merge normal em
`cd8b5124f19c68a1e040d3564f08d8c9d95044fd`, main sincronizada e limpa.
Na integração, a revisão automática ainda estava pendente. Na retomada
desta continuação, foi confirmada como completed, has_any_findings=false
e has_unresolved_findings=false, para o mesmo head. Sem threads pendentes.
A revisão automática do PR #7 ainda informava running nesta conferência.

## PR #9 — BiEn/TZSW e validação de candidatos

Head `383656d88452c5c5467d3e0064b78ef72d0dad53`, revisão própria e automática
concluídas sem achados ou threads pendentes, com 15 testes e o ensaio AES
negativo conferidos. Merge normal em
`169d704ba19af808c0295b1d4048e20c6899d498`; main local sincronizada e limpa
antes da continuação sobre o produtor de RAM no BL2. O ensaio não aceitou
plaintext HZC2 e a integração não declara o handler SVC recuperado.

## PR #10 — produtor BL2 e folha do total de RAM

Head `84b5692855da602aa922dcff46d35c60cd8b58a3`, revisão própria e automática
concluídas sem achados, sem threads pendentes. Os 15 blobs publicados
coincidem com a árvore validada; 34 testes BL2, 73 regressões LK, GNU e
66 execuções isoladas QEMU conferidos. Merge normal em
`b3f8340c3a1d3d1bd9e0b321c1ae62532697cc14`, main sincronizada/limpa antes
da continuação da consulta de geometria. Binding nominal e valores reais
permanecem pendentes; a integração não declara RAM livre ou FDT final.

## PR #11 — consulta de geometria até MMIO

Head `b210c7ffd10cb6b14163a922a649d9f409d41a14`, revisão própria e automática
concluídas sem achados e sem threads pendentes. Os 12 blobs publicados
coincidem com a árvore validada; 48 testes, GNU e planos simbólicos da CLI
conferidos, sem CI configurado. Merge normal em
`5bccfd4192552f2e25070bb53f1a94939d560e55`, main local sincronizada antes
da continuação sobre a reescrita das bases. Os valores iniciais das tabelas
não foram promovidos a estado físico observado.

## PR #12 — reescrita condicional das bases de consulta

Head `33ae7df49dc9aaa013dc7f9604ca1335da415be1`, revisão própria e automática
concluídas sem achados, sem threads ou falhas CI. Os 14 blobs publicados
coincidem com a árvore validada; 58 testes BL2, GNU e planos condicionais
conferidos. Merge normal em `4d4fd72f4fffb2a184d72d6a493df8e791009154`,
main local sincronizada antes da continuação sobre o registro de geometria.
Não foi presumido valor do nibble ou configuração ativa do S21; o ramo
sem escrita preserva o estado anterior, sem restaurar os bytes do arquivo.

## PR #13 — recargas e ciclo parcial do registro de geometria

Head `35d80a1820b2db8e795fb902b104fb33516d3350`, revisão própria e automática
concluídas sem achados, sem threads ou falhas CI reportadas. Os 13 blobs
publicados coincidem com a árvore validada; 70 testes BL2 e GNU de 148
palavras conferidos. Merge normal em
`69940c8e594fc490e1008533aefaab33bda1307c`, main sincronizada antes da
consulta à branch pública do kernel. A integração não identifica os bytes
reais de 0x02073600, os três slots restantes ou o mapa final de RAM.

## PR #14 — referência pública xfwdrev/rebased-11

Head `36708d5f5bbee452e77b55636e235812d7005820`, revisão própria concluída
sem bloqueadores. Oito blobs e árvore publicados coincidem com os
validados; 15 manifestos de fontes, três compilações DTS e duas aplicações
de overlay conferidos. Sem threads ou falhas CI reportadas. A revisão
automática ainda informava running no merge e na retomada; não foi
registrada como aprovação externa.
Merge normal em `51a88288dfdedcb90918b502abb05a64f60942bc`, main local
sincronizada antes da continuação específica das referências BL2. Não
houve build de kernel completo ou execução física.

## PR #15 — consumidores BL2 e correlação do registro DRAM

Head `026f80957bac42c082beced690ed958cde299364`, revisão própria concluída
antes do merge. Dez blobs e árvore conferidos; 12 manifestos de fontes,
14 palavras selecionadas, três formatos bootstat, campo CHIPID e dois
relatórios anteriores reproduzidos sem alteração. Sem threads ou falhas
CI reportadas. Merge normal em
`9cf76c2f1b998b058dfb1493c467ae6b3fc731c8`, main sincronizada.

A revisão automática estava running no merge; nesta continuação foi
conferida como completed, sem achados nem achados pendentes no mesmo head.
A revisão automática do PR #14 ainda informava running. A correlação
kernel/BL2 não observou o registro físico ou o FDT final.

## PR #16 — callback NEWTIME e argumentos bootstat

Head `07915387ae527b129ad616bb16136ba89db3e471`, revisão própria
5639681447 concluída sem bloqueadores. Treze blobs e árvore conferidos;
GNU de 156 palavras/26 alvos/39 operandos, 70 regressões BL2 e seis recusas
CLI. Revisão automática completed sem achados ou pendências no mesmo
head; zero threads, statuses e check-runs. Merge normal em
`83fad63f4034366d771435c6ebf2005fd7ec8f04`, main sincronizada.
Sem valores físicos, execução de firmware ou contrato de RAM final.

## PR #17 — publicação ACPM e destino NEWTIME condicional

Head `46dbd460dc54ca5fa4df50466389968b165e791c`, revisão própria
5640034407 concluída sem bloqueadores. Treze blobs/árvore conferidos;
GNU100 palavras AArch64/141 instruções Thumb, 70 regressões BL2 e 12
recusas CLI. Zero threads ou falhas CI reportadas. A revisão automática
estava running no merge; nesta continuação foi conferida completed, sem
achados ou pendências nesse mesmo head. Merge normal em
`be47018c54773836d493f21e761a12bd8faef237`, main local sincronizada.
Aliases/preservação condicionais; sem handshake ou registro físico observado.

## PR #18 — tabela ECT/NEWTIME e prefixo original no QEMU

Head `a7c19d09fc1948d38b707fffd7565ecadd291bb2`, revisão própria
5640103451 concluída sem bloqueadores. Dezoito blobs e árvore conferidos;
56 casos QEMU, GNU353 palavras/50 alvos/24 operandos, 80 testes de host
e nove recusas CLI passaram. Sem threads ou falhas CI reportadas.
A revisão automática estava running no merge; a consulta posterior
confirmou completed sem achados ou pendências no mesmo head. Merge normal
em `e9a8344a9a4975a63c6970bf964bb74198196b5c`, main sincronizada.
Bindings de laboratório; sem execução física, registro real ou FDT final.


## PR #19 — ciclo condicional e erros parciais NEWTIME

Head `d5db0ba996ceec113aaefafe1f2da087babb66af`, revisão própria
5640215333 concluída sem bloqueadores. Dezessete blobs e árvore conferidos;
196 casos QEMU com ramos explícitos, seis da folha do alocador, GNU de 623
palavras e 92 testes de host passaram. Zero threads ou falhas CI reportadas.
A revisão automática estava running no merge; nesta continuação foi
conferida completed sem achados ou pendências nesse mesmo head. Merge
normal em `7723fbdbe00a819b7f0239900e7990555102264a`, main sincronizada.
Não executou gate MMIO ou helper externo completo, nem observou estado físico.


## PR #20 — flags NEWTIME, dump e depuração

Head `c48ed5f3597f243fedfb39268ebfb8044deb9535`, revisão própria
5640646109 concluída sem bloqueadores. Dezesseis blobs e árvore conferidos;
26 dumps e 14 fragmentos de flags no QEMU, GNU de 662 palavras e 101 testes
de host passaram. Zero threads, statuses ou check-runs reportados no merge.
A revisão automática estava running; após o merge foi conferida completed
sem achados ou pendências nesse mesmo head. Merge normal em
`6c4e6dad3db388e92c4ebd24153abf4f09f4541f`, main sincronizada e limpa.
Não executou UART, rotina de depuração ou helper externo completo;
preservação do registro físico e efeitos transitivos continuam abertos.


## PR #21 — empacotamento posterior da geometria

Head `0469ec8b8cccce1efc2b7f70c02279d94cfa2e66`, revisão própria
5640714443 concluída sem bloqueadores. Dezoito blobs e árvore conferidos;
100 cenários QEMU com retornos fornecidos e 100 execuções subsequentes da
folha, GNU de 386 palavras e 111 testes passaram. Zero threads, statuses
ou check-runs reportados no merge. Revisão automática ainda running no
merge; consulta posterior confirmou completed sem achados ou pendências
no mesmo head. Merge normal em
`70dca683297508bb4be85102a8c63e5fd6c79843`, main sincronizada e limpa.
Não executou consultas/preparação/CHIPID, inicialização Samsung ou telefone;
publicação física e respostas reais continuaram abertas.


## PR #22 — segunda publicação NEWTIME e correção do procedimento

Head `36e631c5d7a9798a9c63c5a9d08662037d48b0e1`, revisão própria
5640767925; dezoito blobs/árvore e validações conferidos. Merge em
`81274a4bcb4d45dc5b7a2a1d85a43ae04a7076bd` enquanto a revisão automática
ainda estava running. Ela concluiu posteriormente, sem achados ou pendências
nesse head; zero threads na conferência desta retomada. Isso não transforma
a revisão posterior numa etapa cumprida antes do merge.

A orientação foi corrigida no AGENTS.md: revisão própria e autorização de
merge não substituem aguardar a revisão automática completed do head exato.
Ausência de status/check-runs não é aprovação. A nova entrega deve cumprir
essa ordem antes de integrar. Evidências anteriores: 119 testes, 160 casos
QEMU (74 stores/86 erros), GNU464 palavras, nove recusas CLI; sem medição física.


## PR #23 — conferência do commit e da ordem de revisão/merge

Conferidos novamente por `git fetch origin main`, `git log` e API GitHub:
head `16191d1dee3f51eadbdd2bc85584535ae0150279`, merge
`566c977f5d976ecfe151d0f43a937b9acaed5d54`, árvore
`4be5f5c5f6691fa872fc129d8810d2bce5af7e4c`. Os dois pais do merge são
`81274a4bcb4d45dc5b7a2a1d85a43ae04a7076bd` e esse head. Na conferência,
main local e origin/main apontavam para o merge, sem alterações locais.

O [comentário automático](https://github.com/rguisantos/S21-baremetal/pull/23#issuecomment-6392031496)
registra `completed`, `has_any_findings=false` e
`has_unresolved_findings=false` para o head exato. Seu `updated_at` é
2026-10-24 21:39:29 -04:00; o `merged_at` é 21:40:34 -04:00, 65 segundos
depois. `updated_at` é a última atualização do comentário, não um campo
dedicado ao instante de conclusão. A sessão também consultou e conferiu
`completed` antes de enviar o merge. Zero threads na nova conferência.
O #23 cumpriu a ordem que o #22 não havia cumprido.

[Extrato verificável dos metadados](docs/references/pr23-review-merge-verification.json).
Revisão própria 5640957518; 128 testes de host, seis casos QEMU e GNU229
registrados na entrega. Nenhuma execução física ou ausência de DEVFREQ
declarada resolvida. Samsung/D1Z/12GB são observações do log do bootloader;
a relação entre os campos de A/B é uma análise estática/laboratorial.


## PR #24 — regra DRAM e cronologia verificadas

Head `dd7833ce3cf7465518ee144038c2b60217261fe3`, revisão própria
5641045529, cinco blobs/árvore `337e23940e31787982760fc74cda567aea712f9f`
conferidos. Nove testes, relatório GNU229 reproduzido, metadados e 697 links.
A revisão automática inicial permaneceu running sem resultado por mais de
15 minutos; solicitada novamente no mesmo head, sem modificar os arquivos,
pelo comentário 6392364030. O registro automático 6392221469 ficou
completed/sem achados ou pendências em atualização de 2026-10-24 22:18:40
-04:00, conferida antes do merge. Zero threads e PR apto à integração.

Merge `0191d5607077678e01c411b271c1c35cc0849f5c` às 22:19:05 -04:00;
main sincronizada e limpa. DRAM observada no log, leitura física e ausência
DEVFREQ mantidas separadas. Não houve execução no telefone.


## PR #25 — callback contínuo e consumidores das colunas 1/12

Head `f1a630463a3ffbe4d8688d59e5cdf461c450634b`, revisão própria
5641368942; 16 blobs e árvore `44dc2bb4c393e1215d8f4e0c291ffbd070e5e660`
conferidos. O [comentário automático](https://github.com/rguisantos/S21-baremetal/pull/25#issuecomment-6393033324)
ficou completed, sem achados ou pendências nesse head, antes do merge.
Seu updated_at é 2026-10-24 23:39:38 -04:00; merge
`17c7e74a3f9ebe8ba5c70b4893916cb83ce2c53b` às 23:41:29 -04:00,
111 segundos depois. updated_at não é um campo dedicado de conclusão;
o estado completed também foi consultado antes de enviar o merge.
Reconferidos comentário e zero threads nesta continuação.

Validação da entrega: 141 testes, quatro execuções contínuas e quatro
controles de orçamento, 12 recusas CLI, GNU188 e cadeia466, quatro
relatórios reproduzidos. Todos os casos contínuos param antes de MMIO;
nenhum retorno completo ou timing físico afirmado. Main sincronizada e
limpa ao concluir aquela integração.


## PR #26 — consumidores e proveniência dos registros

Head `bebedf4dd89668a9b0fd31924fc3647eff0bb7df`, revisão própria
5643432119; 13 blobs e árvore `81348a5e5b8429e0b637d89ebc1918019edc7f61`
conferidos. O [comentário automático](https://github.com/rguisantos/S21-baremetal/pull/26#issuecomment-6398331539)
registrou completed, sem achados ou pendências no head exato. Seu
updated_at é 2026-10-25 09:37:11 -04:00; o merge
`3daf8f33364b9e2d4d9bafdbdd4f28b4d220de58` ocorreu às 09:38:41 -04:00,
90 segundos depois. A sessão consultou completed antes de enviar o merge;
updated_at não é um campo dedicado ao instante de conclusão. Estado e
zero threads reconferidos nesta consolidação.

Entrega estática: 53 testes de host, GNU de 1171 palavras, 12 recusas CLI,
quatro relatórios reproduzidos e 736 links do projeto. Identificado o
leitor da coluna 12, corrigido o fluxo 108→162 e mantidos os limites de
execução, sem afirmar timing físico ou despacho vddcal. Main sincronizada
com a árvore validada e limpa ao concluir a integração.

## PR #27 — plano NEWTIME consolidado

Head `7aa2673a80ca72aa5a04b226d632e5c683b7b69d`, revisão própria
5644674127; sete blobs e árvore `c7ff7d28b806973c4925655b773fd71ce4446886`
conferidos. O comentário automático 6401556729 registrou completed sem
achados ou pendências no head exato, updated_at 2026-10-25 14:37:09 -04:00.
A sessão consultou esse estado e zero threads antes do merge
`eb1f1d78689d1c7872aae4d26b1b5c7da0a5a5ff`, às 14:39:53 -04:00,
164 segundos após aquele updated_at. Esse campo não é um timestamp
exclusivo de conclusão. Não havia checks/statuses com falha.

Entrega documental: GNU1171 reproduzido e 747 links conferidos antes da
publicação. Após recuperação local, sete blobs/árvore/diff reconferidos.
Main sincronizada com o merge e limpa ao concluir a integração.

## PR #28 — recargas e leitor indireto da coluna 1

Head `8d4eb850ed187c5572f1f295c4e35b1e627a3d22`, revisão própria
5644724217; nove blobs e árvore `2656edb65eadb40981b77a5a01f4117305355d9f`
conferidos. O comentário automático 6401727631 registrou completed sem
achados/pendências no head exato, updated_at 2026-10-25 14:53:06 -04:00.
A sessão conferiu esse estado e zero threads antes do merge
`a50a1db2e044da99d54a167eed90c67f276c26f5`, às 14:53:43 -04:00,
37 segundos depois. updated_at não é um timestamp exclusivo de conclusão.
Sem checks/statuses com falha. Main sincronizada com a árvore validada e
limpa ao concluir. GNU324/18 alvos, três recusas CLI, 53 testes e 755 links;
nenhuma execução adicional de firmware.

## PR #29 — binding nominal até a folha SMC

Head `47c7f98cb950c2a67f78492eab57946ed1828efb`, revisão própria
5644820567; doze blobs e árvore `f0c91105b93a66c7a21ba77f3560c6dc1761535d`
conferidos. Comentário automático 6401958074: completed, sem achados ou
pendências no head exato; updated_at 2026-10-25 15:14:01 -04:00. A sessão
consultou esse estado e zero threads antes do merge
`a60cd37183e7891ab446325c6637c8b464d58fef`, às 15:14:21 -04:00,
20 segundos depois. updated_at não é timestamp exclusivo de conclusão.
Sem checks/statuses com falha. Main sincronizada e limpa ao concluir.
GNU324 anteriores mais46/3 alvos/14 operandos, 56 testes, três recusas CLI,
764 links e reprodução exata. Nenhuma SMC ou execução adicional de firmware.

## PR #30 — auditoria parcial do slot47

Head `23ea3f2df37f4562922cd4f0394cf0f84b1029e3`, revisão própria
5644927762; onze blobs e árvore `17cf67ef24f5fdb2582ad0f87b01c1d3721900aa`
conferidos. Comentário automático 6402296891: completed sem achados ou
pendências no head exato, updated_at 2026-10-25 15:45:01 -04:00. A sessão
consultou esse estado e zero threads antes do merge
`dc5e745fc781045ab4849292f03587317bae74dc`, às 15:45:26 -04:00,
25 segundos depois. updated_at não é timestamp exclusivo de conclusão.
Sem checks/statuses com falha. Main sincronizada e limpa ao concluir.
GNU84/3 alvos/22 operandos, 60 testes, três recusas CLI e 772 links;
origem de X0 permaneceu explicitamente aberta, sem nova execução de firmware.

## PR #31 — transportes selecionados da célula NEWTIME

Head `978d780b62593113ea6977a8294eb9d889634dbb`, revisão própria
5645153512; onze blobs e árvore `3adf87758de55ad1a850bbb66d90cbf2e70c743d`
conferidos. Comentário automático 6402956519: completed sem achados ou
pendências no head exato, updated_at 2026-10-25 16:41:04 -04:00. A sessão
consultou esse estado e zero threads antes do merge
`43356de58be84cfaf1b477f1cc8fb9b3b8f7e604`, às 16:41:34 -04:00,
30 segundos depois. updated_at não é timestamp exclusivo de conclusão.
Sem checks/statuses com falha. Main sincronizada e limpa ao concluir.
GNU141/56 alvos/11 operandos, 64 testes NEWTIME mais 16 dos laços, três
recusas CLI e 781 links. Transporte e origem de X0 permaneceram abertos;
nenhuma execução adicional de firmware ou SMC.

## PR #32 — revisão global e prioridade de reprodução

Head `1e6eb7dcd7e097e8ca9c726e08ba11e5907c1f69`, revisão própria
5645528436; nove blobs e árvore `87e0498e3a21f45a2316b433ddad14e4388c52bc`
conferidos. Comentário automático 6403867367: completed sem achados ou
pendências nesse head, instante exibido 2026-10-25 17:57:04.208549 -04:00.
A sessão conferiu esse estado e zero threads antes do merge
`d46e787c51554d090d1f96d61e53462377463aa9`, às 17:57:37 -04:00.
Comentário e threads reconferidos nesta continuação. Sem checks/statuses
com falha; ausência deles não foi usada como aprovação. Main sincronizada
e limpa ao concluir.

Entrega documental: build R10, FDT43, contêiner59 antes/60 após build,
materialização17, diagnóstico12 e loader1+5 com25 IRQs; 791 links.
Baseline obrigatório/CI ficou como próxima implementação, não como código
já existente. Prioridade física voltou ao percurso Samsung e à leitura do
diagnóstico; NEWTIME ficou paralela, sem ampliar execução ou medir telefone.

## PR #33 — baseline obrigatório e CI

Head final `caeb7b3bf8dc76dd77b29508b7fb154bba863a91`, revisão própria
5646937992; árvore `4dde6bcfa61ceb450c5c6ffea6d531d2c4a21089` e 16 blobs
conferidos. A primeira tentativa CI40240373832 falhou na abertura GDB do
diagnóstico e não foi integrada. Correção de NIC/ROM, captura de logs e
limpeza de descendentes validada em novo head; CI40262553431 passou nele.

Comentário automático6404281053 ficou completed sem achados/pendências no
head final, updated_at2026-10-25 23:11:18 -04:00. Estado e zero threads
foram conferidos antes do merge `b70c3a9d1aa3b7fe165f89397b76cdb469d60077`
às23:12:32 -04:00,74segundos depois desse updated_at. Esse campo não é um
timestamp dedicado de conclusão. CI e revisão voltaram a ser exigidos após
a mudança do primeiro head. Main sincronizada e limpa; CI pós-merge
40262929355 também passou em b70c3a9. Metadados reconferidos nesta continuação.

Validação: build novo, host43/60/17, diagnóstico12, loader1+5, sete controles
do runner, CLI/timeouts,16 hashes de logs e800 links. Compatibilidade QEMU10
e8 no laboratório, sem firmware Samsung ou telefone executado.

## PR #34 — contrato Samsung e leitor do registro

Head `4439e686ae18f7664b50180de26b75aa9b47f0d8`, revisão própria5660684329;
14 blobs e árvore `32ec15fe04caee4a5a81c3980d058126fb865b1a` conferidos.
CI40423540199 passou no head. Comentário automático6430238251 ficou
completed sem achados/pendências nesse mesmo head, updated_at2026-10-26
20:02:10 -04:00. Estado e zero threads foram conferidos antes do merge
`715a5e3f0c3b882c981a87f6a5c90a3e91cfb658`, às20:03:17 -04:00,
67segundos após esse updated_at. Esse campo não é um timestamp dedicado
à conclusão. Metadados, zero threads e CI reconferidos nesta continuação.

Main sincronizada e limpa; CI pós-merge40423876014 também passou no merge.
Entrega: matriz de carga/aquisição e leitor offline,17 testes novos, seis
registros QEMU/seis capturas sem marcador, roundtrip de seis snapshots e
baseline completo de nove etapas. Sem firmware Samsung/telefone executado
ou canal físico declarado resolvido.

## PR #35 — perfis fixos e encaminhamento RDX

Head `5bc86ee561a51864d67dea56bff48306248892ee`, revisão própria5660987985;
13 blobs e árvore `6f8a1223a7c89dd1ccec3e35930b202863b4d6df` conferidos.
CI40428755511 passou no head. Comentário automático6430922652 ficou
completed sem achados/pendências no mesmo head, updated_at2026-10-26
20:50:21 -04:00. Estado e zero threads foram conferidos antes do merge
`ce67fc59fde690d779951a2c2f31400c33afd43e`, às20:51:50 -04:00,
89segundos após esse updated_at. Esse campo não é um timestamp dedicado
à conclusão. Metadados e zero threads reconferidos nesta continuação.

Main sincronizada e limpa; CI pós-merge40429068227 também passou no merge.
Entrega: GNU488/103/61,14 testes novos,15 do decoder, reprodução exata,
duas recusas CLI e835 links. Sem firmware/telefone executado ou canal
físico declarado resolvido. A continuação identifica o produtor e a cobertura
nominal dos descritores acrescentados, mantendo a retenção física separada.

## PR #36 — origem da RAM RDX e conclusão da sonda

Head `10fedb344d28d43b2baef76dc00fd6a211b1f06a`, revisão própria5661130032;
13 blobs e árvore `1cf9bf0ad6cd733b1c9df6eda24d5a73a53104d4` conferidos.
Check R10 baseline121949429505 passou no head. Comentário automático
6431258494 ficou completed sem achados/pendências nesse head, updated_at
2026-10-26 21:15:16 -04:00. Estado e zero threads foram conferidos antes
do merge `3cc06d6dc945a47d12964aa77d4d9b92e42e38a2`, às21:16:40 -04:00,
84segundos após aquele updated_at. Esse campo não é timestamp exclusivo
de conclusão. Metadados e zero threads reconferidos nesta continuação.

Main sincronizada e limpa ao concluir;45 testes, GNU839/202/85, dois
relatórios reproduzidos, duas recusas CLI, Image384 e845 links conferidos.
O run pós-merge40431618302 foi encontrado cancelado na instalação das
ferramentas, com baseline skipped; não foi registrado como PASS. Job
121950399793 reexecutado nesta continuação. Isso não altera o PASS do
head do PR antes do merge nem constitui falha observada de um teste.
A segunda tentativa do mesmo run concluiu success no merge3cc06d6,
job121992403220, antes da publicação desta continuação. O cancelamento
inicial continua registrado; a nova tentativa é a validação pós-merge aprovada.

Sem execução Samsung/telefone ou retorno cooperativo introduzido na sonda.

## PR #37 — retorno nominal da Image

Head `5bae6fe4d2e83b8165e9915e0e9394473042bcc5`, revisão própria5661977703;
árvore `c2bfe0da7f509ee728f67f0d53a085d8a06fc7b7`. Comentário automático
6433215200 completed sem achados/pendências no head exato, updated_at
2026-10-26 23:46:07 -04:00. Conferido antes do merge
`0d80be26d95d0d7b77390656be3afa866da26ec4`, às23:47:30 -04:00:83segundos
após aquele campo, que não é timestamp exclusivo da conclusão. Estado e
zero threads reconferidos nesta continuação. CI do head121996875751 e
pós-merge40446128940 passaram. Main sincronizada e limpa ao concluir.

Entrega:29 testes, GNU294/57/58, reprodução de três relatórios, duas
recusas de firmware inválido e859 links. Sem patch de retorno ou execução
do firmware. Esta continuação resolve as rotinas locais de panic, sem
promover recuperação de contexto a captura física demonstrada.

## PRs #38 e #39 — continuação de LK

PR38: head18fcf36c58835c731ba738d452a6570fb0a10045, revisão automática
6434141972 completed sem achados/pendências, zero threads e CI40452698027
success antes do merge3349dbbe9ad4bcc288fcc091c4c2dfbb0d7d13ba.
PR39: head2b9a0e4386a5b33f22ccd7c92c41a08f9f97a279, revisão automática
6434286224 completed sem achados/pendências, zero threads e CI40453651677
success antes do merge42d2bb63e414c5af3701ffab9f15a3c0015a8be4.
CI pós-merge40453852082 reconferido success nesta continuação.

## PR #40 — produtor do bitmap

Head `38e0fff61875c33b3608bc57e3f545073fd60f82`, revisão automática
6441850315 completed sem achados/pendências, CI40503789254 success e zero
threads antes do merge `4546b2457431d6813d9c250251db18ab58a19262`.
CI pós-merge40504139264 conferido success nesta continuação.

## PR #41 — escritor dos modos do token

Head `76d611f90eef3a1ede7889a706dd1752e138189f`, revisão automática
6443214469 completed sem achados/pendências, zero threads e CI40513134170
success antes do merge `436b5397c501b1f37e0f06cd23e52378417f31c7`.
CI pós-merge40513488970 reconferido success nesta continuação.

## PR #42 — observações do bugreport e cenário de bancos

Head `0bf198bd8b2bfb534b437e9dea25ee355dce5943`, revisão automática
6455347436 completed sem achados/pendências, zero threads e CI40596457728
success antes do merge `c2e41bb17d4a284dddf64eb7a09395264918ac15`.
CI pós-merge40596714509 conferido success nesta continuação.
