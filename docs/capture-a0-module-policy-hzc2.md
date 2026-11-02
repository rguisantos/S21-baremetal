# A0: proposta de módulos e verificações estáticas HZC2

Continuação do [build completo do PR #80](capture-a0-crc-trace-hzc2.md),
base `a471e7d`, em 2026-11-02. Esta rodada compara o vendor ramdisk original
com os módulos do candidato e propõe um conjunto para o pacote offline.
O [relatório](references/capture-a0-module-policy-hzc2.json) e a
[validação](references/capture-a0-module-policy-validation-20261102.json)
registram os resultados. Não foi alterado um pacote de boot ou o aparelho.

## Proposta de referência

A proposta usa **o build do kernel candidato e os 274 módulos stock do
vendor_boot original**. Mantém os arquivos originais de módulos e os
pedidos de `modules.load`; o relatório guarda nomes, caminhos e hashes.
A alternativa recompilada é limitada aos mesmos 274 nomes, sem incluir
`input_booster_lkm` e `sec_debug_sched_info` nesta seleção.

Os dois adicionais não são necessários para resolver os imports fortes
ou as dependências declaradas do conjunto selecionado. Isso se limita a
este vendor ramdisk: não os classifica como desnecessários para outras
partições ou finalidades. Os 276 módulos permanecem nos artefatos do build.

A seleção é **uma proposta com duas lacunas de versão**, não uma aprovação
de ABI ou uma imagem pronta. O contêiner de payload modificado, a política
de carga completa e os demais gates A0 continuam abertos. Preservar o
vendor_boot original é uma escolha de referência para reduzir os componentes
a modificar; não resolve a aceitação de um boot.img alterado.

## Resultado dos dois conjuntos selecionados

| Verificação | Stock: 274 | Recompilados: mesmos 274 |
|---|---:|---:|
| Imports fortes lidos da symtab | 13722 | 13722 |
| Imports fracos | 0 | 0 |
| Exports lidos das tabelas reais | 1914 | 1914 |
| Registros em __versions | 13995 | 13995 |
| Arestas do grafo combinado | 569 | 569 |
| Fornecedor ausente para import forte | 0 | 0 |
| Divergência de CRC nos imports versionados | 0 | 0 |
| Conflito de exports | 0 | 0 |
| Falha nas regras modeladas GPL/namespaces | 0 | 0 |
| Imports sem registro de versão | 2 | 2 |

Os seis campos comparados por módulo — imports, exports, versões,
dependências, licenças e namespaces — são iguais nos 274 pares. Isso é
paridade de metadados, não identidade binária ou teste de comportamento.

O leitor também conferiu os exports dos **276** módulos candidatos contra
o Module.symvers final, incluindo CRC, classe de export e namespace.
Para os módulos stock, os fornecedores são combinados a partir dos exports
reais desses módulos e dos exports vmlinux do candidato. A comparação não
pressupõe que os exports stock sejam os do módulo recompilado.

Todas as licenças declaradas nos conjuntos satisfazem a lista literal de
`license_is_gpl_compatible` da fonte fixada; isso descreve a condição usada
pelo carregador, sem constituir uma análise jurídica de licenciamento.
Há dois módulos com imports de namespace declarados: `mali_kbase` usa
`DMA_BUF`; `tzdev` usa
`VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver`.
A configuração candidata não permite namespaces ausentes; nenhuma ausência
foi encontrada nas regras verificadas.

## Duas lacunas que o kernel permite com aviso

Em ambos os conjuntos, `s2mpb02_mfd` tem 36 imports e 35 registros de versão,
incluindo `module_layout`. Faltam registros de consumidor para:

| Import | Fornecedor resolvido | CRC do export fornecedor |
|---|---|---|
| __stack_chk_fail | vmlinux candidato | 0xf0fdf6cb |
| __stack_chk_guard | vmlinux candidato | 0x8f678b07 |

Esses valores vêm do fornecedor; **não foram inseridos nos módulos** nem
tratados como CRCs de consumidor que não existem. O total de 2763 requisitos
stock cobertos no PR #80 continua correto para os registros inventariados;
esta rodada acrescenta o censo de todos os imports fortes.

`kernel/module.c:1357–1359` trata a ausência de uma versão específica numa
seção existente como aviso e retorna 1. Não exige `--force` nesse ramo.
O modelo registra `modeled_source_checks_passed=true`, mas mantém
`strict_plan_checks_passed=false`, com duas entradas
`crc_coverage_not_established`. A distinção evita tanto inventar uma
recusa do kernel quanto declarar cobertura de CRC desses dois imports.

## Vermagic: escopo da confirmação

A fonte candidata compõe `VERMAGIC_STRING` em `include/linux/vermagic.h`
e a usa tanto no carregador quanto nos módulos gerados por modpost.
A referência do mesmo build é:

```text
5.4.242 SMP preempt mod_unload modversions aarch64
```

Os módulos stock têm o primeiro campo
`5.4.242-30958140-abG998BXXSJHZC2`. Em `kernel/module.c:1383–1392`, com
MODVERSIONS e uma seção de versões, `same_magic` ignora esse primeiro
campo e compara o restante. Os módulos lidos têm __versions, e o candidato
tem CONFIG_MODVERSIONS=y. Logo, **a diferença do sufixo isoladamente não
reprova essa comparação na rota kernel candidato + módulos stock**.
Diferenças em SMP/preempt/modversions/arquitetura continuam pertinentes.

Essa validação pertence ao carregador de módulos do kernel. Vendor_boot
é o contêiner que entrega o ramdisk; não se atribui a ele a execução de
`same_magic`. Não foi demonstrado o sentido inverso, carregar módulos do
candidato em um kernel stock em execução, nem aprovação de carga real.

## Precisões sobre CRC e KMI

`expand_and_crc_sym` em `scripts/genksyms/genksyms.c:530` percorre o grafo
de declarações/tipos, incluindo structs, unions, enums e typedefs
alcançáveis. Portanto os CRCs dão evidência sobre essas interfaces. Eles
não medem todos os offsetof/sizeof produzidos pelo compilador, não cobrem
toda estrutura interna e não testam execução, CFI ou todas as regras ABI.

As pendências `android/abi_gki_aarch64_galaxy_presubmit` e `abi_greylist`
são **duas listas ausentes referidas pela configuração stock**, não duas
chaves Kconfig inteiras ausentes da fonte. A proveniência das listas e dos
dez nomes restantes continua conforme a [análise KMI](capture-a0-kmi-hzc2.md).
A igualdade de metadados aqui não demonstra essa origem.

## Reprodução e limites

```sh
python3 -m unittest discover -s scripts -p 'test_capture_a0*.py'
python3 scripts/check_capture_a0_module_policy.py \
  --vendor-boot /insumos/vendor_boot.img \
  --candidate-artifacts /insumos/S21-HZC2-artefatos-20261102.tar.gz \
  --source /insumos/Kernel.tar.gz \
  --output /saida/nova.json
```

O runner exige hashes exatos de imagem original, artefatos e fonte. Faz
leituras limitadas de ELF64 little endian/AArch64 ET_REL, registros de
versão de 64 bytes, kernel_symbol de 24 bytes e CRCs absolutos. Decodifica
as relocations das tabelas de metadados; não aplica relocations ao código.
Lê até 128 MiB por módulo, limitando os metadados selecionados a 16 MiB;
o buffer de entrada inclui debug, mas essas seções não são materializadas
separadamente como metadados.
Não executa o conteúdo dos arquivos ou programas de carregamento.

A normalização de dependências trata hífen/underscore e recusa ambiguidade.
A ordem topológica no relatório serve para auditoria: não substitui
`modules.load`, não ensaia o consumidor userspace e não prova a ordem de
inicialização de drivers. Imports fracos disponíveis com regras dependentes
de ordem são sinalizados como não modelados; não há imports fracos nos
dados reais desta rodada. Conflitos de export, CRCs divergentes e falhas
nas condições modeladas são explicitados, sem escolha silenciosa.

A fonte contém `module_sig_check`, hooks de segurança, inicialização CFI e
chamadas `uh_call(UH_APP_RKP, RKP_MODULE_LOAD, ...)` para PXN. No candidato,
CONFIG_MODULE_SIG=n, mas CFI, UH e RKP estão habilitados. Esses estados e
caminhos runtime não foram validados por este comparador. Assinatura,
CFI, relocação de código, firmware/dependências não expressas em símbolos,
comportamento e aceitação de boot continuam fora desta prova.

O comando retorna 2 após produzir a análise e conserva A0 aberto; retorno
1 indica erro/recusa de insumos ou formato. A proposta registra o conjunto
e as exceções; não autoriza instalação ou mudança da decisão OEM.

## Continuação — origem dos dois helpers, 02/11/2026

A [reexecução nativa de modpost](capture-a0-stack-versions-hzc2.md) sobre os
ELFs finais produz os 35 registros anteriores mais os dois helpers. Os
imports apontam para instruções reais de proteção de pilha na IRQ. Não foi
reproduzida a transição entre os intermediários do build original; os
módulos recebidos continuam com as duas lacunas. Nenhum deles foi reparado.

## Continuação — etapas ThinLTO, 02/11/2026

A [reprodução isolada por etapa](capture-a0-module-stages-hzc2.md) agora
conserva os intermediários e mede a diferença entre as duas linkedições.
Alinhar KBUILD_LDFLAGS_MODULE faz os helpers aparecerem antes do modpost e
produz 37 versões sem lacunas no módulo isolado; o conjunto stock permanece
intacto. A correção candidata requer validação em build completo antes de
fechar o gate de módulos. O runner completo oferece --align-module-prelink
com --compile; o histórico do build stock não foi reproduzido.
