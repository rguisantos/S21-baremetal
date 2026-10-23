# Userland iOS pelo consumidor EFI validado

Ensaio de **2026-10-23 (Campo Grande)**. O novo perfil liga as imagens APFS
identificadas do [ensaio de referência](hackios-userland-qemu.md) ao
consumidor que verifica recursos, reservas UEFI, dois discos e framebuffer.
**SpringBoard e navegação em Ajustes → Geral → Sobre foram conferidos
visualmente, com toques funcionando.** Usamos o mesmo kernel prebuilt, uma
CPU e as imagens já construídas. A confirmação visual é separada da
auditoria de entrada.

## Capturas e resultado visual

| PNG nativo 1125×2436 | Observação |
|---|---|
| [Tela inicial](references/xnu-guarded-userland-20261023/homescreen.png) | SpringBoard antes do toque em Ajustes |
| [Ajustes](references/xnu-guarded-userland-20261023/settings.png) | App aberto após toque `(0.615, 0.71)`; captura conferida visualmente |
| [Geral](references/xnu-guarded-userland-20261023/general.png) | Navegação por toque `(0.5, 0.795)` |
| [Sobre](references/xnu-guarded-userland-20261023/about.png) | Versão exibida 16.5 após toque `(0.5, 0.18)` |

A execução conservada terminou em **1024,6 s de observação total**, com
retorno nativo observado, código zero do QEMU e os quatro mapas reemitidos
iguais à captura inicial. O PNG da tela inicial foi registrado 453,4 s
após a captura em `arm_init`.

A tela inicial foi capturada após o lançamento do SpringBoard. O instante
da captura é registrado no manifesto; não é uma medição exata de prontidão. A tela inicial tem
fundo preto e widgets sem conteúdo. Sobre exibe identidade iPhone X
fornecida pelo HackiOS; não medimos Bluetooth, rede, GPU física ou o
funcionamento de todos os apps/serviços.

## Perfil explícito v1

A entrada opcional `labprofile` do XNUP tem 32 bytes. Ela só é aceita junto
do descritor `resident`, com imagem maior que 1 GiB e de até 3 GiB, ramdisk
pequeno de até 8 MiB e a tag exata `s21_userland_v1` no item `cmdline`.
Os modos antigos mantêm a linha de comando fixa de 30 segundos.

| Offset | Campo | Valor / política |
|---|---|---|
| 0 | Magic, 8 bytes | `S21ULAB\0` |
| 8 | Versão, u32 LE | 1 |
| 12 | Perfil, u32 LE | 1 |
| 16 | Epoch, u64 LE | Unix seconds, de 2020 inclusive a 2100 exclusive |
| 24 | Reservado, u64 LE | Zero |

O C gera `cpus=1 loader_return_after=900 virtio_input=1 epoch=N` em um
buffer limitado. Não aceitamos argumentos livres, CPU adicional ou uma
duração arbitrária. O prefixo fixo do loader acrescenta
`debug=0x8 serial=3 rd=md0`. A linha completa é conferida nos boot_args
capturados, contra o perfil binário fornecido no payload.

A VM tem 7 GiB de RAM e uma CPU Cortex-A76, GICv3, ramfb 1125×2436 e
teclado/tablet virtio. A declaração sintética de recursos usa 7 GiB; a
posse e a janela real vêm dos mapas UEFI capturados, sem tratar o fixture
como uma medição do firmware. O controlador não expõe rede, áudio QEMU,
discos do host ou aparelho Samsung.

O UEFI permanece residente; não há `ExitBootServices` neste percurso. O
retorno é ao loader de laboratório, com Boot Services ainda disponíveis.
Isso não estabelece um handoff físico para o S21.

Além da reserva da janela inteira, exigimos **pelo menos 1 GiB depois de
topOfKernelData**. Essa folga é conferida antes de reservar a janela e
novamente antes da cópia/salto. O caso de 6 GiB é recusado por esse critério
antes de ler o cabeçalho residente. No positivo, a janela capturada começa
em `0xf4000000`, mede `0x10a000000` bytes e conserva **1780350976 bytes**
para memória dinâmica depois dos dados estáticos.

## Entradas identificadas

| Entrada | Tamanho / identidade |
|---|---|
| Kernel | HackiOS `8e61187098f2c26c5daee8f9f72b6416aa64b9ab`, prebuilt SHA-256 `9239d4adb7a2c433d7ed5729b47b63acc5281af73d8a81640ef3c678c8afd26c` |
| Userland | `906425b75e02b4f99eb5d7bb1ef7c9583472d772`, somente o patch de preparação auditado |
| APFS pequeno | 4194304 bytes; SHA-256 `f6b5d240ffc94be4215d373eea4fcdff00f2dcddb46695db5db4c2fce3118065` |
| APFS residente | 2548080640 bytes; SHA-256 `5aec779ffb75f3adffa1582540a2f3d57bdf0edd6d0c78335ee8c03f6e663393` |
| Toolchain | Clang/LLD 19.1.7, AAVMF e QEMU identificados no laboratório |

O runner exige os hashes das imagens do manifesto versionado, os commits
fixados, a árvore kernel sem alterações rastreadas e o patch exato de duas
fontes do userland. A imagem residente é copiada para o offset `0xbc000000`
do arquivo esparso que o QEMU mapeia de modo privado (`share=off`). O
endereço físico continua `0xfc000000`. A raiz é md0; a imagem pequena é md1.

São componentes Apple selecionados e adaptações HackiOS. O teste não é uma
compilação local do XNU nem uma imagem iOS integral sem alterações.

## Auditoria na entrada do kernel

Um breakpoint somente de leitura interrompe a VM em `arm_init` no kernel
prebuilt identificado. Capturamos boot_args, árvore Apple e o primeiro
bloco da imagem residente. O bloco precisa coincidir com o da imagem de
entrada, e os discos da árvore precisam corresponder aos descritores.

O link do EFI gera um mapa de símbolos. A base efetiva observada no serial
é comparada à base preferida para localizar as células estáticas. O QMP
`pmemsave` lê os quatro buffers UEFI e os valores de reserva, perfil e
framebuffer da memória física. Os snapshots têm layout verificado por
`_Static_assert`, tamanho limitado e metadados de versão/stride/status.
O verificador Python deriva novamente a janela, intervalos, papéis md0/md1,
folga e modo gráfico a partir desses bytes. A captura não escreve em
registradores ou memória do guest.

O framebuffer é reservado fora da janela XNU e do payload. Como sua
alocação ocorre após a escolha da janela residente, o estágio 0/1 mostra
páginas convencionais e os estágios 2/3 mostram EfiLoaderData. O registro da
fase impede aceitar uma sequência diferente por conveniência.

### Correção de observabilidade encontrada

A primeira tentativa chegou à entrada do kernel, mas foi recusada pelo
verificador: a otimização interna do compilador representou
`s21_frame_size` como o booleano 1, reconstruindo o valor constante quando
o C o usava. Ler oito bytes desse símbolo não recuperava o valor lógico.
As células de captura do framebuffer passaram a ser `volatile uint64_t`,
preservando sua representação declarada na memória. O positivo aceito foi
recompilado e executado depois dessa alteração. A tentativa inicial não é
contada como validação de interface ou contrato concluído.

### Encerramento e tentativas incompletas

O limite nativo continua **900 segundos**. O observador permite mais 300
segundos depois da retomada em `arm_init` para receber a reimpressão do log
e os mapas. Uma execução anterior mostrou a interface e retornou do kernel,
mas o observador de 990 segundos totais interrompeu a saída antes do último
snapshot. Ela permanece como tentativa incompleta, sem PASS. Outra sessão
foi perdida entre turnos, com Ajustes capturado e sem relatório final; seu
último status e serial também foram preservados separadamente.

O runner agora exige o marcador do orçamento expirado, retorno com razão
zero, os quatro snapshots completos e igualdade dos bytes, stride, versão
e chave com a captura feita na entrada. Também compara os registros de
alocação. Os snapshots reemitidos são os quatro estados de preparação já
capturados; **não constituem um novo GetMemoryMap depois do userland**.
A ausência ou divergência desses dados impede `passed`, mesmo com saída
zero do processo QEMU.

O tour inicial de uma das tentativas colocou a tela no modo de editar
ícones; esses PNGs não foram classificados como apps abertos. A navegação
publicada usa capturas inspecionadas individualmente.

## Evidências e controles

O [manifesto de validação](references/xnu-guarded-userland-20261023/validation.json)
separa interface, contrato, término e tentativas anteriores. O
[relatório bruto](references/xnu-guarded-userland-20261023/report.json) conserva
as revisões, linha QEMU e hashes dos arquivos realmente usados. O
[registro das entradas carregadas](references/xnu-guarded-userland-20261023/loaded-inputs.json)
confere o EFI da ESP, as entradas do payload e todos os bytes do intervalo
residente no arquivo de memória; não apenas seu primeiro bloco APFS.
Nenhuma imagem APFS ou kernel Apple é versionado com essas evidências.

| Verificação | Resultado / escopo |
|---|---|
| Host | 74 testes: recursos 16, memória 22, vídeo 14, residente 10, perfil 12; C com ASan/UBSan |
| Recusas nativas | Perfil desconhecido, cmdline adulterada e memória de 6 GiB; 6 critérios por caso, antes de cópia/salto/leitura residente |
| Compatibilidade | Residente próprio com vídeo: 30 critérios; embedded headless: 22 critérios |
| Replay independente | Quatro mapas completos, boot_args, árvore Apple, papéis md0/md1, folga e framebuffer |
| Controles da captura | Cmdline, disco raiz, folga e posse UEFI adulterados; hashes recalculados e recusa semântica |

## Verificação offline

O comando abaixo reinterpreta os bytes preservados, sem executar a VM:

```sh
python3 scripts/verify_guarded_userland.py \
  --run /caminho/execucao-ou-evidencias \
  --kernel /caminho/mach.development.bcm2837
```

Ele confere hashes, posições dos símbolos, mapas completos, reservas,
boot_args/árvore, perfil, tamanho dos discos e framebuffer. O kernel deve
coincidir com o SHA-256 fixado. Quatro controles alteraram a linha de
comando, os papéis dos discos, a folga ou o tipo UEFI, atualizando também
os hashes dos dados adulterados: todos foram recusados pelas condições
semânticas, não apenas por divergência de checksum.
Os mesmos controles podem ser reproduzidos sem alterar os originais:

```sh
python3 scripts/check_guarded_userland_capture.py \
  --run /caminho/execucao-ou-evidencias \
  --kernel /caminho/mach.development.bcm2837
```


## Executar e observar

As imagens podem ser recuperadas pelo checkpoint já conferido; não é
necessário repetir os downloads Apple. Com as ferramentas do laboratório:

```sh
python3 scripts/run_guarded_userland.py \
  --kernel-tree /caminho/hackios \
  --llvm-root /caminho/llvm-extraido \
  --root-image /caminho/root.apfs \
  --system-image /caminho/system.apfs \
  --efi-code /caminho/AAVMF_CODE.no-secboot.fd \
  --efi-vars /caminho/AAVMF_VARS.fd \
  --out /caminho/execucao-nova --case positive
```

`--case headroom`, `profile` e `cmdline` exercitam as recusas. Elas deixam
a área residente sem conteúdo para demonstrar que a recusa não depende de
ler o disco. O positivo tem duração nativa de até 900 segundos e aceita
comandos atômicos em `control.json`, com o mesmo formato do
[runner de referência](hackios-userland-qemu.md): tap, swipe, teclas,
espera, captura e parada via QMP.

`inputs.json` registra a configuração, `contract.json` a auditoria inicial,
`status.json` o andamento e `report.json` o término. As capturas PNG são
nativas de 1125×2436. `passed` exige contrato conferido, retorno nativo e snapshots completos
coincidentes, além do encerramento sem erro do controlador; o campo automático `UI_visually_verified` continua
falso. As observações visuais são publicadas em registro separado.

## Escopo físico

O perfil é um experimento QEMU. Não modifica nem executa o caminho Samsung.
Os marcos de entrada/cache, memória, carregamento e recuperação do primeiro
registro no S21 continuam no [roadmap](roadmap.md). A identidade iPhone X
exposta pelo HackiOS é sintética e não identifica o dispositivo real.
