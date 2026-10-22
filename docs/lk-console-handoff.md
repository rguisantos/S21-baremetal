# LK HZC2: console e trecho final de handoff

Análise estática de 2026-10-21 do sboot de 4 MiB, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets abaixo são **do arquivo**, não endereços físicos. Instruções decodificadas
com Capstone 5.0.7; ponteiros lidos diretamente como u64 little-endian.
Nenhum firmware foi executado ou alterado.

## Depois da preparação de cache

| Offset | Operação observada |
|---|---|
| 0xfbdd4 | `msr daifset, #2`: mascara IRQ; sozinho não comprova todos os bits DAIF |
| 0xfbdd8 | chamada 0xee658, que passa 30 para 0x101228 |
| 0xfbddc | chamada 0x18a3a8: preparação condicional de cache/MMU já documentada |
| 0xfbde4 | chamada 0xf29a0, com w0=w21 |
| 0xfbdf0 | chamada 0x1b1658, argumento `Starting kernel...` em 0x2169d8 |
| 0xfbe14 | `blr x4`, destino nominal mais deslocamento KASLR |

0xf29a0 compara seu argumento com 5. Os dois ramos imprimem mensagens
`UPLOAD_MODE_VALUE ... Set S2D LOW, DUMP_DIS` ou `... S2D MID, DUMP_EN`,
passam respectivamente 0/1 a 0xff5f0 e escrevem MMIO. 0xff5f0 zera
0x15868500 ou 0x1586c500 conforme o argumento. O ramo LOW também grava
0x0db90000 em 0xf0000180. Não se atribui significado aos registradores
além das mensagens associadas; não reproduzir essas escritas no payload.

A rotina 0x18a3a8 só chama a limpeza e a desativação quando SCTLR.M está
ligado. 0x189db8 limpa M e C no SCTLR correspondente ao CurrentEL e executa
ISB. Se M já estiver desligado, essa rotina não garante C desligado.
Há chamadas posteriores e callbacks; portanto não se declara o estado
final de cache ou EL comprovado. O diagnóstico independente continua necessário.

Continuação em 2026-10-22: o [helper de cache e os argumentos finais](lk-cache-handoff.md)
foram conferidos em 352 cenários com as instruções originais e acessos de
sistema substituídos. A atuação fica no EL atual, M=0/C=1 é preservado e
não há invalidação explícita de I-cache no helper selecionado. Os callbacks
descritos abaixo continuam como fronteira da prova do estado final.

## Caminho da mensagem final até o transmissor

O caminho estático encontrado é:

1. 0x1b1658 prepara a formatação, callback 0x1b14e0 e contexto em 0x31fff0.
2. 0x1b14e0 lê o objeto do contexto e chama 0x20c618.
3. 0x20c618 lê `objeto+8`, depois o primeiro ponteiro da tabela, e faz `br x3`.
4. A tabela inicial aponta para 0x20c478. Essa função percorre uma lista de
   callbacks de saída e, se o global relativo 0xd08a20 for zero, envia bytes
   por 0xef098 → 0xef4c0.

A resolução dos ponteiros pressupõe a base LK corroborada anteriormente,
com delta runtime/arquivo **0xe7f14000**:

| Local no arquivo | Valor inicial | Resolvido para arquivo |
|---|---|---|
| 0x31fff0 | 0xe82358b0 | objeto 0x3218b0 |
| 0x3218b8 | 0xe81a46f8 | tabela 0x2906f8 |
| 0x2906f8 | 0xe8120478 | função 0x20c478 |

Esses são valores iniciais do binário: não se excluem alterações em execução.
A lista e o flag de saída também dependem do estado de boot.

## Nova pista: base 0x10540000

0xef4c0 lê a base de um global relativo **0x4740c0**, consulta `base+0x10`
até o bit 1 estar ativo e grava o byte convertido em uma **escrita de 32 bits**
em `base+0x20`. Para LF, transmite depois CR. Não possui timeout nessa rotina.

A rotina 0xef3e0 fornece um escritor concreto desse global:

- 0xef3f4: `mov w6, #0x10540000`;
- 0xef420: `str w6, [x4, #0xc0]`, com x4 apontando para 0x474000;
- manipula 0x105400c4 e configura registros no bloco 0x10540000;
- é chamada em 0xee674 no caminho de inicialização observado.

**Conclusão limitada:** existe um caminho de console LK que seleciona
**0x10540000**, diferente da UART1 **0x10840000** identificada no DTB.
Isso enfraquece a suposição de que UART1 seja necessariamente o console do
bootloader. Não identifica pinos, conector, clock efetivo, baud rate, ativação
do caminho no aparelho nem prova que a UART permaneça acessível no handoff.
O formato das operações é compatível com um transmissor Samsung, mas não
foi atribuída identidade definitiva à instância por fonte de hardware.

Não alterar a base UART do R10 a partir desta pista. Não copiar a sequência
MMIO nem o acesso de 32 bits como driver validado. A próxima investigação é
cruzar 0x10540000 com o DTS/driver Samsung e rastrear os escritores de
0x4740c0, o flag 0xd08a20 e o registro dos callbacks.

## Reprodução

```bash
python3 scripts/inspect_sboot_hzc2.py /caminho/sboot.bin
```

O relatório agora inclui destinos das chamadas posteriores à preparação,
ponteiros da cadeia de console e palavras de instrução nos offsets relevantes.
Ele exige o hash exato; não precisa de Capstone. Para desassemblar, use o
snippet de [bootloader-hzc2.md](bootloader-hzc2.md) nos intervalos:
`0xfbda0:0xfbe18`, `0xf29a0:0xf2a90`, `0x1b1658:0x1b1780`,
`0x1b14e0:0x1b1504`, `0x20c618:0x20c630`, `0x20c478:0x20c540`,
`0xef3e0:0xef4f4`.

Não há novo arquivo solicitado. O recorte `samsung_kernel/` não contém o
driver serial completo; não confundir sua ausência nesse recorte com ausência
no pacote de fontes recebido. Nenhuma alegação de teste físico foi adicionada.

## Cruzamento com as fontes Samsung — 2026-10-21

Recuperado o `Kernel.tar.gz` já enviado, 209261574 bytes, SHA-256
`c5ad9994240e67ebdc40878c191be040bf30db398bc8513ea1f156eaebd86bf2`.
A identidade do pacote é a mesma da análise anterior. Não foi compilado.

`arch/arm64/boot/dts/exynos/exynos2100.dts` identifica explicitamente:

| Campo | UART0 | UART1 |
|---|---|---|
| Alias | `/uart@10540000` | `/uart@10840000` |
| Região | 0x10540000 / 0x100 | 0x10840000 / 0x100 |
| Compatible | samsung,exynos-uart | samsung,exynos-uart |
| USI serial v2 | presente | presente |
| FIFO | 256 bytes | 256 bytes |
| Interrupt tuple | SPI 508, level high | SPI 533, level high |
| INTID GIC | 540 | 565 |
| Canal debug | `samsung,dbg-uart-ch` presente | ausente no nó consultado |
| Configuração debug | 115200 baud, 8 bits | sem essas propriedades |
| Status da fonte | disabled | disabled |

O `pinctrl-0` da UART0 resolve para `uart0-bus`, phandle 0xb3: sinais
**gpg0-2 e gpg0-3**, função 3, `samsung,pin-pud=3`. Isso nomeia pads do SoC;
não atribui TX/RX individualmente nem identifica test points, USB ou conector.
O syscon USI, phandle 0x4d, é 0x10421000, offset 0. Os clocks são
`gate_uart_clk0` e `ipclk_uart0`, IDs 0x6da/0x6f6 no provider 0x0d.
IDs e phandles são locais desta árvore, não endereços ou frequências.

Assim, a identidade da instância passa de hipótese a **UART0 na fonte**;
sua utilização efetiva no aparelho continua dependente de estado/overlays e LK.
O campo 115200 é configuração declarada, não medição do baud no handoff.

No driver `exynos_tty.c`, `samsung,dbg-uart-ch` evita o pulso inicial de reset
em `exynos_usi_init()`, mas ainda limpa USI_CON e solicita clock via USI_OPTION.
O driver lê `dbg-uart-baud`/`dbg-word-len` com defaults 115200/8. O cabeçalho
`serial_s3c.h` confirma UTXH=0x20, UTRSTAT=0x10, TXFE=bit 1,
USI_CON=0xc4 e USI_OPTION=0xc8. Isso corrobora o polling do LK. O kernel usa
escrita byte em UTXH, enquanto o trecho LK observado usa word; não presumir
que copiar a largura/sequence do LK forma um driver completo.

### Seleção e bloqueio da saída no LK

- 0x20c608 grava w0 no flag relativo 0xd08a20.
- Em 0xedb98 chama-se 0x18b560; se retorna zero, 0xedba0 prepara w0=1 e
  0xedba4 chama 0x20c608. Portanto há um caminho concreto que **suprime o
  fallback serial**, preservando a passagem pelos callbacks da lista.
- A decisão usa estado do global 0xd05f7c e outras chamadas; não foi resolvido
  seu valor no aparelho nem atribuída semântica de política de segurança.
- 0x20c578 registra um elemento na lista de saída relativa 0x3218c0,
  preservando o estado IRQ. 0xff948 chama essa rotina com objeto 0x2ef138.
- O callback inicial desse objeto é 0xe80136c8, equivalente a offset
  0xff6c8 usando o delta LK anterior. Ele usa MMIO e faixas associadas a
  0xf0000000; não foi provado como transporte USB, UART ou console persistente.

A busca foi por chamadas diretas BL no intervalo LK 0xec000–0x20c630;
não exclui chamadas indiretas, aliases de endereço ou outros escritores.
Não se conclui que ativar UART0 baste para obter o log final.

### Reproduzir o cruzamento

```bash
python3 scripts/inspect_uart_reference.py /caminho/Kernel.tar.gz
```

O novo inspetor exige hash do pacote e dos três arquivos, lê o TAR sem
extraí-lo e emite trechos com linhas e hashes. A estrutura dos nós é consultada
por marcadores exatos dessa fonte; não é parser DTS genérico.

Hashes dos arquivos consultados:

| Arquivo | SHA-256 |
|---|---|
| exynos2100.dts | `586ca56987bbaacce0a38ddaee8a852721caaaeb9096ada6bfde8bc8c0d88ca8` |
| exynos_tty.c | `f8e0f52ca9cd2a29e65096749f3498eeef19856fd250c3a272bcf0fb6182b267` |
| serial_s3c.h | `e5c60b29c65ba77a469aa562a5fc4c5b6d64d0abbf48c295967885f6ebdc1aaa` |

O próximo bloqueio é físico e de estado: roteamento dos pads, habilitação real
do console e recuperação do diagnóstico. O material atual permite continuar
a análise estática sem solicitar arquivos novamente.

## Auditoria posterior do pinmux

O acesso do LK a 0x10430080 foi confirmado, mas diverge do GPG0_CON
0x10430120 derivado do driver/DTS. O cálculo do núcleo pinctrl não remapeia
os offsets. Há semelhança com o layout Exynos 9820, sem prova de origem ou
efeito físico. [Análise e decisão](exynos-2100-reference.md#auditoria-do-pinmux--continuação-2026-10-21).
