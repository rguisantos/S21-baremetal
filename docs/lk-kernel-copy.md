# LK HZC2: ligação entre contêiner, cópia da Image e salto

Análise estática de 2026-10-21 do sboot HZC2 já recebido, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets de instrução são do arquivo. A análise não executa o LK Samsung.
Complementa [o produtor do deslocamento](bootloader-hzc2.md).

## Destino colocado no contexto

Após produzir o deslocamento no global relativo 0x4a0048, o chamador prepara
um contexto local. Em 0xfb9ec–0xfba18:

| Offset | Valor/ação |
|---|---|
| 0xfb9ec | w0 = 0x80080000 |
| 0xfb9f0 | x3 = 0x84080000 |
| 0xfb9f4 | x2 = 0x98000000 |
| 0xfb9fc | x19 = 0x94000000 |
| 0xfba04 | [x29+0x50] = x19 |
| 0xfba08 | w1 = campo 0x4a0048 |
| 0xfba0c | [x29+0xa0] = x3 |
| 0xfba10 | w0 = w1 + w0, aritmética de 32 bits |
| 0xfba14 | [x29+0xc8] = x2 |
| 0xfba18 | [x29+0x78] = x0, zero-estendido após escrita em w0 |

Em 0xfba20 lê a versão do header em 0x94000028 via 0x12dfe8. Os ramos:

- versão 2: 0xfbb98 prepara x1=x29+0x20 e w0=6, chama 0x12e048;
- versão 3: 0xfbba8 prepara o mesmo contexto/valor, chama 0x12e540.

Portanto `contexto+0x30` contém 0x94000000 e `contexto+0x58` contém
**0x80080000 + deslocamento**. O primeiro é o endereço staging do contêiner
nesse caminho; não é o endereço de execução. A versão 3 é compatível com
[o boot.img recebido](stock-firmware-hzc2.md), mas o ramo realmente percorrido
no aparelho ainda não foi observado.

## Cópia v2

0x12e068 carrega x19=[contexto+0x30]; 0x12e070 carrega
x23=[contexto+0x58]. O código recompõe kernel_size dos bytes +8..+11 e
page_size de +0x24..+0x27 do boot header. Após cálculos dos componentes,
o ramo em 0x12e39c chega a:

```text
0x12e418  add x1, x19, w1, sxtw  ; fonte = contêiner + page_size
0x12e41c  mov x0, x23           ; destino do contexto
0x12e420  bl  0x1af3c0          ; cópia; x2 conserva kernel_size
```

Não é uma cópia do ELF completo como um único segmento. Esse caminho lê o
payload kernel do contêiner Android. Campos de endereço do header não foram
identificados como fonte do destino x23 nesse trecho.

## Cópia v3

0x12e560 carrega x19=[contexto+0x30], 0x12e568 carrega
x23=[contexto+0x58], 0x12e57c carrega x20=[contexto+0xa8], que o chamador
preencheu com 0x98000000. Isso separa os dois contêineres nesse contexto.

O código em 0x12e764–0x12e7c8 recompõe:

- header_size, bytes boot+0x14..+0x17, arredondado para 4096 em x25;
- kernel_size, bytes boot+8..+11, em x26.

Se x23 não é zero, 0x12e7cc chega a:

```text
0x12e880  mov x2, x26           ; kernel_size
0x12e884  add x1, x19, x25      ; fonte = boot + align_up(header_size,4096)
0x12e888  mov x0, x23           ; destino = 0x80080000 + deslocamento
0x12e88c  bl  0x1af3c0          ; rotina de cópia confirmada por loads/stores
```

A rotina de cópia não aplica relocations ELF; move bytes. O trecho analisado
não escolhe x23 pelo `vendor_boot.kernel_addr` 0x80008000. Isso explica por
que esse campo do arquivo não prova o PC final. Os caminhos seguem para
outras rotinas, incluindo chamadas em 0x151b10; verificação/transformações e
todos os ramos de erro não foram reconstruídos integralmente nesta etapa.

## Ligação com o salto final

O mesmo deslocamento 0x4a0048 é lido em 0xfbe08. O BLR em 0xfbe14 usa
0x80080000 + esse valor. Assim, existe agora uma cadeia estática rastreada:
produtor do deslocamento → destino no contexto → cópia dos bytes kernel →
destino do salto. Isso fortalece a evidência do endereço neste caminho, mas
não confirma estado de EL/cache, reservas ou permissões de execução no aparelho.

O boot.img stock declara kernel_size 29.469.184 bytes. O campo image_size do
Image ARM64 é 0x2067000 e inclui memória além desses bytes. A cópia usa
kernel_size do contêiner; não foi encontrada neste trecho uma limpeza geral
desse restante. Não confundir tamanho carregado com toda a memória exigida
pelo kernel/payload, nem usar a diferença como RAM livre.

## Consequências e teste do diagnóstico

O diagnóstico independente contém seu registro na própria Image e usa
endereçamento relativo. Seu teste QEMU agora aceita:

```bash
python3 scripts/test_entry_diag.py --all-offsets
```

Executado: **128/128 PASS**, EL1/EL2 × 64 deslocamentos de 0 a 0x1f8000 em
passos de 0x8000. Cada execução confere argumentos, estado, registro, código,
pilha não utilizada e sentinelas. O teste padrão de três offsets permanece
como opção rápida. A injeção da cópia e do PC deslocado é feita por GDB na RAM
QEMU; não emula o contêiner Android, validação Samsung ou a execução do LK.
A regra genérica de posicionamento ARM64 e suas diferenças para esses offsets
continuam descritas em [entry-diagnostic.md](entry-diagnostic.md).

O R10 de produção permanece com link e contrato próprios; este teste não
valida sua relocação nem autoriza carregá-lo no telefone. As coletas Shizuku
encerraram-se como indisponíveis para FDT e logs; não pedir repetição. Ainda
faltam um caminho de carregamento verificável e um canal de observação real.
Nenhum novo arquivo é necessário para seguir a análise estática.

## Reproduzir a evidência

`inspect_sboot_hzc2.py` agora inclui `kernel_copy_chain`: palavras do setup,
destinos BL de dispatch/cópia e preparação dos argumentos. Usa hash exato e
não depende de Capstone. Para desassemblar, usar o snippet de
[bootloader-hzc2.md](bootloader-hzc2.md) nos intervalos 0xfb9c8:0xfba38,
0xfbb98:0xfbbb8, 0x12e048:0x12e094, 0x12e298:0x12e424,
0x12e540:0x12e590, 0x12e764:0x12e894 e 0x1af3c0:0x1af488.
