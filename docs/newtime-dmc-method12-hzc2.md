# HZC2: DMC método +12 e subcomandos 8/9

Auditoria estática de 2026-10-29, sobre `f1524a3` (continuação do PR #51).
Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; ponteiros core pertencem ao ACPM Thumb.
Conversões cobrem as duas cópias documentadas, sem confirmar aliases físicos.

## Resultado e condições

A cadeia nominal do [receptor DVFS](newtime-dvfs-receiver-hzc2.md) chega
à interface DMC e aos handlers 8/9. As raízes devem ter sido instaladas
pelos inicializadores e preservadas durante chamadas intermediárias.
Valores iniciais do arquivo não demonstram o estado vivo.

| Elo | Evidência selecionada |
|---|---|
| Wrappers | `0x581fc`: plugin 9, comando 8, arg2=0; `0x58214`: comando 9, arg2 recebido do caller |
| Relay DVFS | `0x58170` lê desc7 pela célula core `0x2fbf0`, depois API+28 |
| Relay comum | `0x38b04`: contagem unsigned, enabled, método +12 e máscara do caller |
| Registro DMC | Inicializador `0x5f600` publica métodos core `0x37c40` em desc9+12 |
| Método +12 | `0x5f758` lê comando e tabela core `0x37cd0` |
| Handlers | Entrada 8 → `0x5fadc`; entrada 9 → `0x5fbbc` |

O relay testa o ponteiro do método **depois** de desreferenciar a tabela;
não há guard selecionado que torne segura uma tabela de métodos nula.
Contagem/disabled/método nulo retornam 10; máscara recusada retorna -11
somente após os guards anteriores. O shift do caller usa seus oito bits
baixos; um shift efetivo >=32 produz zero. A máscara inicial `0x8b4`
permite o caller 7 sob as condições acima.

O wrapper passa `&packed`, e o relay passa o endereço do slot que guarda
esse ponteiro. O método entrega ao handler `r0=&packed`, `r1=arg2`.
Isso difere da interface DVFS que recebe domínio/valor desreferenciados.
O índice do método é `u32(cmd*4)`: não há bounds check local. Uma palavra
fora das 20 posições exportadas é **desconhecida**, não necessariamente
nula; um comando grande pode reencontrar uma posição pelo wrap.
Não se demonstra entrada externa capaz de controlar esses comandos.

## Efeitos e retornos

- `0x59572` chama o comando 8; `0x59578` sobrescreve R0 antes do comando 9
  em `0x5957a`. Uma falha que retorna normalmente não bloqueia essa chamada.
  Uma chamada que não retorna continua sendo uma fronteira distinta.
- O comando 9 salva arg2 em frame+0 (`0x5fbc4`), copia para frame+20
  (`0x5fbe8/0x5fbea`) e não relê esses slots no restante do corpo selecionado.
  Testes do corpo completo variam arg2 e alteram registradores voláteis nos
  hooks; efeitos globais de callees opacos não são excluídos.
- O comando 8 publica callbacks críticos API+56/+60 em objeto+68/+72.
  Seu caminho sel1 mantém retorno -1 mesmo após chamadas selecionadas;
  não é correto interpretar todo -1 como ausência de efeitos.
- `0x65182` espera `(M32[0xa5863a30]&0x1e00)==0`; `0x65196` espera
  bits9..12 iguais a15. Não há timeout nessas duas janelas. O orçamento do
  interpretador de testes é apenas do host.
- O caminho sel0/1 do comando 9 pode executar o RMW final mesmo quando não
  produz resultado de tabela. A escolha depende de campos do MMIO
  `0xa0000010`. Conteúdo das máscaras e tabelas permanece desconhecido.

Esses retornos internos continuam separados dos [planos FVP de retorno,
cache e resposta](newtime-return-planes-hzc2.md). Zero publicado ao BL2
não confirma sucesso físico do DMC.

## Correções da entrega GLM

O extrator e os 65 testes originais foram reproduzidos. O JSON foi
**idêntico byte a byte**, com GNU 2.44. Os hashes originais estão no
[JSON revisado](references/newtime-dmc-method12-hzc2.json).

A reprodução revelou limites não detectados pelos testes originais:

1. `fail_return_neg11` invertia a condição dos guards anteriores.
2. O modelo de despacho atribuía -1 a memória não fornecida e deixava de
   resolver aliases do índice após wrap; agora distingue desconhecido/null.
3. A falta de valor h em um caminho que consulta a tabela virava -1.
   Agora continua desconhecida.
4. O interpretador anunciava recusa de memória ausente, mas fabricava zero.
   Agora faltas de bytes falham. Duas fixtures receberam explicitamente os
   resultados f2 e o retorno inicial produzidos pelo bloco anterior.
5. PUSH salvava R8 no lugar de LR, POP não consumia a palavra PC, MOVW
   alterava flags e ASR era confundido com CMP. Esses casos foram corrigidos
   ou recusados explicitamente. Flags de soma/shift também foram corrigidas.

A frase “nenhum escritor em toda a imagem” foi retirada. As células core
`0x3a660/0x3a664/0x3a668` estão além da segunda cópia; leitores foram
identificados, mas stores calculadas e aliases ainda precisam de análise.
A hipótese do carregador de configuração `0x647ac..0x65170` não é uma
prova de ausência. A [continuação de configuração](newtime-dmc-config-hzc2.md)
agora liga uma store calculada ao comando20 e uma origem adicional do cache;
a [ponte ao produtor BL2](newtime-dmc-bl2-producer-hzc2.md) fornece uma
origem nominal sob alias; dados vivos e preservação continuam abertos.
O chamador/X0 do slot 47 BL2 continua aberto.

## Reprodução

```sh
python3 scripts/inspect_newtime_dmc_method12_hzc2.py /caminho/sboot.bin --json /tmp/dmc.json
python3 -m unittest discover -s scripts -p 'test_newtime_dmc_method12.py'
```

Testes usam bytes/tabelas exportados, sem exigir firmware no CI. A
regeneração valida tamanho/hash antes do GNU e recusa com exit2, sem
escrever JSON novo. São 1494 instruções comparadas em bytes, 147 alvos
relativos, 100 literais distintos e 172 verificações de operandos. Esses
números não significam cobertura semântica de toda a imagem. Os 78 testes
incluem 13 regressões adicionadas na auditoria; hooks substituem serviços
e periféricos. Nenhuma execução no telefone ou ampliação QEMU foi feita.
