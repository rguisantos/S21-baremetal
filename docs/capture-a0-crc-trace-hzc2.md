# A0: acompanhar produtores de CRC e agregados LTO

Continuação do [PR #79](https://github.com/rguisantos/S21-baremetal/pull/79),
base `af69b7e`, em 2026-11-02. A tentativa completa anterior encontrou dois
`.symversions` vazios e seis exports sem versão. Os mesmos produtores
[passaram isoladamente](capture-a0-build-profile-hzc2.md), então a causa
não foi atribuída ao parser ou à ausência dos nomes na whitelist.

O [observador](../scripts/capture_a0_crc_trace.py) registra tamanho, hash,
identidade do arquivo e valores dos seis nomes durante uma tentativa
completa. Lê os dois produtores, agregados netfilter/mac80211/net,
`.tmp_lto.lds` e `Module.symvers`. Não muda Makefiles, comandos do gerador,
configuração ou conteúdo desses arquivos. A correção TUI já documentada
continua sendo o patch explícito aplicado à fonte pelo runner.

## Como reproduzir

Com os [insumos e ferramentas fixados](references/capture-a0-build-pins-hzc2.json):

```sh
python3 -m unittest discover -s scripts -p 'test_capture_a0*.py'
python3 scripts/check_capture_a0_build_profile.py \
  --source /insumos/Kernel.tar.gz \
  --toolchains /insumos/toolchains \
  --host-root /insumos/host \
  --work-dir /saida/nova \
  --compile --trace-versions
```

`--trace-versions` requer `--compile`; essa combinação é validada antes dos
insumos. O runner mantém as verificações de identidade, quatro controles
Kconfig, preparação, CRCs de `module.c` e controle TUI. O observador começa
antes de `make vmlinux modules` e termina depois de seu encerramento.
O resultado conserva os códigos de saída e o perfil final, independentemente
de o build ter sucesso. O gate A0 continua aberto.

## O que o registro permite afirmar

`crc-trace.jsonl`, fora da árvore de objetos, recebe somente metadados e
valores dos seis símbolos. O relatório final inclui seus eventos e hash,
snapshot final, intervalo solicitado, maior intervalo observado, erro do
observador e sinalização de limite. Ele não publica código pré-processado,
objetos, módulos ou fontes Samsung completas.

A amostragem padrão é 100 ms. **Transições entre leituras podem passar
despercebidas**. Arquivos inicialmente vazios durante o redirecionamento
do gerador são normais; uma amostra vazia não demonstra perda de CRC.
A análise deve conferir os valores posteriores, os agregados e a saída da
linkedição. A ordem das amostras não é uma prova completa da ordem de
escritas de processos independentes.

Uma leitura cujo inode, tamanho ou timestamps mudem é marcada instável.
Symlinks e arquivos especiais não são seguidos; as leituras são limitadas
a 16 MiB. CRCs conflitantes são preservados como vários valores, sem
escolha silenciosa. Limite atingido ou erro do observador ficam explícitos,
e nenhum desses resultados certifica ABI. O observador lê arquivos e pode
alterar o tempo de execução do ensaio; não é uma captura exaustiva de I/O.

Doze controles host cobrem essas propriedades e fazem parte da CI.
A0 permanece condicionado ao build completo e comparação de exports/CRCs,
aos insumos KMI/configuração, às políticas de módulos e ao contêiner de
payload modificado. A1 e ações no aparelho continuam separados.
