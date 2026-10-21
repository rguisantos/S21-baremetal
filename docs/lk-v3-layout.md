# Modelo offline das cópias LK v3

Desenvolvimento de 2026-10-21, a partir do sboot HZC2 e das imagens stock já
recebidas. Complementa a [cadeia kernel/contêiner/salto](lk-kernel-copy.md).
O modelo descreve um ramo estático; não executa o bootloader nem valida um
artefato para carregamento no telefone.

## O que foi fechado após a cópia do kernel

No dispatch v3 com w0=6, x23 contém o destino do kernel e x22 vem de
contexto+0x80. O chamador preenche esse campo com **0x84080000**. Quando esses
destinos são não nulos, as cópias rastreadas são:

| Chamada no arquivo sboot | Fonte | Tamanho | Destino |
|---|---|---|---|
| 0x12e88c → 0x1af3c0 | boot + align(header_size,4096) | boot.kernel_size | 0x80080000 + deslocamento |
| 0x12e7f8 → 0x1af3c0 | vendor_boot + align(vendor_header_size,vendor_page) | vendor_ramdisk_size | 0x84080000 |
| 0x12e848 → 0x1af3c0 | boot + align(header_size,4096) + align(kernel_size,4096) | boot.ramdisk_size | 0x84080000 + vendor_ramdisk_size |

O destino do ramdisk de boot usa o **tamanho exato** do ramdisk vendor, sem
arredondá-lo. O alinhamento ocorre nas fontes dos contêineres. Esse detalhe
importa porque o tamanho stock do ramdisk vendor não é múltiplo de página.

O trecho 0x12e710–0x12e7c0 calcula a posição da região DTB vendor a partir
de header_size e vendor_ramdisk_size alinhados à página vendor. Em
0x12e84c/0x12e850, o ponteiro dessa região é passado a 0x149188. Esse helper
grava x0 em um global e retorna: não é nessa função que se seleciona um FDT
ou se comprova o ponteiro final entregue ao kernel.

0x12e860 chama 0x151b10. Seu primeiro helper, 0x150320, lê um campo de
contexto global, em vez de analisar diretamente o header kernel recebido
em x0. A função chama vários outros helpers. **O propósito completo e seus
efeitos transitivos continuam pendentes**; não tratá-la como uma verificação
de assinatura identificada nem como prova de ausência de transformações.

## Conferência com os arquivos originais

Os hashes das duas imagens LZ4 e dos arquivos descompactados foram novamente
conferidos contra o [inventário stock](stock-firmware-hzc2.md). Ambos os
arquivos raw têm 64 MiB. O [relatório JSON reproduzido](references/lk-v3-stock-hzc2-offset0.json)
registra o cenário explícito de deslocamento **zero**:

| Componente | Offset no contêiner | Bytes | Intervalo de destino, fim exclusivo |
|---|---:|---:|---|
| Kernel | boot + 0x1000 | 29.469.184 | 0x80080000–0x81c9aa00 |
| Ramdisk vendor | vendor_boot + 0x1000 | 12.017.257 | 0x84080000–0x84bf5e69 |
| Ramdisk boot | boot + 0x1c1c000 | 701.558 | 0x84bf5e69–0x84ca12df |
| Região DTB vendor | vendor_boot + 0xb77000 | 389.940 | ponteiro staging 0x98b77000 |

O deslocamento zero é uma entrada do modelo, **não uma leitura do resultado
SMC do aparelho**. Os 64 valores rastreados afetam o destino kernel. Os outros
destinos desse contexto não são deslocados junto com ele.

O header Image declara **33.976.320 bytes** de memória. Há **4.507.136 bytes**
além da cópia kernel do contêiner; para o cenário zero, a extensão declarada
termina em 0x820e7000. O modelo não presume que esse restante seja zerado,
livre ou recuperável. Não usar o fim dos bytes copiados como limite da imagem.

## Ferramenta e testes

```bash
python3 scripts/check_lk_v3_layout.py /caminho/sboot.bin \
  /caminho/boot.img /caminho/vendor_boot.img --offset 0
python3 scripts/test_lk_v3_layout.py -v
```

O programa usa somente a biblioteca padrão. Lê arquivos raw, limita cada
contêiner a 64 MiB, exige o hash exato do sboot, headers v3 conhecidos,
página vendor de 4096 bytes e Image ARM64 little-endian sem compressão.
Confere todos os intervalos de componentes antes de emitir o relatório.
Recusa deslocamentos fora de 0..0x1f8000, passo 0x8000, e sobreposições entre
as extensões de destino modeladas. Não extrai arquivos nem escreve contêineres.

Essa é uma política conservadora de análise, não a reprodução de todos os
checks do LK. Um arquivo recusado pelo programa não está automaticamente
rejeitado pelo firmware; um relatório emitido não significa boot permitido.
Os campos vendor kernel_addr/ramdisk_addr/dtb_addr não escolhem os destinos
deste ramo modelado. O programa não verifica AVB, assinaturas, seleção de
DTB/overlay, mudanças posteriores, RAM reservada ou permissões.

Resultado: **7 testes passaram**, incluindo 64 cenários de deslocamento,
tamanhos desalinhados, concatenação sem padding, truncamentos, versão/página
não suportadas, tamanhos inválidos, colisão da extensão Image, independência
dos campos de endereço e recusa CLI de firmware incorreto. Também foi
executado o CLI com boot/vendor_boot stock e sboot de hashes conferidos;
os cenários stock zero e 0x1f8000 foram conferidos.
Esses testes são de host; não executam o LK nem substituem os testes QEMU.

O JSON marca `runtime_observed=false`, `bootability_verified=false`,
`tail_zeroing_verified=false` e `is_final_fdt=false`. Os dados do firmware
continuam fora do Git; somente ferramentas, testes e documentação são publicados.

## Limites e próximo bloqueio

`inspect_sboot_hzc2.py` inclui `kernel_v3_tail` com chamadas e palavras de
instrução que sustentam o rastreio. Para desassemblagem independente, usar
0x12e6f8:0x12e890, 0x149188:0x149194, 0x150320:0x150330 e
0x151b10:0x151c00, além do setup do contexto já documentado.

Ainda faltam a seleção/alteração final do FDT, reservas de RAM, estado de
EL/MMU/caches e um canal de observação. O modelo não transforma o shim em
carregador Samsung nem prepara um pacote de flash. O consumidor do ponteiro
foi rastreado na [seleção DTB e merges DTBO/DPM](lk-dtb-pipeline.md).
Restam os valores das edições dinâmicas e os checks posteriores até o salto.
