# A0: perfil nativo p3s, preparação e CRCs do candidato

Continuação do [inventário stock](capture-a0-modules-hzc2.md), base
`0b67d7b` (PR #78), em 2026-11-01. Esta etapa compila a fonte Samsung
fixada, sem instrumentar a entrada e sem operação no aparelho. O resultado
não autoriza A1, flash ou uso de módulos stock com o candidato.

## Ambiente que o código realmente exige

O `build_kernel.sh` do arquivo Samsung exporta `PLATFORM_VERSION=11`,
`ANDROID_MAJOR_VERSION=r` e **`SEC_BUILD_CONF_VENDOR_BUILD_OS=15`**.
A terceira variável é necessária aos predicados do Kconfig Mali em
`drivers/gpu/arm/Kconfig`. Não se substituíram esses valores por uma versão
Android presumida. README_Platform descreve componentes da plataforma,
não estabelece compatibilidade do kernel ou de módulos.

O [runner](../scripts/check_capture_a0_build_profile.py) usa a fonte
verificada, um diretório de saída novo e ferramentas identificadas por
conteúdo. Executa quatro configurações nativas: completa; sem vendor OS;
com GNU ld explícito; sem o prefixo do compilador compat32. As duas últimas
podem retornar zero enquanto removem recursos necessários, por isso o
retorno de `make` sozinho não é o critério de aprovação.

O perfil conferido inclui Clang 110001, LLD, LTO/Clang, CFI/Shadow sem
CFI permissivo, MODVERSIONS, TRIM_UNUSED_KSYMS, compat VDSO e Mali R38P0.
Também se registram todas as diferenças da configuração regenerada,
separadas da aprovação desse subconjunto. Uma configuração que preserva
os recursos selecionados não é automaticamente igual à IKCONFIG stock.

## Resultados nativos já conferidos

A [validação da rodada](references/capture-a0-build-validation-20261101.json)
registra os testes e os limites. O [relatório](references/capture-a0-build-profile-hzc2.json) separa os
controles encerrados do estado da compilação completa.

| Controle | Retorno make | Efeito observado |
|---|---:|---|
| Ambiente completo | 0 | Perfil crítico preservado |
| Sem vendor OS | 2 | Erro de sintaxe no Kconfig Mali |
| GNU ld explícito | 0 | LLD/LTO/CFI removidos da configuração |
| Sem compilador compat32 | 0 | COMPAT_VDSO removido |

Na configuração completa, a comparação com o defconfig fornecido tem
duas diferenças: `CONFIG_KMI_SYMBOL_LISTS=""` aparece e
`CONFIG_SEC_AUTO_INPUT=m` desaparece. A busca literal na fonte completa
localizou SEC_AUTO_INPUT somente no defconfig, sem declaração Kconfig.
Isso é uma discrepância de proveniência a resolver; não se presumiu que
seja irrelevante. As duas chaves fonte-versus-IKCONFIG stock discutidas na
[rodada KMI](capture-a0-kmi-hzc2.md) continuam uma comparação distinta.

`make prepare` produziu VDSOs AArch64 e ARM de 32 bits. O objeto
`kernel/module.o` gerou quatro atribuições reais de genksyms, todas iguais
aos requisitos dos consumidores stock:

| Símbolo | CRC candidato e stock |
|---|---|
| `module_layout` | `0x1e5b7ab7` |
| `__module_get` | `0x02cbec78` |
| `try_module_get` | `0xd497d133` |
| `module_put` | `0xa503ed0d` |

São CRCs recalculados do candidato, não uma cópia dos valores extraídos
dos módulos. A coincidência de `module_layout`, exigido pelos 274 módulos,
fecha apenas essa comparação parcial. Não equivale a comparar os 2763
nomes do conjunto stock nem a estabelecer compatibilidade de ABI.

## Identidade das ferramentas

O Clang r383902 mantém o commit e a árvore de conteúdo fixados em A0.
A identidade Git inclui conteúdo, caminhos, modos executáveis e destinos
de symlinks. O verificador recusa arquivos extras e diferenças; não aceita
apenas o texto de `clang --version`. O hash do gzip de transporte é uma
observação separada: metadados ou compressão do arquivo servido podem
mudar sem mudar a árvore Git. Os três executáveis Clang/clang.real/LLD
continuam sujeitos aos hashes SHA-256 já fixados.

As duas toolchains GNU Android 4.9 foram recuperadas de revisões AOSP
fixas da linha android11-release. São dependências **do candidato**;
não foi demonstrado que representam a revisão exata utilizada pela
Samsung no stock. As bibliotecas/ferramentas host também são distintas
dessas toolchains de destino. Os [pins desta rodada](references/capture-a0-build-pins-hzc2.json) registram as origens.

## Correção delimitada do TUI para O=

Três includes de `drivers/misc/tui/Makefile` usam caminhos relativos:
DPU30, panel e tzdev. Em build `O=`, são procurados a partir da árvore de
objetos; os headers existem na fonte. A [correção](../scripts/patches/p3s-tui-srctree.patch)
acrescenta `$(srctree)/` somente a esses três caminhos, sem desativar TUI,
TrustZone, CFI ou outros recursos. Isso não demonstra defeito no build
in-tree prescrito pelo script original.

O runner primeiro exige a falha dos objetos `stui_inf.o` e
`stui_hal_display.o` pelos headers `tee_client_api.h` e
`dynamic_mipi/band_info.h`; aplica a mudança somente ao Makefile com o
hash original conhecido; então exige sucesso dos mesmos objetos. A fonte
compilada passa a ser um candidato com patch explícito, não uma reprodução
byte a byte do pacote stock.

## Tentativa completa: bloqueio na linkedição

`make vmlinux modules` terminou com retorno 2, sem timeout. Foram compilados
3856 objetos antes do caminho LTO/MODPOST; a linkedição de
`.tmp_vmlinux.kallsyms1` foi recusada. MODPOST avisou que seis exports
não receberam versão; o LLD encontrou relocação R_AARCH64_ABS32 contra
os respectivos símbolos `__crc_*`:

- `nf_conntrack_destroy`, `nf_register_net_hooks`, `nf_unregister_net_hooks`;
- `ieee80211_rx_irqsafe`, `ieee80211_rx_napi`, `ieee80211_sta_ps_transition`.

Os arquivos `net/netfilter/core.o.symversions` e
`net/mac80211/rx.o.symversions` estavam vazios. O `Module.symvers`
intermediário contém CRC zero nesses seis nomes; não é o conjunto final
de kernel e módulos e não foi aceito para a cobertura dos 2763 requisitos
stock. Nenhum vmlinux ou conjunto de módulos concluído foi aprovado.

O próximo alvo é o pipeline de pré-processamento/genksyms desses dois
objetos, conferindo os exports efetivamente vistos e a ordem de atualização
de autoksyms. A causa dos arquivos vazios ainda não está demonstrada. A conferência
do `gki/abi_symbollist.raw` fixado encontrou os seis nomes na whitelist;
não se atribuiu a falha à simples ausência desses nomes nessa lista.
Não se aplicou `-fPIC`, nem se desligaram MODVERSIONS/LTO/CFI para
contornar o erro. Os quatro CRCs de `module.c` continuam válidos como
comparação parcial, sem cobrir os seis exports ou o conjunto completo.

## Conferência isolada dos dois produtores

Uma preparação nova, com as mesmas três árvores de ferramentas e perfil
crítico preservado, compilou somente `net/netfilter/core.o` e
`net/mac80211/rx.o`. Ambos os `.symversions` têm 127 bytes e três
atribuições. O [relatório isolado](references/capture-a0-genksyms-isolated-hzc2.json)
registra os seis valores e hashes. O pré-processamento Clang de cada
comando `.cmd`, com `-E -D__GENKSYMS__`, contém três marcadores de export;
`genksyms -r /dev/null` retorna zero e gera exatamente os bytes dos
respectivos `.symversions`.

Com `-w`, genksyms retorna 1 e relata expansão de tipos incompletos, mas
gera as mesmas atribuições. Esse modo de diagnóstico não foi confundido
com o comando quiet usado pelo Kbuild, que retornou zero no ensaio isolado.
Esses seis nomes não aparecem na união de CRCs exigidos pelos consumidores
stock inventariados; não há CRC stock deles nesse inventário para comparar.

O ensaio **não reproduziu os arquivos vazios** da tentativa completa.
Não demonstra correção do build completo ou causa intrínseca no parser.
O próximo ensaio deve acompanhar conteúdo/hash dos dois `.symversions`
ao longo do pipeline completo e seus agregados LTO, começando por uma
saída nova. Não se injetam manualmente estas atribuições no kernel.

## Reprodução

Prepare a fonte e as três toolchains indicadas nos pins. O diretório host
contém ferramentas e headers de flex, bison, m4, bc, cpio, libelf e zlib;
GCC/G++ host, make, libc e utilitários do sistema também são necessários.
Não se publicam pacotes completos, firmware, módulos ou fontes Samsung.

```sh
python3 -m unittest discover -s scripts -p 'test_capture_a0*.py'
python3 scripts/check_capture_a0_build_profile.py \
  --source /insumos/Kernel.tar.gz \
  --toolchains /insumos/toolchains \
  --host-root /insumos/host \
  --work-dir /saida/a0-build-novo \
  --compile
```

As subpastas de toolchains devem ser `clang-r383902`, `aarch64-android49`
e `arm-android49`. O runner verifica a identidade antes de executar os
compiladores. A saída deve ser nova e os caminhos de build não devem
conter espaços ou metacaracteres de shell/Make. Sem `--compile`, roda os
controles, `prepare`, `module.o` e os dois objetos TUI. Com a opção, tenta
`vmlinux modules` em quatro jobs, com limite de 30 minutos para essa etapa.
Timeout encerra o grupo de processos; não transforma objetos parciais em
build concluído. O relatório é salvo antes da etapa longa e após seu fim.

Retorno **1** indica recusa de insumos ou falha numa etapa preparatória.
Retorno **2** indica que a análise terminou e mantém A0 aberto: consulte
`full_build_completed` e `candidate_comparison` para distinguir build final
reprovado, comparação ausente ou cobertura de CRC aprovada. O relatório distingue
preparação, CRCs parciais de genksyms e comparação de `Module.symvers`
após build completo. Cabeçalhos dos VDSOs ARM/AArch64 são conferidos,
sem afirmar execução em hardware.

## Identificação de versão e dependências host

O header gerado desta execução declara `UTS_RELEASE="5.4.242"`; o vermagic
stock tem prefixo `5.4.242-30958140-abG998BXXSJHZC2`. Não se forjou esse
sufixo para obter igualdade textual. Em `kernel/module.c:1383`, o ramo
MODVERSIONS de `same_magic` ignora o primeiro campo quando `has_crcs` é
verdadeiro; `check_modinfo` fornece `info->index.vers`. Logo, a diferença
de prefixo não prova por si só recusa nem aceitação. Os demais campos e
as outras verificações do carregador continuam pertinentes.

O Makefile kperfmon tenta copiar headers de caminhos Android externos.
Esses caminhos não existem neste ambiente; há headers já presentes no
pacote. Seus avisos não foram tratados como prova de ausência global de
dependências de plataforma. Os pins identificam também esse Makefile.
O ambiente host não é uma imagem hermética, e caminhos de debug ou logs
podem variar entre execuções: não se afirma reprodução byte a byte do
kernel stock ou do relatório de uma compilação inteira.

## Limites e próximo passo

A compatibilidade continua exigindo resolver a proveniência KMI e a
configuração efetiva, conferir o conjunto kernel/módulos e suas políticas
(CFI, fornecedores, GPL/namespaces, assinatura e relocação). CRC igual é
um requisito necessário, não prova de ABI ou comportamento.
O [contêiner de payload modificado](capture-a0-repack-extent-hzc2.md)
continua um bloqueio independente. A1 ainda requer prova no ELF/Image
final da seção de captura e da ordem de entrada/continuação.
