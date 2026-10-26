# Revisão do projeto e próximos passos — 2026-10-25

Base auditada: **main `43356de58be84cfaf1b477f1cc8fb9b3b8f7e604`**, após
PR #31. Data em America/Campo_Grande. A consulta ao GitHub encontrou zero
PRs e zero issues abertos naquele instante, antes desta entrega documental.

Continuação de implementação: o [baseline obrigatório e CI](baseline-validation.md)
atende à primeira recomendação abaixo. Os achados e resultados desta revisão
permanecem como registro da base auditada.

**A prioridade deve voltar ao primeiro diagnóstico observável no S21.**
O laboratório R10 funciona nos ensaios selecionados. Para chegar ao aparelho,
faltam um caminho de carregamento verificável, região/coerência e recuperação
do registro. NEWTIME, criptografia e XNU são frentes com dependências próprias;
a contagem de instruções ou testes não mede a prontidão física do projeto.

## Escopo desta revisão

Conferidos README, roadmap, regras de integração, código de entrada e main
R10, diagnóstico independente, linker, loader em quarentena, scripts de
teste e documentos das frentes Samsung/memória/XNU. Os dois READMEs enviados
foram relidos nos caminhos locais, preservando os originais. Não foi feita
nova auditoria linha a linha de todos os drivers ou uma nova execução iOS.
Nenhum telefone, partição, registrador Samsung ou serviço seguro foi acessado.

A revisão rerodou os testes da tabela abaixo e compilou o ELF de produção.
[Evidência resumida, comandos e hashes dos logs/fontes](references/repository-review-20261025.json).

| Verificação executada | Resultado | Limite |
|---|---|---|
| Parser/política FDT C | 43 casos, ASan/UBSan, PASS | Fixtures do host, sem FDT ativo do aparelho |
| Contêiner e consumidor C | 59 casos antes do build; 60 depois, ASan/UBSan, PASS | Um caso depende de existir o ELF real |
| Materialização | 17 casos, ASan/UBSan, PASS | Modelo, bytes e recusas antes de escrita |
| Compilação do R10 real | PASS | Há warnings em MCT/SMP experimentais; nenhum boot Samsung demonstrado |
| Image de diagnóstico no QEMU | 6 entradas aceitas e 6 recusas M/C, PASS | EL1/EL2 e relocações laboratoriais |
| Carregador QEMU com main R10 de produção | 1 handoff e 5 recusas, PASS | Uma CPU, backend UART QEMU; 25 IRQs observadas no caso positivo |

R8/R9 e XNU mantêm os resultados históricos identificados nos documentos;
suas regressões não foram repetidas nesta revisão. Não somar as contagens
como porcentagem de cobertura ou prontidão do telefone.

## Achados que mudam a próxima entrega

**1. Cobertura do contêiner depende de um artefato anterior.** Em
`scripts/test_payload.py`, o caso que confere `__payload_end` e o tamanho
real de BSS/pilhas só roda se `r8/build/r10_payload.elf` existir. A primeira
execução passou com 59 casos; depois de `make -C r8 build/r10_payload.elf`,
passou com 60 e `R10 ELF extent PASS`. O código não falhou: falta tornar a
pré-condição e a cobertura obrigatória explícitas no comando de validação.
Os comandos completos do README já compilam antes dos testes; a execução
isolada não garante a mesma cobertura. Nesta entrega, a documentação do
formato passa a explicitar esse requisito; runner obrigatório e CI continuam
planejados, sem alteração da lógica dos testes.

**2. Falta uma checagem de compilação/testes versionada no GitHub.** Não há
arquivos rastreados em `.github`. A revisão automática de PR está configurada
e deve continuar concluindo antes do merge, conforme AGENTS.md. Recomenda-se
acrescentar workflow e comando único para build, host e QEMU selecionado,
com logs, timeout e falha explícita se um teste obrigatório for pulado.
O bootstrap atual também depende do índice APT/estado do host; versões e
hashes fixados devem preceder a retirada das ferramentas offline.

**3. O contrato de entrada permanece uma lacuna de produto.** O assembly
R10 recusa tudo que não seja EL2, testa M/C de EL2 e EL1 e só depois escreve
pilhas/BSS. O diagnóstico separado aceita EL1/EL2, grava 128 bytes dentro
da própria Image e não usa periféricos. O salto físico Samsung ainda não
forneceu esses dados; a inicialização LK em EL1 não mede o EL no salto final.
O shim continua desativado e o contêiner S21R10 não é um carregador Samsung.

**4. Carregar e observar precisam ser planejados juntos.** No último estado
informado pelo usuário, o aparelho estava sem root e com bootloader travado.
A revisão não mediu novamente esse estado. Um caminho que dependa de acesso
privilegiado, imagem personalizada ou bootloader alterado não pode ser tratado
como disponível sem satisfazer essas condições. O bugreport recuperou logs
stock; ele ainda não é um transporte demonstrado do registro do diagnóstico.
UART e leitura de RAM seguem pendentes. As mesmas coletas Shizuku negadas
não devem ser repetidas sem uma mudança concreta de acesso ou canal.

**5. DRAM observada não fornece RAM utilizável.** Samsung/D1Z/12 GB e a
assinatura B foram observados no log do bootloader. Não fornecem os bancos,
reservas, initrd ou FDT final. A reconstrução estática de NEWTIME já chegou a
bindings nominais e SMC, mas o slot47/X0 e transporte de `0x31580` continuam
abertos: três das 47 referências de cópia foram examinadas, outras 44 não.
Essa frente deve ter perguntas e critérios de parada definidos e permanecer
paralela ao contrato do primeiro diagnóstico.

**6. A documentação central acumulou estados históricos.** O roadmap ainda
indicava PR #26 no cabeçalho e `cd8b512` no rodapé; a revisão central apontada
no README era de 21/10. Os leitores NEWTIME recentes também faltavam no
catálogo de scripts. Esta entrega atualiza os pontos de entrada preservando
os relatórios antigos como evidência histórica. O manifesto de binários
grandes já existe; sua ausência não deve reaparecer como pendência atual.

## Ordem recomendada de trabalho

| Ordem | Entrega | Critério de conclusão |
|---:|---|---|
| 1 | **Baseline reproduzível e CI**: comando único que constrói o ELF real antes de testar; relatórios de host/QEMU e recusa de skips obrigatórios | Execução limpa repete 43 FDT, 60 contêiner, 17 materialização, 12 diagnóstico e 1+5 loader; falhas propagadas e revisão automática preservada |
| 2 | **Contrato do diagnóstico Samsung**: matriz de caminho de carga, formato, validações, região/coerência, entrada, recuperação e restrições do último estado informado | Cada requisito com fonte/evidência ou bloqueio nomeado; identificar o percurso que pode ser demonstrado e como ler os 128 bytes |
| 3 | **Fechar entrada e observação da rota escolhida**: seguir cópia/salto final e callbacks relevantes, mais canal de leitura | Critérios do Marco A atendidos antes de qualquer execução física; registro completo vinculado à Image/endereço |
| 4 | **Memória e R10 em uma CPU**: FDT ativo ou reconstrução verificável de bancos/reservas, imagem/pilhas/DTB/initrd e permissões GIC/timer | Adaptar a entrada ao estado observado, validar intervalos e obter boot/IRQs no aparelho sem suposições de RAM livre |
| 5 | **Expansão e port XNU**: SMP/PSCI, periféricos e adaptador Samsung → XNU, com testes próprios | Base de uma CPU e contratos físicos comprovados; XNU e R10 conservam ABIs distintos |

Na pesquisa paralela, priorizar uma aresta que resolva um requisito acima.
Para NEWTIME, isso pode ser um transporte de tabela, preservação de binding
ou informação que feche o mapa; inventariar as 44 cópias não é requisito
universal do diagnóstico. Para EPBL/SMC, aprofundar o provedor quando sua
ligação com o bloqueio da rota estiver demonstrada. Estados desconhecidos
continuam desconhecidos; não fornecer respostas MMIO/SMC para fechar a prova.

O próximo PR de implementação recomendado é o **baseline obrigatório e CI**,
sem alterar a entrada de hardware. Em paralelo, a próxima investigação deve
produzir a matriz do diagnóstico e seu canal de leitura. O detalhamento das
frentes físicas permanece no [roadmap](roadmap.md); os critérios dos Marcos
A/B e o escopo do callback QEMU não foram relaxados por esta revisão.
