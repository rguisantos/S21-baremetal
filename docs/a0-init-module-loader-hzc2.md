# A0: o init stock resolve dependências antes de insmod

Análise estática de 05/11/2026, base `d6099d7`, usando o boot.img.lz4
enviado pelo usuário. O loader do primeiro estágio foi identificado no
próprio init stock. Isso avança a pendência do
[vendor_boot](capture-a0-stock-load-validation-hzc2.md), sem executar init,
carregar módulos ou observar o telefone.

## Identidade e método reproduzível

LZ4: 20255202 bytes, SHA-256
`cb5f76269c71f5d643afdcda57ff1561b708b9fcb724876b59b0d407abb3477e`.
Raw: 67108864 bytes, SHA-256
`28818995d6c3060df19602a0104c2c7dac9861f31f2620f9dab8466e6cdf51a1`.
Coincidem com os pins stock HZC2 existentes. Descompressão LZ4 e gzip são
limitadas e consomem os buffers conferidos; o CPIO não é extraído no disco
pelo verificador. O ramdisk de boot contém oito entradas, incluindo init,
fstab.exynos2100 e dpolicy; não contém scripts .rc/.sh de carga.

Init: 1502328 bytes, SHA-256
`389d314c35d4d058da8845213191ff1058275fd403809ea2c8b244983825775b`.
É um ELF AArch64 estático, Android 30, com mini-debug comprimido em
.gnu_debugdata. A seção contém símbolos que o nm recupera após descompressão
XZ limitada. O [verificador](../scripts/inspect_a0_init_modules.py) confere
o ELF antes de consumir seções ou iniciar leitores nativos. nm recebe o
mini-debug por memfd selado; GNU objdump recebe o mesmo init verificado por
outro memfd selado. Nenhum dos dois arquivos é executado.

O [relatório](references/a0-init-module-loader-hzc2.json) fixa as seções,
símbolos, onze calls diretos, cinco instruções adicionais e cinco literais.
Os destinos BL são decodificados dos bytes e as palavras selecionadas também
conferidas com GNU. Duas execuções reais produziram JSONs byte a byte iguais.
PCs abaixo são endereços virtuais do ELF, não offsets do arquivo.

## Caminho selecionado

| Ligação | Evidência |
|---|---|
| FirstStageMain → LoadKernelModules | BL 0x25ec18 → 0x25d4cc; símbolos em 0x25ddec/0x25d4cc |
| Seleção da lista | BL 0x25d798 → GetModuleLoadList em 0x25d304; literais modules.load e modules.load.recovery |
| Construção do resolvedor | BL 0x25d7a8 → Modprobe em 0x2f3e88 |
| Carga da lista | BL 0x25d824 e 0x25d9d0 → LoadListedModules em 0x2f5084 |
| Lista → aliases | BL 0x2f50dc → LoadWithAliases em 0x2f4d30 |
| Aliases → dependências | BL 0x2f4f84 → InsmodWithDeps em 0x2f4744 |
| Consulta de dependências | BL 0x2f47a4 → GetDependencies em 0x2f4684 |
| Resolução recursiva | BL 0x2f4804 → LoadWithAliases, antes da chamada Insmod |
| Carga do módulo | BL 0x2f4ab8 → Insmod em 0x2f6344 |
| Interface ao kernel | W0=273 em 0x2f659c e BL 0x2f65ac → syscall; W3=0 |

O corpo de InsmodWithDeps percorre as strings de dependências de trás para
frente: SUB X22,X22,#24 em 0x2f47e8, chamada recursiva e teste/retorno ao laço
em 0x2f4824/0x2f482c. O call de Insmod fica adiante, em 0x2f4ab8. A seleção
de syscall 273 corresponde a finit_module no ABI AArch64 Linux; o código
observado entrega fd/opções e flags zero. Não equivale a insmod sequencial
externo para cada linha de modules.load.

Os nomes foram recuperados do próprio mini-debug, e não atribuídos apenas
por semelhança de strings com fonte AOSP. Existem ainda caminhos para
aliases, blocklist, softdeps, seleção recovery e opções de cmdline. O
verificador não prova toda a semântica dos contêineres C++, os argumentos
vivos ou todos os ramos desses caminhos.

## Consequência para as 151 relações

O stock usa uma implementação com resolvedor de dependências no caminho
selecionado. Assim, as 151 relações fora da ordem literal de modules.load
não devem ser tomadas como 151 falhas de carga demonstradas. O grafo e os
arquivos stock já passaram estruturalmente no PR #93.

O modelo DFS anterior é uma demonstração de que o grafo admite uma ordem,
não uma reprodução exata do loader Samsung. Em particular, a direção de
percurso observada agora é reversa, e aliases/softdeps podem acrescentar
condições. Nenhuma lista ou ramdisk foi reordenado com base no modelo.

Fecha-se a identificação estática do loader e da resolução antes da carga
na rota selecionada. Permanecem abertos execução real, êxito de cada init de
módulo, CFI/RKP, ABI, aceitação do pacote modificado e confiança Samsung.
O ELF stock não prova que o protótipo B será aceito ou funcionará. A0
continua aberto; não houve início de A1 ou operação no aparelho.

## Reprodução e validação

```sh
python3 scripts/inspect_a0_init_modules.py /insumos/boot.img.lz4 \
  --output build/init-module-loader-novo.json
python3 scripts/test_a0_init_modules.py
```

O destino deve ser novo. Exit 0 confirma identidade e bindings selecionados;
qualquer diferença de hash, seção, mini-debug, símbolo, call ou instrução
causa recusa. Não existe execução do init para produzir esse resultado.
Os nove testes novos cobrem limites de ELF/XZ, chamadas BL nos dois sentidos,
recusa anterior aos leitores, endereço de símbolo divergente, destino
alterado e imutabilidade dos buffers nativos. Integração na CI existente.

Validação local adicional: 394 testes existentes da família A0 aprovados e
baseline R10 9/9. Esses 394 não incluem os nove testes novos acima, que
foram executados separadamente.

## Continuação — referência executável em host

A [execução da referência AOSP fixada](a0-modprobe-host-replay-hzc2.md)
com controles stock e backend simulado produziu 274 módulos únicos, duas
tentativas equivalentes a EEXIST e dois controles negativos. Não demonstra
equivalência binária Samsung nem a ordem real no telefone.
