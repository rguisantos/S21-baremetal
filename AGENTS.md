# Orientações para trabalhar neste repositório

Orientação do usuário em 2026-10-23: **sempre fazer commit e manter o
repositório organizado**. O usuário também determinou realizar a revisão e
o merge das entregas concluídas, sem encerrar o trabalho apenas com o PR aberto.

- Ao concluir uma alteração, confira o diff e registre os arquivos pertinentes
  em um commit com mensagem objetiva. Preserve alterações alheias ao trabalho.
- Revise o diff e as discussões do PR, confira as validações pertinentes,
  corrija bloqueadores e faça o merge do head revisado. Depois sincronize a
  main local e prossiga o desenvolvimento. Não integre alterações com falhas
  conhecidas ou conflitos pendentes.
- Organize código em `scripts/`, `r8/`, `lab/` ou no módulo correspondente;
  documentação em `docs/` e evidências textuais em `docs/references/`.
- Atualize os índices, README, roadmap e worklog quando o estado técnico ou
  os próximos passos mudarem. Diferencie evidência observada de hipótese.
- Use hashes e revisões fixadas para análise de firmware/fontes. Não adicione
  pacotes completos de firmware, dumps privados ou dependências temporárias.
- Execute a validação pertinente à mudança. Preserve comandos/resultados
  necessários para reprodução; repita ensaios longos quando houver motivo técnico.
- Antes de encerrar, confira o commit e a árvore de trabalho e informe o que
  foi alterado, validado e o que ainda permanece pendente.
