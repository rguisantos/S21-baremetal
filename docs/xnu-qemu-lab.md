# XNU no QEMU com um processo Darwin próprio

Marco de **2026-10-22, America/Campo_Grande**. Executamos a cadeia
**UEFI → loader EFI HackiOS → XNU → nosso processo de usuário** no QEMU
virt, com uma CPU. A raiz APFS foi montada e o processo terminou por
`RB_HALT`, devolvendo o log ao carregador, sem panic.

O kernel e loader são **prebuilt upstream verificados por SHA-256**.
O programa de usuário é nosso, montado a partir de `lab/xnu/init.S`.
Não compilamos XNU nesta etapa. Não usamos IPSW, SDK, dyld, bibliotecas
de aplicativos ou programas do iOS. SpringBoard e o boot no S21 não
foram testados.

## Resultado e contraprova

| Ensaio | Resultado observado |
|---|---|
| Arquivo correto | PID 1/UID 0; leitura e EOF APFS; espera de timer; ALL PASS; CPU halted; retorno normal ao loader; saída QEMU 0 |
| Arquivo com um byte alterado | Mesmo init e mesmo tamanho de arquivo; FAIL APFS fixture; retorno normal; saída QEMU 0; **harness sai 1 e recusa o ensaio** |
| Testes de host | **13 testes passaram**: formato Mach-O, identidade por hash e detecção de falhas/ausências/ordem/timeout/panic/retorno truncado |

O caso positivo satisfaz **17 critérios do harness**. Isso não são 17 boots
ou testes físicos. O controle negativo interrompe as checagens de usuário
na falha APFS; timer e ALL PASS não são executados nesse caso.

Assinaturas do caso positivo:

```text
S21 XNU LAB: identity PASS pid=1 uid=0
S21 XNU LAB: APFS fixture PASS
S21 XNU LAB: timer PASS select=200ms elapsed=100ms..10s
S21 XNU LAB: ALL PASS; requesting RB_HALT
CPU halted
```

O retorno também contém `returned <comprimento> 0` e o delimitador final
do log. O harness exige ambos, saída QEMU zero e ausência de timeout,
panic, usertrap/userabort, early exception ou marcador FAIL. Encontrar
somente a mensagem ALL PASS não basta.

Evidências versionadas:

- [Relatório dos dois casos](references/xnu-qemu-lab-20261022.json): hashes,
  comandos com caminhos substituíveis, critérios e resultado do controle.
- [Serial completo positivo](references/xnu-qemu-positive-20261022.txt)
  e [serial completo do controle](references/xnu-qemu-negative-20261022.txt).
  CRLF foi convertido para LF; controles e espaços/tabs finais foram
  escapados, sem corte de conteúdo. O relatório distingue o hash bruto do texto exibido.

Mensagens de usuário reaparecem na cópia do log devolvida pelo loader.
São duas apresentações do mesmo ensaio. Identidade iPhone/t8015 e números
sintéticos impressos vêm da árvore produzida pelo loader e não identificam
um telefone físico.

## O que o programa confere

1. Abre `/dev/console` e verifica `getpid()==1` e `getuid()==0`.
2. Abre `/etc/s21-lab.txt`, lê a extensão esperada, compara todos os bytes
   com `S21-XNU-LAB-FIXTURE-v1\n` e exige EOF na leitura seguinte.
3. Mede o relógio antes e depois de `select()` com timeout de 200 ms;
   aceita avanço entre 100 ms e 10 s. Esse intervalo admite atrasos do
   host; não é benchmark de precisão ou latência do timer.
4. Solicita `reboot(RB_HALT)`. Se a chamada retornar, escreve FAIL.

O syscall Darwin usa x16 e `svc #0x80`, com erro indicado pelo carry.
`gettimeofday` tem uma terceira saída opcional, `mach_absolute_time`;
ela é explicitamente nula. Isso foi conferido no
[kern_time.c da base Apple fixada](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/bsd/kern/kern_time.c).
Uma primeira versão do diagnóstico deixava esse argumento residual
e recebeu erro; foi corrigida antes dos ensaios publicados.

O código ocupa um segmento RX de 16 KiB num Mach-O arm64 estático,
com `LC_UNIXTHREAD`/`ARM_THREAD_STATE64`. `lab/xnu/macho.py` empacota esse
único programa; não é um linker Mach-O geral. Não carrega ELF, bibliotecas,
símbolos externos ou relocations. O nome `/sbin/launchd` atende à procura
inicial do kernel; **o executável nesse caminho é o diagnóstico próprio**,
não o launchd Apple.

## Entradas e ambiente

| Entrada | Versão/identidade |
|---|---|
| HackiOS kernel | `8e61187098f2c26c5daee8f9f72b6416aa64b9ab` |
| HackiOS userland | `906425b75e02b4f99eb5d7bb1ef7c9583472d772`; somente o gerador APFS é executado |
| Kernel prebuilt | Darwin 22.5.0 / XNU 8796.121.2; SHA-256 `9239d4adb7a2c433d7ed5729b47b63acc5281af73d8a81640ef3c678c8afd26c` |
| Loader EFI | SHA-256 `9749fa6ccaba925a585e72d586a4086150d39c67129d44bce8ae9badb2c895d1` |
| QEMU | 10.0.13, pacote Debian `1:10.0.13+ds-0+deb13u1` já disponível no projeto |
| Máquina | `virt,gic-version=3`, cortex-a76, uma CPU, 6 GiB de RAM guest, TCG |
| Binutils | AArch64 GNU as/objcopy 2.44; dispensa GCC e toolchain Mach-O |
| Firmware | Debian `qemu-efi-aarch64_2025.02-8+deb13u1_all.deb`; CODE não Secure Boot e template VARS identificados por hash |
| Host | Linux x86_64, Python 3.11+, git; ferramentas extraídas sem instalação como root |

O pacote UEFI tem 5122856 bytes e SHA-256
`a00b2411a79c8aeafd95a7c868ac3cd1aab592f1af9fff965f02d81a625276ed`,
conferidos contra a
[página Debian](https://packages.debian.org/trixie/all/qemu-efi-aarch64/download).
Foi obtido de
`https://deb.debian.org/debian/pool/main/e/edk2/qemu-efi-aarch64_2025.02-8+deb13u1_all.deb`
e extraído por `dpkg-deb -x` fora do repositório. CODE e VARS têm 64 MiB
cada. Os hashes estão no runner e relatório. São firmware do emulador,
não imagens Samsung.

O runner verifica revisões e hashes dos dois scripts upstream que executa,
kernel, loader e UEFI. Identidade do prebuilt não comprova build a partir
dos fontes. Não há download automático ou novos prebuilt no Git.

## Reprodução

Prepare clones externos nos commits indicados, em diretório próprio para
dependências, e extraia o pacote UEFI conferido acima:

```sh
git clone https://github.com/oosexgang/hackios-xnu-kernel.git kernel
git -C kernel checkout --detach 8e61187098f2c26c5daee8f9f72b6416aa64b9ab
git clone https://github.com/oosexgang/hackios-xnu-userland.git userland
git -C userland checkout --detach 906425b75e02b4f99eb5d7bb1ef7c9583472d772
dpkg-deb -x qemu-efi-aarch64_2025.02-8+deb13u1_all.deb efi
```

Da raiz do S21-baremetal, ajuste os caminhos e rode:

```sh
python3 scripts/test_xnu_lab.py
python3 scripts/run_xnu_lab.py \
  --kernel-tree /caminho/deps/kernel \
  --userland-tree /caminho/deps/userland \
  --efi-code /caminho/deps/efi/usr/share/AAVMF/AAVMF_CODE.no-secboot.fd \
  --efi-vars /caminho/deps/efi/usr/share/AAVMF/AAVMF_VARS.fd
```

Cada execução cria `build/xnu-lab-*`, ignorado pelo Git, com build, APFS,
contêiner, NVRAM, serial, setup.log e report.json. Um `--out` explícito deve
ser novo; diretórios existentes são recusados. `--tools` aponta para outro
toolchain/QEMU local; há fallback para ferramentas do PATH. O prazo padrão
é 90 s.

Repita o segundo comando com `--negative-fixture` para a contraprova:
ela deve produzir `FAIL APFS fixture`, `passed=false` e sair com **código 1**.
Erro de preparação sai com **2** e não conta como contraprova. Compare os
hashes do init e o tamanho das fixtures: mesmo executável e somente um
byte do arquivo alterado.

O runner apresenta ao QEMU arquivos de sua pasta e CODE UEFI somente
leitura; VARS e FAT são cópias do ensaio. Não há rede, disco físico ou
porta de monitor/GDB nessa execução. Não implementa operações no telefone.

## Consequência para o projeto

X1 tem agora **boot de XNU prebuilt e programa próprio reproduzidos**.
Build do kernel pelos fontes, serviços Darwin mais amplos, SMP e userland
iOS continuam com critérios separados. Segue a especificação e teste do
adaptador de argumentos/memória; a [estratégia Android/XNU](dual-boot-strategy.md)
organiza as dependências.

A investigação HZC2 continua necessária: entrada, coerência, RAM/reservas
e um canal de leitura no S21. RAM, janela UEFI, endereços QEMU, árvore Apple
e permissões observados neste ensaio não descrevem o Exynos.
