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
