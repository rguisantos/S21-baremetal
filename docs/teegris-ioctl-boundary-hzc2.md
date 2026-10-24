# HZC2: ligação de ioctl e fronteira SVC do TEEGRIS

Continuação de **2026-10-24 (Campo Grande)**, sobre main `2f31df4`, após
o merge do PR #7. A [etapa TZAR](tzar-crypto-hzc2.md) localizou os pedidos
de `/dev/crypto`; agora a ligação ELF e o wrapper que recebe essas chamadas
foram conferidos. Não foi identificado o consumidor após a exceção SVC.

**Resultado:** dois calls de `libteesl` usam a mesma PLT/GOT e a relocação
do símbolo versionado `ioctl`. O contrato ELF declara `libtzsl.so` como
provedora de `TEEGRIS_4`; sua função prepara **X7=15** e executa **SVC #0**.
Foram delimitados os argumentos e a conversão posterior de erro/retorno.
Isso fecha a ligação estática até a instrução de exceção, sem demonstrar
carregamento/resolução de símbolos ou comportamento do serviço em execução.

## Entradas e identidade

Usa exclusivamente o mesmo `tzar.img` de 7340816 bytes, SHA-256
`791c8818555e64d0e060c406e68748e869c7d53fbc9c9bbc893a1dd4f65a2077`,
e o hash interno do primeiro bloco TZAR já conferido. Nenhuma imagem nova
é necessária para reproduzir esta etapa.

| Módulo do arquivo TZAR | Bytes | SHA-256 |
|---|---:|---|
| `/lib64/libteesl.so` | 345744 | `354d68d5936e11258f8c6a27828a4f7389045da57bdfa9bfc255603a46f77895` |
| `/lib64/libtzsl.so` | 136760 | `9a4054c545be3bc4d8042ad6940ea4d0bf4e70e3d8082639765c674c029498bc` |

Os endereços abaixo são virtuais de link do ELF. O relatório registra
também offsets de arquivo; não são endereços físicos ou valores da GOT
capturados no telefone.

## Do call ao símbolo versionado

| Vínculo | Evidência |
|---|---|
| Calls de alocação e atualização | BL em `0x2a894` e `0x2c860`, ambos para `0x9760` |
| Stub PLT | ADRP X16; LDR X17; ADD X16; BR X17 em `0x9760–0x976c` |
| Slot usado pelo stub | endereço ligado `0x61698`, construído por ADRP e pelo mesmo offset nos LDR/ADD |
| Relocação desse slot | `R_AARCH64_JUMP_SLOT`, índice de símbolo dinâmico **67**, addend zero |
| Requisito de versão do símbolo | índice local **4** → `TEEGRIS_4`, arquivo `libtzsl.so` |
| Dependência/identidade da provedora | `libtzsl.so` está em DT_NEEDED; SONAME correspondente |
| Exportação da provedora | símbolo dinâmico **98**, `ioctl`, endereço `0x8654`, tamanho **72**; índice local de versão **2** → `TEEGRIS_4` |

Os índices 4 e 2 pertencem a tabelas de módulos distintos. O leitor cruza
nome da versão e biblioteca, em vez de exigir igualdade desses índices.
As tabelas RELA, VERSYM, VERNEED, VERDEF e DYNAMIC são percorridas com
limites de tamanho, elos, strings e contagens. Elos inválidos, versões
reservadas, registros duplicados e slots ambíguos são recusados.

A identidade declarada não prova que o carregador realizou essa resolução,
nem exclui interposição de símbolos em execução. O relatório conserva essa
limitação; não transforma o conteúdo estático da GOT em um ponteiro observado.

## Contrato do wrapper

O corpo inteiro de 18 instruções é ligado ao símbolo e conferido por template:

| Campo/ação | Evidência no ELF `libtzsl` |
|---|---|
| Primeiro argumento | `0x8658`: extensão de sinal W0 → X0, descritor |
| Segundo argumento | `0x865c`: extensão de sinal W1 → X1, número do pedido ioctl |
| Terceiro argumento | X2 atravessa o wrapper até a exceção; o conteúdo apontado não é lido pelo prefixo |
| Seletor da chamada | `0x8660`: X7 recebe **15** |
| Fronteira | `0x866c`: **`svc #0`** |
| Teste do retorno | `0x8674/0x8678`: CMN X0,#0x1000 / B.LS |
| Ramo de erro | nega W19, chama helper de errno, grava W19 no endereço retornado e prepara `0xffffffffffffffff` |
| Retorno ao chamador | `0x868c`: MOV W0,W19; 32 bits de resultado |

Os pedidos 7 e 1 da etapa anterior ocupam o argumento ioctl; **15 é o
seletor preparado em X7 para a exceção**. O immediate do SVC é zero.
Nenhum desses campos foi ligado ao seletor MMIO EPBL `0x19`.

Não foi fornecida resposta ao SVC. O handler de exceção, o despacho pelo
descritor e a implementação do dispositivo continuam pendentes. O wrapper
não fornece o estado de segurança/EL do chamador, o mapa usado pelo serviço
ou o conteúdo dos buffers depois da exceção.

## Conversão do resultado: limite exato e largura

A aritmética CMN/B.LS seleciona erro para os padrões X0 que representam
**-4095 até -1** em 64 bits. **-4096 é excluído** desse ramo. No erro, grava
o positivo correspondente como word de errno e devolve W0=`0xffffffff`.
No outro ramo, devolve os 32 bits baixos e não escreve errno nesse recorte;
o valor anterior de errno permanece desconhecido.

| X0 explicitamente fornecido ao modelo aritmético | W0 devolvido | Word escrito em errno |
|---|---|---|
| 0 | `0x00000000` | nenhuma escrita |
| -1 | `0xffffffff` | 1 |
| -4095 | `0xffffffff` | 4095 |
| -4096 | `0xfffff000` | nenhuma escrita |
| `0x100000001` | `0x00000001` | nenhuma escrita |

São exemplos de uma função pura de normalização, não resultados de syscall.
Ela exige X0 u64 explícito, sem truncar entradas inválidas, aceitar bool ou
inventar sucesso do dispositivo. O endereço real de errno não foi observado.

## Reprodução e validação

```sh
python3 scripts/inspect_teegris_ioctl.py /caminho/tzar.img
python3 scripts/check_teegris_ioctl_gnu.py /caminho/tzar.img
(cd scripts && python3 -m unittest test_teegris_ioctl test_tzar_hzc2 -v)
```

**30 testes passaram:** 15 novos para metadados ELF, PLT e normalização,
mais 15 regressões TZAR. O leitor ELF compartilhado agora expõe os índices
necessários e recusa sobreposição de segmentos mesmo quando somente um
deles tem permissão de execução. As evidências anteriores do inspetor e
do conferidor TZAR foram reemitidas e coincidem byte a byte com as publicadas.

GNU binutils 2.44 confere, de forma independente, os índices/nomes de versão,
a biblioteca requerida, SONAME, relocação e exportação selecionada, além de
**24 palavras de instrução e quatro destinos relativos**. Os ELFs usados
pelo GNU têm nomes temporários controlados e são removidos ao final.

- [Ligação, argumentos e normalização](references/teegris-ioctl-hzc2.json)
- [Conferência GNU](references/teegris-ioctl-gnu.json)
- [Saída dos 30 testes](references/teegris-ioctl-host-tests.txt)

Nenhum ELF, syscall, SMC, MMIO ou firmware foi executado. A próxima evidência
útil nesse percurso é o handler correspondente ao SVC e seu despacho para
o dispositivo. Para o EPBL continuam abertas a implementação de `0x19`,
a entrada DMA e a saída real de 48 bytes. Carregamento e observação do
diagnóstico no S21 seguem no [roadmap](roadmap.md).
