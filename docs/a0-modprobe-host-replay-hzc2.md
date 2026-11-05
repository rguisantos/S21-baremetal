# A0: resolução de módulos executada em host com backend simulado

Continuação de 05/11/2026, base `136c0e6`. O
[init stock](a0-init-module-loader-hzc2.md) identifica o caminho de resolução,
mas sua sequência completa não foi executada. Esta rodada executa uma
referência AOSP fixada com os arquivos reais do vendor ramdisk e um backend
que registra tentativas, sem carregar módulos.

## O que foi executado

A referência é system/core, revisão
`6072de17cd812daf238092695f26a552d3122f8c`, tag Android 11 r1. Os arquivos
libmodprobe.cpp e include/modprobe/modprobe.h foram obtidos do espelho AOSP
por HTTPS com TLS verificado e são exigidos pelos seguintes pins:

| Arquivo local | Bytes | SHA-256 |
|---|---:|---|
| libmodprobe.cpp | 15997 | ae0e51e9827fe9293918f4e83bbc7ee9baf251e4423a39e52ca0699adfcad5f1 |
| modprobe.h | 3301 | 399ca3a67d7106c8a1ef713107e8e98dce5e87d1fe514557ed4f5a27a553ef40 |

O [runner](../scripts/replay_a0_modprobe.py) conserva os corpos do resolvedor
e substitui includes por adaptadores de host: logging sem efeito,
ReadFileToString sobre um mapa dos controles conferidos, Split/EndsWith e
uma implementação simulada dos métodos externos. A unidade C++ gerada é
fornecida ao compilador em memfd selado. Fontes e insumos não são baixados
pelo runner e precisam coincidir com os pins antes da compilação.

Insmod registra sucesso para um módulo novo, o equivalente a EEXIST para
um nome já carregado no modelo e falha para o nome injetado. Essa distinção
segue o ramo EEXIST de
[libmodprobe_ext.cpp da mesma revisão](https://github.com/aosp-mirror/platform_system_core/blob/6072de17cd812daf238092695f26a552d3122f8c/libmodprobe/libmodprobe_ext.cpp).
Esse arquivo externo não foi compilado: não existem chamadas de carga ou
remoção de módulos no backend. Rmmod retorna false e GetKernelCmdline retorna
string vazia. ModuleExists usa o mapa de dependências, após verificar que
as referências stock apontam a arquivos regulares presentes.

São escolhas explícitas do ensaio: blocklist habilitada, lista estrita,
cmdline vazia, disponibilidade dos arquivos e sucesso de inserções novas
salvo falha injetada. Nenhuma opção do kernel ou comportamento de driver
é ensaiado. **Não é execução do init Samsung nem equivalência binária
demonstrada com sua libmodprobe.** A ligação com Samsung permanece a análise
estática selecionada do PR #94.

## Resultado com os controles reais

O vendor_boot usado é o mesmo stock HZC2 conferido no PR #93. Os buffers
dos arquivos são incorporados ao programa gerado; nenhum caminho privado
é reaberto pelo resolvedor. O runner primeiro exige as verificações
estruturais de módulos/carga já existentes.

- modules.alias: 1652 regras.
- modules.softdep: 26 linhas, com 45 alvos pre/post.
- modules.dep: 274 chaves e 3654 arestas.
- modules.load: 274 pedidos.
- modules.options e modules.blocklist: ausentes nesse vendor ramdisk.

| Backend injetado | Retorno do resolvedor | Novos módulos no modelo | Tentativas |
|---|---|---:|---:|
| Sucesso para novos nomes | success | 274 | 276 |
| Falha em dss, primeiro pedido da lista | failure | 0 | 1 |
| Falha em exynos_acme | failure | 209 | 216 |

No caso sem falhas, as 3654 dependências do arquivo precedem seus
consumidores na sequência de primeiras inserções. Há duas tentativas
repetidas, exynos_acme e mali_kbase; retornam o equivalente simulado a
EEXIST e não aumentam o contador. A reentrada durante resolução de
dependências/softdeps não deve ser contada como dois módulos novos.

A falha em exynos_acme ocorre em seis tentativas. Existem inserções bem
sucedidas depois da primeira falha, mas o processamento estrito da lista
termina com failure e 209 inserções novas. Isso distingue falha ignorada
em uma tentativa opcional de resultado global aprovado. Não foi desativado
nenhum teste para obter o caso positivo.

A softdep pre de mali_kbase cita memory_group_manager, que não tem chave
direta em modules.dep nem arquivo entre os 274 selecionados. A referência
ainda conclui o caso positivo. Isso não prova presença built-in, equivalência
funcional de outro driver ou funcionamento da GPU. Preserva a diferença
entre dependência opcional do resolvedor e requisito real do driver.

O [relatório completo](references/a0-modprobe-host-replay-hzc2.json) guarda
as tentativas, pins, unidade gerada e hipóteses. Duas compilações/execuções
finais produziram relatórios byte a byte idênticos. Não se transfere esse
resultado para o protótipo B, para uma cmdline desconhecida ou para o
telefone. A0 continua aberto para ABI/CFI/RKP e aceitação Samsung.

## Reprodução

Com os dois arquivos oficiais no diretório de fontes e o raw stock:

```sh
python3 scripts/replay_a0_modprobe.py \
  --vendor-boot /insumos/vendor_boot.img \
  --source-dir /referencia-fixada/libmodprobe \
  --output-dir build/modprobe-host-novo
python3 scripts/test_a0_modprobe_replay.py
```

O header deve ter o nome local modprobe.h. O diretório de saída deve ser
novo. O runner gera resolver, logs dos três casos e report.json apenas no
diretório escolhido. Exige g++/Linux e não usa acesso ao aparelho. Exit 0
confirma os três controles declarados; falhas de fonte, compilação,
timeout, processo, contabilidade ou cobertura são recusadas.

Os nove testes novos conferem contagem de EEXIST/falhas, formato/encerramento
do trace, identidade de fonte, literais C++ e adaptação dos includes. Esses
testes estão na CI e não baixam fontes. A execução nativa com fontes AOSP
foi local, não deve ser alegada como executada por esses testes de CI.

Validação adicional local: 394 testes A0 existentes, nove controles do init
stock e baseline R10 9/9 aprovados. Os nove testes de replay são separados
dessas contagens.
