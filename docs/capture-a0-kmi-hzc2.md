# A0 HZC2: as duas diferenças KMI e o limite da compatibilidade

Rodada de 01/11/2026, Campo Grande, base `35f3ae9` após PR #75.
Continuação do [inventário A0](capture-a0-hzc2.md), sem build de kernel,
carregamento de módulos ou operação no aparelho.

**O candidato ainda não é compatível por demonstração.** Há uma dependência
concreta faltando: o IKCONFIG stock cita 19 listas KMI; duas não estão no
arquivo Samsung recebido. As 17 disponíveis somam 4990 símbolos distintos,
todos presentes na whitelist candidata de 5000. Dez nomes dessa whitelist
não têm origem demonstrada nas listas disponíveis. Não são dez símbolos
comprovadamente ausentes do kernel stock nem dez falhas de CRC medidas.

## Efeito das duas chaves

| Chave | Evidência na árvore fixada | O que continua faltando |
|---|---|---|
| `CONFIG_UNUSED_KSYMS_WHITELIST` | String com caminho; `gen_autoksyms.sh` lê o arquivo e gera defines `__KSYM_*`, consumidos por `export.h` com TRIM_UNUSED_KSYMS | Demonstrar que o caminho remapeado resolve o conteúdo efetivamente usado pelo build stock |
| `CONFIG_KMI_SYMBOL_LISTS` | String declarada em `init/Kconfig:2293`; única ocorrência literal do identificador no censo da árvore | Resolver a proveniência das listas e o pipeline externo que pode gerar a whitelist |

O censo leu os **72523 arquivos regulares**, 1107809877 bytes, sem pular
arquivos grandes. Os 39 symlinks não foram seguidos; nenhum dos insumos
selecionados depende deles. A busca inclui `CONFIG_` e o nome sem prefixo,
com limites de identificador. É um censo literal da árvore recebida, sem
resolver nomes construídos dinamicamente ou scripts externos a esse arquivo.
Não se transforma a ausência de consumidor literal em garantia global de
que a opção é inofensiva.

Não foi identificado um controle direto de campos de estruturas C por
essas duas strings. O efeito demonstrado da whitelist é sobre a superfície
de exports. Com LTO, mudar exports também pode mudar retenção de código e
o layout do binário; isso é distinto de alterar o layout de uma estrutura.
O [build.config.universal2100_r fixado](references/capture-a0-kmi-hzc2.json)
contém variáveis KMI e gates de ABI, mas seleciona outro defconfig GKI.
Não foi executado nem adotado como reprodução automática do perfil p3s.

## Dois insumos ausentes e dez nomes sem origem fechada

O valor KMI do IKCONFIG foi recuperado do boot stock já identificado no A0,
e seu hash coincide com o publicado no PR #75. Os dois caminhos sem membro
regular ou symlink no arquivo recebido são:

- `android/abi_gki_aarch64_galaxy_presubmit`
- `abi_greylist`

A whitelist `gki/abi_symbollist.raw` está disponível e fixada por hash.
A união das outras 17 listas é subconjunto dela, com diferença de dez nomes
registrada no [relatório completo](references/capture-a0-kmi-hzc2.json).
Isso não prova que os nomes vieram das duas listas faltantes, nem que a
whitelist da fonte seja idêntica àquela usada para compilar o stock.
Não se removem os dez nomes, inventam arquivos vazios ou desabilitam TRIM
para contornar essa lacuna e então declarar a ABI reproduzida.

## Seis controles com o gerador e os headers originais

O [runner](../scripts/check_capture_a0_kmi.py) confere o arquivo Samsung
e o IKCONFIG por SHA-256 antes de executar qualquer fonte. Usa somente
configurações sintéticas próprias no `auto.conf` consumido pelo shell;
não executa os caminhos/valores privados da configuração stock.
Os arquivos originais do gerador, `export.h` e `kconfig.h` vêm do arquivo
verificado. Os controles foram executados em x86_64 com GCC host:

| Controle | Resultado |
|---|---|
| Whitelist relativa | Dois exports na fixture; imports necessários e `module_layout` preservados |
| Caminho absoluto com conteúdo igual | Header autoksyms, exports e layout da fixture iguais ao controle relativo |
| Mudar apenas a string KMI | Mesmo header, exports e layout nesse percurso isolado |
| Retirar um nome da whitelist | Seu export desaparece; a estrutura de teste permanece com tamanho16/offset8 |
| Caminho inexistente | Gerador recusa antes de produzir o header |
| Mudar de fato o tipo de um campo | Controle positivo detecta tamanho8/offset4, mantendo os dois exports |

São estruturas e funções da fixture, com macros auxiliares mínimas e o ramo
de export sem PREL32. Não são estruturas Samsung comparadas, um build com
LTO/CFI ou um módulo p3s carregável. **CRCs não foram calculados/comparados.**
O teste mostra por que export e tipo/layout precisam de verificações próprias.

## Gate de módulos que permanece aberto

Na fonte fixada, `scripts/Makefile.build` envia fonte pré-processado com
`__GENKSYMS__` ao gerador de versões. `scripts/mod/modpost.c` monta as
entradas `__versions`; `kernel/module.c` verifica versões e `module_layout`.
No ramo em que encontra o símbolo e compara os CRCs, divergência é recusada.
Há outros ramos, inclusive ausência de CRC/entrada, que não equivalem a
uma checagem completa de tipos. Nem a igualdade nominal da versão do kernel
nem os controles deste documento substituem essa validação.

Antes de declarar compatibilidade, a entrega precisa identificar módulos
stock realmente usados e obter o build candidato completo: imports/exports,
`Module.symvers`, CRCs relevantes, política de vermagic, namespaces/licenças,
CFI e tipos/interfaces consumidos. Nenhum `Module.symvers` candidato ou
conjunto de módulos reais foi comparado nesta rodada. O README_Platform
anexo trata de componentes do build Android, com exemplos de bibliotecas e
BPF; ele não é um relatório de ABI dos módulos de kernel HZC2.

## Precisão sobre o resultado do packer

No ensaio do PR #75, os headers Android e os payloads kernel/ramdisk/DTB
permaneceram idênticos. Mudaram bytes da extensão opaca e campos do rodapé;
em vendor_boot também mudou o offset de vbmeta. O conteúdo do intervalo
hasheado muda mesmo preservando os componentes principais. Portanto os
586/3474 bytes não devem ser descritos como reescrita comprovada do header
Android, nem como alteração que deixa todo o conteúdo hasheado intacto.
A recomposição integral preservou esses bytes. Isso isola a falha no
percurso Magisk/versão/opções ensaiados, sem provar outros packers compatíveis.

## Reprodução e próximo passo

O arquivo `stock.config` deve ser extraído por `ikconfig()` de
`capture_a0_formats.py`, a partir do kernel descomprimido do boot stock
identificado no A0. O runner exige seu hash exato e não o publica no Git.

```sh
python3 scripts/test_capture_a0_kmi.py
python3 scripts/check_capture_a0_kmi.py \
  --source /caminho/Kernel.tar.gz \
  --stock-config /caminho/stock.config \
  --output-dir build/capture-a0-kmi-novo
```

O diretório deve ser novo e ter caminho sem espaços ou metacaracteres de
shell. O código 2 registra a análise concluída com insumos KMI ainda não
explicados; 1 é recusa/erro. O JSON foi reproduzido byte a byte em uma segunda
execução. Os [23 testes de limites/recusas](../scripts/test_capture_a0_kmi.py)
também estão na CI; os seis controles originais exigem os inputs privados.

**Próximo passo continua em A0:** resolver a origem dos insumos KMI e da
whitelist, fechar o perfil de build/módulos e o contêiner íntegro. O problema
do packer permanece independente. A1 e a prova no ELF/Image final continuam
pendentes; nenhuma decisão OEM ou ação no telefone foi solicitada/executada.

[Validação desta rodada](references/capture-a0-kmi-validation-20261101.json).

## Continuação — repetibilidade e cobertura AVB, 01/11/2026

A [análise delimitada do repack](capture-a0-repack-extent-hzc2.md) reproduziu saídas idênticas em três processos por imagem, alterando os mtimes dos arquivos extraídos. A extensão omitida está dentro do hash, mas o rodapé AVB está fora. As diferenças internas são 584 bytes em boot e 651 em vendor_boot; os demais bytes alterados ficam fora. O controle sem alterações exige preservação integral; payload modificado exige metadados coerentes e rota de aceitação demonstrada. A0 continua aberto.
