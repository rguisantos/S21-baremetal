# A0 HZC2: pai candidato, controles stock e protótipo B

Rodada de 04/11/2026 (Campo Grande), continuação do PR #91 a partir de
443a8a6. Trabalho estático/offline, executado pelo assistente. Os bytes
stock foram recuperados e conferidos; não se depende somente dos resultados
parciais relatados no chat.

**Resultado:** boot e vendor_boot stock satisfazem os respectivos hash
descriptors diretos do pai candidato. As duas imagens B não satisfazem os
mesmos descriptors. A hipótese de que a divergência de B seria apenas um
pai incompatível com esses arquivos stock fica excluída por estes controles
positivos. Não se demonstra que o aparelho tenha instalado ou consumido
este pai, nem que confie na chave embutida.

## Identidades e proveniência dos bytes

Os [pins novos](references/capture-a0-parent-pins-hzc2.json) fixam:

- BL_G998BXXSJHZC2_G998BXXSJHZC2_MQB107295400_REV01_user_low_ship_MULTI_CERT.tar.md5:
  10936433 bytes, SHA-256
  `5b48c27798b103ec906112fc4baad1aacd8d39c970dae6c478d3bd559e2cf31f`.
- Membro vbmeta.img.lz4 desse tar: 3793 bytes, SHA-256
  `063de3663de033a932f18a78622f2a39f430d45c1dc13786df4a77b102d0e85f`.
- vbmeta.img descomprimido: 10128 bytes, SHA-256
  `cd86d91b22e4e273abb65189cadea1c6d76683822e4fefa0c5407110462917ea`.

O tar completo foi identificado por SHA-256; seu trailer MD5 não foi validado
como assinatura ou proveniência Samsung. Nome de pacote não prova estado do
aparelho. O vínculo com os dois arquivos stock é demonstrado pelos digests
abaixo, além da identificação dos bytes do pacote.

Stock comprimido e descomprimido conferiram com os
[pins já publicados](references/capture-a0-pins-hzc2.json):

| Arquivo stock descomprimido | Bytes | SHA-256 |
|---|---:|---|
| boot.img | 67108864 | `28818995d6c3060df19602a0104c2c7dac9861f31f2620f9dab8466e6cdf51a1` |
| vendor_boot.img | 67108864 | `f5b18d6b18230702cef98d80f4543a0f452cddb5829310b3acdafd6d600a60b5` |

O [bundle B preservado](references/capture-a0-natural-b-artifact-20261104.json)
foi novamente lido e conferido: 27103200 bytes, SHA-256
`f23a98c6ead07b81d899a68c4566ec38860941264bdc29da40f73429e1504a5e`.
Os cinco membros, manifesto e quatro payloads bateram com os pins. Nenhuma
imagem, README interno, relatório histórico ou manifesto do bundle foi
alterado. A informação antiga de pai não fornecido descreve aquela montagem;
esta comparação é uma execução posterior, com entrada adicional.

## Teste completo: stock versus B

O [verificador](../scripts/capture_a0_parent.py) lê os campos do pai e calcula
`SHA256(salt || image[0:image_size])`. Não substitui image_size pelo tamanho
do payload Android, pelo original_image_size do footer do filho ou pelo
tamanho total do arquivo. Os valores são recalculados por hashlib e OpenSSL
sobre os mesmos bytes conferidos; ambos os métodos concordaram nas quatro
operações. A extração dos descriptors é comum aos dois métodos.

| Partição | Offset do descriptor no pai | image_size do pai | Stock | B |
|---|---:|---:|---|---|
| boot | 5848 | 30180128 | PASS | Diverge |
| vendor_boot | 7064 | 12415760 | PASS | Diverge |

boot, digest esperado no pai **e obtido no stock**:
`49151546375204f3e857954d061f4d341bfc2a6e0cafeb392c796b2ff60f2ffd`.
Digest de B:
`f20fd9a142ea9ec7941fbaa234bccf8481698ac0cc92c602c13eb485e841603d`.

vendor_boot, digest esperado no pai **e obtido no stock**:
`ef3455e744fcc1ac8b53fc57bfe1751e9dd04afc02093db5960fb24fb5524526`.
Digest de B:
`a4ac34a4d7ced228a017b73118a5162bc53d7a0043b3485e6876b116934a9b9a`.

O [relatório integral](references/capture-a0-parent-hzc2.json) contém salts,
comprimentos, offsets, hashes completos e resultados por variante. O runner
recusa concluir a comparação se faltar qualquer controle stock ou se seu
digest não corresponder ao pai. Também recusa input divergente dos pins.

## O que o pai autentica e o que não foi verificado

O censo contém 21 descriptors: sete hashes diretos, quatro chains, seis
properties e quatro cmdlines. Os hashes diretos nomeiam boot, bootloader,
harx, keystorage, ldfw, tzsw e vendor_boot. As chains nomeiam recovery, dtbo,
prism e optics, nos rollback locations 6, 7, 12 e 13. Boot e vendor_boot
**não são delegações neste arquivo**. Os outros cinco conteúdos e as quatro
cadeias não foram fornecidos ao teste de digests desta rodada; não se afirma
validação integral da cadeia. Properties/cmdlines são contabilizados por
tag, tamanho e hash, sem avaliar sua semântica.

A estrutura AVB tem 9344 bytes: header 256, autenticação 576 e auxiliar 8512.
SHA256_RSA4096 passou com a chave embutida tanto no verificador Python quanto
em OpenSSL. A entrada assinada header+auxiliary tem 8768 bytes, SHA-256
`f92468182b38116c4e44403a1495a1deae89e31b4a1f8eacc9eb913b2550dfa8`.

O blob público de 1032 bytes tem SHA-256
`d185cb2fb075fdc3b128836be117bd44851aabacce2ebffd285cf4e2b3aa54e6`;
é byte a byte igual aos blobs embutidos nos dois filhos stock. Os filhos B
têm outro blob, o de laboratório. Essas igualdades não estabelecem que o
bootloader/monitor confie em qualquer das chaves.

Os 784 bytes após a estrutura AVB começam com SignerVer03. Foram apenas
identificados por tamanho/hash: não estão na entrada RSA AVB testada e não
foram regenerados nem validados como assinatura Samsung. A verificação
RSA não autentica automaticamente o arquivo completo de 10128 bytes.

As definições de campos seguem os
[headers AVB já fixados no projeto](references/capture-a0-natural-b-primary-pins-20261104.json),
commit AOSP 25a14f7e3e6493a7f1a42aa9f78209d4dbe848e9. O parser desta rodada
suporta somente o perfil observado, com limites explícitos; não substitui
libavb ou a política Samsung.

## Consequência para os gates

Para esse pai passar a aprovar B por seus hash descriptors, os digests
teriam de mudar. Isso altera o auxiliar autenticado e invalida a assinatura
AVB atual. Uma nova assinatura de laboratório não demonstra confiança pela
rota Samsung travada. Não dispomos da chave privada correspondente à chave
stock e esta rodada não oferece uma rota alternativa de aceitação.

O [PIT transcrito](download-pit-observation-hzc2.md) associa VBMETA,
Identifier 23, a vbmeta.img; a
[observação ADB já registrada](runtime-collection.md) associa vbmeta a sda23.
Esses nomes não identificam os bytes instalados nem demonstram o uso desse
arquivo no boot. Não houve nova coleta, leitura de partição ou operação no
aparelho para preencher essa lacuna.

A0 permanece aberto: identidade/uso do pai instalado e confiança/aceitação
Samsung, SignerVer03, KMI e política runtime. A1 não começou. Não há decisão
OEM, autorização de flash ou alteração da main. Conferência externa dos
bytes por outra pessoa continua pendente; esta é uma reprodução do assistente.

## Reprodução e validação

Requer Linux, Python 3, OpenSSL e liblz4.so.1 (pacote liblz4-1). Nenhum insumo
privado é baixado ou executado pelo runner. Os arquivos locais são abertos
uma vez, conferidos e processados no mesmo buffer. O tar não é extraído no
disco; a descompressão LZ4 é limitada e sua saída novamente conferida. Os
digests nativos recebem stdin; chave pública e assinatura usam memfds selados.

```sh
A0_INPUTS=/insumos
python3 scripts/check_capture_a0_parent.py \
  --bl-archive "$A0_INPUTS/BL_G998BXXSJHZC2_G998BXXSJHZC2_MQB107295400_REV01_user_low_ship_MULTI_CERT.tar.md5" \
  --stock-lz4-dir "$A0_INPUTS" \
  --prototype-archive "$A0_INPUTS/S21-A0-B-prototipo-offline-20261104.tar.gz" \
  --output build/parent-comparison-nova.json
python3 scripts/test_capture_a0_parent.py
python3 -m unittest discover -s scripts -p 'test_capture_a0*.py'
python3 scripts/validate_baseline.py --output-dir build/baseline-parent-nova
```

Saída zero do verificador significa comparação concluída com controles
stock aprovados, sem autorizar uso físico ou fechar A0. O campo
B_satisfies_unchanged_candidate_parent registra o resultado, que foi false.
O destino JSON deve ser novo. Erros de identidade, formato, RSA, controle
stock ou divergência entre os dois métodos interrompem a execução.

Os [32 testes novos](../scripts/test_capture_a0_parent.py) cobrem controles
positivos/negativos, limites e salt do pai, ausência/troca de stock,
hash versus chain, assinatura adulterada por dois métodos, cauda opaca,
archives ambíguos/perigosos, LZ4 truncado/concatenado/acima do limite e uma
execução sintética completa com pins. A família A0 passou 378 testes e o
baseline obrigatório passou 9/9. A
[validação textual](references/capture-a0-parent-validation-20261104.json)
registra comandos e hashes. Comparações entre ambientes devem usar
identidades/valores calculados; versão OpenSSL e metadados de execução podem
diferir sem invalidar uma confirmação independente documentada.
