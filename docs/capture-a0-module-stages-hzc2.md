# A0: diferença ThinLTO reproduzida e correção candidata

Continuação do PR #82, base `2bb8d76`, em 02/11/2026, Campo Grande.
O [relatório](references/capture-a0-module-stages-hzc2.json) contém as quatro
capturas de etapa e os comandos resolvidos; a [validação](references/capture-a0-module-stages-validation-20261102.json)
registra dois builds isolados. Nenhuma operação foi feita no aparelho.

## O que foi medido

O alvo nativo drivers/mfd/s2mpb02_mfd.ko foi compilado com a fonte Samsung,
as três árvores de toolchain e a configuração preservada do PR #80.
O SHA-256 da configuração permaneceu
5e82e452e6a5bc008f191e971f0cc21cd97be5cad7965542403dedc67b45570a,
com LTO/ThinLTO, CFI, compat32, MODVERSIONS e proteção de pilha preservados.
Foram preparados scripts/VDSOs; o kernel inteiro não foi recompilado.

O caminho original passa um .lto.o ao modpost e, posteriormente, liga o
arquivo fino .o com .mod.o para gerar .ko. Os comandos efetivos eram:

```text
preliminar: ld.lld -r ... --whole-archive s2mpb02_mfd.o
final:      ld.lld -r -mllvm -import-instr-limit=5 --build-id ...
            --whole-archive s2mpb02_mfd.o s2mpb02_mfd.mod.o
```

A preliminar não recebia o limite de importação que estava na final.
Com a fonte original, os helpers aparecem só na saída final: o modpost não
os viu na entrada daquela etapa. O C de versões gerado foi conservado
sem alterações pela linkedição final, explicando as duas lacunas neste
ensaio isolado do candidato.

| Medida | Original | Preliminar alinhada |
|---|---:|---:|
| Imports relevantes no .lto.o | 34 | 36 |
| Versões geradas pelo modpost | 35 | 37 |
| Imports no .ko final | 36 | 36 |
| Versões no .ko final | 35 | 37 |
| Imports surgidos após modpost | 2 | 0 |
| Imports finais sem versão | 2 | 0 |
| CRCs presentes divergentes dos fornecedores | 0 | 0 |

O censo bruto do intermediário tem mais um símbolo, __this_module, que o
modpost ignora por regra explícita. A tabela usa os imports relevantes e
conta module_layout entre as versões. Os dois adicionados são
__stack_chk_fail e __stack_chk_guard, com os CRCs de fornecedor já fixados.
Eles foram gerados pelo modpost; não houve inserção manual de registros.

## Controle da variável e patch

Um controle independente reutilizou o mesmo arquivo fino e o mesmo script
de CRCs, acrescentando **somente -mllvm -import-instr-limit=5** à linkedição
preliminar. Os helpers passaram a existir antes do modpost, e o conjunto
de imports coincidiu com a preliminar alinhada. Isso isola o efeito desse
limite neste caso; não se atribui a diferença a um cache ou a uma falha de
cálculo de CRC. Não foi necessário desativar proteção de pilha ou CFI.

A [correção candidata](../scripts/patches/p3s-modpost-lto-flags.patch) acrescenta
KBUILD_LDFLAGS_MODULE ao comando LTO preliminar em scripts/Makefile.modpost.
Essa variável já fornece o limite e --build-id à etapa final. O patch é
aplicado somente à fonte privada extraída, após conferir o hash original:
083ce8e6dc233be0cb4d347bd7e2de850639d7b9a05c3cdc707f6c1fe8dbac98.
O arquivo resultante tem SHA-256
5c577cd70b59082e5b66faa3aef3856458d9d9958642c800fff11c3746c42d30.
Não se afirma que todos os demais flags das duas etapas ficaram idênticos.

Os dois objetos IR, o arquivo fino composto e seu script de versões ficaram
idênticos entre os controles original/alinhado. A saída alinhada conservou
imports, exports/CRCs, dependências, licenças, namespaces e vermagic em
paridade com o módulo do PR #80. Os bytes da seção .text também ficaram
iguais entre os controles deste ensaio, hash
92e75dd0497d408640b1fd01b6db38bfff54b83496d03ec3beab929c59b945a7.
Isso se limita à seção observada: não é identidade do ELF inteiro nem
prova de relocations aplicadas, ABI, CFI/RKP em execução ou boot.

## Captura e insumos

O runner para após modpost com KBUILD_MODPOST_NOFINAL=1, copia os arquivos
estáveis e depois executa a final. Repete essas fronteiras com o patch.
As capturas guardam .o de cada fonte, .o composto, .o.symversions, .lto.o,
.mod, .mod.c, .mod.o, .ko e os .cmd existentes. Cópias recusam links, FIFO,
substituição durante a leitura e tamanhos acima dos limites; cada arquivo
tem tamanho e hash. As fases podem ter arquivos ainda ausentes, marcados
como tais. Os snapshots ficam fora da árvore de objetos.

A compilação isolada usa explicitamente o Module.symvers final preservado
como entrada do modpost, porque não reconstrói vmlinux. O runner verifica
os fornecedores e CRCs de todos os imports observados. Essa é uma diferença
controlada em relação à execução completa que lê vmlinux; não se alega
reprodução byte a byte do build completo original ou do histórico Samsung.

Dois builds novos em diretórios distintos reproduziram os mesmos conjuntos
de imports, contagens, lacunas, CRCs e resultados do patch/controle. Hashes
de objetos, comandos completos e logs podem depender dos caminhos de build;
a comparação entre execuções foi semântica, sem exigir JSONs idênticos.

Os intermediários foram preservados em
S21-HZC2-intermediarios-modpost-20261102.tar.gz: 2452332 bytes,
SHA-256 95522de8d4c6296d7f67667dd1a0b8a6cae771077d315c585e8df78055489512,
79 arquivos de payload mais manifesto. Contém os quatro snapshots, logs,
controle e referência; não contém a fonte/toolchains completos, cache de
build inteiro ou pacote de flash. Arquivos finos retêm seus caminhos de
membros e podem precisar ser reconstruídos com os objetos IR capturados.
Nenhum firmware completo ou binário do checkpoint foi adicionado ao Git.

## Reprodução e próximo gate

```sh
python3 -m unittest discover -s scripts -p 'test_capture_a0*.py'
python3 scripts/check_capture_a0_module_stages.py \
  --source /insumos/Kernel.tar.gz \
  --candidate-artifacts /insumos/S21-HZC2-artefatos-20261102.tar.gz \
  --toolchains /insumos/toolchains --host-root /insumos/host \
  --work-dir /saida/nova
```

As árvores/pins e pacotes host são os do [build p3s](capture-a0-build-profile-hzc2.md).
Fonte e artefatos são conferidos por hash antes da extração; as árvores e os
executáveis fixados são verificados antes da execução. A restauração desta
rodada isolou duas cópias temporárias extras da instalação Clang; a árvore
exata passou antes do uso. O host de build não é uma imagem hermética.
Cada etapa nativa tem timeout de 180 s com encerramento do grupo de processos.
O retorno 2 significa análise concluída com A0 ainda aberto.

Para o próximo build completo, check_capture_a0_build_profile.py agora
oferece **--compile --align-module-prelink**, combinável com --trace-versions.
A opção exige --compile, aplica o patch fixado e registra hashes antes/depois;
o padrão anterior permanece sem esse patch. A opção foi integrada e testada,
mas um build completo com ela não foi executado nesta rodada.

A correção fecha a cobertura estrita apenas do módulo isolado recompilado.
Os 274 módulos stock da proposta anterior não foram substituídos e continuam
com suas duas ausências originais. Próximo gate: build completo com patch,
comparação de todos os módulos/CRCs e revisão da política do pacote. A0 segue
aberto também para proveniência KMI e contêiner modificado. A1 e a decisão
física continuam separados; o histórico do build stock não foi estabelecido.
