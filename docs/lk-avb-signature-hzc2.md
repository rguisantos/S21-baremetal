# LK HZC2: verificador vbmeta, hash e assinatura RSA

A rotina `0x1262b0` separa validade do cabeçalho, hash e assinatura da
confiança na chave. Seu retorno zero publica uma chave candidata; o
[callback de confiança](lk-avb-key-trust-hzc2.md) e os demais controles do
slot vêm depois. O resultado `OK_NOT_SIGNED` é **1**, distinto do sucesso
criptográfico **0**. Nenhum desses resultados locais comprova autorização
final para iniciar uma Image no telefone.

Análise estática do `sboot.bin` de 4.194.304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Os PCs são offsets de arquivo; ponteiros de dados usam o delta nominal
VA−arquivo `0xe7f14000`, com LK em `[0xec000,0x36c000)`. Essa tradução não
declara RAM livre, endereço físico ou preservação em execução. Base do
repositório: `fbbcd3f`, após PR #59. Aparelho de uso pessoal fora dos ensaios.

## Entrada, validações e resultados

O chamador em `0x1227e8..0x1227f4` passa bytes em X0, tamanho em X1,
endereços de saída do ponteiro da chave em X2 e de seu tamanho em X3.
`0x1262dc/0x1262e4` zeram as saídas não nulas antes das verificações.
O caminho selecionado exige pelo menos 256 bytes, compara os quatro bytes
`AVB0` e chama `0x125b48` para converter o cabeçalho. O corpo desse conversor
fica como callee opaco nesta entrega; os nomes dos campos abaixo seguem a
correspondência de layout com a referência fixada.

As instruções seguintes conferem major=1, minor≤1, último byte do campo
release igual a zero, alinhamento dos blocos de autenticação e auxiliar em
64 bytes e limites de soma/intervalos. Os helpers `0x125310/0x1253b0` detectam
overflow de soma u64. Hash e assinatura devem caber no bloco de autenticação;
chave e metadata, quando presentes, devem caber no auxiliar. Isso delimita
as verificações locais, sem certificar toda a segurança de memória ou os
callees transitivos.

| Retorno vbmeta | Nome conferido na tabela | Origem local |
|---|---|---|
| 0 | OK | Comparação do hash e retorno verdadeiro do helper RSA; publica saídas opcionais da chave |
| 1 | OK_NOT_SIGNED | Algorithm=0, após as verificações anteriores; não calcula hash/RSA |
| 2 | INVALID_VBMETA_HEADER | Tamanho, magic, limites, alinhamento ou algoritmo/comprimento incompatível |
| 3 | UNSUPPORTED_VERSION | Major diferente de 1 ou minor maior que 1 |
| 4 | HASH_MISMATCH | Comparação do digest em `0x126894` diferente de zero |
| 5 | SIGNATURE_MISMATCH | Byte baixo do resultado de `0x126b30` igual a zero |

Os nomes vêm de seis ponteiros na tabela `0x230748`, consumida por
`0x1269a8`. O extrator traduz os ponteiros e confere os literais completos.
Retorno 2 agrupa motivos diferentes; não é diagnóstico exclusivo de formato.

## Algoritmos e bytes incluídos no hash

`0x120cd8` aceita IDs de 0 a 6 e devolve `0x305be0 + 24*ID`.
São três u64 little-endian por registro: ponteiro para padding, tamanho do
padding e tamanho do digest. O registro zero contém três zeros. Os outros
seis foram conferidos integralmente, incluindo cada byte `ff`, separador e
prefixo DER DigestInfo do PKCS#1 v1.5.

| ID | Hash | RSA (bits) | Digest (bytes) | Padding (bytes) | Padding no arquivo |
|---|---|---|---|---|---|
| 1 | SHA-256 | 2048 | 32 | 224 | 0x22fa28 |
| 2 | SHA-256 | 4096 | 32 | 480 | 0x22fb08 |
| 3 | SHA-256 | 8192 | 32 | 992 | 0x22fce8 |
| 4 | SHA-512 | 2048 | 64 | 192 | 0x2300c8 |
| 5 | SHA-512 | 4096 | 64 | 448 | 0x230188 |
| 6 | SHA-512 | 8192 | 64 | 960 | 0x230348 |

A tabela de saltos `0x230740` contém `0f 0f 0f 31 31 31`. Seu consumidor
subtrai 1 do ID e usa deslocamento **signed byte ×4**, relativo a
`0x126814`: IDs1–3 vão a `0x126850`, IDs4–6 a `0x1268d8`. O relatório
registra esses destinos à parte dos grafos locais, que param no BR.

Nos dois grupos, o fluxo inicializa o contexto, atualiza com os **256 bytes
originais do cabeçalho** e depois com **todo o bloco auxiliar**, finaliza e
compara o digest ao hash armazenado no bloco de autenticação. Esse último
bloco não entra no hash. Os helpers SHA são chamados em `0x127330/0x127388/
0x127460` e `0x1277f8/0x127890/0x127968`; seus corpos não foram auditados
nesta entrega. Identificação SHA-256/SHA-512 resulta da correspondência
entre dispatch, comprimentos e prefixos DER/referência, sem executar SHA do
firmware.

## Helper RSA e separação da confiança

`0x126950..0x12696c` prepara oito argumentos para `0x126b30`: chave e
tamanho no auxiliar; assinatura e tamanho no bloco de autenticação; hash e
tamanho nesse mesmo bloco; padding e tamanho provenientes da tabela.
O helper local:

- exige ponteiros não nulos, bits de chave 2048/4096/8192 e extensão
  serializada `8 + 2*(bits/8)`;
- converte módulo e RR para arrays de palavras, exige assinatura com
  `bits/8` bytes e padding com `signature_size − hash_size` bytes;
- copia a assinatura, usa `0x126a18` para multiplicações Montgomery e
  executa oito pares de quadraturas mais uma multiplicação final, sequência
  correspondente ao expoente 65537;
- compara padding e, depois, digest. Só mantém o bool verdadeiro no caminho
  em que as duas comparações retornam zero.

O comparador `0x1250b8` acumula OR do XOR dos bytes, incluindo zeros;
comprimento zero retorna igualdade. A chamada externa RSA falsa leva a
retorno vbmeta5; a verdadeira permite publicar chave/tamanho e retornar0.
Essa chave ainda precisa ser autorizada pelo callback de confiança. A
igualdade com a [chave embutida](lk-embedded-avb-key-hzc2.md) ou com a
resposta efetiva do monitor não foi demonstrada.

**Limite da conclusão:** correspondência de código e tabelas não certifica
aritmética RSA, correção transitiva ou tratamento seguro de todas as falhas.
Os caminhos de falha nas alocações internas do modpow podem reunir-se às
comparações dos bytes; não foi demonstrado que todos os caminhos recusem
uma entrada em toda condição. Nenhum bypass ou assinatura física aceita é
declarado por esta análise. Alocador, cópias, logs, conversores e SHA
continuam callees opacos no relatório.

## Conversão para resultado do slot

Após a chamada, `0x1227f8..0x122800` despacha valores u32 de 0 a 5.
A tabela `0x230708` é `36 15 00 4a 15 15`, signed byte ×4 sobre
`0x122d10`. Resultados vbmeta e resultados do slot são enums distintos:

| Resultado vbmeta | Destino | Resultado/ação local do slot |
|---|---|---|
| 0 | 0x122de8 | Exige ponteiro e tamanho da chave não nulos antes de continuar em 0x122808 |
| 1, 4, 5 | 0x122d64 | Define W20=3 (verification error); frame+248 escolhe cleanup ou continuação com erro retido |
| 2 | 0x122d10 | Define W20=6 (invalid metadata), segue cleanup |
| 3 | 0x122e38 | Define W20=7 (unsupported version), segue cleanup |

O ramo do sucesso sem chave chama `0x124f68`, tratado como fronteira opaca;
não é um sucesso adicional. O caso fora da tabela tem continuação genérica,
mas não foi identificado como resultado normal do verificador nesta análise.
Frame+248 ainda não foi ligado à sua origem aqui. Um erro local pode
continuar processamento sem deixar de ser erro; isso não equivale a boot
autorizado. Os rótulos posteriores do wrapper são os da análise anterior.

## Reprodução e validação

```bash
python3 scripts/inspect_lk_avb_signature.py /caminho/sboot.bin
python3 scripts/test_lk_avb_signature.py -v
```

O [relatório](references/lk-avb-signature-hzc2.json) confere 1.147 palavras
GNU, 232 destinos relativos e 74 operandos selecionados em nove blocos.
Além disso, decodifica duas tabelas de salto, quatro endereços de tabelas,
seis nomes de resultado e seis registros/prefixos de algoritmo. A imagem
deve corresponder ao tamanho e hash **antes** da desassemblagem.

Os 18 testes novos usam entradas sintéticas e verificam limites, signed
byte ×4, ADR, registros, endian, digest/padding, mutações DER/ff/separador,
ponteiros fora do arquivo e recusa da imagem errada. Não validam uma
assinatura com a rotina Samsung. Estão incluídos no CI, antes do baseline.

Referência primária fixada: [AndroidBootloader/platform_external_avb,
b27a9aa](https://github.com/AndroidBootloader/platform_external_avb/tree/b27a9aa53d2db7720e4d88d6950dcd979da97de3/libavb),
arquivos `avb_vbmeta_image.c/.h`, `avb_rsa.c` e `avb_crypto.c`; hashes exatos
no relatório. São referências de formato, algoritmos e resultados, não
fontes correspondentes atribuídos ao fork Samsung. A evidência local é
o disassembly do HZC2 fixado.

[Validação local](references/lk-avb-signature-validation-20261030.json):
relatório reproduzido byte a byte, testes novos e regressões aprovados,
baseline completo de nove etapas aprovado. Firmware Samsung não foi
executado nem emulado, e o telefone não foi alterado.

Próxima fronteira: ações e retorno completos do wrapper `0x17f5d0` após
`0x17f724`, origem da continuação tolerada no slot e implementação do
fornecedor seguro da chave. Os contratos de carga, memória e captura do
[diagnóstico físico](samsung-diagnostic-contract.md) continuam pendentes.
