# HZC2 — geometria de vendor_boot e inicialização dos módulos

Comparação offline de 23/11/2026 (Campo Grande), sobre `9a5bb1d`. O port usa
SM-G998B/AUT no HZC2 e FlopKernel 5.4.304, com Flop fixado em
`113ce9d986f74e1526981324ec164e4d90930071`. Nosso candidato usa Samsung
5.4.242 e Clang r383902. A [validação da Stability 1.2](https://github.com/malick186/S21-Ultra-5g-SM-G998B-Android-17-OneUI-9.5/blob/1139b53be94317a57966a38d7953b6f87ed79842/docs/STABILITY-1.2.md)
registra instalação limpa pelo mantenedor em um SM-G998B desbloqueado.
O [patch publicado](https://github.com/malick186/S21-Ultra-5g-SM-G998B-Android-17-OneUI-9.5/blob/1139b53be94317a57966a38d7953b6f87ed79842/patches/kernel.patch)
tem SHA-256 `f636d8a7f90dbd424629679cc1a0c5dec5c2876fe98e40f16c1d7357befa423d`.
A coluna do port abaixo é leitura da receita. As duas primeiras colunas são leituras das imagens.

| Campo de vendor_boot | HZC2 original | Protótipo B | Receita p3s |
|---|---:|---:|---:|
| Página | 4096 | 4096 | 4096 |
| Kernel | 0x80008000 | 0x80008000 | 0x80008000 |
| Ramdisk | 0x84000000 | 0x84000000 | 0x84000000 |
| Tags | 0x80000000 | 0x80000000 | 0x80000000 |
| DTB | 0x81f00000 | 0x81f00000 | 0x81f00000 |
| Board | SRPTH19D019KU | SRPTH19D019KU | SRPTH19D019KU |

Os cabeçalhos v3 medem 2112 bytes. No comparativo integral, só os offsets
decimais 24, 25 e 26 diferem. São três bytes do u32 de tamanho do ramdisk,
que passa de 12017257 para 11774882. O montador B reproduziu o original
byte a byte no controle sem substituições. Os endereços da tabela são campos
de arquivo. A execução física e a aceitação das imagens continuam em aberto.

## Entradas dos módulos e IKCONFIG

Em cada par de módulos (original do vendor_boot e recompilado do pacote
alinhado), `init_module` e a função de inicialização têm a mesma seção,
valor e tamanho. As seções `.text` de cada par são byte a byte iguais antes
das relocações.

| Módulo | Função | Offset em .text | Bytes da função | Bytes da seção comparada |
|---|---|---:|---:|---:|
| pdic_notifier_module.ko | pdic_notifier_init | 0xedc | 144 | 11832 |
| gpu_cooling.ko | exynos_gpu_cooling_init | 0xfb4 | 612 | 7232 |

O HZC2 registra essas funções diretamente em
`drivers/usb/typec/common/pdic_notifier.c` e `drivers/thermal/samsung/gpu_cooling.c`.
O port acrescenta wrappers na seção de init. A coincidência com os módulos
Samsung dá motivo para preservar as entradas atuais. Permanecem relevantes o
destino após relocação, a chamada pelo kernel e o resultado em execução.
O caminho literal `drivers/optics/flicker_test.c` do patch não foi localizado
no tar da fonte Samsung. Isso deixa aberta a existência de implementação equivalente em outro caminho.

O Makefile Samsung já usa `$(KCONFIG_CONFIG)` para a configuração embutida.
No vmlinux alinhado, os símbolos `kernel_config_data` e
`kernel_config_data_end` delimitam um gzip em `.rodata`. Seu conteúdo
descomprimido é **idêntico aos 202262 bytes da .config** do mesmo build,
SHA-256 `5e82e452e6a5bc008f191e971f0cc21cd97be5cad7965542403dedc67b45570a`.
O ELF também contém `ikconfig_read_current` e `default_llseek`. A leitura
de /proc/config.gz em runtime continua pendente. A .config inclui
PSTORE_RAM e PSTORE_CONSOLE. A configuração por si só não identifica região
reservada, registro do backend ou log persistente disponível em um boot.

## Como reproduzir a medição

1. Conferir os [pins de fonte, LZ4 e imagem original](references/capture-a0-pins-hzc2.json),
   a [identidade do pacote alinhado](capture-a0-aligned-full-hzc2.md) e o
   [manifesto do protótipo B](references/capture-a0-natural-b-artifact-20261104.json).
   O vmlinux medido tem SHA-256 `0355418bebc35257984558d234d61af4d6b71a312c8089b760fda7c1b3405eeb`.
2. Ler o vendor_boot original com `check_capture_a0_parent.lz4_frame`,
   limite de 67108864 bytes. Selecionar o membro vendor_boot.img do tar B
   e conferir os dois hashes raw antes da comparação. Comparar os primeiros
   2112 bytes e decodificar little-endian nos offsets 12, 16, 20, 2076 e
   2104 (u64 no último). Nome da placa em [2080,2096). Rodar
   `capture_a0_natural.stage(stock, {}) == stock` como controle.
3. Abrir o ramdisk no original com os leitores gzip/newc de
   `capture_a0_modules`. Nos dois módulos em lib/modules e nos homônimos
   recompilados, usar `readelf -WS` e `readelf -Ws` para identificar a seção
   das funções. Comparar a seção completa devolvida por `elf_sections`.
4. Usar `nm -n vmlinux` e `readelf -WS vmlinux` para localizar o gzip
   embutido. Neste ELF a seção .rodata começa em 0xee0000 no arquivo,
   VA 0xffffffc010f50000. O gzip ocupa o intervalo relativo [0x2138,0xd062).
   Descomprimir e comparar com a .config do pacote.

**Decisão para A0.** Manter o empacotamento B e as duas entradas Samsung
estudadas. A comparação não identificou uma correção a importar nesses pontos.
A próxima evidência que distinguiria os casos é a chamada de inicialização
após relocação e seu resultado. O relato sobre o FlopKernel não estabelece
uma falha CFI no candidato. A captura cooperativa do Marco A continua dependente
da validação de execução e aceitação já registrada no projeto.
