# HackiOS: falhas de preparação relatadas e reproduzidas

Em **2026-10-22**, o usuário trouxe um relato GLM-5.3 de preparação do
userland iOS no QEMU, ainda em andamento. Reproduzimos quatro problemas
de preparação com arquivos sintéticos e fornecemos um patch para a versão
auditada. A correção foi conferida por seis fixtures de jobs, quatro
fragmentos Bash e `git apply --check`; o build completo não foi executado.

Os heads consultados continuavam nos commits já examinados:

- kernel: `8e61187098f2c26c5daee8f9f72b6416aa64b9ab`;
- userland: `906425b75e02b4f99eb5d7bb1ef7c9583472d772`.

O [relatório verificável](references/hackios-userland-host-20261022.json)
registra hashes das fontes, código de cada ensaio, modos e nomes gerados.
A preparação não usou binários/plists Apple, imagens iOS ou SDK. Os
programas apontados pelos plists de teste são arquivos de texto próprios.

## Quatro correções

| Problema | Evidência local | Correção no patch |
|---|---|---|
| Jobs `--rest` gravados em `RWA_PACKED16` | Dois jobs sob demanda colapsam em um arquivo; ocorre com a variável ausente ou definida | Trocar o iterador interno por env_name nos dois laços |
| Arquivos graváveis pelo grupo | umask 002 gera plists 0664 e diretório 0775; o leitor APFS conserva esses modos, embora use UID/GID 0 | umask 022 no início do build; a raiz gerada é recriada pelo script |
| drawable_test ausente no percurso prebuilt | A cópia original falha mesmo copiando os cinco executáveis presentes | Manter os cinco obrigatórios e copiar drawable_test somente quando existe |
| timedatectl falha sob set -e | A atribuição termina o shell antes de atingir o fallback UTC | Tratar a falha dentro da substituição e conservar o fallback |

Em `mkjobs.py`, o nome do arquivo corrente está em `name`. O laço de
propagação da variável `RWA_PACKED16` reutiliza esse nome; na gravação dos
jobs extras, o caminho passa a usar o nome da variável. A falha independe
de ativar a opção gráfica. Jobs explicitamente nomeados usam `label` na
gravação e permanecem separados.

## Controles observados

Cada fixture tem um job nomeado e dois jobs extras. A execução original
imprime que tratou dois extras, embora seus nomes não sejam preservados.

| Fonte e umask | Arquivos resultantes | Modos dos plists |
|---|---|---|
| Original, 002 | Um plist nomeado + RWA_PACKED16 | 0664 |
| Original, 022 | Um plist nomeado + RWA_PACKED16 | 0644 |
| Corrigida, 002 | Três plists distintos | 0664 |
| Corrigida, 022 | Três plists distintos | 0644 |

Outros dois controles, com `RWA_PACKED16=1`, preservaram a distinção:
original colide, corrigido conserva os três nomes e propaga a variável.
Isso testa propagação de ambiente, não execução Metal ou formatos de cor.

A terceira linha mostra por que renomear a variável não resolve os modos.
A conferência usou `read_tree` do gerador APFS original: ele atribui UID/GID
0 por padrão e conserva `st_mode`. Não montamos APFS nem executamos launchd
para reproduzir sua rejeição; essa parte continua como observação relatada
pelo GLM, coerente com os metadados encontrados.

Na cópia opcional, o fragmento original saiu 1; o corrigido saiu 0 e
conservou os cinco executáveis presentes. No timezone, um comando
timedatectl sintético retorna erro: original saiu 1 sem resultado, corrigido
saiu 0 e retornou UTC. Nenhum relógio/configuração do host foi alterado.

## Reprodução e patch

O script exige o commit e SHA-256 exatos das três fontes que lê/executa.
Gera cópias corrigidas em pasta nova e deixa o checkout de entrada intacto:

```sh
python3 scripts/check_hackios_userland.py \
  --userland-tree /caminho/hackios-xnu-userland \
  --out /caminho/nova-auditoria
```

O patch gerado deve ser idêntico ao
[patch versionado](../lab/xnu/patches/hackios-userland-portability.patch).
Para conferir aplicabilidade na cópia externa original:

```sh
git -C /caminho/hackios-xnu-userland apply --check \
  /caminho/S21-baremetal/lab/xnu/patches/hackios-userland-portability.patch
```

O patch preserva tabs e heredocs, altera somente os dois laços e três
pontos de `build.sh`. É específico desse commit; não incorpora mudanças
de spool, RAM compartilhada, imagem de sistema ou lista de daemons. Não
foi enviado como alteração ou comentário ao projeto upstream.

## Estado da interface e continuação do relato

O relato recebido cita backboardd, IOSurfaces, muitos processos e registro
do SpringBoard. São marcos intermediários de uma execução que o usuário
informou ainda estar em andamento. O material trazido não inclui o print
final ou o log bruto completo dessa sessão. Não contamos essa execução
como uma reprodução local de interface iOS.

Para registrar o próximo marco visual, conservar o screendump real do
framebuffer QEMU junto ao serial da mesma sessão, hashes das imagens,
comando de execução e diff aplicado. Uma interação seguida de nova captura
permite conferir atualização da tela e input, além do primeiro frame.

Quanto à retomada em outra sessão, a documentação oficial distingue RAM
em arquivo compartilhado do restante do estado da VM, que precisa ser
salvo/restaurado separadamente
([QEMU VM templating](https://www.qemu.org/docs/master/system/vm-templating.html),
documentação consultada em 2026-10-22, versão publicada 11.1.50). Essa
referência conceitual não valida uma receita de migração no QEMU 10.0.13
do relato. Checkpoint/retomada e continuidade da interface precisam de
ensaio próprio.

No S21-baremetal, o [XNU com init próprio](xnu-qemu-lab.md) já havia sido
reproduzido. Esta entrega avançou o
[adaptador FDT → recursos Apple](xnu-fdt-adapter.md); memória, carregamento
Samsung, GIC/timer e display Exynos continuam com critérios próprios.
