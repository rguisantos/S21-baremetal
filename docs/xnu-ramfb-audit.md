# HackiOS: ramfb do prebuilt e correção na fonte

Em **2026-10-23**, reproduzimos o defeito gráfico relatado pelo GLM no
`loader.efi` publicado da revisão `8e61187098f2c26c5daee8f9f72b6416aa64b9ab`.
O loader declara **800×600**, mas reprograma o QEMU para **1125×2436**.
A correção na fonte conserva o modo de telefone, relê a conclusão DMA e
recusa erro/timeout. Seis cenários passaram; o consumidor EFI do projeto
manteve os **22 critérios positivos** do laboratório XNU sem display.

Este ensaio usa um padrão próprio desenhado pelo EFI. **Não é uma execução
do SpringBoard, dos apps iOS ou do Exynos.** O novo relato do GLM informa
interface iOS funcionando com seu loader modificado; os PNGs e o log bruto
daquela sessão ainda não foram disponibilizados neste workspace.

## Evidência do prebuilt original

- SHA-256 do loader: `9749fa6ccaba925a585e72d586a4086150d39c67129d44bce8ae9badb2c895d1`.
- Nova ESP por execução, cópia incondicional para `EFI/BOOT/BOOTAA64.EFI`
  e igualdade dos hashes. Não usamos `cp -u` nem a ESP do teste anterior.
- QEMU **10.0.13**, TCG, uma CPU Cortex-A76, 6 GiB de RAM virtual, AAVMF
  Debian `2025.02-8+deb13u1`; hashes no manifesto.
- Memória padrão do QEMU: sem `memory-backend-file`, `share=on`, migração,
  rede, som ou imagens iOS. `-L` aponta para os dados/ROMs extraídos em
  diretório próprio. O payload desse controle é o laboratório com init próprio.

O [serial original](references/xnu-ramfb-published-20261023.txt) contém:

```text
ramfb: control 250018 after the request
display 800 x 600 at 1bf110000
```

O screendump nativo é 1125×2436 e preto. Pausamos a VM com QMP e lemos
48 bytes físicos em `0xa101c258`, sem escrever na memória do guest.
O descritor em `0xa101c278` já continha **control=0**, length=28 e ponteiro
para aquela configuração. A configuração continha framebuffer
`0x1bdced000`, largura 1125, altura 2436 e stride 4500. Portanto o status
impresso não representa o valor que estava na memória após a transação.

A [desmontagem do prebuilt](references/xnu-ramfb-prebuilt-disassembly-20261023.txt)
mostra o gatilho MMIO em `0xa1002860`, seguido de chamada incondicional ao
formatador, usando o valor anterior. Esse percurso não relê o descritor.
As posições são exclusivas desse hash, carregado na base preferida
`0xa1000000`; o runner recusa outra base antes da leitura.

Isso confirma o achado central do GLM para esse prebuilt. **Não confirma
que toda compilação do projeto falha:** recompilamos a fonte original,
sem correção nem instrumentação, com Clang/LLD 19.1.7 e `-O1`, e ela
configurou 1125×2436 corretamente. A montagem desse build tem uma leitura
real do descritor. O compilador usado para gerar o prebuilt não foi
identificado neste ensaio.

## Correção e controles

A [correção aplicada pelo nosso builder](../lab/xnu/ramfb.py) torna o
objeto DMA `volatile`, acrescenta barreiras de compilador/CPU, limita a
espera a um milhão de leituras e distingue conclusão, erro e operação
pendente. Somente publica `SCREEN` após sucesso. Erro ou esgotamento da
espera devolvem `EFI_DEVICE_ERROR`, sem continuar o handoff com o GOP antigo.
Se não há dispositivo/recursos para iniciar a transação, mantém o fallback
GOP anterior, pois nenhum novo framebuffer foi enviado ao dispositivo.

O protocolo [oficial fw_cfg](https://www.qemu.org/docs/master/specs/fw_cfg.html)
define zero como conclusão, bit 0 como erro e outros bits como pendência.
A documentação consultada é a versão publicada 11.1.50; a execução acima
usou QEMU 10.0.13. As barreiras aqui se destinam à DMA coerente emulada do
QEMU; não implementam manutenção de caches de um dispositivo físico Exynos.

| Controle executado | Resultado observado |
|---|---|
| Prebuilt original, hash conferido | Defeito reproduzido: declara 800×600; QEMU 1125×2436; control em RAM já zero |
| Fonte original recompilada, sem instrumentação | Declara e configura 1125×2436 com Clang 19 |
| Fonte original + desenho diagnóstico | Padrão visível em 1125×2436 |
| Fonte corrigida + mesmo desenho | Padrão visível em 1125×2436; cores/borda conferidas |
| Fonte corrigida + escrita no seletor somente leitura 0 | QEMU devolve control=1; EFI recusa antes do desenho |
| Fonte corrigida + gatilho DMA omitido | Descritor fica pendente; espera termina e EFI recusa |

Os dois últimos são binários de teste separados, gerados em cópias. O
builder normal não inclui essas injeções nem o padrão gráfico. O controle
sem instrumentação é interrompido após anunciar o display; não representa
boot completo gráfico do kernel. O padrão também estaciona antes do kernel.

Capturas **reais**, sem edição, pelo QMP `screendump` com `format=png`:

- [Prebuilt: framebuffer preto](references/xnu-ramfb-published-20261023.png).
- [Correção: padrão EFI de quatro cores e borda branca](references/xnu-ramfb-fixed-probe-20261023.png).

Usamos PNG diretamente porque o PPM observado neste QEMU para largura
1125 tinha 2436 bytes de padding além do RGB compacto esperado; a leitura
convencional pelo Pillow produzia diagonais artificiais. Esse problema da
captura não foi interpretado como defeito do framebuffer.

## Reprodução

É necessário o baseline positivo de [XNU com init próprio](xnu-qemu-lab.md),
as fontes externas na revisão acima, Clang/LLD 19 extraídos, AAVMF com os
hashes conferidos, QEMU/dados/SeaBIOS do kit e Pillow. Não precisa de IPSW.
O runner cria pastas novas, verifica entradas e usa QMP em stdin/stdout:

```sh
python3 scripts/check_xnu_ramfb.py \
  --kernel-tree /caminho/hackios-xnu-kernel \
  --llvm-root /caminho/llvm-extraido \
  --efi-code /caminho/AAVMF_CODE.no-secboot.fd \
  --efi-vars /caminho/AAVMF_VARS.fd \
  --lab-run /caminho/baseline-positivo \
  --out /caminho/nova-auditoria-ramfb
```

O [manifesto](references/xnu-ramfb-20261023.json) registra os seis comandos,
fontes/ELFs EFI por hash, capturas, amostras de pixels, bytes do descritor e
regressão positiva com quatro mapas UEFI. Os caminhos usam aliases `@run`,
`@repo`, `@headless`, `@tools-and-baseline` e `@upstream`. Os sete logs seriais
inteiros estão versionados, com bytes de controle escapados. Builds,
montagens e binários intermediários são regeneráveis e não foram adicionados.

Há também um [patch independente](../lab/xnu/patches/hackios-ramfb-dma.patch)
para essa revisão, sem alterar arquivos externos durante o ensaio:

```sh
git -C /caminho/hackios-xnu-kernel apply --check \
  /caminho/S21-baremetal/lab/xnu/patches/hackios-ramfb-dma.patch
```

## Próximo marco

Antes de contabilizar interface iOS local, validar o contrato de vídeo
`boot_args` e a reserva do framebuffer com o kernel em execução; depois
repetir o fluxo de userland com revisões/diffs e imagens identificados,
capturar SpringBoard e uma interação. O verificador atual de memória/ABI
continua deliberadamente restrito ao perfil sem display; não foi relaxado.

Para conferir a sessão externa do GLM, bastam os PNGs originais, o
`hackios-boot-console.log` e o patch/diff usado, junto aos hashes das imagens
e comando final. O relato de reexecução do README original terminou durante
a preparação: esse teste permanece incompleto. Isso não invalida o marco
gráfico relatado com alterações, nem o transforma em boot Samsung.
