# A0: plano de fases, gates e integridade transversal

Continuação: o [protótipo B offline](capture-a0-natural-b-hzc2.md) registra a escolha delegada e sua execução em 04/11/2026 UTC. Os resultados abaixo preservam o estado da rodada original.

Plano registrado em 03/11/2026, Campo Grande, a partir de origin/main
692f12d, após o PR #88. Formaliza a sequência acordada no chat; não escolhe
empacotamento, não autoriza ação no aparelho e não inicia A1.

## Referência e limites

O [PR #88](https://github.com/rguisantos/S21-baremetal/pull/88) documenta
o [mecanismo de alinhamento da Image](capture-a0-image-producer-hzc2.md):
24576 bytes a menos antes de ALIGN(65536), mais 40960 bytes a menos no
padding, resultam no deslocamento de 65536 bytes em __init_begin/stext.
O padding decorre dos limites anteriores sob a mesma regra; não é uma
segunda causa independente. A origem produtora dos 24576 bytes anteriores
(opção, objeto, função ou ordem de link) continua **não identificada**.

A [origem do corte de 25 MiB](capture-a0-copy-origin-hzc2.md) também ficou
não identificada. O controle sintético com RLIMIT_FSIZE produz o mesmo
prefixo/hash e erro explícito, sem atribuição histórica. Reabrir essa
investigação exige trilha, recorrência ou material histórico novo.

Os resultados existentes não demonstram ABI, carga, CFI/RKP ou aceitação
Samsung em runtime. O [roadmap](roadmap.md) e a
[proposta de carga, captura e recuperação](marco-a-carga-captura-recuperacao.md)
continuam sendo as referências para os marcos A/B e os gates A0–A5.
As fases abaixo subdividem o trabalho restante de A0; não renumeram esses gates.

## Fases e critérios de saída

### Fase 1 — atribuição da Image

Comparar receita de link, seções e limites do vmlinux candidato com aquilo
que tiver evidência do stock. Não tratar intervalos de kallsyms como uma
tabela ELF stock ou o mecanismo ALIGN como causa produtora já atribuída.

Saída: origem demonstrada, ou registro formal de **não identificada**,
com evidências disponíveis, hipóteses excluídas e hipóteses restantes.
O relatório do PR #88 já oferece essa base documental. Nova investigação
exige um alvo concreto adicional; não repetir a decomposição sem motivo.
Esse encerramento preserva a incerteza técnica e não aprova um pacote.

### Fase 2 — decisão de empacotamento

Depois do registro de saída da Fase 1, preparar opções comparáveis para
decisão escrita do **usuário**: preenchimento, strip ou outra geometria.
Não adotar uma opção antecipadamente. O [montador atual](capture-a0-container-hzc2.md)
exige payloads de tamanho exatamente igual ao stock, recusando tanto
crescimento quanto redução. O [dimensionamento existente](capture-a0-payload-sizes-hzc2.md)
é evidência de medição, não aprovação de política de instalação.

A comparação deve separar kernel, ramdisk, dependências, comprimentos,
hashes e efeitos sobre o contêiner/assinaturas. Strip não substitui uma
solução para a Image menor. Tamanho de arquivo stock não prova capacidade
física da partição. Nenhum contêiner é considerado aceito por apenas caber.

Saída: opção explicitamente aceita pelo usuário, com requisitos e validações
pendentes registrados, ou caminho de contêiner bloqueado se nenhuma opção
for aceita. Apresentar opções não equivale a autorização para adotá-las.

### Fase 3 — aceitação e assinatura

Tratar assinatura/aceitação Samsung, SignerVer03 e vbmeta pai na rota
escolhida. A chave de laboratório e um hash/RSA offline válidos não
demonstram confiança ou aceitação pelo monitor Samsung. Preservar bytes
SignerVer03 não equivale a regenerar ou validar sua assinatura.

Saída: aceitação demonstrada na rota escolhida, ou bloqueio documentado.
Se a prova depender de operação física sem autorização, a etapa permanece
bloqueada; o documento não fornece essa autorização por associação.

### Fase 4 — KMI e política runtime

Fechar a proveniência dos dez nomes sem origem demonstrada e das duas
listas ausentes, galaxy_presubmit e abi_greylist, conforme a
[auditoria KMI](capture-a0-kmi-hzc2.md). Não atribuir os dez nomes às duas
listas por suposição. Definir conjunto/dependências e política de carga
dos módulos, incluindo condições CFI/RKP, separando regras estáticas de
comportamento efetivamente validado em runtime.

Saída: evidências e política verificadas no alcance declarado, ou bloqueios
específicos documentados. Definir uma política não prova sua execução.
Cobertura de CRC, coerência dos recompilados e vermagic não aprovam ABI
ou carga runtime; essas lacunas não se convertem em PASS documental.

### Fase 5 — revisão contínua de integridade

Revisar a cobertura das fronteiras de consumo em todas as fases.
**É uma obrigação transversal desde a Fase 1**, não uma verificação adiada
até depois da Fase 4. Para cada payload: ler uma vez, verificar o buffer
e processar esse mesmo buffer. Hash seguido de reabertura não basta.
Consumidores nativos precisam de uma forma demonstrada de consumir os
mesmos bytes verificados, sem presumir estabilidade futura do caminho.

O hash do tarball preservado ancora a origem, não uma cópia posterior.
As 275 releituras do PR #87 provam aqueles destinos no instante verificado;
não certificam todos os consumos do pipeline. O runner do PR #88 aplica
buffers verificados ao seu escopo, sem fechar a cobertura do pipeline inteiro.

Saída por etapa: consumidores e bytes cobertos identificados, recusas
testadas e lacunas explicitadas. A conferência externa do tarball permanece
pendente até execução independente no ambiente do usuário; uma nova execução
do assistente não muda essa classificação.

## Gates, decisões e escopo

- Bloqueio documentado mantém o gate fechado. Registrar uma fase como
  bloqueada não libera A1; mudar esse critério exige revisão explícita.
- Nada de A1 enquanto as Fases 1–4 não atenderem aos requisitos aplicáveis
  e aos gates da proposta de captura. A integridade transversal continua exigida.
- Não aplicar preenchimento, strip como política ou nova geometria antes
  da saída documental da Fase 1 e da decisão escrita da Fase 2. A saída
  não identificada da Fase 1, sozinha, não autoriza empacotamento.
- A decisão OEM e qualquer ação no aparelho dependem de nova decisão
  escrita do usuário. Não repetir coletas já negadas.
- No Git, somente código e relatórios textuais. Firmware, Image, módulos
  e ramdisks permanecem fora. Não reabrir frentes pausadas por associação.

Estado: **A0 aberto; A1 não iniciado; sem decisão OEM ou ação no aparelho.**
Este registro não executa as fases nem escolhe uma opção de empacotamento.

## Execução offline registrada

A [execução por fase](capture-a0-execucao-hzc2.md) formaliza a saída não
identificada da Fase 1, apresenta opções na Fase 2 e registra os bloqueios
das Fases 3/4. Corrige e executa as fronteiras do runner de dimensionamento
na Fase 5, sem certificar todo o pipeline. Não adota pacote ou inicia A1.
