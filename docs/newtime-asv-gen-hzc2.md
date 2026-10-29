# HZC2: auditoria ASV/GEN, n e W19

Análise estática de 2026-10-28 (Campo Grande), base remota `3e3a868`.
Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs de arquivo. Sem execução Samsung ou ampliação QEMU.

**n=13 e as fórmulas condicionais de W19 conferem. A exclusão do caminho
habilitado não confere:** o relatório recebido deslocou GEN em uma palavra.
O corpo GEN tem duas palavras, columns/rows; as células começam em +8.
O callback `0x1c19c` sustenta isso: `0x1c2a4` publica o cursor posterior
às duas leituras, não corpo+12. O diretório, distinto do corpo, usa `<I4sI>`.

| Nome | Corpo no arquivo | Forma | Chaves / segunda célula |
|---|---|---|---|
| MMIF | `0x69ab8` | 13×6 u32 | chaves 0..12; subkey 0 ou 4 |
| MINTSCI | `0x6abf4` | 13×6 u32 | chaves 0..12; subkey 0 ou 2 |
| VMIF | `0x6b758` | 13×9 u32 | chaves 0..12; enable 2730 ou 3172 |
| VINTSCI | `0x6bb10` | 13×9 u32 | chaves 0/1 enable 0; 2..12 enable 800 |

`0x1b020/28` compara a primeira célula ao byte G+18; `0x1b030/34` testa a
segunda. Logo VMIF pode selecionar `0x1b1a8` para 0..12, VINTSCI para 2..12,
sob preservação. São candidatos estáticos, não execuções observadas.

F+152 recebe a segunda célula M em `0x1ace8/0x1acec`:
MIF usa 0 para chaves 0..3 e 4 para 4..12; INTSCI usa 0 para chave0 e 2 para
1..12. Ausência de chave M conserva a última linha, valor 4/2. Esses valores
coincidem com as chaves dos sub-registros ASV {0,4}/{0,2}; não são 421/141.
O argumento de fallback obrigatório por procurar421 é inválido.

O campo escrito pelo argumento X4 é M+16, quinta célula: MIF 2730/3172,
INTSCI 800. O LDP do caso MIF em `0x1adc8` recebe células 3/4 iguais no payload.
Há uma compactação anterior condicionada a seletor MIF/G+18=0/gate ligado:
copia campos 1..5 da linha 3 M e 1..8 da última linha V para a primeira linha.
As chaves não mudam, MIF mantém subkey 0, e enable VMIF continua não zero.
As variantes estão no JSON; não se presumiu GEN imutável no wrapper inteiro.

O driver passa ASV em X1 (`0x190f4`) e GEN em X2 (`0x19108`). O callback
ASV versão 3 constrói registros de 40 bytes. No lookup `0x1ab94`, MIF/INTSCI
têm columns 12, n=13 e dois sub-registros. `0x1aba0` carrega [D+16] em W23.
Handles/objetos são simbólicos, condicionados a publicação e preservação.

MMIF/MINTSCI têm seis colunas: `0x1ad00` leva F+132 a zero, desativando a
troca de W19 no CSEL do fallback. As folhas `0x1a668`, `0x1a26c`, `0x1a294`
não referenciam X19/W19 nem fazem calls. O caminho habilitado permanece.

```
MIF:    u32(G[23] + sext4(G[37] & 15))
INTSCI: u32(G[24] + sext4(G[37] >> 4))
```

Stores selecionados do inicializador usam nibbles de respostas SMC; sob
GPRs de endereço e bytes preservados, a faixa signed é -8..22. Magic já
presente não comprova essa proveniência. MOVN/MOVK X1 substituem os bits
baixos: pedidos `0xffffffffc4002400/2401/2402`, não `0x2400c400ffff` etc.
`0x16428` retorna X2 em X0; nenhuma resposta foi medida.

O offset é u32(12*i+W19), zero-estendido. W19 fixo implica 13 cargas se o
laço for alcançado/completado; 156 é a união das posições para colunas 0..11.
Por domínio, 31 padrões conservadores dão 384 pares na matriz, 11 após ela
e 8 distantes por wrap unsigned (negativos em i=0). Não se provou viabilidade
física dessas combinações de respostas.

Os índices 156..166 são 11 endereços candidatos em i=12. No MIF, são
`0x7a020..0x7a02a`: cabeçalho INTSCI de 8 bytes e 3 bytes da matriz seguinte.
No INTSCI, `0x7a0c4..0x7a0ce`: quatro dentro da reserva total+4 e sete além;
todos dentro da origem copiada `[0x69000,0x7d000)`. Esses limites não são
intercambiáveis. total+4 é uma fórmula de alocação, não guard de leitura.

Não se provou entrada ASV nula segura: `0x1b044` dereferencia D antes de
uma eventual saída n=0. Não se concluiu OOB físico nem bilhões de iterações
reais com campo negativo. Gates, aliases, G/SMC e slot47/X0 seguem abertos.

```sh
python3 scripts/inspect_newtime_asv_gen_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_asv_gen_hzc2.py),
[21 regressões](../scripts/test_newtime_asv_gen.py),
[JSON](references/newtime-asv-gen-hzc2.json),
[validação](references/newtime-asv-gen-validation-20261028.json).
GNU: 972 palavras, 159 destinos, 61 operandos selecionados. Os dois JSONs
ASV recebidos são idênticos. O extrator ASV e a suíte de 95 testes não vieram
nos anexos; esses 95 e a seleção exata dos 332 checks não foram reproduzidos.
