# Userland iOS 16.5 no QEMU

Ensaio local de referência em **2026-10-23 (Campo Grande)**. **O SpringBoard foi visto e respondeu a toques: Ajustes e a página Geral
foram abertos e conferidos visualmente.** O XNU prebuilt iniciou quatro
CPUs, montou o sistema APFS e lançou launchd/backboardd/SpringBoard. As
capturas são PNGs nativos de 1125×2436, separados das mensagens de processo.

## Evidência visual

| Captura | Observação conferida |
|---|---|
| [Tela inicial](references/hackios-userland-20261023/homescreen.png) | SpringBoard com grade de ícones antes do toque |
| [Ajustes](references/hackios-userland-20261023/settings.png) | App aberto após toque em `(0.615, 0.71)` e espera de 30 segundos |
| [Geral](references/hackios-userland-20261023/general.png) | Navegação dentro do app após toque em `(0.5, 0.795)` |
| [Sobre](references/hackios-userland-20261023/about.png) | Versão exibida 16.5 após terceiro toque; identidade fornecida pela emulação |

A captura de 60 segundos ainda mostra o logo Apple. A de 375 segundos já
mostra a tela inicial; esse é o instante da amostra conferida, não uma
medição exata de prontidão. A página Sobre exibe iPhone X e um serial de referência HackiOS; esses
valores não identificam hardware Apple ou o S21. O
[registro visual](references/hackios-userland-20261023/visual-evidence.json)
vincula cada observação ao SHA-256 da imagem original. O
[relatório bruto](references/hackios-userland-20261023/run-report.json)
conserva a linha completa do QEMU, entradas, ações e capturas; seu campo
automático de verificação visual permanece falso. O
[console integral comprimido](references/hackios-userland-20261023/serial.log.gz)
tem hash bruto conferido e é acompanhado de
[marcos legíveis](references/hackios-userland-20261023/milestones.txt).
A execução terminou por comando de parada aos 544,69 segundos, com
returncode 0 e sem erro do runner.

Não inferimos sucesso de apps por brilho ou
por terem sido lançados. A primeira tela inicial apresenta fundo branco
e widgets sem conteúdo; não validamos todos os serviços, gráficos ou apps.

## O que foi preparado

| Entrada | Identificação |
|---|---|
| HackiOS kernel | `8e61187098f2c26c5daee8f9f72b6416aa64b9ab` |
| HackiOS userland | `906425b75e02b4f99eb5d7bb1ef7c9583472d772` |
| Apple | iOS 16.5, build 20F66, IPSW iPhone10,3/iPhone10,6; três membros selecionados |
| Loader | Fonte de referência recompilada com Clang/LLD 19.1.7 e correção ramfb; SHA-256 `25cfe5093931befaba5a0d6cce411f1f15f042e30e8e1851b0850d70edab832a` |
| Imagem de boot | 4194304 bytes; SHA-256 `f6b5d240ffc94be4215d373eea4fcdff00f2dcddb46695db5db4c2fce3118065` |
| Imagem de sistema | 2548080640 bytes; SHA-256 `5aec779ffb75f3adffa1582540a2f3d57bdf0edd6d0c78335ee8c03f6e663393` |
| Execução | QEMU 10.0.13, TCG, Cortex-A76 ×4, RAM 7 GiB, ramfb 1125×2436, teclado/tablet virtio |

O [registro das entradas](references/hackios-userland-inputs-20261023.json)
contém tamanhos, SHA-256 e CRC ZIP dos três DMGs, os 19 arquivos prebuilt do
userland e a comparação byte a byte das duas fontes corrigidas. O kernel
permaneceu no commit fixado, sem alteração de arquivos rastreados.

A preparação usa os scripts upstream de seleção/extração e construção
APFS. Seus binários Apple, caches dyld, seleção de arquivos, stage0, init,
bibliotecas de adaptação e plists formam um sistema adaptado pelo HackiOS.
Não se trata de uma imagem iOS integral sem alterações, nem de uma
compilação local do XNU.

## Alterações declaradas

Aplicamos somente o [patch de preparação auditado](hackios-userland-host.md)
a `build.sh` e `mkjobs.py`: nomes dos jobs extras, umask 022, cópia opcional
de drawable_test e fallback de timezone. `fetch.sh` e `mkapfs.py` foram
usados sem alterações. Os componentes baixados passaram CRC da entrada ZIP
e foram identificados por SHA-256. Uma resposta HTTP 503 exigiu retomar o
fetch; o build final ocorreu depois da extração completa.

O build foi `PREBUILT=1 REST=1 SHARE=1`, com
[`RC_JOBS=lab/xnu/userland-rc.jobs`](../lab/xnu/userland-rc.jobs): dois
comandos leves, sem o cpu_test 240 do exemplo upstream. Essa escolha muda
explicitamente o trabalho iniciado no boot. Foram gerados 407 plists em
0644 e 406 labels distintos; a duplicação de `com.apple.sysdiagnose`
pertence às variantes upstream. Nenhum arquivo `RWA_PACKED16` foi gerado.

O loader incorpora a [correção ramfb na fonte](xnu-ramfb-audit.md), com
barreiras, leitura do controle DMA e timeout. Não usamos o patch binário
que mantém o painel GOP 800×600. O display e o painel relatados pelo driver
medem 1125×2436, com stride de 4500 bytes.

O runner usa `-L` para as ROMs locais e AAVMF verificado, ESP e NVRAM novos,
TCG com cache de 384 MiB e memória de arquivo **privada (`share=off`)**.
O sistema residente é copiado para o offset `0xbc000000` do arquivo de
RAM, correspondente ao endereço físico `0xfc000000`. A imagem pequena
segue no payload XNUP. O SHA-256 do kernel e da imagem pequena foi conferido
nas entradas do payload; o da imagem residente foi conferido no arquivo
que o QEMU mapeou. O loader do ESP também coincide com o manifesto.

Não há rede, áudio QEMU, discos do host ou aparelho Samsung nessa execução.
A linha completa do QEMU, hashes e capturas constam do relatório da execução.

## Preparar o workspace

Fixe as duas revisões acima e use o `common/setup.sh` do kernel para
configurar a árvore compartilhada do userland. Aplique o patch de
portabilidade versionado e compile o loader com a correção ramfb conforme
a [auditoria](xnu-ramfb-audit.md). Para as imagens:

```sh
cd /caminho/hackios
# Requer 7-Zip moderno com APFS e ferramentas do workspace no PATH.
KEEP=1 bash ios165/fetch.sh
PREBUILT=1 REST=1 SHARE=1 \
  RC_JOBS=/caminho/S21-baremetal/lab/xnu/userland-rc.jobs \
  bash userland/build.sh
```

Execute o build somente após o fetch concluir. Marcadores `.done-*` sem a
árvore extraída correspondente não comprovam uma preparação completa. O
[log do build](references/hackios-userland-20261023/image-build.log.gz)
registra ambas as imagens concluídas; o sistema tem 622090 blocos de 4096
bytes. As imagens usadas no boot vieram da restauração conferida.

## Como executar e observar

Com o workspace HackiOS fixado e as imagens já construídas:

```sh
python3 scripts/run_hackios_userland.py \
  --kernel-tree /caminho/hackios \
  --loader /caminho/loader.efi \
  --loader-build /caminho/loader-build.json \
  --root-image /caminho/root.apfs \
  --system-image /caminho/system.apfs \
  --efi-code /caminho/AAVMF_CODE.no-secboot.fd \
  --efi-vars /caminho/AAVMF_VARS.fd \
  --out /caminho/execucao-nova --seconds 1800
```

`loader-build.json` é o registro produzido pela compilação ramfb do
laboratório. A pasta de saída precisa ser nova. `inputs.json` registra a
configuração antes de iniciar o QEMU; `status.json` registra progresso,
capturas e ações; `report.json` registra o término. As capturas PNG são
nativas do QMP e conservam a resolução original. A detecção de palavras
no console não confirma interface; o campo automático
`UI_visually_verified` permanece falso.

Para interagir, grave atomicamente `control.json` dentro da execução:

```json
{"actions":[
  {"type":"swipe","x0":0.5,"y0":0.96,"x1":0.5,"y1":0.25,"ms":600},
  {"type":"wait","seconds":10},
  {"type":"capture","name":"apos-gesto"}
]}
```

Coordenadas são normalizadas de 0 a 1. Também há `tap`, teclas `home` e
`lock`, esperas de até 30 segundos e `{"stop":true}`. Nomes de capturas
precisam ser únicos. O console contém falhas de serviços sem suporte nessa
plataforma; elas não devem ser confundidas com um boot completo de todos
os serviços ou com sucesso de um app sem conferir sua tela.

## Checkpoint verificável

As imagens preparadas foram preservadas fora do Git. O sistema foi dividido
em sete partes de até 384 MiB; o manifesto inclui tamanho e SHA-256 de
cada parte e das duas imagens completas. A restauração foi executada e
reproduziu os hashes. Um controle com hash alterado foi recusado e removeu
o arquivo parcial.

```sh
python3 scripts/restore_hackios_images.py \
  --manifest /caminho/s21-ios165-checkpoint.json \
  --directory /caminho/partes --out /caminho/restauracao-nova
```

As imagens Apple não são publicadas no repositório. O checkpoint permite
retomar o ensaio sem repetir a extração caso o ambiente seja restaurado.

## Relação com o port S21

Este ensaio usa o ABI upstream de imagem residente, separado do consumidor
EFI restrito do S21-baremetal. A [extensão para disco residente](xnu-resident-contract.md) foi implementada
e exercitada com uma imagem de 4 MiB, init próprio e recusas. Falta o perfil
explícito e a execução do userland completo por essa variante; o ensaio
gráfico aqui registrado continua usando o loader de referência.

O resultado de interface e interação no QEMU fecha uma etapa do
laboratório X4. O primeiro diagnóstico no telefone, entrada/cache, mapa de
RAM e observação Samsung permanecem nos marcos físicos do
[roadmap](roadmap.md).
