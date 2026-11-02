# A0: helpers de pilha e reexecução de modpost HZC2

Continuação do PR #81, base `b900afc`, em 02/11/2026, Campo Grande.
O [relatório nativo](references/capture-a0-stack-versions-hzc2.json) e a
[validação](references/capture-a0-stack-versions-validation-20261102.json)
registram esta rodada. A0 permanece aberto; nenhum pacote foi alterado.

## O resultado novo

O modpost original da fonte Samsung foi compilado e executado sobre cópias
privadas do **ELF final** de s2mpb02_mfd stock e candidato. Com os exports/CRCs
do Module.symvers final do candidato, produziu 37 registros em cada caso:
os 35 presentes no módulo e os dois helpers ausentes, sem mudar os 35 CRCs.

| Entrada final | Imports | Registros no ELF recebido | Registros no C gerado | CRCs antigos alterados |
|---|---:|---:|---:|---:|
| Stock HZC2 | 36 | 35 | 37 | 0 |
| Candidato PR #80 | 36 | 35 | 37 | 0 |

Os 37 são 36 imports mais module_layout. As duas linhas adicionais são
__stack_chk_fail=0xf0fdf6cb e __stack_chk_guard=0x8f678b07, obtidas pelo próprio
programa a partir dos exports fornecidos. Isso descarta uma regra deliberada
de exclusão desses helpers nesse modpost/arquitetura/ensaio. Os dois ELFs
recebidos ficaram byte a byte intactos. O C gerado não foi compilado em
módulos nem usado para substituir registros de consumidor existentes.

## Os imports têm usos reais no código

Nos dois ELFs, cinco relocations apontam para instruções dentro do intervalo
de s2mpb02_irq_thread informado pela symtab. O leitor confere binding global
indefinido, addend zero, limites, tipo da relocation e classe da instrução.
Os offsets são relativos à seção .text, não endereços físicos do telefone.

| Offset .text | Offset na função | Relocation | Destino | Instrução |
|---|---|---|---|---|
| 0xb6c | +0x14 | R_AARCH64_ADR_PREL_PG_HI21 (275) | __stack_chk_guard | ADRP |
| 0xb70 | +0x18 | R_AARCH64_LDST64_ABS_LO12_NC (286) | __stack_chk_guard | LDR X |
| 0xbc4 | +0x6c | R_AARCH64_ADR_PREL_PG_HI21 (275) | __stack_chk_guard | ADRP |
| 0xbcc | +0x74 | R_AARCH64_LDST64_ABS_LO12_NC (286) | __stack_chk_guard | LDR X |
| 0xbf0 | +0x98 | R_AARCH64_CALL26 (283) | __stack_chk_fail | BL |

Uma conferência independente com GNU objdump sobre o candidato também
localizou o salvamento do canário, sua comparação no epílogo e a chamada de
falha. O runner publica as cinco referências de instrução; não executa a IRQ.
A fonte drivers/mfd/s2mpb02-irq.c:111–140 contém o buffer irq_reg e a chamada
que recebe seu endereço. A configuração preservada tem STACKPROTECTOR_STRONG,
THINLTO e CFI habilitados; isso é contexto, sem atribuir por si só a causa.

## Onde a prova da causa ainda falta

scripts/Makefile.modpost:86–115 cria um .lto.o a partir do .o, executa modpost
sobre aquele intermediário e só depois chama Makefile.modfinal. Este compila
.mod.c e liga .o + .mod.o na saída .ko, conforme Makefile.modfinal:25–57.
Portanto o ELF consumido no ensaio desta rodada **é diferente da etapa de
entrada do modpost no build original**.

Os artefatos preservados do PR #80 contêm os módulos finais, sem o cache
completo de objetos. Não foram fornecidos os .lto.o e .mod.c originais desta
etapa. Não foi demonstrado que os helpers surgiram apenas na segunda
linkedição, nem que houve uma falha de CRC, cache ou otimização. Também não
foi reproduzido o histórico do build Samsung stock. A hipótese de diferença
entre etapas continua sendo um alvo de medição, não uma conclusão.

O próximo ensaio dessa causa deve preservar, no mesmo build e para esse
módulo, .o, .o.symversions, .lto.o, .mod.c, .mod.o, .ko e seus comandos .cmd;
comparar imports e versões em cada fronteira e verificar se a geração final
muda o conjunto. Não é necessário repetir um kernel inteiro sem essa captura.
A reexecução isolada aqui confirma o comportamento diante do ELF final.

## Diagnósticos que não foram escondidos

O modpost retorna zero nos dois casos. Ao reler o ELF stock final, emite dois
avisos de section mismatch: cleanup_module.cfi_jt para .exit.text e
init_module.cfi_jt para .init.text. O candidato não produz esses avisos.
Os textos, com o caminho de trabalho normalizado, estão no relatório.
Eles pertencem à reexecução sobre a saída final e não demonstram uma falha
no build original, nem autorizam remover anotações __init/__exit.

## Reprodução e escopo

```sh
python3 -m unittest discover -s scripts -p 'test_capture_a0*.py'
python3 scripts/check_capture_a0_stack_versions.py \
  --source /insumos/Kernel.tar.gz \
  --vendor-boot /insumos/vendor_boot.img \
  --candidate-artifacts /insumos/S21-HZC2-artefatos-20261102.tar.gz \
  --clang-dir /insumos/clang-r383902 \
  --output-dir /saida/nova
```

O runner verifica hashes exatos de fonte, imagens, artefatos, clang.real e
libc++.so.1 antes de executar ferramentas. A árvore completa de toolchain
não é reconstruída neste ensaio: os dois binários necessários são fixados
individualmente. O libc++ de 1233936 bytes foi recuperado do mesmo commit,
conferindo os objetos Git das árvores raiz/lib64 e do blob; seu SHA-256
b0157c4eccf705a00528728b4dc4797b56ac10d43829114cd3002dde763e7ccc é exigido.
O Clang tem o hash já publicado nos [pins do build](references/capture-a0-build-pins-hzc2.json).

As fontes de modpost/file2alias/sumversion e headers permanecem sem patch.
mk_elfconfig recebe o header ELF final verificado. O Clang AArch64 gera as
178 definições de tamanho/offset de devicetable-offsets.c com um preâmbulo
auxiliar explícito de tipos escalares/UUID de 64 bits; o código desse
preâmbulo está no runner. Isso prepara o comparador host, sem representar
preparação Kconfig ou recompilação do kernel. O cc host e sua versão são
registrados. Cada processo tem timeout de 60 segundos; a saída é guardada
privadamente. O retorno 2 significa análise concluída com A0 aberto.

O comportamento permissivo de check_version e as duas lacunas do
[plano do PR #81](capture-a0-module-policy-hzc2.md) permanecem como estavam.
Esta rodada não fecha cobertura estrita nos ELFs originais, ABI, CFI/RKP em
execução, proveniência KMI, contêiner modificado, A1 ou decisão OEM.
