# Construtor LK de bancos RAM: argumentos conferidos

Análise de **2026-10-22 (Campo Grande)** do sboot HZC2 recebido. O trecho
`0xfad60` foi seguido até as chamadas ao escritor `0xf1570`, incluindo os
blocos fora de ordem em `0xfb670–0xfb7cc`. A sequência de argumentos foi
conferida com as instruções originais em Unicorn **2.1.4**, em **268 cenários
fornecidos**. Não foram executados serviços seguros ou editores de FDT.

O resultado fecha a aritmética desses ramos. As entradas efetivas do aparelho
continuam desconhecidas: isso não produz o FDT final ou autoriza RAM livre.
Complementa [ajustes dinâmicos](lk-dynamic-fdt.md), [intervalo Harx](lk-harx-memory-gap.md)
e [SEC_PGTBL](sec-pgtbl-hzc2.md).

## Entradas e paradas antes dos bancos

Todos os offsets são de arquivo, sem atribuir uma base física ao sboot.

| Entrada | Chamada/uso no LK | Tratamento observado |
|---|---|---|
| Total de RAM | `0xfad84 → 0x11b758` | X0 passa a X25; getter lê/cacheia `0x02038848`, com possível limite de configuração; valor real desconhecido |
| Versão soc_info | SMC legado `-0x12e`, índice 0 | W0 deve ser `0x66001000`; senão estaciona em `0xfadc4` |
| Base soc_info | Mesmo serviço, índice 2 | X0 igual a `0xffffffffffffffff` estaciona em `0xfb66c` |
| Quantidade soc_info | Mesmo serviço, índice 1 | W0 igual a `0xffffffff` estaciona em `0xfb65c`; metade alta ignorada na soma |
| Base/tamanho SEC_PGTBL | `0x82002060`, índices 1/2 | Tratamento anterior preservado, inclusive ausência de teste do alinhamento do tamanho |
| Status/base/tamanho Harx | `0xfaee8 → 0xf9320` | Erro zera os buffers; divisão exige sucesso e os dois valores não zero |

O cursor inicial é `base_soc + zero_extend(quantidade_soc[31:0])`, com soma
de 64 bits. Os nomes das mensagens LK não demonstram equivalência entre esse
serviço legado e a interface positiva `0x8200012e` usada pelo Harx. Nenhum
valor foi deduzido da capacidade comercial de 12 GiB ou de um heap no DTS.

Continuação de 2026-10-24: o [produtor BL2 do total](bl2-ram-size-hzc2.md)
foi ligado à escrita em `0x02038848`. Uma folha candidata soma quatro
palavras de geometria e passou 66 execuções isoladas QEMU. A resolução dos
callbacks, as palavras reais e o valor efetivamente consumido pelo LK
continuam abertos; isso não substitui as nove entradas do modelo abaixo.

## Ordem das solicitações ao escritor

`u32` abaixo significa conservar os 32 bits baixos; somas de ponteiros em X
também podem dar wrap de 64 bits. São operações reproduzidas, não validações
de ordem, ausência de sobreposição ou disponibilidade de memória.

| Ordem/ramo | Base passada em X0 | Tamanho passado em W1 | Chamada |
|---|---|---|---|
| Primeiro intervalo | `0x80000000` | `u32(base_soc - 0x80000000)` | `0xfaf34` |
| Antes de Harx, se ambos os buffers não zero | cursor | `u32(base_Harx - cursor)` | `0xfaf50` |
| Antes de SEC_PGTBL, se W22 não zero | cursor após Harx | `u32(base_PGTBL - cursor)` | `0xfb678` |
| Cauda, total ≤ `0x7fffffff` | fim_PGTBL se divisão, senão cursor | `u32(total + 0x80000000 - base_cauda)` | `0xfb740` / `0xfb7c8` |
| Cauda, total ≥ `0x80000000` | mesma seleção | `u32(-base_cauda)` | `0xfb690` / `0xfaf74` |
| Bancos altos, total > `0x80000000` | `0x880000000 + i × 0x20000000` | sempre `0x20000000` | `0xfb7a8` |

Depois do intervalo anterior ao Harx, o cursor muda para `base_Harx +
tamanho_Harx`. Depois do prefixo SEC_PGTBL, a cauda começa no fim normalizado
da tabela. Isso omite esses intervalos da sequência solicitada como RAM,
sem criar por esse trecho novas entradas de `/reserved-memory`.

O laço alto subtrai 2 GiB do total e compara o incremento de **512 MiB**
depois de cada chamada. O número de chamadas é o teto dessa divisão; o último
bloco não é reduzido ao restante. Um cenário artificial de 2 GiB + 1 byte
pede um bloco alto inteiro e excede esse restante em `0x1fffffff` bytes.
Com 12 GiB explicitamente fornecidos, pede 20 blocos altos. Nenhum desses
cenários revela o valor real do getter ou demonstra defeito no mapa do telefone.

O escritor `0xf1570` formata `memory@%lx`, `/memory@%lx` e
`<0x%x 0x%x 0x%x>`; usa base alta/baixa de 32 bits e tamanho de 32 bits,
e tenta escrever `reg` e `device_type=memory`. O modelo registra os bytes
big-endian que essa tupla representa. Sucesso do editor, nomes repetidos,
bancos existentes, reservas e transformações posteriores não foram simulados.

## Ferramentas e reprodução

`check_lk_memory_banks.py` exige o sboot bruto de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Sem cenário, emite somente palavras, chamadas e strings conferidas. Não tem
valores padrão para respostas seguras ou quantidade de RAM.

```bash
python3 scripts/check_lk_memory_banks.py /caminho/sboot.bin
python3 scripts/check_lk_memory_banks.py /caminho/sboot.bin --scenario /caminho/cenario.json
python3 scripts/emulate_lk_memory_banks.py /caminho/sboot.bin --scenario /caminho/cenario.json
python3 scripts/emulate_lk_memory_banks.py /caminho/sboot.bin --self-check
python3 -m unittest discover -s scripts -p 'test_lk*.py' -v
```

O emulador requer a dependência opcional `unicorn==2.1.4`. Um cenário JSON
deve declarar todas as nove entradas abaixo; estes valores são **exemplo
artificial**, não respostas lidas do S21:

```json
{
  "total_ram_bytes": "0x80000001",
  "soc_version_x0": "0x66001000",
  "soc_base_x0": "0xa0000000",
  "soc_reserved_size_x0": "0x200000",
  "pgtbl_base_x0": "0x0",
  "pgtbl_size_x0": "0x0",
  "harx_status_w0": "0x1",
  "harx_base": "0x0",
  "harx_size": "0x0"
}
```

Inteiros são sem sinal; respostas X têm até 64 bits e `harx_status_w0`, 32.
O leitor limita o JSON a 8192 bytes e recusa campos ausentes/extras,
duplicidades, tipos incorretos e aninhamento excessivo. A ferramenta limita
a saída a **128 chamadas**; isso é um limite de host, ausente no laço LK.
Tamanhos zero, subtrações com wrap e fim que excede 64 bits são registrados
como argumentos, sem transformá-los em intervalos de memória validados.

## Escopo da execução no Unicorn

O harness mapeia três páginas RX do sboot e uma pilha RW de 128 KiB. Executa
a seção inicial, intercepta a instrução SMC e substitui o getter/Harx/printf;
depois salta de **0xfaef4 para 0xfaf28** e segue os ramos de bancos até
**0xfaf84**. Não executa preparação/merge FDT, leitura do flag em `0x15860810`
ou o caminho de edição de bootargs para `0xfd`, que retorna ao mesmo bloco
de bancos. Essas partes continuam fora desta conferência.

As chamadas `0xf1570` são capturadas antes da execução. Registradores voláteis
são envenenados nas substituições; assume-se preservação de X19–X29, como
esperado pelo chamador. Há limite de 4096 visitas/1 segundo por cenário,
guardas de PC e argumentos de SMC. Nenhum MMIO físico ou FDT é mapeado.

**268/268 cenários coincidiram**: 192 combinações, 12 casos de borda e 64
casos determinísticos de seed `0xfad60`. Foram 263 saídas da fase de bancos,
duas paradas de versão, uma de base e duas de quantidade soc_info. O máximo
foi 877 visitas e 128 chamadas em um cenário. Os **44 testes de host LK**
passaram, incluindo 17 novos casos de bancos/parser/identidade.

[Evidência estática e exemplo](references/lk-memory-banks-hzc2.json) e
[relatório Unicorn](references/lk-memory-banks-unicorn-hzc2.json) ficam no Git;
os blobs e dependências ficaram fora dele. R8/R9/R10 não mudaram e suas
suítes não foram reexecutadas. Os próximos dados necessários para fechar o
mapa são os valores/condições efetivos e o resultado das edições do FDT;
o material recebido continua suficiente para investigação estática.
