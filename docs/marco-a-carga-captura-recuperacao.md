# Marco A: proposta de carga, captura e recuperação

Proposta de 31/10/2026, Campo Grande, base `fbb867d` após PR #73.
**Documento de projeto, sem implementação da nova sonda e sem autorização
de desbloqueio, apagamento ou gravação no telefone.**

A rota selecionada para validação de laboratório é uma **Image Linux de
diagnóstico com captura cooperativa na entrada**. O produtor registra o
estado antes da inicialização Linux, preserva o contrato de entrada e
continua o kernel. Um exportador Linux disponibiliza uma cópia somente
de leitura, recuperável pelo computador no mesmo boot, depois que o
sistema e suas permissões de acesso estiverem funcionais.

Essa rota exige um produtor novo. A [Image atual](entry-diagnostic.md)
permanece independente: cabeçalho/código mais registro S21ENTRY v1 de
128 bytes, seguida de WFE. Ela não passa a iniciar Android, retornar ao LK
ou transmitir bytes pela existência desta proposta.

## Decisão e condições atuais

| Item | Estado desta proposta |
|---|---|
| Objetivo imediato | Uma captura de entrada recuperada, ligada ao artefato do ensaio |
| Desenvolvimento escolhido | Instrumentação cooperativa, continuação Linux e exportador limitado |
| Execução no telefone | Bloqueada até cumprir os critérios deste documento |
| Desbloqueio OEM | Decisão pendente; não inferida da mensagem de outro agente |
| Último acesso informado | SM-G998B/p3s HZC2, shell uid2000, bootloader travado |
| Transporte observado | Download/Heimdall leu a PIT; flash próprio e captura de RAM não demonstrados |
| Sonda WFE + ADB posterior ou RDX | Sem percurso de aquisição demonstrado; não é a rota selecionada |

As [propriedades e a tela recebidas](download-pit-observation-hzc2.md)
indicam bloqueio no último relato. A opção OEM ativa foi informada
separadamente. Não se decodifica o sufixo `(U)` como um pedido pendente
ou como prova isolada de permissão/estado. Uma decisão escrita sobre OEM
deve anteceder qualquer transição destrutiva, não a preparação deste plano.

O [AOSP](https://source.android.com/docs/core/architecture/bootloader/locking_unlocking)
distingue capacidade de solicitar desbloqueio do estado desbloqueado e
prevê reset de dados na transição. O [handler HZC2](lk-device-state-switch-hzc2.md)
também prepara um pedido de wipe, sem demonstrar sua execução física.
Os comandos genéricos AOSP não são um procedimento validado para este Samsung.

O [Warranty Bit Knox](https://docs.samsungknox.com/admin/knox-platform-for-enterprise/faq/)
é uma questão distinta, com efeitos permanentes documentados sobre recursos
Knox quando acionado. Isso não prova inviabilidade de voltar a usar Android
stock nem fornece uma implementação de dual-boot. Não se faz nova inferência
sobre o campo WARRANTY VOID anteriormente transcrito.

## As seis correções incorporadas

1. OEM ativo nas configurações não significa desbloqueio executado; o
   significado específico de `(U)` não é inventado.
2. Desbloquear pode mudar a aceitação da imagem; pacote, entrada, memória,
   captura e retorno ao uso normal continuam trabalhos separados.
3. Os 128 bytes pertencem ao registro da sonda atual, não à Image inteira.
4. WFE não inicia Android. ADB/root após outro boot não provam retenção;
   a captura deve ter um produtor, um leitor e um intervalo de vida definidos.
5. A memória da própria captura precisa pertencer ao ensaio desde o Marco A.
6. Efeitos Knox e viabilidade Android/dual-boot não são equivalentes.

Já existem [DTB stock e overlays analisados](stock-firmware-hzc2.md).
O FDT final ajustado pelo bootloader, com memória/reservas dinâmicas, continua
pendente. Não se afirma que nenhum FDT foi extraído nem se adia toda a memória
para o Marco B.

## Carga proposta e o papel do desbloqueio

O artefato futuro será um kernel Linux instrumentado, reconstruído de fonte
fixada e com cabeçalho ARM64 correto, dentro de um contêiner Samsung/Android
cuja compatibilidade precisa ser demonstrada. A instrumentação é uma mudança
de fonte/link, não a concatenação da sonda WFE ao binário stock.

Os [READMEs Kernel/Platform](loader-contract.md) recebidos descrevem builds
de kernel Android11 e módulos de plataforma Android15, respectivamente.
Não bastam para atribuir equivalência ao kernel HZC2. A referência Flop/Proton
é candidata, não substitui essa conferência. Antes de definir o pacote é
preciso fechar fonte, configuração, toolchain, módulos/ramdisks necessários
e compatibilidade com o sistema que deverá continuar o boot.

O magiskboot estudado no [instalador de referência](loader-contract.md)
é uma ferramenta candidata de repack offline, não uma rota já validada
para esta Image. Qualquer ferramenta escolhida deve ter revisão/hash fixados,
round-trip stock sem alterações semânticas e comparação dos componentes.
BOOT, VENDOR_BOOT e RECOVERY não são destinos intercambiáveis. O conjunto
mínimo de partições alteradas será definido pelos resultados, sem assumir
unidades/capacidades da PIT ainda não medidas.

| Um desbloqueio aceito poderia permitir | Não demonstra por si só |
|---|---|
| Alterar a política de aceitação de imagens próprias | Aceitação deste pacote em HZC2 |
| Tornar viável instalar um kernel instrumentado | Compatibilidade de módulos, Android e política SELinux |
| Abrir uma condição diferente da coleta uid2000 atual | Root, leitura do novo nó, memória segura ou recuperação |

Não há comandos de desbloqueio, flash, reparticionamento ou escrita de
armazenamento neste documento. Nenhum pacote físico está pronto.

## Desenho da captura: produtor e vida dos bytes

O fluxo proposto é:

1. O carregador entrega a Image Linux instrumentada pela rota validada.
2. Antes da primeira alteração de EL/MMU/cache feita pelo kernel, um bloco
   mínimo lê o estado e os argumentos. Não usa o SP recebido como pilha,
   não dereferencia X0, não acessa periféricos e não chama serviços seguros.
   A inserção pertence à entrada primária escolhida pelo header; entradas
   secundárias e de resume não são instrumentadas por associação.
3. Com EL1/EL2 e M=C=0, grava uma cápsula em armazenamento pertencente à
   própria Image e publica o marcador por último, com a ordenação validada.
4. Restaura o estado modificado pela instrumentação, inclusive DAIF/NZCV
   quando alterados, conserva X0–X3/SP e os demais requisitos do caminho
   original e salta para a continuação original do kernel. Não retorna ao LK.
5. Depois que Linux pode acessar a cápsula com segurança, o exportador
   valida o marcador e copia os bytes para seu próprio snapshot imutável.
6. O computador coleta esse snapshot por uma interface explicitamente
   autorizada no sistema que continuou o boot, sem reiniciar o aparelho.

Nos casos recusados, a instrumentação não grava a cápsula e segue para a
continuação original sob o contrato que esta exigir. Ausência de marcador
significa resultado indeterminado; não identifica sozinha recusa ou falta
de execução. Não se promete que Linux iniciará sob condições que violem seu
[protocolo de entrada](https://www.kernel.org/doc/html/latest/arch/arm64/booting.html).
Testes negativos de M/C podem exigir uma continuação controlada no laboratório.

### Memória a reservar e conferir

| Região | Proprietário e condição |
|---|---|
| Image completa, incluindo instrumentação e cápsula | Extensão real declarada no header/contêiner e respeitada pelo carregador; nenhuma janela fixa suposta livre |
| Cápsula inicial | Seção carregada e retida da própria Image, fora de BSS, init descartável e qualquer rotina de zeragem; conteúdo inicial definido |
| Snapshot do exportador | Memória própria do kernel, copiada somente após validar a cápsula; nenhuma leitura arbitrária solicitada pelo usuário |
| FDT, initrd, firmware residente e outros buffers | Não sobrepostos; reservas e intervalos correspondentes demonstrados antes do ensaio físico |

A seção deve aparecer nos bytes carregados e no mapa do linker. Uma variável
C inicializada com zero não basta para garantir que esteja fora de BSS.
É necessário conferir a seção, o layout final e a cadeia que poderia zerá-la.
Relocações/KASLR ou cópias feitas pelo kernel também precisam conservar a
cápsula ou ter uma migração demonstrada. Não se presume endereço constante
entre a entrada física e o ponteiro virtual usado depois pelo exportador.
O pool LK/UFS não é memória livre para esse uso. Endereço de link não é
certificado de posse, identidade física ou coerência.

### Cápsula proposta S21COOP1

Este é um **contrato proposto**, ainda sem produtor, leitor ou ABI implementados.
Não modifica S21ENTRY v1 e não pode ser enviado ao leitor v1 existente.
A cápsula terá 256 bytes little-endian; limites e offsets devem ser testados
antes de congelar a ABI no próximo trabalho de implementação.

| Offset | Bytes | Campo |
|---:|---:|---|
| 0 | 8 | Marcador `S21COOP1`, publicado por último |
| 8 | 4 | Versão1 |
| 12 | 4 | Tamanho256 |
| 16 | 32 | Tag do ensaio, escolhida pelo host e incorporada ao artefato |
| 48 | 32 | X0–X3 recebidos |
| 80 | 8 | CurrentEL bruto |
| 88 | 8 | DAIF recebido |
| 96 | 8 | SCTLR do EL de entrada |
| 104 | 8 | MPIDR_EL1 |
| 112 | 8 | SPSel |
| 120 | 8 | SP recebido |
| 128 | 8 | Base efetiva da Image |
| 136 | 8 | Endereço efetivo da cápsula |
| 144 | 8 | Endereço da continuação original Linux |
| 152 | 104 | Reservado, zero |

Não há ponteiro de leitura escolhido pelo coletor. X0 é apenas um argumento
registrado. A tag associa o registro ao artefato/manifesto; não autentica a
execução. Reusar a mesma Image em vários boots não demonstra frescor pela
tag. Um novo ensaio que precise dessa distinção exige nova tag/artefato e
contexto de coleta, sem apresentar isso como atestação criptográfica.
Os endereços gravados pertencem ao instante da captura; o exportador usa
seu símbolo próprio no contexto Linux, sem dereferenciar esses campos.

## Leitor no mesmo boot e acesso Android

A interface candidata será um nó binário específico, somente de leitura,
por exemplo `/sys/kernel/s21_entry/capture`, com tamanho máximo256 e sem
parâmetro de endereço, escrita ou ioctl de memória. **Esse nó não existe
hoje.** O exportador recusará dados sem marcador/layout válido e conservará
um snapshot estável durante as leituras. O leitor host exigirá exatamente
256 bytes, versão, limites, campos reservados e correspondência ao manifesto.
O offset vem do ELF/layout dessa compilação. Não reutiliza as premissas v1
de registro no fim da Image e código inteiro inalterado após o boot Linux.

Criar o nó não garante leitura pelo shell: DAC, SELinux e o domínio do
coletor precisam de uma configuração mínima específica, testada junto ao
pacote. Não se propõe SELinux permissivo, acesso genérico a `/dev/mem` ou
root como substituto dessa interface. Se a política não puder ser entregue
e validada no sistema que continuará o boot, a rota permanece bloqueada.

ADB é somente o transporte posterior do sistema em execução. Nenhum ADB
é pressuposto enquanto a sonda WFE estiver parada. USB Linux, permissões
e transferência completa precisam ser demonstrados antes de chamar essa
etapa de canal funcional. O coletor deverá guardar original binário,
hashes do artefato/captura, tag, layout ELF e contexto/tempo da sessão.
Hashes, argumentos e endereços não autorizam publicar dumps pessoais no Git.

## Recuperação e retorno ao uso normal

No sucesso, Linux continua no mesmo boot e o computador obtém os bytes
antes de qualquer reinício. Não há dependência de RDX, retenção após reset,
persistência em partição ou driver UFS baremetal na sonda.

Em falha, o plano de recuperação é separado da captura: não se classifica
um reboot ou a volta ao modo Download como registro recuperado. Antes de
qualquer ensaio físico precisam existir artefatos stock identificados por
hash, conjunto exato de partições afetadas, ferramenta/protocolo compatíveis
e um procedimento de restauração demonstrado para esse conjunto e estado.
A PIT lida e o último Android funcional não demonstram essa restauração.
Restaurar imagens stock também não desfaz apagamento de dados nem efeitos
permanentes Knox; esses riscos não são classificados como reversíveis.
Não se usa relock como recuperação automática nem se inicia flash até
essa condição estar fechada e a ação física especificamente autorizada.

## Entregas e critérios de parada

| Etapa | Entrega necessária | Critério para avançar |
|---|---|---|
| A0 — fonte e pacote | Fonte/configuração/toolchain fixadas; plano de módulos, ramdisk e política; inventário stock e round-trip offline | Build/layout reproduzíveis e dependências de compatibilidade explícitas; caso contrário parar nessa lacuna |
| A1 — produtor cooperativo | Código de entrada, seção retida, cápsula e leitor novo; continuação controlada | EL1/EL2, argumentos/SP/estado preservados; positivos e recusas com guardas; disassembly confirma ordem antes das mudanças Linux |
| A2 — cadeia de laboratório | Instrumentação em Linux AArch64 QEMU, exportador e coleta sem reboot | Linux continua, bytes sobrevivem à zeragem BSS/init e duas leituras concordam; tag/tamanho/layout inválidos recusados; QEMU não é validação p3s |
| A3 — acesso e restauração p3s | Evidências de compatibilidade do build, política de leitura, rota de instalação e recuperação do conjunto afetado | Pré-condições disponíveis e conferidas; hipóteses que só o ensaio físico mede registradas como risco, não como validação concluída |
| A4 — decisão física | Condições acima fechadas e decisão OEM/consentimento para a operação concreta | Só então considerar a instalação de uma Image de diagnóstico |
| A5 — captura física | Registro válido adquirido no mesmo boot, ligado ao artefato/contexto | Evidência de entrada para a Image Linux instrumentada; falha ou silêncio mantém o marco aberto |

A1 com continuação controlada não prova A2. A2 com kernel/configuração de
QEMU não prova compatibilidade p3s, acesso Android, instalação ou recuperação.
Este documento não declara nenhuma dessas novas entregas concluída.

Os gates não exigem a captura física como prova prévia de si mesma. Exigem
o percurso, a memória e o acesso justificados, ensaios de laboratório e um
plano de recuperação concreto. Aceitação efetiva, continuação Android e
leitura no p3s ainda são resultados do ensaio físico e podem falhar; essas
incertezas precisam constar da proposta da operação a autorizar.

Se a decisão for **manter travado**, a rota física desta Image modificada
é NO-GO no estado documentado. A única investigação de aceitação admitida
nesta proposta é um mecanismo concreto e reproduzível para carregar esse
tipo de artefato, com código/documentação e condições correspondentes ao
HZC2. Se não houver tal alvo ao concluir sua triagem documentada, registrar
o bloqueio e encerrar essa frente física. Não buscar indefinidamente
constantes, SMCs ou modos de serviço, nem afirmar inexistência global de canais.

## Prioridade e alcance do resultado

NEWTIME/DMC/ASV, expansão XNU, SMP e periféricos não necessários à captura
ficam pausados. LK/UFS/RPMB/AVB só voltam à prioridade quando uma lacuna
nomeada de A0–A5 depender deles. Entrada, memória e cache continuam ativos
como requisitos da rota, independentemente da decisão OEM. Coletas uid2000
já negadas não são repetidas sem mudança concreta de acesso.

O resultado físico proposto mede o ponto de captura da **Image Linux
instrumentada**. Não prova o estado de outro payload, da sonda WFE, de R10
ou XNU, nem oferece atestação de frescor. A seleção/contêiner/tamanho da
imagem podem afetar o carregamento e precisam acompanhar a evidência.

O [Marco A original](samsung-diagnostic-contract.md) para a sonda WFE
permanece aberto; este documento introduz uma etapa intermediária cooperativa
de observação, sem mudar silenciosamente seu critério. A evidência pode
orientar a adaptação posterior, mas não substitui o ensaio standalone.
O Marco B continua exigindo FDT final/memória, entrada compatível e
permissões GIC/timer, primeiro em uma CPU. O dual-boot continua posterior.

**Próxima entrega concreta:** especificar e implementar A1 em laboratório,
com fonte de referência escolhida em A0, sem operação no telefone. Falta de
fonte/build compatível é motivo para parar e registrar o bloqueio de A0,
não para voltar automaticamente a novas rodadas de engenharia reversa.

[Validação documental desta entrega](references/marco-a-proposal-review-20261031.json). Os ensaios A0–A5 propostos não foram executados.
