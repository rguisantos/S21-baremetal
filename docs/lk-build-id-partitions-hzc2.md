# LK HZC2: Build-id de vbmeta/super e processamento das partições

`0x17deb0` é uma conferência de **Build-id**: usa um valor em cache atribuído
a vbmeta e compara seu prefixo com o SignInfo de super. A identidade entre
produtor e consumidor desse cache foi ligada estaticamente. O retorno
negativo força o rótulo red no [wrapper](lk-avb-wrapper-hzc2.md); um retorno
zero não certifica leitura nova, autenticidade ou autorização final de boot.

Base main `e8cecfb`, após PR #61. `sboot.bin` HZC2 de 4.194.304 bytes,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; endereços relativos usam o delta nominal
VA−arquivo `0xe7f14000`. Não representam medição de RAM disponível ou
estado do telefone. Nenhum firmware Samsung, SMC ou acesso ao aparelho
foi executado.

## Identidades e fluxo da comparação

| Campo/rotina | Ligação no HZC2 |
|---|---|
| Build-id atribuído a vbmeta | Relativo `0xd05890`; consumidor ADRP/ADD em `0x17dec0/0x17dec8` |
| Escritor selecionado | ADRP X3 + ADD X0 em `0x17ea48/0x17ea50` resolve o mesmo `0xd05890` |
| SignInfo de super | Getter `0x154ba0` devolve cache relativo `0xcd62a0` |
| Referência comparada | Endereço devolvido pelo getter +16 |
| Palavra de política | u32 em relativo `0xaaa70c`; origem e valor vivo ainda desconhecidos |

O teste inicial `0x151018(cache,16)` aloca uma referência, zera seus bytes e
compara 16 bytes: retorna 1 se iguais a zero, 0 se diferentes e −1 se a
alocação falhar. `0x17ded4` trata **qualquer resultado não zero** como
falha. A mensagem SignInfo(Build-id) is NULL também cobre a falha de
alocação; não deve ser promovida a prova exclusiva de conteúdo ausente.

O getter de super é chamado, e `0x150480` classifica seu prefixo. Os
primeiros 11 bytes de `SignerVer01/02/03`, comparados sem distinção de caixa
ASCII por `0x1b2718` e `0x1afc88`, produzem 1/2/3. Ponteiro nulo ou prefixo
não reconhecido produz 0. A classificação do prefixo não verifica uma
assinatura ou certifica o restante do registro.

Se o prefixo é reconhecido, o checker usa `strlen(cache_vbmeta)` como
comprimento de uma comparação **sensível a caixa** contra `super+16`, por
`0x1b26b0`. Não usa comprimento 16 nem exige que a referência termine no
mesmo ponto. Assim, sucesso dessa operação significa igualdade do prefixo
selecionado, não igualdade integral dos dois identificadores. O teste de
16 bytes zerados também não equivale a testar só o primeiro byte NUL.
Terminação e acessibilidade da string são premissas ainda não medidas.

| Observações locais | Retorno do checker |
|---|---|
| Teste inicial não zero, inclusive alocação falhou | −1, independentemente da palavra de política |
| Signer de super reconhecido e prefixo igual | 0 |
| Signer reconhecido, prefixo diferente e política=0 | −1 |
| Signer reconhecido, prefixo diferente e política≠0 | 0 |
| Signer não reconhecido e política=0 | −1 |
| Signer não reconhecido e política≠0 | 0 |

Esses resultados dependem de os callees retornarem normalmente e de
preservarem o estado necessário. Os ramos de falha também preparam texto
em relativo `0xaaa6fc` e chamam o logger `0x17ddc8`; seus efeitos transitivos
não foram reconstruídos aqui. O wrapper testa o retorno como signed32 e
força red em caso negativo, conforme a análise anterior.

## Origem do valor e atualização de super

No caminho selecionado de vbmeta em `0x17e920`, o código localiza SignInfo
após blocos da imagem. O ramo de prefixo reconhecido em `0x17f044` e retorno
não negativo do callee `0x1526f8` pode convergir em `0x17ea24`. Ali o código
copia `strlen(SignInfo+16)` bytes para `0xd05890` em `0x17ea54`. Essa chamada
não inclui o terminador NUL. Não foi estabelecida a capacidade do destino,
sua limpeza anterior, a terminação posterior ou a preservação dos bytes
até o checker. Não se generaliza esse produtor para todas as rotas do
processador ou de seus callees.

`0x154ba0` pede um buffer de 384 bytes para obter metadados de super. Quando
o helper de seleção sinaliza sucesso, prepara uma leitura de 256 bytes em
offset derivado dos campos locais, para o cache `0xcd62a0`, por `0x154018`.
O resultado dessa leitura não é testado. O getter devolve o **mesmo endereço
de cache** mesmo se a alocação ou a seleção falhar, sem uma limpeza explícita
desse cache nesses ramos. Não há prova de que os bytes retornados sejam novos.

O próprio leitor `0x154018` chama o backend `0x11b258` e, sem testar seu
retorno, copia o buffer temporário ao destino e retorna 1. Lookup/alocação
falhos têm caminhos que retornam 0, mas 1 não demonstra sucesso do backend.
O backend, a seleção dos metadados e os dados vivos continuam fronteiras;
nenhuma falha física ou reutilização efetiva foi observada.

## Extração, relatório e processamento de partições

Os corpos locais de `0x17e2c0`, `0x17e828` e `0x17e920` foram incluídos no
relatório, mantendo seus callees como fronteiras:

| Rotina | Comportamento local delimitado | Limite |
|---|---|---|
| 0x17e2c0 | Normaliza o nome, seleciona leitura por início ou rodapé e pode copiar 256 bytes de SignInfo ao destino | Há saídas de erro sem escrita explícita no destino; não foi estabelecido status universal de saída válida |
| 0x17e828 | Seleciona o nome associado ao texto de erro, extrai SignInfo e imprime VBMETA/SAMSUNG/CUSTOM | O caller não consome seu retorno como autorização; log não certifica aquisição válida de todos os campos |
| 0x17e920 | Lê metadados, usa o rótulo green em escolhas de leitura e chama verificadores Samsung/política | Conteúdo, assinaturas e efeitos transitivos desses verificadores continuam abertos |

Nos caminhos de rodapé, o callback da tabela em +24 é chamado com offset
−64 e tamanho 64. O comprimento devolvido é conferido e `0x121588` é chamado
para tratar o rodapé; esse callee fica opaco. No extrator, nomes como
VBMETA/VBMETA_SAMSUNG/VBMETA_SYSTEM usam outra rota local de leitura.
Os destinos temporários e a aritmética de offsets não foram certificados
como seguros em todas as entradas.

O processador referencia tags `usr` e `mrk`, campos em cache e consultas a
`0x157230`. Alguns ramos imprimem mensagens, esperam ou chamam outras
rotinas; essas chamadas não foram convertidas em sucesso ou parada física
presumidos. Há dois laços locais fixos, `0x17ee2c` e `0x17f2dc`, em caminhos
associados à mensagem recovery kernel rp check fail. O único RET local é
`0x17eb08`; não há contrato de bool de sucesso comum a todos os caminhos.
A cauda de assert chama `0x124f68`; se esse callee voltasse ao próximo PC,
encontraria a palavra UDF em `0x17f374`.

O processador pode publicar 1 ou 3 em relativo `0xaaa710`, além de atualizar
estado por outros callees. Esse campo é o tipo consultado pelo wrapper
antes de chamar o checker de Build-id. Isso liga um produtor local do tipo,
sem fechar toda sua inicialização ou a validade do SignInfo.

O laço de nomes no wrapper chama `0x17e920` e testa seu próprio contador,
não W0. Após `0x17e828`, a continuação também não testa seu retorno. Isso
não elimina os laços, efeitos de estado, verificadores internos ou serviços
seguros. Nenhuma dessas observações estabelece aceitação de uma Image
alterada no telefone.

## Reprodução e próxima fronteira

```bash
python3 scripts/inspect_lk_build_id.py /caminho/sboot.bin
python3 scripts/test_lk_build_id.py -v
```

O [relatório](references/lk-build-id-partitions-hzc2.json) confere 1.497
palavras GNU, 375 destinos relativos, 85 operandos, 18 literais e 16 grafos
locais. Liga o escritor ao leitor por decoders de ADRP/ADD e carga W32,
com fonte e destino de ADD distintos. A imagem deve corresponder ao hash
antes da desassemblagem.

Os 14 testes novos exercitam os decoders, larguras, escala, registros,
endereços divergentes, offset de 16 e recusa de imagem/CLI. São testes
sintéticos de host, não execução da comparação ou do firmware Samsung.
Regressões AVB 48 e grafos de retorno 14 também passaram; baseline completo
de nove etapas aprovado e [validação reproduzível](references/lk-build-id-partitions-validation-20261030.json).

Próxima fronteira: verificadores `0x1526f8/0x150aa8/0x1516b8`, procedência
da palavra `0xaaa70c`, aquisição/preservação dos caches e fornecedor seguro
da chave. Carga, memória e captura do [diagnóstico físico](samsung-diagnostic-contract.md)
continuam pendentes. O telefone permanece fora desses ensaios.
