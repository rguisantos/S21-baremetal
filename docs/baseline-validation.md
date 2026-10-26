# Baseline obrigatório de R10

Implementação da prioridade de reprodução da
[revisão de 2026-10-25](repository-review-2026-10-25.md), sobre a main
`d46e787`. Escopo: software do projeto no host Linux e QEMU virt, uma CPU.

## Comando único

Na raiz do repositório:

```bash
python3 scripts/validate_baseline.py
```

O runner cria uma pasta nova em `build/baseline-*`, imprime o caminho e
constrói o ELF de produção nesse diretório. Não depende de objetos ou ELF
anteriores em `r8/build`. Cada etapa tem log separado, timeout de 180 segundos
e resultado no `summary.json`, incluindo código de saída, marcadores ausentes,
SHA-256 do log e duração. O resumo registra também Python, plataforma,
modo de ferramentas e hash/tamanho do ELF aprovado. Uma falha interrompe a
sequência com exit 1 e preserva os resultados já obtidos. UBSan usa
`halt_on_error=1`, para erros não virarem apenas mensagens ignoradas.
O runner captura stdout/stderr por pipe e escreve cada log por um único
processo, antes de calcular o hash; descendentes não escrevem diretamente
no arquivo de log.

Para escolher um caminho reproduzível, use um diretório que ainda não exista:

```bash
python3 scripts/validate_baseline.py --output-dir build/baseline-manual
```

O runner recusa reutilizar diretórios, timeouts não positivos e Python com
otimização que desative `assert`. Código de saída zero sem as assinaturas de
cobertura previstas também falha. No timeout, encerra o grupo do processo,
incluindo descendentes em outra sessão que ignorem SIGTERM. Os testes têm suas próprias
pastas temporárias; os logs e o build inicial ficam na pasta do runner.
O rastreio usa PPid/NSpid de `/proc` e pidfds; funciona quando `/proc` está
montado no namespace ancestral e não exige `task/*/children`.

## Cobertura exigida

| Etapa | Critério |
|---|---|
| Contrato do runner | Sete controles: sucesso/hash, exit zero sem cobertura, exit não zero mesmo com PASS, timeout/grupo, reuso de diretório, ELF ausente e Python otimizado |
| Versões | Compilador cross, objdump e QEMU iniciam e registram suas versões |
| Build | ELF R10 real compilado em diretório novo |
| FDT | 43 casos com ASan/UBSan |
| Contêiner | 60 casos com ASan/UBSan e extensão real de BSS/pilhas |
| Materialização | 17 casos; bytes, guards e recusas antes de escrever |
| Diagnóstico | Seis entradas EL1/EL2 e seis recusas M/C |
| Loader QEMU | Materialização exata, main de produção em EL1 com IRQs de timer, um handoff e cinco recusas |

As contagens e assinaturas são gates explícitos. Ao alterar a cobertura,
atualize os marcadores do runner junto com os testes. Não há opção de pular
uma etapa obrigatória. R8/R9, XNU e análises de firmware têm suítes próprias;
este baseline selecionado não as substitui.

`test_payload.py` agora exige um ELF e falha com exit 2 se ele faltar, inclusive
quando executado isoladamente. Para usar um ELF já compilado:

```bash
make -C r8 build/r10_payload.elf
python3 scripts/test_payload.py --elf r8/build/r10_payload.elf
```

O default desse teste continua `r8/build/r10_payload.elf`. O caso real deixou
de ser condicional; o comportamento anterior de passar somente 59 casos foi
removido. Importar as fixtures por outros testes não exige esse artefato.

## Ferramentas e CI

O modo padrão conserva a seleção do Makefile, usando `tools/root` quando
disponível. Linux x86_64 com `/proc` e pidfds, Bash, make, Python 3.9+,
`cc` com sanitizers e `readelf`
continuam necessários. Para ignorar as ferramentas extraídas e usar somente
cross-toolchain/QEMU do PATH:

```bash
python3 scripts/validate_baseline.py --system-tools
# A mesma seleção pode ser usada em outros alvos:
USE_SYSTEM_TOOLS=1 make -C r8 tool_versions
```

O [workflow Baseline](../.github/workflows/baseline.yml) roda em PRs, pushes na
main e acionamento manual. Usa Ubuntu 24.04, instala dependências pelo APT e
executa o mesmo comando com `--system-tools`. O job `R10 baseline` tem limite
de 15 minutos; logs/resumo são enviados como artifact por 14 dias, inclusive
após falha do runner. Falha de checkout/instalação pode impedir a criação
desses arquivos. O ELF não é distribuído pelo workflow.

Os ensaios de diagnóstico e loader usam `-nic none`: não dependem de ROM
de rede opcional. O primeiro CI (run 40240373832) passou build/host, mas
parou na conexão GDB do diagnóstico. Uma reprodução com QEMU Ubuntu 8.2.2
e sem a ROM de rede mostrou `failed to find romfile "efi-virtio.rom"`;
desativar a NIC elimina essa dependência. O diagnóstico agora também
inclui stderr do QEMU no log antes de propagar um erro.

Checkout e upload-artifact são fixados em SHAs completos das ações oficiais;
o token tem apenas `contents: read` e o checkout não persiste credenciais.
[Referência oficial de permissões e pinning](https://docs.github.com/en/actions/reference/security/secure-use).
Isso não configura proteção da branch: a revisão automática completed do
head exato, sem achados/pendências, continua exigida por AGENTS.md e precisa
ser conferida junto ao resultado do CI antes de cada merge.

Os pacotes APT e a imagem hospedada podem variar. As versões são registradas,
mas não há promessa de build bit a bit idêntico entre ambientes. Os binários
offline existentes foram preservados; o bootstrap não foi substituído.

## Resultado observado e próximo passo

A execução local completa passou com GCC cross 14.2, binutils 2.44 e
QEMU 10.0.13, em diretório novo. Contagens da tabela e controles de falha
passaram. O baseline completo também passou com o binário Ubuntu QEMU
8.2.2 sem ROM de rede, usando GCC 14.2 e o loader/bibliotecas de `tools/root`;
esse ensaio de compatibilidade não é a imagem Ubuntu hospedada.
[Comandos, resultados e hashes](references/baseline-validation-20261025.json).
O resultado hospedado deve ser consultado nos checks do PR correspondente;
a existência do YAML não demonstra uma execução aprovada.

Próxima prioridade: matriz do percurso Samsung e canal de recuperação dos
128 bytes do diagnóstico. Este baseline não mede o estado do telefone, não
prova RAM livre e não amplia o escopo de execução do callback NEWTIME.
