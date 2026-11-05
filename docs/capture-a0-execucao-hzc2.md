# A0: execução do plano e proposta de empacotamento

Continuação: o [protótipo B offline](capture-a0-natural-b-hzc2.md) registra a escolha delegada e sua execução em 04/11/2026 UTC. Os resultados abaixo preservam o estado da rodada original.

Rodada de 03/11/2026, Campo Grande, base e0aa2e1 do PR #89.
Executa o alcance offline do [plano](capture-a0-plano-hzc2.md). Não adota
pacote, não integra o PR #89, não inicia A1 e não opera o aparelho.

Durante a execução houve novas recusas de cópias locais de dhd.ko. O
prefixo de 35 MiB foi preservado; a origem continua não identificada. A
correção passou a selar os payloads durante a extração e não reconsumir os
caminhos intermediários. Isso protege o consumo, sem atribuir ou corrigir
o escritor desconhecido. Detalhes e limites da observação estão abaixo.

## Resultado por fase

| Fase | Execução e resultado | O que continua faltando |
|---|---|---|
| 1 — Image | Registrada a saída documental não identificada, com a evidência/hipóteses do PR #88 | Causa produtora dos 24576 bytes anteriores ao ALIGN desconhecida |
| 2 — pacote | Três opções calculadas, com limites e dependências separados | Escolha escrita do usuário; nenhuma opção adotada |
| 3 — assinatura/aceitação | Boot e vendor_boot stock novamente passaram hash e RSA da chave embutida | SignerVer03, vbmeta pai, confiança e aceitação do pacote modificado |
| 4 — KMI/runtime | Política de trabalho proposta e hooks CFI/RKP conferidos na fonte fixada | Dez origens de lista, duas listas ausentes e validação runtime |
| 5 — integridade | Runner de dimensionamento corrigido e executado: 275 entradas nativas seladas | Outros runners e conferência externa no ambiente do usuário |

Um bloqueio documentado mantém o gate fechado. Nenhuma linha desta tabela
transforma ausência de evidência em aprovação de A0 ou A1.

## Fase 1: encerramento documental com causa não identificada

O [relatório do PR #88](capture-a0-image-producer-hzc2.md) já satisfaz a
modalidade documental de saída prevista no plano. O padding de -40960 é
consequência dos limites anteriores sob a mesma regra de alinhamento, não
uma segunda causa independente. Não se repetiram kallsyms, decomposição
ou busca do corte histórico. Nova atribuição exige mapa/ELF stock ou um
alvo de comparação controlada de objeto/opção, conforme as hipóteses já
registradas. Esse resultado permite preparar a proposta abaixo, sem adotá-la.

## Fase 2: opções concretas para decisão

| Opção | Image e ramdisk | Trabalho e limitação |
|---|---|---|
| A — comprimentos exatos | Image exige +65536 bytes; gzip com strip exige +242375 | Preenchimento semanticamente válido ainda não demonstrado em nenhum dos dois formatos |
| B — comprimentos naturais com perfil strip-debug | Image 29403648; gzip 11774882 | Novo montador de geometria interna; definir extensões/AVB e validar todos os componentes |
| C — comprimentos naturais sem strip | Image 29403648; gzip 103744124 | Corpo vendor calculado excede o arquivo stock de 67108864 bytes; capacidade física não demonstrada |

**Recomendação para a próxima pesquisa de laboratório: opção B.** Conserva
os comprimentos naturais dos payloads medidos e evita inventar bytes para
satisfazer o montador atual. Isso não aprova strip como política, o novo
montador ou um pacote Samsung. A escolha continua sendo do usuário.

A opção B deslocaria as coordenadas derivadas dos headers v3 assim:

| Coordenada relativa ao arquivo | Stock | Projeção B | Delta |
|---|---:|---:|---:|
| Ramdisk em boot | 29474816 | 29409280 | -65536 |
| Fim do corpo boot alinhado | 30179328 | 30113792 | -65536 |
| DTB em vendor_boot | 12021760 | 11780096 | -241664 |
| Fim do corpo vendor alinhado | 12414976 | 12173312 | -241664 |

O delta de -242375 no gzip não é o delta do início do DTB: o segundo segue
o alinhamento de 4096. Esses são cálculos de coordenadas de payload, **não
uma nova geometria de contêiner implementada**. Posição/validade das extensões
opacas, SignerVer03, vbmeta e footer continuam indefinidas nessa projeção.
O montador atual recusa B e C, pois aceita apenas substituições de tamanho
idêntico. Nenhum header, contêiner stock ou assinatura foi reescrito.

Na opção C, o corpo vendor calculado termina em 104144896, acima do tamanho
do arquivo stock. Isso não mede a capacidade da partição física. Na opção A,
não basta acrescentar zeros ao gzip: o leitor atual recusa bytes residuais;
também não existe prova de semântica de padding da Image nesse percurso.
Strip não resolve sozinho a diferença de comprimento da Image.

## Fase 3: criptografia stock reconferida, aceitação bloqueada

Os dois arquivos raw foram lidos em buffers verificados pelos pins HZC2.
O leitor existente conferiu descriptors e RSA/PKCS#1 com a chave embutida.
Ambos usam o blob público de SHA
d185cb2fb075fdc3b128836be117bd44851aabacce2ebffd285cf4e2b3aa54e6.
O marcador SignerVer03 foi localizado a +16 na região opaca de boot e a
+0 em vendor_boot. Localizar o marcador não valida sua assinatura.

O vbmeta pai não foi fornecido como entrada desta execução. Não há prova
nova de confiança da chave no monitor, rollback, política Samsung ou
aceitação de payload modificado. O [controle com chave de laboratório](capture-a0-container-hzc2.md)
permanece separado. Fase 3 bloqueada para aceitação; não se requisita
desbloqueio, root, flash ou nova coleta para contornar esse bloqueio.

## Fase 4: política proposta e dependências runtime

A proposta usa kernel e 274 módulos do mesmo build alinhado, mantém os
nomes selecionados e exclui input_booster_lkm/sec_debug_sched_info. Exige
revisar a coerência das dependências do pacote final; esta rodada não
regenerou modules.dep. Não mistura módulos stock com recompilados nem
propõe force-load, inserção manual de CRC ou flexibilização de namespaces.

Mantém os valores já medidos: LTO/CFI/CFI shadow e MODVERSIONS ativos,
CFI permissive desativado, UH/RKP ativos, MODULE_SIG desativado na fonte
candidata e importações de namespace ausentes não permitidas. MODULE_SIG=n
não demonstra ausência de outras verificações Samsung.

Na fonte Samsung fixada, kernel/module.c chama cfi_init em 3658 e registra
cfi_module_add em 4521. Há chamadas UH_APP_RKP/RKP_MODULE_LOAD com
PXN_SET em 3794 e PXN_CLEAR em 3932. kernel/cfi.c contém o ramo permissive
e a implementação cfi_module_add. São testemunhas de fonte, sem executar
esses hooks ou provar seu comportamento no aparelho.

Os dez nomes continuam sem origem de **lista** demonstrada; os dois inputs
ausentes continuam abi_greylist e android/abi_gki_aarch64_galaxy_presubmit.
O [relatório KMI](capture-a0-kmi-hzc2.md) permanece válido. Citar nomes na
configuração não fornece os bytes dessas listas. Não se atribuem
os dez nomes aos dois arquivos por suposição. Fase 4 bloqueada para essas
origens e para carga/ABI/CFI/RKP em runtime. Política proposta não é execução.

## Fase 5: consumo corrigido e repetição real

Antes, o runner de dimensionamento verificava um caminho e depois o
reabria em objcopy/strip; os módulos do ramdisk eram emitidos enquanto
se calculava seu hash. A implementação agora:

1. Lê tarball, fonte e boot/vendor raw uma vez, verifica e processa os
   mesmos buffers. Mantém os hashes dos membros selecionados e a releitura
   das 275 cópias extraídas; não repete os 2133 payloads individualmente.
2. Durante a extração, confere cada buffer de payload e imediatamente cria
   seu memfd selado. Objcopy/strip e o mapeador ELF usam esses snapshots,
   impedindo escrita/crescimento/redução e sem reconsumir as cópias mutáveis.
   O ramdisk usa snapshots dos módulos antes/depois do strip, conferidos
   antes de emissão, em vez de depender do caminho intermediário.
3. Verifica cada buffer de substituição antes de emiti-lo no CPIO.
4. Hasheia os bytes gzip emitidos pelo escritor; lê/verifica o destino
   contra esse hash e faz o replay usando esse mesmo buffer comprimido.

A execução completa produziu novamente Image, dois ramdisks e metadados
dos 274 módulos idênticos às medições publicadas do PR #86:

| Artefato de medição | Bytes | SHA-256 |
|---|---:|---|
| Image | 29403648 | 9614f9a0ec8e83177ccb2010a585a128fd11f028cb46c417f2c1dbed2c2fd571 |
| Gzip sem strip | 103744124 | 5a2adf2e84a124113651efa124f90b071df6214db8c51a3be6272b59ab35f374 |
| Gzip strip-debug | 11774882 | 7bc62305b3467bd1dbc92acbd346e1db3a96cd7e037367ce4a9e7b94817fbcd9 |

Nenhum preenchimento ou novo contêiner foi produzido. São perfis de
medição sobre cópias, sem adoção de política de instalação. Hashes iguais
não dispensam a nova vinculação do consumidor; testes verificam os dois.

O alcance é **check_capture_a0_sizes.py e seus consumidores de payload**.
Outros runners antigos com verify seguido de reabertura ainda precisam
de revisão; não se certifica o pipeline inteiro nem a estabilidade futura
dos caminhos. A conferência externa do tarball continua pendente no
ambiente do usuário, sem ser confundida com esta execução do assistente.

## Recorrência preservada: dhd.ko cortado em 35 MiB

Uma primeira execução completa da correção de consumo repetiu os hashes
anteriores. Duas tentativas seguintes foram recusadas antes de strip em
dhd.ko; nenhuma gerou relatório de sucesso. As releituras da extração já
haviam concluído, mas a cópia posteriormente consumida estava menor. A
origem do truncamento não é atribuída ao compilador, arquivo preservado,
limite de processo, plataforma ou ferramenta sem evidência de escritor.

| Evidência real preservada | Valor |
|---|---|
| Dhd íntegro da primeira execução, hash validado | 51582680 bytes, SHA 8b35af1011201872809d2679fc1f23ed75498ed21019fcc0a4c4160e561a78fd |
| Cópia recusada, não sintética | 36700160 bytes, exatamente 35 MiB |
| SHA da cópia e do prefixo do íntegro | 109a69412d0322ba1898b96ba4d02bf1573bccb9dd1811be62ac52f57879dfd5 |
| Cauda ausente | 14882520 bytes |
| Tabela de seções ELF do íntegro | Offset 51579416, 3264 bytes, toda fora do prefixo |

A cópia foi capturada em buffer estável na leitura observada; o módulo
íntegro veio de uma cópia cujo SHA corresponde à referência publicada.
mtime/ctime diferem aproximadamente 5,46 segundos na amostra recusada.
Esses metadados não identificam processo ou mecanismo. A consulta posterior
não encontrou descritor aberto para essa cópia no alcance visível de /proc.
fanotify_init foi recusado com EPERM e capacidades efetivas zero. Uma
observação limitada por inotify também não atribuiu escritor: o log
coletado não contém encerramento e é marcado incompleto. Não é auditoria
completa nem prova de ausência de escrita por outro processo.

[Registro do incidente](references/capture-a0-recurrent-copy-incident-20261103.json)
e [método/eventos observados](references/capture-a0-copy-observation-20261103.json).
Os bytes recusados e metadados foram guardados fora do Git em
S21-A0-dhd-copia-recusada-20261103.tar.gz, 10303135 bytes, SHA
4916f6f89ba4d5827a8067efb41702b00ddba8125e11c91c92581dad43f43202.
O bundle está identificado no registro e seu payload é explicitamente
inválido, para investigação, nunca para carga. É distinto do incidente
histórico mali de 25 MiB e não demonstra que ambos têm o mesmo autor.

A reação implementada não repara nem ignora a cópia errada: os consumidores
passam a usar snapshots selados dos buffers vindos do tarball verificado,
criados antes da janela de mutação dos caminhos. Testes truncam as cópias
após extrair e demonstram que o consumidor continua lendo o snapshot
correto. A origem das mutações continua aberta e a falha é registrada.

## Controle de sobreposição de chamadas de execução

Foi feito um controle limitado nesta sessão, com o mesmo buffer íntegro
de dhd e gravação em blocos de 1 MiB/intervalo de 60 ms. A rotina não tem
truncate posterior: verifica o hash ao terminar e novamente quatro segundos
depois. Nos casos sobrepostos, outra chamada exec_command apenas espera
quatro segundos e grava uma nota não relacionada; seu código não abre o payload.

| Condição da amostra | Hash imediato | Verificação posterior |
|---|---|---|
| .ko sem outra chamada sobreposta, 2 casos | Integral em ambos | Integral em ambos |
| .ko com chamada sobreposta, 2 casos | Integral em ambos | Prefixo de 35 MiB em ambos, mesmo SHA da cópia recusada |
| .bin com chamada sobreposta, 1 caso | Integral | Integral |
| .bin sem sobreposição, 1 caso | Integral | Integral |

Os dois casos .ko divergentes também apresentaram mtime anterior ao da
verificação integral e ctime posterior. É uma condição de reprodução
observada, **não identificação do processo ou do mecanismo subjacente**.
A amostra não prova uma regra universal de extensão, um limite fixo de
tamanho, nem atribui retroativamente o incidente mali de 25 MiB. Também
não explica os 24576 bytes da Image. A segunda recusa de dhd, no ensaio
inotify, tinha 17 MiB, não 35 MiB; seu SHA também confere com o prefixo.

[Métodos, resultados e orquestração](references/capture-a0-overlap-observation-20261103.json).
O controle usa chamadas da API de execução desta sessão: writer iniciado
com yield de 1000 ms, seguido da outra chamada com yield de 10000 ms.
Somente executar dois scripts em um Linux comum não reproduz necessariamente
a mesma condição. Não se conclui que o Linux Mint do usuário tenha esse defeito.

Como mitigação operacional desta sessão, evitar sobrepor chamadas de
execução durante gravações grandes; como garantia do consumidor, manter
snapshots selados e hashes. A primeira é uma precaução baseada nessa amostra,
sem garantia universal. A segunda é a proteção implementada e testada,
independente de descobrir o escritor. As recusas e os acertos
permanecem registrados separadamente.

## Reprodução e validação

```sh
python3 scripts/test_capture_a0_consumption.py
python3 scripts/check_capture_a0_sizes.py \
  --stock-dir /insumos/raw \
  --candidate-artifacts /insumos/S21-HZC2-alinhado-completo-20261102.tar.gz \
  --source /insumos/Kernel.tar.gz --tools-root tools/root \
  --output-dir /saida/dimensionamento-novo
python3 scripts/check_capture_a0_plan.py \
  --stock-dir /insumos/raw --source /insumos/Kernel.tar.gz \
  --sizing-report /saida/dimensionamento-novo/report.json \
  --output /saida/execucao-plano.json
```

Os dois runners retornam 2 com questões abertas e 1 em caso de recusa.
O segundo usa objetos Git do commit e0aa2e1 como referência textual e
confere o relatório produzido pelo primeiro contra os artefatos publicados;
não substitui sua execução nativa. Não há novo build C do kernel.

São 16 controles novos, 312 testes A0 e baseline obrigatório 9/9 aprovados.
Incluem troca do caminho após a leitura, tentativa de escrita/truncamento
do descritor, hash gzip divergente com conteúdo descomprimido igual,
recusa antes de emitir payload errado e mudanças de coordenadas por página.
[Relatório](references/capture-a0-plan-execution-hzc2.json) e
[validação](references/capture-a0-plan-execution-validation-20261103.json).
Hashes do relatório completo de medição identificam a execução; identidade
dos bytes é comparada por artefato/metadados, sem exigir PIDs/tempos iguais.

A0 aberto. A1 não iniciado. Fase 2 aguarda escolha do usuário; Fases 3/4
permanecem bloqueadas no alcance descrito. Nenhuma decisão OEM/ação no
aparelho ou merge de PR foi realizado. Somente código/relatórios textuais no Git.
