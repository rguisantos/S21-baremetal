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

## Resultado da tentativa completa

**`make vmlinux modules` terminou com retorno 0.** Foram produzidos vmlinux
e 276 módulos. O perfil crítico LTO/CFI/compat32 permaneceu preservado, e
a configuração gerada não mudou durante o build. O [relatório](references/capture-a0-crc-trace-hzc2.json)
registra os hashes; a [validação](references/capture-a0-crc-trace-validation-20261102.json)
consolida as verificações. O retorno 2 do runner conserva o gate A0 aberto
e não deve ser confundido com o retorno de `make`.

O Module.symvers final cobriu os **2763 nomes com CRC exigido pelos
consumidores stock: 2763 iguais, zero ausentes, zero divergentes e zero
conflitos stock**. Isso fecha a comparação necessária desse conjunto; não
resolve fornecedores, GPL/namespaces, CFI em execução, assinatura,
relocação ou comportamento do carregador.

GNU readelf 2.42 conferiu cabeçalhos e metadados dos 276 módulos AArch64
ET_REL. Os 274 nomes do vendor ramdisk stock estão presentes; os adicionais
são `input_booster_lkm` e `sec_debug_sched_info`. A comparação se limita a
esse ramdisk, sem classificar esses dois como desnecessários nem fazer um
censo de todas as partições. O vermagic candidato é `5.4.242 SMP preempt
mod_unload modversions aarch64`; a regra fonte de comparação do prefixo de
release com CRCs está na [rodada anterior](capture-a0-build-profile-hzc2.md).
O header de vmlinux é ELF64 little endian/AArch64, ET_DYN, entrada virtual
`0xffffffc010080000`. Não foi testada entrada real no aparelho ou em QEMU.

## Percurso observado dos seis CRCs

| Arquivo | Primeira amostra com os CRCs selecionados (s) | Bytes | Nomes selecionados |
|---|---:|---:|---:|
| net/netfilter/core.o.symversions | 310,762 | 127 | 3 |
| net/mac80211/rx.o.symversions | 315,709 | 127 | 3 |
| net/mac80211/built-in.a.symversions | 337,977 | 2829 | 3 |
| net/netfilter/built-in.a.symversions | 375,945 | 680 | 3 |
| net/built-in.a.symversions | 431,687 | 21767 | 6 |
| Script LTO | 650,831 | 242783 | 6 |
| Module.symvers inicial | 771,815 | 280866 | 6 |
| Module.symvers final | 850,285 | 444057 | 6 |

Os valores são iguais aos seis calculados no ensaio isolado do PR #79.
Foram 27 eventos, sem erro do observador ou limite atingido. O maior
intervalo entre amostras foi 0,690 s, acima dos 100 ms solicitados.
Uma leitura vazia antes da primeira versão preenchida foi observada em
cada produtor, coerente com o redirecionamento do gerador. Depois da
primeira leitura preenchida, não foi observado novo conteúdo vazio nesses
dois arquivos. Isso não exclui transições entre amostras.

**A falha anterior não se reproduziu e sua causa não foi demonstrada.**
Não se atribui o sucesso a uma correção de genksyms: os scripts de geração
e agregação foram conferidos contra o arquivo Samsung e permaneceram
intactos. Na preparação desta rodada, a verificação recusou um membro
truncado da instalação Clang; ele foi reposto antes da execução e todas
as árvores foram verificadas. Esse incidente também não foi estabelecido
como causa dos arquivos vazios da tentativa anterior.

## Artefatos e sequência

Os artefatos de referência incluem vmlinux, módulos, Module.symvers,
configuração e evidências, com manifesto de hashes. O pacote `S21-HZC2-artefatos-20261102.tar.gz`
tem 316867773 bytes e 292 arquivos verificados; não contém um contêiner de
flash nem o cache completo de objetos. Seus hashes estão na validação.
Os binários são preservados separadamente do repositório.

A produção do candidato e a cobertura desses CRCs estão demonstradas.
O próximo trabalho A0 é conferir plano/política e dependências de módulos,
proveniência/configuração KMI pendentes e o contêiner de payload modificado.
O histórico de seis CRCs ausentes fica documentado, sem bloquear esta
evidência de build concluído. A1, instalação e decisão física continuam
condicionados aos respectivos gates da proposta cooperativa.

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
