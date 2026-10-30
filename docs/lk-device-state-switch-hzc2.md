# HZC2: transição de estado e pedido de apagamento ao recovery

Análise estática em 30/10/2026. Firmware de 4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Endereços abaixo são offsets no arquivo. Nenhuma rotina foi executada no
telefone ou em emulador nesta análise.

**Conclusão:** o caminho de confirmação em `0x151c00` prepara uma mensagem
com `--wipe_data` e `--reason=bootloader_unlock`, solicita uma escrita por
um wrapper de armazenamento e depois chama o setter de estado. Isso torna
inadequado tratar a transição como uma consulta sem efeito sobre dados.
Não comprova que o backend aceite a escrita, que a mudança persista ou que
o recovery tenha apagado o aparelho. Não é um procedimento físico de desbloqueio.

## Testemunhas e fluxo delimitado

O [relatório GNU](references/lk-device-state-switch-hzc2.json) conserva
238 palavras, 62 alvos relativos e 18 palavras selecionadas conferidas
diretamente contra o binário. Inclui o chamador, o handler, o getter,
o copiador de string e o wrapper `blk_bwrite`. Chamadas externas permanecem
opacas; continuidade pressupõe retorno normal e preservação do estado da ABI.

| Offset | Observação |
|---|---|
| `0x12f42c` | Chamada direta de `0x151c00`; este recorte não estabelece o caminho físico até o chamador |
| `0x151c04..20` | Passa `MISC`, literal em `0x216960`, ao lookup `0x14a1b0`; descritor nulo retorna localmente |
| `0x151c30..40` | Getter `0x10b8f8` preenche o estado; após retorno zero, calcula `W21 = estado_u32 XOR 1` |
| `0x151c58..6c` | Resultado 1 do helper `0x101728` seleciona confirmação; 16 seleciona cancelamento; outros repetem o poll |
| `0x151c84..90` | Copia a string completa de `0x23fff8` para `frame+0x80`, usando `0x1b2570` |
| `0x151cc0..d4` | Passa `frame+0x40`, argumentos do descritor e `W3=0x440` ao wrapper `0x11b350` |
| `0x151cd8..fc` | Não testa o retorno dessa chamada antes de outros helpers e do setter `0x10b930(estado XOR 1)` |
| `0x151dc0..e0` | Ramo local de cancelamento chama `0x146ba0` com `Cancel_to_switch_device_state` e retorna |

Os códigos 1/16 não foram convertidos em nomes de teclas. O toggle recebe
um u32 sem validação booleana local; não generalizar XOR 1 para qualquer
valor como um contrato de desbloqueio. O handler contém mensagens de lock
e unlock; o pedido de recovery está no caminho compartilhado de confirmação.

A literal em `0x23fff8` tem **64 bytes incluindo NUL**, com quatro linhas
separadas por LF, não quatro strings independentes:

```text
recovery
--wipe_data
--reason=bootloader_unlock
--locale=en_US
```

O copiador `0x1b2570` lê e grava byte a byte até incluir o NUL. A string ocupa
o deslocamento 64 dentro do buffer passado ao armazenamento. Os demais
bytes do buffer de `0x440` não foram demonstrados inicializados neste recorte;
não reconstruir uma imagem completa de MISC a partir dessa literal.

O wrapper `0x11b350` conserva os argumentos, obtém um descritor por
`0x11b060` e faz `BR` pelo método `+176`. Seu ramo de tamanho zero usa a
literal `blk_bwrite`. No chamador, X1 é formado dos bytes 28..31 do descritor
MISC e X2 dos bytes 20..23; suas unidades não foram promovidas a bytes,
setores ou LUNs certificados. Binding e conclusão físicos continuam abertos.

O nome MISC coincide com Identifier 20 na PIT recebida e com o link Android
`misc -> /dev/block/sda20`. Isso corrobora a nomenclatura, sem demonstrar o
conteúdo do descritor vivo usado pelo handler ou autorizar uma escrita nesse nó.

O getter possui um caminho de erro e outro que lê um cache para o ponteiro
recebido. Isso não identifica o provedor persistente. O setter e os serviços
posteriores também não foram executados ou tratados como prova de sucesso.

## Reprodução e consequência para o projeto

Após conferir o SHA-256, um objdump AArch64 pode reproduzir o handler:

```bash
aarch64-linux-gnu-objdump -D -z -b binary -m aarch64 \
  --start-address=0x151c00 --stop-address=0x151ee4 sboot.bin
```

Os demais intervalos e as palavras estão no JSON. A literal completa pode
ser conferida lendo 64 bytes a partir de `0x23fff8`. Encontrar o texto não
foi usado sozinho como prova de consumo: ADRP/ADD, chamada ao copiador e
argumentos ao wrapper foram conferidos nas instruções.

A [consulta Download/PIT](download-pit-observation-hzc2.md) e os links
Android identificaram destinos de armazenamento, mas os atributos de
geometria foram negados ao shell. Esse resultado não justifica executar
esta rotina para obter dados. Mudança de estado/desbloqueio exige um plano
separado de preservação dos dados, recuperação e consentimento explícito
antes de qualquer confirmação destrutiva. Este relatório não fornece
comandos para essa transição e não resolve a carga da Image própria.
