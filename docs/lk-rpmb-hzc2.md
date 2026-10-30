# LK HZC2: backend dos contadores, pacotes RPMB e pedidos seguros

O [rollback Samsung](lk-samsung-checks-hzc2.md) usa um bloco de 256 bytes
por meio de `0x10ada0`/`0x10ade0`. A continuação liga essas entradas ao
despachante `0x109ed8`, ao dispositivo chamado `scsirpmb` e aos pedidos
seguros de nonce/MAC. A revisão de rollback dentro do bloco e o contador
de escrita recebido do dispositivo são valores distintos. Nenhum deles
foi medido no telefone; persistência e aceitação física continuam abertas.

Base main `c8ac96c6f3953617dab82784e354a2198254bf45`, após PR #63.
`sboot.bin`: 4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; endereços globais são relativos à tradução
nominal VA−arquivo `0xe7f14000`, sem identificar RAM física disponível.
Análise inteiramente estática: nenhum firmware Samsung, pacote de
armazenamento ou SMC foi executado.

## Da revisão ao bloco

O getter `0x1509b0` e o setter `0x150800` selecionam índice de bloco 1,
quantidade 1 e buffer de 256 bytes. A revisão selecionada é uma célula u32
nesse buffer, indexada pelo argumento original. O getter pode devolver o
[fallback 19](lk-samsung-checks-hzc2.md), sem obter um contador novo.

O setter rejeita índice unsigned>64 ou revisão unsigned>999. Para índices
0..5, uma consulta opaca com bit17 ligado seleciona skip e retorno0.
Caso contrário, exige a palavra relativa `0x8a6370` igual a1, lê o bloco,
substitui a célula e solicita a escrita. Falha local de leitura/escrita
seleciona −1; não há leitura posterior para comprovar persistência. O
limite índice64 não certifica capacidade do buffer: 64×4 já é256, e não
se declara segurança de memória para toda entrada aceita pelo teste.
O [chamador de rollback](lk-samsung-checks-hzc2.md) ignora o status do setter.

As duas entradas RPMB consultam outra palavra: relativa `0x8a6368`.
Zero devolve `0x40304` com diagnóstico; não zero despacha por cauda para
`0x10a648` (leitura) ou `0x10a850` (escrita). Esse gate é distinto de
`0x8a6370`; não se presume que seus valores vivos coincidam.

## Pacote local e despacho

O frontend zera um pacote de 512 bytes alinhado em128. Campos selecionados:

| Offset no pacote local | Uso observado |
|---|---|
| +0 u16 | Comando: 2 consulta contador de escrita, 3 escrita, 4 leitura |
| +2 u16 | Resultado recebido |
| +4 u16 | Quantidade usada pelo caminho de escrita; frontends preparam1 |
| +6 u16 | Índice truncado a16 bits |
| +8 u32 | Contador de escrita recebido/preparado |
| +12..27 | Nonce de16 bytes |
| +28 u32 | Ponteiro de dados truncado a32 bits, antes de materializar os dados |
| +32 u32 | Quantidade para o caminho de leitura, preparada como1 |

Esses offsets descrevem o pacote **local**, antes da conversão. O
despachante reverte todos os 512 bytes para formar cada frame de I/O,
e reverte os bytes da resposta. A posição+28 é reutilizada para dados:
no comando3 copia256 bytes do endereço recebido antes de reverter.
Não se interpreta o ponteiro do pacote como campo nativo transmitido.

O switch em `0x109f20` lê quatro halfwords little-endian, estende com
sinal e multiplica por4, com base `0x109f30`. Tabela em `0x226018`:

| Comando | Halfword signed | Destino |
|---|---:|---|
| 1 | 218 | `0x10a298` |
| 2 | 0 | `0x109f30` |
| 3 | 86 | `0x10a088` |
| 4 | 280 | `0x10a390` |

Comandos fora de1..4 devolvem0 sem I/O nesse despachante. O comando1 não
pertence ao caminho de rollback selecionado; seu corpo também está
incluído na cobertura GNU. O comando5 é preparado internamente para
obter resultado após os pedidos1/3, sem reentrar nesse switch.

`0x18eb08("scsirpmb")` fornece um objeto; chamadas indiretas usam métodos
em+152 para envio/escrita e+144 para recepção/leitura. O retorno desses
I/Os é sobrescrito sem teste local nos pontos selecionados. Destinos vivos
dos métodos, efeitos transitivos e conclusão física da transferência não
foram obtidos. Ausência do objeto seleciona `0x50a03`; o tratamento não
certifica todas as alocações e comprimentos.

## Ordem dos resultados e dos dados

Em `0x10a648`, quantidade signed≤0 retorna0 sem tráfego. Caso contrário,
cada iteração usa comando4, um índice low16 e endereço de saída low32,
avançando256 bytes com aritmética W32. O frontend copia o resultado u16
para o chamador **antes** de comparar o nonce. Divergência do nonce
retorna `0x50a02`; depois vêm os testes do retorno do despachante e do
resultado do pacote. O despachante copia os256 bytes recebidos para o
buffer do chamador antes de testar status do helper MAC e sua comparação.
Essas stores não estabelecem que os dados sejam autenticados ou novos.

Em `0x10a850`, há consulta comando2 com nonce **antes** do teste signed
de quantidade. O resultado u16 é publicado ao chamador, mas não é testado
antes de entrar no laço de escrita. O frontend testa o nonce e o retorno
do despachante; se ambos passam e quantidade≤0, pode retornar0 mesmo com
resultado inicial não zero. Para quantidade positiva, lê pacote+8 e
prepara comando3 por bloco com contador inicial+iteração, wrapping u32,
índice low16 e ponteiro de entrada low32 avançando256. Para cada escrita
posterior, testa retorno do despachante e resultado u16.

Há três detalhes adicionais no despachante:

- Resposta comando2 com resultado7 segue uma saída local0 sem comparar
  MAC. O frontend mantém seu tratamento separado de nonce/resultado; não
  se transforma essa saída em contador válido ou autorização global.
- No comando3, o MAC produzido é copiado ao último frame **antes** de
  testar o helper. Status não zero registra erro em `0x10a528` e volta a
  `0x10a174`, prosseguindo ao I/O. Não há aborto nesse ramo local.
- Nas verificações comuns das respostas2/3/4, comparação MAC diferente
  seleciona2; igualdade conserva o status do helper. Na leitura, os dados
  já foram copiados antes desses testes.

São propriedades da ordem local, condicionadas aos callees retornarem
normalmente e preservarem o estado necessário. Não comprovam um bypass,
MAC válido, contador persistido ou aceitação por qualquer chamador final.

## Pedido de MAC e nonce

O literal do firmware chama `0x109db8` de obtenção de HMAC. O helper prepara
descritor de três u64 alinhado em128, solicita limpeza do descritor/entrada
e invalidação da saída. Os auxiliares de cache têm cobertura GNU com
`DC CVAC`/`DC IVAC`; isso não mede coerência em uma execução real.

| Argumento MAC | Valor |
|---|---|
| X0 | `0xc2001018` |
| X1 | 3 |
| X2 | Descritor: +0 entrada, +8 comprimento, +16 saída |
| X3 | 0 |

O pedido passa pelo wrapper SMC `0xf6088`. Retorno low32 `0x20000` repete,
com no máximo20.480 tentativas; esgotamento retorna `0x80100`. Low32 zero
invalida novamente32 bytes de saída e retorna0; outro status é registrado
e devolvido em W0. Algoritmo, procedência da chave e execução do serviço
seguro continuam opacos. Nos frames, a comparação usa32 bytes em+196,
e a entrada por frame são284 bytes a partir de+228. Os comandos de múltiplos
frames concatenam esses intervalos antes do pedido.

O helper `0xf6fb0`, chamado com comprimento16 pelos frontends, prepara
SMC X0=`0xc200101c`, X1=X2=X3=0. Só copia X1/X2 retornados ao nonce após
X0 inteiro ser zero; os frontends verificam apenas low32 do status do
helper. `0xffffffff` tem diagnóstico específico. Há outros ramos para
comprimentos gerais, incluídos na cobertura, mas não se estabelece
qualidade criptográfica nem nonce efetivamente recebido no aparelho.

O [monitor EL3 candidato](monitor-preparation-hzc2.md) permanece sem
plaintext validado para identificar esses handlers. O
[TZSW TEEGRIS](tzsw-bien-hzc2.md) é outro componente, com fronteira de
envelope própria. Não se atribui a ele o dispatcher dessas SMCs nem se
repete a tentativa criptográfica já documentada como negativa.

## Verificação e reprodução

`inspect_lk_rpmb.py` exige tamanho/SHA antes de invocar GNU. Confere1.156
palavras em12 blocos,225 destinos relativos,133 operandos e20 literais.
O relatório compacto conserva blocos, testemunhos selecionados, branches,
grafos e SHA do índice completo PC/palavra, sem incluir firmware completo.
Grafos param no BR/SMC; BL/BLR têm continuação condicional normal e não
avaliam registradores, viabilidade de caminhos ou execução dos callees.

```sh
python3 scripts/test_lk_rpmb.py -v
python3 scripts/inspect_lk_rpmb.py /private/path/sboot.bin > /tmp/lk-rpmb.json
cmp /tmp/lk-rpmb.json docs/references/lk-rpmb-hzc2.json
python3 -m unittest discover -s scripts -p 'test_lk_avb*.py'
python3 scripts/test_lk_samsung_checks.py
python3 scripts/test_lk_build_id.py
python3 scripts/validate_baseline.py --output-dir build/baseline-rpmb
```

Os16 testes sintéticos exercitam sinal/escala/endianness, extremos,
limites, duplicatas, campos do descritor, gate e recusa antes de GNU.
Não executam o firmware. Evidências: [relatório](references/lk-rpmb-hzc2.json)
e [validação](references/lk-rpmb-validation-20261030.json).
Próximo: registro/destinos concretos dos callbacks `scsirpmb`, origem dos
gates e fonte validada do serviço seguro. Revisões vivas, readback e os
contratos físicos do diagnóstico continuam pendentes.
