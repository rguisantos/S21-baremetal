# HZC2: origem imediata do bitmap de política

Análise estática de 2026-10-27 (Campo Grande), base `42d2bb6` após PR #39.
**Os bits consultados por 0x157230 vêm de um bitmap de 32 bytes em 0xcd6618.
Um produtor concreto copia o campo +0x120 de uma resposta de processamento
de token para esse bitmap.** Isso liga o consumidor CP/fingerprint à política
de token; não revela a configuração ativa nem comprova aceitação da Image.

## Evidência e reprodução

Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets do arquivo; globais são relativos ao modelo LK. O bitmap e
os slots de ponteiros estão fora dos bytes do arquivo: não foram lidos ao vivo.
Nenhuma instrução Samsung, SMC, MMIO ou comando no aparelho foi executado.

```sh
python3 scripts/inspect_lk_policy_bitmap.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p test_lk_payload_return.py
python3 -m unittest discover -s scripts -p test_lk_final_edges.py
```

O [JSON](references/lk-policy-bitmap-hzc2.json) contém 423 palavras GNU,
93 destinos relativos conferidos por decoder independente, dez strings e
12 grafos locais. Blocos nomeados `fragment` são recortes, não funções inteiras;
as saídas do intervalo permanecem fronteiras. [Validação](references/lk-policy-bitmap-validation-20261027.json).

## Leitores e ligação ao consumidor

Para índices não negativos, 0x157230 calcula o índice da palavra de 64 bits,
carrega `u64(B+8*(i/64))`, desloca pelo índice módulo 64 e retorna o bit 0.
Para i=0..255 isso consulta os quatro u64 de B=0xcd6618. O código não possui
checagem de limites; não se atribui essa validação ao firmware. Índices negativos
usam aritmética assinada e extensão UXTW do índice da palavra, fora do domínio
normal considerado aqui.

0x157578 retorna uma palavra inteira com índice SXTW; 0x157270 encaminha
32 bytes desse endereço à rotina de cópia. Esses dois helpers corroboram
layout e extensão nominal, sem provar que uma chamada recebeu índice válido.

O [dispatcher pós-cópia](lk-postcopy-policy-hzc2.md) consulta i=5,28,37 em
0x151b28/0x151b54/0x151b88. Todos pertencem ao primeiro u64 do bitmap.
Não confundir esses índices com os argumentos 20,21,23 enviados ao helper
CP: são dois domínios diferentes. O terceiro teste também depende do bit 19
das flags lidas por 0x147ed8, que não é este bitmap.

## Produtor e cadeia dos 32 bytes

As strings nomeiam 0x157280 como `get_token_mode`, 0x156e98 como `read_token`
e 0x1427d8 como `em_context_make_response`. Identificam intenção nominal,
sem demonstrar autenticidade do token ou execução física.

| Etapa | Evidência estática |
|---|---|
| Preparação | 0x15729c chama 0x156c00(21); slots relativos request=0xcd6500, workspace=0xcd64f0, response=0xcd6608 |
| Buffers | Preparação chama 0x1303f0 com (1,0x17c98), (1,0x16940), (1,0x2a088) e publica request, response, workspace respectivamente; retornos reais desconhecidos |
| Entrada nominal | 0x1572b0 chama read_token(request+0x628); seu lookup usa a string `STEADY`, depois encaminha campos do descritor ao helper 0x11b258 |
| Prefixo | O produtor compara o início request+0x628 com `ENG` usando comprimento obtido da string; ramo diferente não executa a cópia do bitmap |
| Processamento | 0x1422e0(request,workspace), 0x132130(workspace), 0x1427d8(response,workspace,0); cada retorno não zero desvia |
| Campo intermediário | No ramo de bit 5 de u64(workspace+16), 0x1429c0 copia 32 bytes de workspace+0x29f68 para response+0x120 e marca bit 5 de response+24 |
| Publicação | Após retorno zero de 0x1427d8, exige u32(response+0)=0 e bit 5 de response+24; 0x1573e0 copia response+0x120 para 0xcd6618 |

A fonte de 0x1429c0 resulta de X22=workspace+0x29000, mais 0xf68.
O destino resulta de X19=response, mais 0x120. Esse vínculo é nominal sob
preservação dos objetos e dos ponteiros, não uma igualdade de buffers observada.
Há chamadas de impressão e releituras entre as verificações e a publicação;
seus efeitos não são presumidos puros. A lista da tabela não substitui todas
as condições anteriores de inicialização, retorno e acesso válido.

O read_token fornece X3=0x11000 a 0x11b258 e recompõe campos do descritor
em X1/W2. A implementação de I/O não foi reconstruída aqui. Não se conclui
que a partição foi lida com sucesso só porque o wrapper retorna zero no ramo
em que o descritor existe. `STEADY` é o nome de lookup encontrado, não prova
de conteúdo ou de uma interface disponível ao usuário.

## Retorno, limpeza e preservação

O corpo selecionado de get_token_mode não limpa diretamente o bitmap antes
dos desvios: a ausência da cópia não demonstra bitmap zero. A limpeza
0x156b70 encaminha zeragem/liberação dos três buffers e zera seus slots;
não zera diretamente 0xcd6618. Isso separa a vida útil dos contextos da cópia
publicada. Aliases, outros escritores e efeitos transitivos continuam abertos;
não se afirma persistência após reset nem ausência global de modificações.

O chamador selecionado em 0x15823c chama get_token_mode e salta para
0x1580f0. Ali chama a limpeza e retorna W19, sem copiar o retorno de
get_token_mode para W19 nesse trecho. Portanto também não se pode usar o
retorno desse chamador como certificado de publicação do bitmap.

## O que foi resolvido e o que falta

Foi fechada a origem imediata e o transporte nominal:
workspace+0x29f68 → response+0x120 → bitmap → consulta CP/fingerprint.
Não é um conjunto de constantes embutidas do firmware. A inicialização real,
o token presente, a produção do workspace por 0x132130 e os efeitos dos
helpers anteriores permanecem desconhecidos.

Próximo alvo: seguir a produção desse campo em 0x132130 e separar a validação
do token da autenticação da Image anterior à cópia. Esta descoberta não
estabelece um caminho de carregamento próprio nem recuperação do diagnóstico.
Não houve mudança da sonda ou tentativa física.
