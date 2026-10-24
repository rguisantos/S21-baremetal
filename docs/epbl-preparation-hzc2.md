# HZC2: preparação EPBL e dispatcher SMC parcial

Auditoria estática de **2026-10-23 (Campo Grande)**, após a
[busca do estado anterior do descritor BL2](descriptor-provenance-hzc2.md).
sboot original: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Offsets de código são no arquivo. Valores de ponteiros são nominais; a
tradução para offsets de arquivo é uma hipótese explícita abaixo.

**Avanço:** há um dispatcher comum legível, com normalização dos IDs
negativos e duas etapas de seleção indireta. A preparação anterior monta
um pedido in-place dependente de MMIO. A janela da tabela de handlers fica
dentro da região candidata a essa transformação. **Não foi recuperado
plaintext verificado, ligado um handler específico ou executado serviço
seguro.** O inicializador do descritor -0xe6 continua aberto.

## Preparação condicional antes do vetor

O início EPBL contém ADR em `0x3020`, que prepara a continuação `0x3028`,
e B para `0x3128`, cujo corpo é RET. A continuação consulta um flag no
endereço nominal `0x15860990`: se não zero, pula a chamada de preparação;
se zero, prepara a pilha e chama `0x312c` em `0x3044`.

O prefixo `0x312c` copia o marcador de quatro bytes `SUCC` para a pilha.
Compara-o ao estado apontado por uma célula nominal; se já coincidir,
retorna sem repetir o percurso principal. Caso contrário, escreve `STAR`,
prepara buffers e interage com MMIO. A saída normal restaura `SUCC`; o
ramo de falha escreve `FAIL` e contém um laço após a chamada de impressão.
Nem os flags nem o progresso efetivo desses caminhos foram observados.

A instalação do candidato VBAR_EL3 em `0x3064–0x306c` vem depois dessa
preparação condicional. A palavra bruta no candidato de vetor `0xe800`
continuava indefinida no arquivo recebido. Não se pode substituir isso
por uma sequência executável imaginada ou afirmar qual vetor atende BL2.

## Pedido in-place e hipótese de mapeamento

Os produtores ADRP/LDR em `0x37f0/0x3804` e `0x37f4/0x3808` leem as
células `0xfe78` e `0xfea8`. Elas contêm respectivamente `0x02028700`
e `0x02033de0`. O código monta na pilha:

| Campo observado no frame X29 | Valor preparado |
|---|---|
| +0xe0 | `0x02028700`, origem |
| +0xe8, palavra W | `0xb6e0`, extensão |
| +0xf0 | `0x02028700`, destino |
| +0xf8, palavra W | `0xb6e0`, extensão |

Isso demonstra **origem=destino no pedido**, não que a memória já tenha
sido transformada. A chamada `0x3878 → 0x4248 → 0x3ad4` entrega essa
estrutura ao consumidor que lê esses campos e programa registradores.

Um delta nominal candidato de **`0x02024000`** relaciona ponteiros e
bytes do arquivo. A célula `0xfdf8` contém `0x02028540`, coerente com a
string de versão `v1.5(release):Athens-...` em `0x4540`. Sob o mesmo delta:

| Célula | Ponteiro | Offset candidato | Bytes encontrados |
|---|---|---|---|
| `0xfe18` | `0x020286e4` | `0x46e4` | `EBRS` |
| `0xfe30` | `0x020286bc` | `0x46bc` | `EBHS` |

São âncoras consistentes, sem prova de relocação/runtime ou de semântica de
todos os campos desses registros. Não se transfere um endereço EPBL do
Exynos 990 para o HZC2 como premissa.

Com essa hipótese, o pedido cobre **`[0x4700,0xfde0)`**, 46816 bytes.
Não publicamos um binário transformado nem declaramos o algoritmo/chave:
as instruções legíveis, os marcadores e as strings de auto-descriptografia
identificam uma preparação, mas seus resultados dependem do hardware.

## Dependência concreta de MMIO

O prefixo constrói endereços na base **`0x18330000`**. Há leituras de
status em +0x18c/+0x1010, escritas de configuração e leituras em
+0x11c0…+0x11ec que alimentam buffers da operação seguinte. O consumidor
`0x3ad4` também programa campos dessa base. Isso é fluxo observado de
instruções e dados, sem atribuir nomes de registradores de outro SoC.

Dois percursos anteriores à chamada do consumidor têm contador de polling
e limite `0x100000`, com comparação B.LS. Seus ramos de esgotamento preparam
W0=`0x1106` e W0=`0x1107`, respectivamente. São **status internos dessa
preparação**, não retornos demonstrados dos SMC -0xe6, -0x3ff ou -0x500,
nem constantes do enum DRM por coincidência numérica.

Não executamos essas leituras/escritas nem fornecemos respostas de sucesso
a um emulador. Uma emulação que inventasse status, dados ou resultado da
transformação não recuperaria a implementação segura real.

## Dispatcher comum: normalização não é handler resolvido

O prefixo legível em `0x43d8–0x44ac` contém salvamento de contexto,
normalização, classificação e BLR indireto. Há uma ressalva de entrada:
**`0x43d8` testa o bit 30 de W0 e salta ao retorno de recusa em `0x44a4`**.
Os IDs negativos têm esse bit definido. Portanto, entrar por esse endereço
os recusaria antes da normalização. A ligação entre vetores, contexto de
chamada e eventual entrada posterior ainda não foi estabelecida.

No **bloco comum a partir de `0x4424`**, sob a condição de que seja alcançado,
o código compara os 16 bits altos de W0 com `0xffff`. Quando coincidem,
aplica complemento +1 em W e OR com `0x82000000`; os demais IDs ficam iguais.
Isso não é uma função de valor absoluto para qualquer número com sinal.

| W0 fornecido ao modelo comum | W0 normalizado |
|---|---|
| `0xffffff1a` (-0xe6) | `0x820000e6` |
| `0xffffff19` (-0xe7) | `0x820000e7` |
| `0xffffff17` (-0xe9) | `0x820000e9` |
| `0xfffffc01` (-0x3ff) | `0x820003ff` |
| `0xfffffb00` (-0x500) | `0x82000500` |
| `0x82002011` | `0x82002011` |

Todos esses exemplos produzem índice de owner **66 (`0x42`)**: bits 29:24
mais o bit 31 deslocado para a posição 6. O bit 30 não integra esse índice.
Mesmo owner não significa mesma função, semântica ou resultado.

## Duas tabelas e uma fronteira verificável

O dispatcher lê um byte em `0x02034280 + owner`, literal em `0x44c8`.
Sob o delta candidato, owner 66 corresponde ao byte de arquivo `0x102c2`.
Ele é zero no arquivo; **não é classificação medida em execução**.

- Se o byte de classe tem bit 7 definido, há recusa antes de selecionar o alvo.
- Caso contrário, `0x4470` multiplica a classe por 32 e `0x4474` carrega
  o primeiro ponteiro de oito bytes do slot baseado em `0xe410`.
- O salto de chamada indireta está em `0x4494` (BLR X15).

Para classes 0–127, a janela conservadora dos 128 slots de 32 bytes é
**`[0xe410,0xf410)`**. Ela está inteira dentro da região candidata
in-place `[0x4700,0xfde0)`. Seus bytes brutos não fornecem, por si, ponteiros
runtime confiáveis. A classe pode ser inicializada/alterada antes da chamada;
o estado do dispatcher e o contrato de cada slot ainda precisam ser ligados.

Isso fecha a localização do **mecanismo comum parcial**, não o despacho
completo de um SMC BL2 ou do LK. Não foram atribuídos alvos fictícios aos
slots, lido o zero inicial como garantia runtime ou transferidos status de
um serviço para outro.

## Reprodução e verificação

```sh
python3 scripts/inspect_epbl_preparation.py /caminho/sboot.bin
(cd scripts && python3 -m unittest test_epbl_preparation test_descriptor_provenance -v)
```

O inspetor stdlib lê até o limite e recusa tamanho/SHA-256 diferentes.
Modela somente aritmética de IDs/classificação e tradução nominal limitada;
não executa o dispatcher, a rotina de hardware ou os handlers.

**18 testes novos + 16 regressões = 34 PASS.** Cobrem truncamento X/W,
limite do prefixo legado, bit de guarda, formação do owner, stride/bit de
recusa da classe, tradução de intervalo inteiro, ADRP negativo, largura/base
incorretas e firmware inválido. Não são testes de retorno seguro.

GNU objdump 2.44 coincidiu nas **311 palavras de instrução e 46 destinos
relativos** dos dez blocos selecionados. O intervalo candidato à transformação
e os bytes brutos de tabelas não entram como código validado nessa contagem.

- [Pedidos, normalização, âncoras e hashes](references/epbl-preparation-hzc2.json)
- [Linhas GNU e destinos conferidos](references/epbl-preparation-validation.json)
- [Saída dos 34 testes](references/epbl-preparation-host-tests.txt)

Próximo limite: verificar a transformação/preparação e a entrada vetorial,
ou obter uma implementação correspondente verificável, antes de interpretar
as tabelas como funções. Os arquivos atuais bastaram para esta investigação;
não foi necessário reenviá-los. Memória física, coerência, carregamento Samsung
e recuperação do primeiro registro continuam pendentes no [roadmap](roadmap.md).

A [continuação sobre a fronteira do prefixo](epbl-frontier-hzc2.md) confere 1182 instruções e 13 saídas para a região pendente. A segunda escrita de VBAR corrobora o delta nominal, mas contém uma chamada pendente antes dela. A ausência do dispatcher no grafo direto não é prova de ausência de entrada por exceção.
