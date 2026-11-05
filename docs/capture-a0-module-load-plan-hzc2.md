# A0: dependências declaradas e plano de carga dos módulos

Continuação de 05/11/2026, base `07edc8b`, após integração de #89–#91.

O [novo verificador](../scripts/check_capture_a0_load_plan.py) transforma
os metadados já medidos em uma ordem determinística de dependências primeiro
e permite verificar os arquivos de controle de carga no vendor_boot stock.
Não altera imagens ou carrega módulos.

## Resultado executado

O [inventário fixado](references/capture-a0-modules-hzc2.json), de 415440
bytes e SHA-256 `76fbc6e96cd0310fdc83e501acc39ae1eec955714cbb2e6698b7ff7240267e0b`,
contém 274 módulos e 569 dependências declaradas em modinfo. Todas resolvem
para nomes do conjunto, sem colisões após normalizar hífen/underscore e
sem ciclos. A [saída reproduzível](references/capture-a0-module-load-plan-hzc2.json)
inclui a ordem proposta completa. Ela não se confunde com a ordem original
de modules.load, que não foi conservada no relatório antigo.

Este resultado reprocessa metadados versionados; não relê os ELFs privados.
A análise de imports/exports e o grafo combinado já pertencem à
[auditoria de política](capture-a0-module-policy-hzc2.md). Este verificador
isola as dependências declaradas, sem alegar substituir aquela auditoria.

## Verificação dos arquivos reais

Com `--vendor-boot`, o runner exige a identidade stock publicada no A0,
usa o mesmo buffer conferido para layout/descompressão/CPIO e exige igualdade
integral dos metadados medidos com o inventário fixado. Só então lê
modules.load e modules.dep, sem extrair arquivos ou seguir symlinks.

Ele recusa referências ausentes, duplicatas e sintaxe fora do perfil stock.
Sinaliza entradas de modules.dep ausentes, dependências declaradas omitidas,
ciclos e dependentes bloqueados, inclusive por arestas adicionais do arquivo.
Também lista módulos não pedidos em modules.load e dependências que aparecem
depois do consumidor ou não aparecem na lista.

Uma sequência literal fora de ordem não demonstra falha de boot: um loader
do tipo modprobe pode resolver dependências recursivamente. A implementação
e os argumentos do consumidor userspace ainda precisam de validação própria.
O campo control_files_checks_passed trata cobertura/coerência estrutural;
literal_load_order_dependency_first registra a comparação separadamente.

Os arquivos privados não estão neste ambiente. Portanto o modo stock real
**não foi executado** e control_files_checks_passed permanece null na saída
publicada. A existência dos testes sintéticos não encerra essa pendência.

## Reprodução

```sh
python3 scripts/test_capture_a0_load_plan.py
python3 scripts/check_capture_a0_load_plan.py --output build/load-plan-novo.json
# Com o insumo existente, sem qualquer operação no aparelho:
python3 scripts/check_capture_a0_load_plan.py \
  --vendor-boot /insumos/vendor_boot.img --output build/load-plan-stock-novo.json
```

O destino deve ser novo. Exit 1 indica recusa/erro; exit 2 indica relatório
com cobertura incompleta ou diagnóstico negativo. Exit 0 exige grafo declarado
fechado/acíclico e arquivos de controle estruturalmente aprovados. Nenhum
desses estados aprova ABI, init de drivers, firmware, CFI/RKP, confiança AVB,
SignerVer03, carga física ou A0. O conteúdo do ramdisk não é modificado.

Os 16 testes incluem nomes normalizados, ciclos, dependências ausentes,
arestas adicionais cíclicas, arquivos ambíguos, omissão de arestas, ordem
literal invertida e o inventário real fixado. O caso invertido mantém
explícita a diferença entre diagnóstico estrutural e falha runtime.

Validação local: 394 testes da família A0 e baseline R10 9/9 aprovados.
O modo de contêiner foi exercitado de ponta a ponta com uma fixture sintética,
incluindo recusa de truncagem; o stock privado continua não executado.
