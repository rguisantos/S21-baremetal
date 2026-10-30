# HZC2: escrita DMC por descritor e duas origens da base h/g2

Continuação estática sobre `60f291a`, sem execução Samsung/QEMU.
Mesmo sboot de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; endereços core são locais ao ACPM.
A [auditoria 8/9](newtime-dmc-method12-hzc2.md) deixou máscaras e base vivas
em aberto. Agora há uma rotina concreta de escrita por descritor e uma
origem adicional para o cache. Não se demonstrou o valor físico dessas raízes.

## Caminho até a store

No método +0 DMC (`0x5ff14`), sob o gate vivo
`M32[core0x37d3c]==0`, o pacote é `M32[r0slot]` e o comando usa low16 de
sua primeira palavra. A entrada **20** da tabela core0x37cd0 contém
`0x32539` → handler `0x5fd38`; o método passa R0=0 e R1=packet.
O recebimento do pacote, a permissão do caller e a satisfação desse gate
continuam condições, não observações no aparelho.

| Campo do pacote | Uso no handler |
|---|---|
| byte7 | índice do descritor |
| byte6 | coluna |
| byte5 | linha |
| byte4 | modo |
| u32 em +8 | valor gravado |
| u32 em +12 | recebe retorno do helper |

`0x5fd6a` chama `0x60148`, que transporta o quinto argumento pela pilha e
chama `M32[core0x38038+104]`. O ponteiro inicial `0x37469` seleciona
`0x64c68`. A chamada seguinte `0x5fd74→0x5f8dc` permanece opaca nesta entrega.
O método +12 compartilha a tabela, mas os pedidos DVFS 8/9 já rastreados
não usam o comando20. Não foi demonstrado controle externo desse comando.

## Fórmula e condições de alias

Com aritmética u32:

```
D = 0x3a7a0 + 16*indice
B = 0x3a600 + M32[D+4]           # capturado antes do laço
A = B + 4*(M32[D+8]*linha + coluna)
M32[A] = quinto_argumento       # store 0x64c94
```

O modo1 substitui a linha por0 e o limite por12, inclusive. Outros modos
começam na linha recebida e usam a mesma linha como limite. A comparação
é signed, e o incremento é u32; o caminho pelo pacote fornece linha u8.
O helper isolado aceita registradores completos: o caso 0x7fffffff pode
não encerrar pelo wrap signed. Isso não demonstra alcance pelo pacote.

O stride `M32[D+8]` e o valor na pilha são recarregados a cada iteração.
Uma store que os alcance pode alterar iterações seguintes. A base B é
capturada uma vez. Os testes incluem alias ao próprio stride e alteração
do offset após a captura, além de índices/arithmetic wrap.

Para alcançar as células de interesse, a condição necessária da fórmula é:

| Destino core | Condição sobre o deslocamento calculado |
|---|---|
| 0x3a660 | `u32(offset+4*(stride*linha+coluna))==0x60` |
| 0x3a664 | igual a0x64 |
| 0x3a668 | igual a0x68 |

Fixtures explícitas satisfazem essas equações nas palavras reais. Elas
provam o comportamento condicional da rotina. **O descritor vivo que
produziria esse alias não foi identificado.** Não há exclusão de outros
escritores ou efeitos de chamadas opacas, nem prova de exploit/entrada física.

## Base compartilhada de h e g2

O cache é core `0x38404` (`0x381c8+0x23c`):

- `0x648be`, no carregador `0x647ac`, instala
  `u32(0x3a600+M32[core0x3a884])`. É o offset do descritor de índice14.
- h (`0x64658`) e g2 (`0x6467c`) consultam esse mesmo cache. Somente quando
  ele está zerado copiam `M32[core0x3a664]` para ali.
- h lê `M32[cache+8*(input+18)+4]`; g2 usa input+31. Toda a aritmética é
  u32. Um cache não zero instalado pelo carregador dispensa o fallback.

Logo, a base usada por 8/9 não depende sempre de ler0x3a664. Ordem de
execução, preservação do cache e conteúdo da região0x3a600/0x3a7a0 seguem
abertos. Essa região está além da segunda cópia presente no arquivo.
A [continuação BL2](newtime-dmc-bl2-producer-hzc2.md) identifica o produtor
nominal do diretório e das palavras0x3a660/64/68 sob alias. Ordem/preservação
física e recebimento do comando20 continuam abertos. Slot47/X0 permanece aberto.

## Reprodução e validação

```sh
python3 scripts/inspect_newtime_dmc_config_hzc2.py /caminho/sboot.bin --json /tmp/dmc-config.json
python3 -m unittest discover -s scripts -p 'test_newtime_dmc_config.py'
```

[Extrator](../scripts/inspect_newtime_dmc_config_hzc2.py),
[16 testes](../scripts/test_newtime_dmc_config.py) e
[JSON](references/newtime-dmc-config-hzc2.json). Hash/tamanho conferidos
antes do GNU. São440 instruções/458 halfwords,22 alvos relativos,
37 literais distintos e48 operandos selecionados. JSON reproduzido
exatamente; imagens curta/longa/alterada recusadas com exit2 sem saída.

Os testes decodificam palavras Thumb e cobrem o handler/wrapper/helper,
o gate do método0,13 linhas inclusivas,80 entradas aleatórias,alias de
stride,cache compartilhado e memória ausente. O avaliador ganhou MULS
com resultado u32 e flags N/Z; C/V preservados. Hooks substituem callees
opacos. A suíte NEWTIME completa desta árvore passou com560 testes.
