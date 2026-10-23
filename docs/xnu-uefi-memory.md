# Memória do XNU: reservas reais da UEFI no QEMU

Entrega de **2026-10-22 em Campo Grande / 2026-10-23 UTC**. O carregador
recompilado agora reserva o payload de entrada e confere a janela XNU
contra mapas completos retornados por `GetMemoryMap`. O runner cruza esses
mapas com os argumentos e a árvore capturados no kernel, sem usar a RAM
da fixture FDT como prova de alocação.

Resultado: **um boot com 22 critérios aprovados, oito recusas e 22 testes
novos de host**. Os 16 testes anteriores dos recursos também passaram.
Kernel continua prebuilt identificado por hash; o loader foi recompilado e
o init próprio foi reaproveitado do baseline verificado.
Não houve execução no S21, SMP ou interface iOS.

## Problema corrigido

A variante anterior evitava o intervalo de entrada ao escolher a janela,
mas não o reservava junto à UEFI. Assim, a escolha do destino não impedia
uma alocação posterior do firmware de usar a memória do payload. Agora o
loader exige que os 64 MiB estejam convencionais e solicita
`AllocatePages(AllocateAddress, EfiLoaderData, ...)` antes de ler o payload.
Uma região já ocupada provoca recusa, sem tratá-la como nossa só porque
contém bytes de uma imagem.

A janela inteira do XNU é selecionada em memória convencional, alinhada a
32 MiB, e reservada pelo mesmo serviço. Status e endereço retornado precisam
confirmar a solicitação exata. O tamanho continua limitado a 6 GiB pelo
perfil upstream; os recursos periféricos continuam no perfil QEMU fixado.

## Quatro capturas na mesma execução

| Estágio | Verificação | Descritores observados |
|---|---|---|
| `payload-free` | Payload ainda em memória convencional | 80 |
| `window-free` | Payload reservado; janela candidata ainda convencional | 82 |
| `before-copy` | Payload e janela inteiros em `EfiLoaderData`; layout confere antes de qualquer cópia de segmentos | 82 |
| `handoff` | As duas reservas continuam cobertas imediatamente antes da manutenção de cache/salto | 82 |

Cada descritor observado tem **48 bytes**, versão 1. O prefixo conhecido
tem 40 bytes; o código respeita o `DescriptorSize` retornado e conserva os
bytes adicionais. Não filtra regiões menores que 1 MiB nem omite tipos do
mapa. Os quatro buffers são estáticos: obter um snapshot não exige alocar
outro buffer que altere o mapa.

O parser limita o mapa a 64 KiB/1024 descritores, stride entre 40 e 256
bytes em múltiplos de oito, versão 1 e tipos conhecidos 0–15. Recusa
truncamento, sobreposição, tamanho nulo, overflow e bases desalinhadas.
Falha de `GetMemoryMap`, inclusive buffer insuficiente, interrompe a carga.
Não há iteração com stride zero ou mapa parcial.

Para as regiões que serão usadas, a política exige tipo convencional
antes da reserva e `EfiLoaderData` depois, capacidade WB e ausência de
flags runtime/WP/RP/RO. Esses atributos não demonstram as permissões atuais
das tabelas de páginas da CPU. A cobertura aceita descritores adjacentes
em qualquer ordem, mas exige ausência de buracos em toda a região.

Referência normativa: [UEFI 2.10 A, serviços de alocação e GetMemoryMap](https://uefi.org/specs/UEFI/2.10_A/07_Services_Boot_Services.html#memory-allocation-services).
O layout do prefixo é conferido por `_Static_assert` na compilação EFI.

## Regiões observadas

| Região | Intervalo físico, fim exclusivo | Evidência |
|---|---|---|
| Payload de entrada | `[0xf0000000, 0xf4000000)` — 64 MiB | Reserva exata com status 0 e endereço retornado correto |
| Janela XNU inteira | `[0xf4000000, 0x1be000000)` — 3232 MiB | Convencional antes; reserva exata; coberta antes da cópia e do salto |
| Segmentos do kernel | Dentro de `[0xf7004000, 0xf82e4000)` | Cada segmento cruzado com Mach-O e mapa UEFI |
| Ramdisk | `[0xf82e4000, 0xf86e4000)` | 4 MiB dentro da janela |
| Árvore Apple | `0xf86e4000`, 14800 bytes | Capturada e reemitida sem alteração |
| boot_args | `0xf86f4000`, 736 bytes | Capturados; fim de dados alinhado em `0xf86f8000` |

A UEFI **uniu as duas reservas adjacentes em um único descritor tipo 2**,
`[0xf0000000, 0x1be000000)`. Por isso, tamanho/tipo de um descritor sozinho
não identifica uma alocação. O verificador exige a transição, os dois
resultados de `AllocatePages` e a correspondência com o contrato capturado.

Esse merge também expôs uma suposição no percurso de cache upstream: ele
excluía a janela só quando o descritor começava dentro dela. A variante
agora recorta os dois lados de qualquer descritor sobreposto, deixando a
janela XNU para o tratamento próprio. Isso foi exercitado no boot QEMU;
não é validação de coerência de caches físicos Samsung.

## Contraprovas e evidências

As cinco recusas anteriores de recursos/payload continuam passando. Três
binários de teste, compilados explicitamente com `S21_MEMORY_TEST=1/2/3`,
acrescentam falhas usando **serviços reais da UEFI no QEMU**:

| Falha provocada | Recusa esperada |
|---|---|
| Payload reservado como BootServicesData antes da tentativa | `REJECT payload not free` |
| Uma página da janela devolvida e reservada como BootServicesData | `REJECT window ownership stage 2` |
| Uma página do payload devolvida após a reserva da janela | `REJECT payload ownership stage 2` |

Os testes exigem sucesso da chamada que provoca a falha, a recusa específica
e ausência das marcas de cópia/salto/Darwin/init. Os binários negativos não
são o loader normal; o padrão compilado é `S21_MEMORY_TEST=0`. Todas as
nove execuções encerraram QEMU com status 0; esse status isolado não prova
boot ou recusa correta.

Os 22 testes novos cobrem o mesmo C com ASan/UBSan, confronto com o decoder
Python, extensões de descritor, todos os prefixos de um descritor, buracos,
tipos/atributos, overlaps, overflow, seleção e registros de evidência
incompletos/incompatíveis. LeakSanitizer permanece desativado no host
instrumentado. Os 16 testes de recursos anteriores também passaram.

O [manifesto da execução](references/xnu-uefi-memory-20261023.json) registra
comandos, hashes, alocações, capturas e nove transcrições. O
[serial positivo completo](references/xnu-memory-positive-20261023.txt)
inclui todos os bytes dos quatro mapas em linhas `S21 UEFI DESC`.
`lab/xnu/efi_memory.py:parse_serial` reconstrói esses bytes sem perda,
inclusive a partir da transcrição em texto. Os hashes são comparados aos
arquivos binários brutos da execução.

## Reproduzir e limites

Use os mesmos clones, baseline, UEFI e ferramentas da
[integração EFI](xnu-efi-adapter-lab.md). O runner agora executa nove casos:

```sh
python3 scripts/test_xnu_efi_resources.py
python3 scripts/test_xnu_efi_memory.py
python3 scripts/run_xnu_adapter_lab.py \
  --lab-run /caminho/baseline-positivo \
  --kernel-tree /caminho/hackios-xnu-kernel \
  --llvm-root /caminho/llvm-extraido \
  --efi-code /caminho/AAVMF_CODE.no-secboot.fd \
  --efi-vars /caminho/AAVMF_VARS.fd \
  --out /caminho/nova-execucao
```

O último snapshot é usado também pelo percurso de cache. Não há emissão
dos mapas ou chamada de alocação entre essa captura bem-sucedida e o salto.
Os mapas são emitidos **depois do retorno do kernel**; nas recusas, antes
do encerramento. A captura de boot_args/árvore continua sendo somente
leitura por GDB em `arm_init`, com retomada até init/APFS/timer/RB_HALT.

A UEFI permanece residente, conforme o desenho upstream. Não chamamos
`ExitBootServices` nem reutilizamos a chave do mapa para esse serviço.
É a lista completa **reportada pela UEFI naquele instante**, não uma prova
de todos os recursos físicos do SoC. A reserva começa na aplicação EFI;
não demonstra preservação do payload durante os estágios anteriores do
firmware. Também não garante um snapshot recuperável se o kernel não
retornar, persistência após reset, estado de caches no S21 ou execução
segura de imagens arbitrárias. O kernel prebuilt fixado é uma entrada
confiada; as checagens estruturais não autenticam executáveis.

O marco de memória UEFI está concluído **neste laboratório**. P1/P2 e o
diagnóstico mínimo físico continuam no [roadmap](roadmap.md). Para Samsung,
a origem da RAM/reservas, o estado de entrada e o canal de recuperação
precisam de evidência própria. Nenhum arquivo extra do usuário foi necessário.

A [extensão explícita para vídeo QEMU](xnu-video-contract.md) acrescenta a reserva do framebuffer, sem mudar o padrão headless; seus resultados são registrados separadamente.
