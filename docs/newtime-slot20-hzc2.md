# HZC2: chamadores do slot 20, origem de X5 e limite do slot 47

Análise **estática, 2026-10-27 (Campo Grande)**, base `912edb3`, após PR #47.
**Foram ligados oito locais de carga a nove chamadas nominais do slot 20**
de `0x30fe8`: sete passam X5=0; duas passam um buffer local de 64 bytes
em SP+0xc0. A construção desse buffer e as leituras de seus meios u16
agora têm PCs e fórmulas. Isso resolve X5 **nesses caminhos selecionados**,
sob preservação dos bindings; não identifica todos os chamadores indiretos.

Não foi encontrada ligação com a célula do slot 47 de `0x31408`.
Uma busca adicional de formas de endereço também não resolveu seu X0.
Não houve execução Samsung, resposta MMIO/SMC ou mudança no
[escopo QEMU](newtime-gate-observation-scope-hzc2.md).

## Imagem, método e reprodução

Mesmo sboot HZC2 de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs/células são offsets de arquivo; ponteiros nominais usam o delta
`0x020ea000`. S corresponde à âncora `0x31688`. Nenhum SP absoluto,
conteúdo de MMIO ou valor físico do S21 foi fornecido ao analisador.

```bash
python3 scripts/inspect_newtime_slot20_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
python3 scripts/validate_baseline.py
```

O [analisador](../scripts/inspect_newtime_slot20_hzc2.py) exige o hash exato.
O GNU confere **486 palavras, 48 alvos relativos e 41 operandos**.
O [JSON](references/newtime-slot20-hzc2.json) guarda argumentos, candidatos,
instruções, hashes dos intervalos e condições. São deduções manuais de
caminhos selecionados e modelos de aritmética de host, sem execução simbólica
geral ou prova de alcançabilidade de todo o programa.

## Deslocamento 160 não identifica sozinho uma tabela

O scan de 26432 palavras em `[0x16000,0x2fd00)` aceita somente LDR X com
imediato unsigned e LDP X com imediato signed sem writeback, testando ambos
os elementos de um par. Há **16 candidatos** para o deslocamento 160:

| Grupo | Locais de carga | Resultado selecionado |
|---|---:|---|
| Base nominal `0x30fe8` | 8 | Célula `0x31088`, slot 20; ponteiro inicial `0x02115498`, alvo `0x2b498` |
| Dados de pilha | 5 | Usos de SP/X29, sem despacho ligado ao slot nessa análise |
| Outra base ou base recebida | 3 | Não são uma ligação demonstrada à célula `0x31088` |

Em `0x22560`, a base selecionada é `0x31408`, portanto a célula é `0x314a8`,
de outra tabela. Em `0x2725c`, usa-se diretamente `0x31000+160`, célula
`0x310a0`. Em `0x27d40`, o método vem de uma base recebida em `0x31998`;
alias e alvo continuam abertos. Não foi convertido esse último caso em
ausência de uma possível chamada ao mesmo código.

As bases dos oito locais selecionados vêm de ADRP/ADD e registradores
conservados. Preservação ABI entre chamadas, entrada normal, memória da
tabela e bindings são condições da ligação, não medições. O scan B/BL da
entrada `0x2b498`, até `0xec000`, continua sem referência direta.

## Nove chamadas selecionadas

| Carga do método | BLR | X5 | W2 conservado pelo callee |
|---|---|---|---|
| `0x2354c` | `0x23550` | 0 | `0x6` |
| `0x245cc` | `0x245e8` | 0 | `0x2` |
| `0x24830` | `0x24838` | 0 | `0x2000` |
| `0x249f0` | `0x24a00` | SP+0xc0 | `0x2000` |
| `0x24a3c` | `0x24a44` | SP+0xc0 | `0x2000` |
| `0x24cd4` | `0x24cec` | 0 | `0x1000` |
| `0x24cd4` | `0x24d68` | 0 | `0x4` |
| `0x25560` | `0x25570` | 0 | `0x2` |
| `0x25674` | `0x25684` | 0 | `0x4` |

O local `0x24cd4` tem duas saídas condicionais, por isso há nove chamadas
para oito cargas. As duas chamadas com buffer passam W1=0/1 e W0=W28
no laço de canais 0–3. Seus argumentos não foram reconstruídos como valores
retornados pela NEWTIME ou recebidos do slot 47.

X4 também merece distinção: sete chamadas usam um ponteiro carregado de
S+640; `0x25570/0x25684` passam SP+0x70 de seu próprio quadro, como região
de trabalho. Uma origem nominal de canal conhecida na
[etapa anterior](newtime-channel-origins-hzc2.md) não torna todos esses
argumentos iguais ou preservados.

## Construção do buffer local

Na entrada `0x246f4`, o prólogo reserva **896 bytes**: 800 pelo SUB e 96
pelo STP. Aqui SP_A é o SP depois desse prólogo. A área
`[SP_A+0xc0,SP_A+0x100)` é zerada e preenchida por `0x24888–0x24978`.
Ela tem 16 palavras u32, quatro por canal.

Para canal i=0–3, componente j=0–1 e palavra k=0–1:

`buffer[4*i+2*j+k] = u32(C_i + atual_u16 - salvo_u16)`

| Termo | Origem no caminho selecionado |
|---|---|
| C_i | LDR W9 em `0x248c8`, base carregada de `0x30fc0[i]` mais 1664 |
| atual_u16 | Ponteiro de canal + `0x50+0x50*j+2*k` |
| salvo_u16 | `SP_A+0x128+0xa0*i+0x50*j+2*k`, na cópia de salvamento anterior |
| destino | `SP_A+0xc0+16*i+8*j+4*k` |

SUB/ADD em W e stores W conservam aritmética módulo 2³², sem saturação.
O nome `counter` no modelo identifica C_i como base aditiva; não atribui
unidade ou um nome de registrador físico confirmado. As amostras e a
preservação dos buffers por chamadas intermediárias não foram observadas.

## Cópia e leitura no callee

`0x2b498` reserva 176 bytes e zera os 64 bytes finais do quadro. Se X5
não é zero, `0x2b504` copia 64 bytes para `[SP_B+0x70,SP_B+0xb0)`.
Se é zero, pula essa cópia. SP_B é o SP do callee, distinto de SP_A:
sob chamada normal, `SP_B=SP_A-176`. Os intervalos de origem e destino
são diferentes e não se sobrepõem no modelo sem wrap.

No ramo condicionado pelo **bit 13 do W2 original**, conservado em W23,
as leituras de `0x2b848/0x2b84c` usam:

`low16(buffer[4*canal+2*componente])` e
`low16(buffer[4*canal+2*componente+1])`.

Essas leituras são LDURH; não usam todos os 32 bits como valor nem
interpretam os bytes como ponteiros. Nos caminhos selecionados há três
chamadas com `0x2000`: uma passa zero e duas passam o buffer calculado.
A inicialização em zero descreve o preparo local; conservação até leituras
posteriores ainda exige as condições de memória, chamadas e aliases.
O modelo de host valida suas dimensões de entrada, sem atribuir esses
guards ao firmware.

## Busca adicional do slot 47

Na mesma região BL2, a busca complementar registra:

- Os quatro LDR de deslocamento 376 já ligados à outra tabela na
  [auditoria anterior](newtime-slot47-hzc2.md).
- Nenhum LDR/LDP nas formas aceitas com deslocamentos 1408 ou 5504,
  que seriam alternativas com bases `0x31000` ou `0x30000`.
- Nenhum LDR X literal ou ADR direto apontando à célula de arquivo `0x31580`.
- Dez pares adjacentes ADRP+ADD X formando `0x31408`, mas nenhum formando
  a própria célula. Construir a base não demonstra despacho pelo slot 47.

Essas são buscas de encodings e endereços candidatos, não uma exclusão
geral. ADRP/ADD não adjacentes, índices em registrador, outras formas de
carga, bases recebidas, aliases e outras imagens continuam fora da cobertura.

Passaram **108 testes NEWTIME**, incluindo 13 novos de largura/sinal,
buffer/quadro e encodings; reprodução exata, recusas de firmware inválido
e baseline completo de código próprio.
[Validação](references/newtime-slot20-validation-20261027.json).

X5 tem origem definida nas nove chamadas selecionadas. A origem do X0 e
o despacho efetivo do slot 47 permanecem abertos; não foi demonstrado que
esse buffer transporte a célula, seu valor ou um binding para ela.
