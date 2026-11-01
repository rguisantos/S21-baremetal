# A0 HZC2 — repetibilidade do repack e limites do hash

Rodada de 01/11/2026, continuação do [inventário A0](capture-a0-hzc2.md)
e da [conferência KMI](capture-a0-kmi-hzc2.md). **A0 permanece aberto.**
O ensaio usa somente arquivos locais, sem operação no telefone.

## Resultado observado

Com o Magisk v30.7 fixado e as mesmas opções, três processos independentes
por imagem produziram saídas byte a byte iguais. Os arquivos extraídos
receberam mtimes distintos (1, 1700000000 e 1790000000 segundos Unix) antes
do repack. Não há evidência de timestamp ou aleatoriedade como causa desta
diferença. Isso delimita o perfil ensaiado; não prova todos os modos ou
versões do Magisk determinísticos.

Os headers Android, kernel/ramdisk/DTB e o blob vbmeta permanecem iguais.
Os hashes das saídas também coincidem com o ensaio original do A0:

| Imagem | SHA-256 da saída nas três execuções |
|---|---|
| boot | `e121314da768a7d31574ff6d4693c6025de81fde7817708d1e6727c2fb756067` |
| vendor_boot | `76b01725c3a845cca53e0f54b9a8947dbcebfb6eff9b6495928142f96fa63cef` |

As coordenadas abaixo são do arquivo **original** e os intervalos são
semiabertos: incluem o início, excluem o fim. O hash usa o `image_size` do
descriptor original, não o `original_image_size` reescrito no rodapé.

| Medida em bytes | boot | vendor_boot |
|---|---:|---:|
| Fim do corpo Android | 30179328 | 12414976 |
| Intervalo original hasheado | [0, 30180128) | [0, 12415760) |
| Extensão original após o corpo | 800 | 784 |
| Bytes diferentes dentro do hash | **584** | **651** |
| Bytes diferentes fora do hash | **2** | **2823** |
| Total diferente | 586 | 3474 |
| Intervalo do rodapé AVB | [67108800, 67108864) | [67108800, 67108864) |
| Offset vbmeta original → repack | 30183424 → 30183424 | 12419072 → 12414976 |
| Sobreposição do novo vbmeta com o hash original | 0 | 784 |

Portanto, **a extensão original está dentro do hash; o rodapé AVB está
fora**. Em vendor_boot os 2823 bytes externos se dividem em 1132 no espaço
anterior ao vbmeta original, 1688 na posição antiga do blob e três no
rodapé. Em boot os dois bytes externos são do rodapé. Alterar somente o
rodapé pode preservar o digest do payload e ainda quebrar a consistência
dos extents; digest válido não equivale a pacote válido.

## Relação com o código fixado

Fonte primária: [bootimg.cpp do Magisk](https://github.com/topjohnwu/Magisk/blob/e8a58776f1d7bdf852072ad0baa6eceb9a1e4aac/native/src/boot/bootimg.cpp),
commit `e8a58776f1d7bdf852072ad0baa6eceb9a1e4aac`, Git blob
`d5a4e3f2dd8c325d018e7074be1172dd92ea8825` (37584 bytes).

- Linhas 583–591: reconhece caudas específicas, incluindo SEAndroid,
  LG Bump e um percurso AVB1 separado.
- Linhas 919–938: emite a cauda reconhecida, alinha e copia o vbmeta.
- Linhas 1016–1024: copia o rodapé e atualiza tamanho/offset. A opção
  `PATCHVBMETAFLAG` não está habilitada no ambiente deste ensaio.

Em boot, os primeiros 16 bytes da extensão, `SEANDROIDENFORCE`, são
preservados. Os 784 seguintes começam com `SignerVer03` e acabam
substituídos por zeros. Em vendor_boot, a extensão de 784 bytes começa
diretamente com `SignerVer03`; o vbmeta movido passa a ocupar sua posição.
Esse comportamento corresponde à reconstrução das caudas reconhecidas,
sem preservar genericamente o bloco opaco. Não foi decodificado o formato
completo desse bloco nem demonstrada capacidade de recriá-lo/assiná-lo.

## Consequência para o gate

Não há motivo demonstrado para zerar ou congelar um campo variável.
Zerar bytes originais cobertos pelo hash também invalida seu digest.
Mesmo se houvesse variabilidade, o hash precisaria cobrir os bytes finais;
isso não implica, por si só, impossibilidade de empacotar.

O controle **sem alteração de payload** exige preservar o arquivo original
inteiro. O [controle de recomposição anterior](capture-a0-hzc2.md) já faz
isso, mas recusa payload modificado. Um kernel próprio necessariamente
altera bytes hasheados: precisa de contêiner e metadados coerentes, além de
uma política de assinatura/aceitação demonstrada para a rota escolhida.
Não se impõe a regra impossível de nunca escrever no intervalo hasheado.
Preservar um bloco opaco ou recalcular um digest, isoladamente, não prova
assinatura válida, confiança da chave ou aceitação pelo bootloader.

## Reprodução e limites

O [runner](../scripts/check_capture_a0_repack.py) exige os hashes exatos do
host tool e dos dois inputs `.lz4`, definidos nos [pins A0](references/capture-a0-pins-hzc2.json).
Confere também os arquivos descomprimidos, usa um diretório novo e reduz
o ambiente nativo a PATH/LC_ALL. Não publica imagens, ramdisks ou firmware.

```sh
python3 scripts/test_capture_a0_repack.py
python3 scripts/check_capture_a0_repack.py \
  --stock-dir /caminho/stock \
  --magiskboot scripts/magiskboot/magiskboot \
  --output-dir build/capture-a0-repack-novo
```

O retorno **2** significa análise concluída com o controle sem alterações
reprovado; 1 significa erro/recusa. O [relatório publicado](references/capture-a0-repack-extent-hzc2.json)
foi reproduzido integralmente em outra execução. Os 12 testes sintéticos
cobrem extensão, rodapé, padding, movimento de vbmeta e recusas de inputs;
estão na CI junto dos 55 testes A0 anteriores.

O próximo trabalho continua em A0: build/KMI/módulos reais, Module.symvers,
CRCs e perfil LTO/CFI/compat32, além da estratégia de contêiner para payload
modificado. A1 não foi implementado; não houve validação de assinatura RSA,
decisão OEM ou ação física. [Validação](references/capture-a0-repack-validation-20261101.json).
