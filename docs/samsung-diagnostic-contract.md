# Diagnóstico Samsung: percurso de carga e recuperação

Consolidação em **2026-10-26 (Campo Grande)**, base main `b70c3a9` após
PR #33. Não houve acesso ao telefone ou execução de firmware nesta entrega.
Os READMEs Kernel/Platform recebidos foram relidos: descrevem compilação,
não fornecem um transporte de carga/leitura ou estado de entrada.

**Nenhum percurso físico completo está demonstrado nas condições informadas.**
A cópia/salto LK têm evidências estáticas; a Image própria e seu registro têm
testes QEMU. Entre esses resultados faltam aceitação da imagem, posse/coerência
e aquisição dos bytes. Esta matriz não autoriza uma tentativa física.

## Contexto e referências

O último estado informado pelo usuário é SM-G998B/p3s, Exynos 2100, build
G998BXXSJHZC2/Android 15, sem root e bootloader travado. É um relato anterior,
não uma nova medição. Rish/Shizuku operou como uid=2000 e várias leituras
foram negadas; o bugreport posterior recuperou logs stock. Estado Knox não
substitui a comprovação de um caminho que aceite uma imagem própria.

**Atualização de 30/10:** propriedades ADB e tela Download reconfirmaram o
bloqueio informado. Uma [sessão Heimdall leu a PIT com 48 entradas](download-pit-observation-hzc2.md)
e encerrou a interface. A consulta física Download agora está observada para
essa operação; não demonstrou carga própria, leitura de RAM ou retorno da sonda.

A continuação [por shell Android](runtime-collection.md#links-de-armazenamento-e-sete-leituras-negadas--2026-10-30)
obteve nomes/destinos de 35 partições, mas negou sete atributos de geometria.
Essas leituras estão encerradas sob o mesmo acesso. A análise do
[handler de transição](lk-device-state-switch-hzc2.md) identifica um pedido
de wipe ao recovery; ele não foi executado ou proposto como consulta.

A documentação [AOSP sobre estado do dispositivo](https://source.android.com/docs/security/features/verifiedboot/device-state)
descreve verificação da raiz de confiança no estado LOCKED. É uma regra de
referência Android, não uma reconstrução de todos os validadores Samsung.
[Transições de estado](https://source.android.com/docs/core/architecture/bootloader/locking_unlocking)
não são mecanismo de preservação de RAM. Os comandos genéricos dessas páginas
não foram validados como interface deste Samsung e não são instruções desta entrega.

As evidências Samsung abaixo usam o sboot já recebido, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Endereços de instrução são offsets no arquivo; valores AP/RAM são nominais
quando não houver observação explícita. Não foram relidos registradores físicos.

## Matriz do Marco A

| Requisito | Evidência disponível | Lacuna para execução física |
|---|---|---|
| Identidade e acesso | [Coleta shell](runtime-collection.md), [bugreport HZC2](dram-observed-hzc2.md), ADB/tela Download e [PIT lida em 30/10](download-pit-observation-hzc2.md); shell/travado | Consulta Download demonstrada para PIT; caminho de imagem própria ainda não demonstrado |
| Artefato | [Diagnóstico](entry-diagnostic.md): Image ARM64 bruto, registro final de 128 bytes, sem EFI/Android/assinatura Samsung | Header ARM64 não é um boot.img aceito pelo telefone |
| Contêiner/cópia | [Stock v3](stock-firmware-hzc2.md), [cópia LK](lk-kernel-copy.md): 0x12e88c copia kernel_size de boot+header arredondado | [Marcador e pedido de SHA anteriores à cópia](lk-precopy-measurement-hzc2.md) delimitados; autenticação completa, serviços seguros e aceitação de contêiner próprio continuam abertos |
| Destino | Contexto em 0xfba18 e BLR 0xfbe14 ligam nominalmente 0x80080000+deslocamento_u32 | Não estabelece endereço efetivo desta Image no aparelho ou RAM livre |
| Propriedade | A própria Image inclui o registro; não precisa de outro buffer de saída | Região completa gravável/executável, reservas e ausência de concorrentes ainda não demonstradas |
| Coerência | [Helper LK](lk-cache-handoff.md): M=1 limpa M/C no EL atual; M=0/C=1 conserva C. Há chamadas depois | Cache da Image, outros agentes, traps e estado após callbacks não observados |
| Entrada | Diagnóstico aceita EL1/EL2 com M=C=0; [trecho final](lk-final-edges.md) delimitado | EL/SCTLR finais e permissões dos registradores de sistema não medidos |
| Argumentos e CPUs | Diagnóstico registra x0–x3/SP/MPIDR sem usar pilha/FDT; testes de uma CPU | x0 não é FDT certificado; exclusividade de uma CPU/região precisa de contrato |
| Aquisição | GDB recupera os bytes no QEMU, antes de reiniciar a VM | Não há canal demonstrado para ler a RAM do diagnóstico no Samsung |
| Vínculo e tempo | Leitor offline compara layout/endereço e, opcionalmente, Image inteira | Registro v1 não tem nonce/identificador de execução; autenticidade e frescor dependem do contexto de captura |
| Recuperação do aparelho | Há Android stock funcionando no último relato | Nenhum plano de retorno/retomada foi ensaiado para uma Image que estaciona em WFE |

A [continuação de retorno do LK](lk-payload-return-hzc2.md) está mapeada:
`0xfbe18` descarta o valor devolvido, o wrapper retorna zero e o bootstrap
chama `thread_exit()`. Os blocos selecionados não entram diretamente em
RDX. Essa cadeia nominal não valida contexto/pilha, não muda a sonda e não
estabelece o percurso físico de recuperação.

O Marco B (R10 em uma CPU) continua exigindo também FDT/bancos/reservas
confiáveis e permissões GIC/timer. Resolver o Marco A não comprova esses dados.
O R10 exige EL2; a Image de diagnóstico aceita EL1/EL2. Os contratos são distintos.

## Percursos considerados

| Percurso | O que já se sabe | Estado nesta entrega |
|---|---|---|
| Boot stock + bugreport | Recuperou texto do bootloader via dumpstate | Observação stock; não executa a Image própria nem lê uma faixa arbitrária de RAM |
| Download + Heimdall, consulta PIT | Sessão física negociada e 48 entradas recebidas no Mint; interface liberada | Leitura da tabela de partições observada. Não demonstra upload, aceitação de imagem própria, leitura de partição ou aquisição de RAM |
| Imagem Android própria via cadeia Samsung | Formato e trecho de cópia têm modelos; [instalador Proton](loader-contract.md) altera boot/vendor_boot | Não disponível como percurso demonstrado sob o último estado travado; nem pacote do diagnóstico nem aceitação/retorno validados |
| Chainload a partir de Linux | Shim antigo desativado; [referência pública](xfwdrev-kernel-reference.md) tem kexec e /dev/mem desativados | Não é um carregador existente; config de referência não prova config stock ou controle de EL2 |
| GDB QEMU | Carrega a Image bruta e lê registros/snapshot antes de continuar/resetar | Disponível somente no laboratório; não é conexão GDB do telefone |

Desbloqueio, root, recovery personalizado e leitura de memória continuam sem
demonstração. Download foi observado apenas na consulta PIT acima. O comando
solicitado foi de leitura; não foram fornecidos comandos de instalação de
imagem, flash, dump OEM, reparticionamento ou desbloqueio neste procedimento.

## Canais de recuperação

| Canal | Limite que impede tratá-lo como saída do diagnóstico |
|---|---|
| Bugreport/last_kmsg | Evidência de logs stock persistidos; não há ligação de transporte com os 128 bytes da Image própria |
| [Debug-snapshot LK](lk-memory-log.md) | Área 0xf0000000–0xf0210000 reservada para outro produtor. Não é memória livre nem há contrato para inserir o registro ali |
| [UART0/MUIC](uart-routing.md) | Roteamento/estado físico, clocks e acessibilidade ainda abertos. A Image atual não serializa o registro; habilitar uma UART sozinho não o transmite |
| Android depois de outro boot | Precisa provar retenção/reserva, endereço, leitura permitida e ausência de sobrescrita; não se presume que reset conserve a Image |
| HVC/log Harx | [Atributo negado](harx-log-observation.md); serviço de log não é leitura arbitrária do registro |
| Debugger/leitor de RAM externo ou OEM | [Origem RDX encontrada](lk-rdx-memory-origin-hzc2.md): o primeiro par de bancos conservado cobre a janela candidata e há binding nominal DWC3; a sonda atual não retorna ao LK. Disponibilidade, permissões e preservação após reset continuam sem demonstração física |

As coletas negadas não devem ser repetidas sem mudança concreta de acesso/canal.
Não copiar o registro para área reservada alheia, habilitar MMIO/SMC ou executar
consumidores NEWTIME fora do escopo para contornar essa lacuna.

## Contrato de uma futura captura

Antes de executar a Image no aparelho, registrar a rota que aceita o artefato
e o modo de recuperar a região **enquanto os bytes ainda pertencem ao ensaio**.
O contexto precisa incluir Image/ELF e hashes da mesma compilação, intervalo
completo, base efetiva, produtor da captura, instante/boot e operações ocorridas
entre entrada e leitura. O offset do registro vem do ELF correspondente.
Para o layout v1 atual, `diag_record = image_size - 128`; o QEMU confere essa
igualdade contra os símbolos do ELF. Uma alteração de layout exige revisão.

Adquirir 128 bytes exatos, sem prefixo de dump, e preferir também a Image inteira.
Conferir marcador/versão/tamanho, campos reservados, EL/M/C e base+offset.
Comparar a captura completa com a Image original, permitindo diferença só no
registro. Guardar originais privados fora do Git; não publicar cmdline, dumps,
seriais ou campos pessoais para provar origem.

Um registro sem marcador pode significar recusa, falta de execução, gravação
incompleta ou captura errada. Um marcador válido pode ser antigo ou fabricado.
A inspeção isolada não escolhe entre essas hipóteses, não autentica execução
e não comprova persistência. Não há antirreplay no formato v1.

## Leitor e ensaio disponíveis agora

`inspect_entry_record.py` lê somente arquivos locais, limita entradas e emite
JSON. Recusa tamanho diferente de 128, marcador incompleto, versão/layout ou
estado incompatíveis e endereços divergentes. `--snapshot` exige comparação
byte a byte da Image inteira. O resultado distingue `record_fields_only` de
`full_image_bytes`; origem, frescor e autenticação continuam `not_verified`.
O leitor nunca dereferencia x0 ou determina que a base declarada seja RAM livre.

Exemplo **somente QEMU**, com diretório novo:

```bash
python3 scripts/test_entry_diag.py --output-dir build/entry-captures-local
python3 scripts/inspect_entry_record.py \
  build/entry-captures-local/el1-offset0-mc0.record \
  --image build/entry-captures-local/entry_diag.Image \
  --load-address 0x40080000 \
  --snapshot build/entry-captures-local/el1-offset0-mc0.snapshot
python3 scripts/test_entry_record.py
python3 scripts/validate_baseline.py
```

O harness exporta referência, registros e snapshots de sucesso, mais
`captures.json` com fonte QEMU, endereços e hashes após completar os testes.
Recusas exportam os bytes sem marcador completo; o leitor os rejeita e não
as classifica por si só. Dezessete testes de host e seis registros reais do
QEMU passam; seis capturas sem marcador são recusadas. O baseline/CI
exige ambas as verificações. [Evidência](references/diagnostic-contract-20261026.json).

## Próxima investigação

O próximo passo é delimitar **uma interface concreta de carga e aquisição**,
com suas permissões e preservação, usando as imagens/fontes existentes.
O [levantamento RDX](lk-dump-export-hzc2.md) já identificou um encaminhamento
nominal e separou o perfil fixo das entradas de memória acrescentadas em
execução. A [continuação](lk-rdx-memory-origin-hzc2.md) encontrou o produtor
`0xee370`, a cobertura nominal da janela candidata e o binding DWC3.
A conclusão para a Image atual é manter a combinação com RDX bloqueada:
ela estaciona em WFE sem devolver o controle ao LK. Para mudar a decisão,
é necessário um percurso de carga compatível e aquisição independente
enquanto parada, ou retomada com preservação especificada e validada.
Reset exige medir retenção e ausência de sobrescrita; não é retorno
presumido. Para a rota Android própria, fechar aceitação/transformações
ainda abertas no LK.
O [retorno nominal rastreado](lk-payload-return-hzc2.md) termina a aplicação;
uma proposta cooperativa deve especificar o produtor de observação e seu
contexto, além de conservar pilha e bytes. Acrescentar RET isoladamente
não satisfaz esses requisitos.
Sem uma interface disponível nas condições do aparelho, registrar o bloqueio
e a condição específica que mudaria a decisão; mais uma busca de constantes
ou leitura Shizuku já negada não o resolve. Nenhuma execução física é próxima
etapa automática desta matriz.

Continuação de 27/10: [0x151b10 delimitada](lk-postcopy-policy-hzc2.md) como dispatcher com configuração CP/fingerprint via SMC. Retorno zero local não certifica aceitação; serviços seguros e demais efeitos transitivos permanecem abertos. Próxima fronteira: consultas de política 0x157230 e validação anterior à cópia.

Continuação: [origem imediata do bitmap](lk-policy-bitmap-hzc2.md) liga workspace+0x29f68 → response+0x120 → 0xcd6618 → 0x157230. O produtor é get_token_mode; produção do workspace, token ativo e autenticação da Image seguem abertos.

Continuação de 30/10: [marcador pré-cópia e SHA](lk-precopy-measurement-hzc2.md) ligam 0x151a10 a um pedido pelo monitor, com fonte nominal 0x31d740 e comprimento de 0x31d738. A [continuação identifica os bytes iniciais como chave pública AVB RSA-4096 embutida](lk-embedded-avb-key-hzc2.md), com comprimento de 1.032 bytes. Preservação ao vivo, confiança da chave e autenticação do contêiner continuam abertas; os retornos selecionados não certificam aceitação.

Continuação de 30/10: o [callback AVB de confiança](lk-avb-key-trust-hzc2.md) usa nominalmente o slot +48 da tabela inicializada em 0xd05900 e pede ao monitor uma chave com o nome `vbmeta`. O consumidor verifica I/O antes do byte de confiança. O slot +72 e rótulos do wrapper foram delimitados; não comprovam chave ativa, igualdade com o objeto embutido ou aceitação final. Próximo: verificador 0x1262b0 e ações/retorno do wrapper 0x17f5d0.

Continuação de 30/10: o [verificador vbmeta e caminho RSA](lk-avb-signature-hzc2.md) distingue sucesso, imagem não assinada e falhas de cabeçalho/hash/assinatura. Foram conferidos seis algoritmos, padding PKCS#1 v1.5 e tradução de resultados para o slot, sem execução de firmware. Isso não fecha confiança da chave nem aceitação final: ações/retorno do wrapper após 0x17f724 e origem da continuação tolerada permanecem fronteiras.

Continuação de 30/10: o [wrapper AVB e seu chamador](lk-avb-wrapper-hzc2.md) estão delimitados localmente. Red nominal alcança laço antes do retorno; green/yellow/orange podem devolver o resultado do slot, sobrescrito imediatamente pelo chamador. Os pedidos de metadados não certificam efeitos do monitor, e a verificação adicional 0x17deb0 permanece fronteira. Os contratos físicos continuam abertos.

Continuação de 30/10: a [conferência de Build-id](lk-build-id-partitions-hzc2.md) liga o produtor e consumidor do cache vbmeta e a referência super. O teste usa prefixo e palavra de política; getters não comprovam bytes novos. Corpos locais de extração/processamento foram delimitados, com verificadores e serviços externos ainda opacos. Carga, posse de memória e captura física continuam pendentes.

Continuação de 30/10: os [verificadores Samsung](lk-samsung-checks-hzc2.md) foram delimitados localmente, incluindo o pedido seguro 0xffffffffffffff10 e a tradução de seus retornos. Fallback de contador e retorno zero não foram promovidos a estado medido ou aceitação física. Predicados, backend seguro e fornecedores de chave permanecem abertos; não houve operação no aparelho.

Continuação de 30/10: o [backend RPMB](lk-rpmb-hzc2.md) liga os contadores aos pacotes locais, callbacks de armazenamento e pedidos seguros de nonce/MAC. Foram delimitadas cópias anteriores aos testes e continuação local após erro de MAC; isso não comprova I/O, autenticação, persistência ou aceitação física. Destinos vivos dos callbacks e implementação segura seguem pendentes.

Continuação de 30/10: a [referência FlopKernel](flop-kernel-reference.md) acrescenta confirmação do layout RPMB e leitor offline, sem executar kernel, firmware ou operações no aparelho. Fontes p3s e flags do defconfig não satisfazem os contratos físicos de carga, memória ou captura.

Continuação de 30/10: [registro e callbacks RPMB do LK](lk-rpmb-transport-hzc2.md) foram ligados nominalmente até a entrada UFS. Configuração ativa do host, resposta/DMA e persistência não foram observadas; essa ligação não satisfaz os contratos físicos de carga, memória ou captura.

Continuação de 30/10: [descritores/espera/resposta UFS](lk-ufs-completion-hzc2.md) foram delimitados localmente, com origem nominal do status SCSI. Sem configuração ativa, posse/coerência e resposta física adquiridas, isso não comprova persistência nem satisfaz carga, memória ou captura do diagnóstico.

Continuação de 30/10: [host/buffers UFS](lk-ufs-host-memory-hzc2.md) têm publicação e configuração ligadas nominalmente. O [cruzamento FlopKernel](flop-ufs-dma-reference.md) acrescenta contratos DMA e referências UART, sem medir coerência, memória livre, persistência ou satisfazer a captura do diagnóstico físico.

Continuação de 30/10: o [pool nominal do heap UFS](lk-heap-pool-hzc2.md) foi delimitado e o alocador executado em QEMU com entradas fornecidas. Essa memória é usada pelo LK; não é RAM livre para a sonda nem prova de tradução física, DMA ou captura no aparelho.

Continuação de 30/10: a [construção de tradução do pool](lk-pool-mmu-hzc2.md) foi delimitada no perfil EL1/4KiB e executada em QEMU sem instalar as tabelas. Isso não é captura de registradores/tabelas do S21 nem identifica RAM livre, DMA coerente ou entrada/captura do diagnóstico físico.
