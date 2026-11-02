# A0: build completo com prelink ThinLTO alinhado

Continuação do PR #83, base `9163742`, em 02/11/2026, Campo Grande.
**make vmlinux modules terminou com retorno zero**, produzindo vmlinux e
276 módulos. O [relatório de build](references/capture-a0-aligned-full-build-hzc2.json),
a [auditoria](references/capture-a0-aligned-full-audit-hzc2.json) e a
[validação](references/capture-a0-aligned-full-validation-20261102.json)
registram os resultados. Nenhuma operação foi feita no aparelho.

## Resultado do gate desta rodada

O patch de prelink do PR #83 passou no build completo. A configuração
permaneceu idêntica à do candidato anterior, SHA-256
5e82e452e6a5bc008f191e971f0cc21cd97be5cad7965542403dedc67b45570a,
com LTO/ThinLTO, CFI, compat32, MODVERSIONS e proteção de pilha preservados.
A correção TUI já fixada continua presente; nenhum desses controles foi
desabilitado. As três árvores de toolchain e os executáveis fixados foram
conferidos antes da execução.

O Module.symvers final permaneceu **byte a byte igual ao PR #80**:
b5aebd8e2db225b247a552f5e5a07a66042ed29e74ca3f348e94487227975139.
Os 2763 requisitos stock inventariados continuam cobertos, sem ausências,
divergências ou conflitos. A correção altera a geração dos registros de
consumidor; não muda esses CRCs de fornecedor.

A auditoria conferiu cada export real dos 276 módulos contra o Module.symvers
final e comparou os imports do .lto.o, o C gerado e o __versions final.
No conjunto completo houve **zero imports surgidos após modpost, zero imports
sem versão e zero registros de versão sem uso**. Os registros gerados foram
preservados na final de todos os módulos. Não se usa uma contagem isolada
como substituto para a conferência dos nomes e CRCs.

| Conjunto diante dos exports do novo kernel | Stock original | Recompilados selecionados | Todos os recompilados |
|---|---:|---:|---:|
| Módulos | 274 | 274 | 276 |
| Imports fortes | 13722 | 13722 | 13797 |
| Imports fracos | 0 | 0 | 0 |
| Exports dos módulos | 1914 | 1914 | 1914 |
| Registros de versão | 13995 | 13996 | 14073 |
| Imports sem versão | 2 | 0 | 0 |
| CRC presente divergente | 0 | 0 | 0 |
| Regras GPL/namespace modeladas reprovadas | 0 | 0 | 0 |
| Cobertura estrita do plano modelado | Incompleta | Passou | Passou |

O stock permanece como recebido. A fonte candidata permite suas duas
versões ausentes com aviso; a auditoria conserva modeled_source_checks_passed
verdadeiro e strict_plan_checks_passed falso nesse caso, conforme PR #81.
Os dois conjuntos recompilados passaram também os checks modelados de
fornecedores, dependências, conflitos de export, GPL e namespaces.
Isso não demonstra carregamento ou ABI em execução.

## Diferenças em relação ao PR #80

Os 276 nomes continuam iguais. Imports, exports/CRCs, dependências, licenças,
namespaces e vermagic não mudaram nos metadados comparados. As únicas
mudanças de registros de versão foram:

| Módulo | Mudança gerada automaticamente |
|---|---|
| s2mpb02_mfd | Acrescentou __stack_chk_fail=0xf0fdf6cb e __stack_chk_guard=0x8f678b07 |
| dhd | Retirou __const_udelay=0xeae3dfd6, que não era importado pelo módulo final |

Nenhum CRC já presente foi alterado. Em s2mpb02_mfd, 36 imports aparecem
antes de modpost, que gera 37 registros incluindo module_layout. Em dhd,
328 imports correspondem a 329 registros. O total selecionado aumenta só
um registro: dois adicionados e um retirado. Não houve inserção ou remoção
manual de linhas nos módulos.

## Proposta de conjunto para o pacote offline

A proposta de referência passa a ser **o novo kernel com os 274 módulos
recompilados correspondentes ao vendor ramdisk**. Eles vêm do mesmo build
completo e têm a cobertura de versões conferida. O relatório registra nomes,
hashes e o mapeamento de cada caminho de build para seu caminho original
lib/modules no pacote. Preserva os pedidos e a ordem de modules.load como
entrada para a futura montagem; a ordem topológica serve só à auditoria.

Os dois adicionais input_booster_lkm e sec_debug_sched_info permanecem nos
artefatos e passaram a auditoria dos 276, mas ficam fora do conjunto
selecionado de 274. Não fornecem dependências necessárias a essa seleção
nas regras verificadas; isso não é um censo de outras partições ou uma
classificação global desses módulos como dispensáveis.

Nenhum ramdisk ou contêiner foi montado ou substituído. modules.dep original
é preservado por hash como referência, sem afirmar que um arquivo de
empacotamento novo já foi validado. O conjunto stock e sua proposta anterior
continuam documentados historicamente; suas ausências não foram reparadas.
A nova proposta é offline e não autoriza instalação.

## Evidência e limites

A fonte efetiva usada na auditoria foi conferida contra o arquivo Samsung:
module.c, license.h, export.h, modpost.c e genksyms.c permanecem iguais;
Makefile.modpost e TUI correspondem exatamente aos dois patches fixados.
A comparação usa exports vmlinux do novo Module.symvers e as tabelas reais
de cada conjunto de módulos. O sentido inverso em um kernel stock em
execução não foi testado.

GNU readelf 2.44 conferiu independentemente o ELF AArch64 ET_DYN de vmlinux
e os 276 ELFs ET_REL. Entrada virtual de vmlinux: 0xffffffc010080000;
SHA-256: 0355418bebc35257984558d234d61af4d6b71a312c8089b760fda7c1b3405eeb.
Não foi ensaiada essa entrada. Os alvos foram vmlinux/modules, sem criação
de um boot.img ou de um contêiner de flash.

O leitor encontrou três intermediários com mais de 4096 seções: fimc-is
8245, dhd 6859 e mcd-panel-s6e3hab 5199. A leitura de intermediários agora
pede explicitamente um limite de 16384; o padrão dos módulos finais continua
4096. Permanecem os limites de 128 MiB por ELF e 16 MiB de metadados, mais
as verificações de índices/tamanhos. Numeração ELF estendida não é aceita.
Os testes distinguem a exceção explícita do intermediário e o padrão final.

O observador de CRC registrou 30 eventos, sem erro ou esgotamento do limite;
o maior intervalo entre amostras foi 1,8 s. Os seis valores chegaram aos
agregados, script LTO e Module.symvers final. Vazios transitórios anteriores
aos primeiros valores preenchidos foram observados; a falha persistente
antiga não foi reproduzida. O sampler não exclui transições entre amostras.

No candidato, MODULE_SIG=n e CFI/UH/RKP estão habilitados. Compilação e
checks estáticos não validam os hooks de segurança, serviços RKP, CFI,
relocations ou comportamento dos drivers em execução. A origem das duas
listas KMI ausentes/dez nomes continua pendente. O contêiner modificado
também continua como gate; A0 não está concluído e A1 não foi iniciado.

## Artefatos preservados

S21-HZC2-alinhado-completo-20261102.tar.gz contém 2133 payloads verificados
mais manifesto, 430051580 bytes; SHA-256
d649de92e904eff21fd0cf40af0d10b5a10b67a54de54b5b6f234df628e10015. Inclui vmlinux, os 276 módulos,
todos os .lto.o/.mod.c/.mod.o e comandos/scripts de CRC disponíveis,
configuração, exports, mapas, logs e as fontes de evidência necessárias
ao replay. Não é cache completo de objetos, árvore completa de fonte ou
toolchains, Image de boot ou contêiner de flash.

O primeiro empacotamento foi recusado por conter uma cópia temporária extra
de vmlinux fora do manifesto. O arquivo final foi gerado estritamente pelos
nomes do manifesto e todos os payloads foram relidos/verificados no tar.
A ocorrência não mudou os resultados do build ou os binários auditados.

## Reprodução

```sh
python3 scripts/check_capture_a0_build_profile.py \
  --source /insumos/Kernel.tar.gz --toolchains /insumos/toolchains \
  --host-root /insumos/host --work-dir /saida/build-novo \
  --compile --trace-versions --align-module-prelink
python3 scripts/check_capture_a0_aligned_build.py \
  --build-dir /saida/build-novo --vendor-boot /insumos/vendor_boot.img \
  --source /insumos/Kernel.tar.gz \
  --reference-artifacts /insumos/S21-HZC2-artefatos-20261102.tar.gz \
  --output /saida/auditoria-nova.json
```

Ambos retornam 2 após a análise, mantendo A0 aberto; retorno de make é
registrado separadamente. Para repetir a auditoria sem compilar, use a pasta
desempacotada dos novos artefatos em --build-dir e acrescente
--preserved-layout. Essa rota foi conferida contra a árvore do build com
relatórios idênticos byte a byte. Os insumos de referência continuam
exigidos por identidade e hash.
