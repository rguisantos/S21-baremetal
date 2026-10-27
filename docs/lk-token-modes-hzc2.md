# HZC2: escritor dos bits de modo do token

Análise estática de 2026-10-27, base `4546b24` após PR #40.
O comando 21 chega a `0x13a998`, que acumula identificadores de modo no
bitmap do workspace. Isso estende a [cadeia de publicação](lk-policy-bitmap-hzc2.md),
sem revelar token ativo, autenticação da Image ou aceitação de uma Image alterada.

## Reprodução e escopo

Firmware sboot HZC2, 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets do arquivo. Nenhuma instrução Samsung foi executada.

```sh
python3 scripts/inspect_lk_token_modes.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p test_lk_payload_return.py
python3 -m unittest discover -s scripts -p test_lk_final_edges.py
```

O [relatório](references/lk-token-modes-hzc2.json) confere 335 palavras GNU e
72 destinos relativos com decoder independente; inclui dez grafos locais,
seis strings e duas tabelas de 35 entradas. Os grafos mantêm chamadas opacas
e BR como fronteiras; a decodificação separada das tabelas não é execução
nem prova de alcançabilidade global. [Validação](references/lk-token-modes-validation-20261027.json).

## Ligação do comando

Após verificações e retorno zero de helper opaco, `0x142330/0x142334`
copia request+8 para workspace+0. O produtor prepara request+8=21.
As duas tabelas do dispatcher usam entrada signed-u16, destino igual à
âncora mais quatro vezes a entrada; os guards limitam comando−1 a 0..34.

| Tabela | Slot do comando 21 | Entrada | Âncora | Destino |
|---|---|---|---|---|
| 0x2384f8 | 0x238520 | 54 | 0x1323c0 | 0x132498, log EM_CMD_GET_MODES_BIT |
| 0x238540 | 0x238568 | 148 | 0x132750 | 0x1329a0, chamada de 0x13a998 |

O retorno do handler é preservado em W20 e testado em 0x13275c.
Os helpers anteriores ao despacho continuam opacos.

## Lista e operação sobre o bitmap

A string identifica o handler como `em_token_get_mode_information_for_bit`.
Ele aloca um objeto de 0x4cdc0 bytes e chama o parser 0x136eb0 com entrada
workspace+0x50e e objeto de saída. Preparação, helper 0x138740 e comparações
precedem o escritor: não se atribui a essas chamadas uma prova criptográfica.

O escritor lê count=u16(parsed+0x5ca8), exige count≤128 e percorre count
identificadores u16 a partir de parsed+0x5caa. Cada identificador deve ser≤255.
Para cada ID válido, as instruções 0x13ab0c..0x13ab2c realizam:

```text
word = id >> 6
bit = id & 63
u64(workspace + 0x29f68 + 8*word) |= 1 << bit
```

São quatro palavras de 64 bits. O corpo observado não limpa esse destino:
OR conserva bits anteriores e IDs repetidos são idempotentes. A inicialização
real e efeitos transitivos dos helpers permanecem desconhecidos.
Após completar a lista, inclusive count=0, 0x13ab60/0x13ab64 marca o bit 5
de workspace+16. Uma lista vazia não demonstra bitmap vazio.

## Erros e publicação

Count>128 retorna 0xf03c0012 antes das escritas OR locais. ID>255 retorna
0xf03c0013; se ocorrer depois de IDs válidos, as escritas locais anteriores
já aconteceram. Não há rollback local dessas escritas no caminho de erro;
não se presume ausência de efeitos de chamadas opacas nem limpeza de um
bit 5 preexistente.

Isso não demonstra publicação parcial em B=0xcd6618: o retorno não zero
do dispatcher desvia em 0x157378 antes da resposta e da cópia para B.
No caminho nominal, a cadeia já delimitada é workspace+0x29f68 →
response+0x120 → B. Conteúdo ativo, outros escritores e aliases são desconhecidos.

A próxima fronteira é a semântica do parser 0x136eb0 e do helper 0x138740,
separada da validação da Image. Não há receita de token ou bypass demonstrado.
