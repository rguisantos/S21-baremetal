# A0: contêiner offline com geometria fixa e chave de laboratório

Rodada de 02/11/2026, Campo Grande, base PR #84 / `ed262c4`.
O [build alinhado](capture-a0-aligned-full-hzc2.md) permanece como candidato
de kernel/módulos. Esta rodada entrega um montador limitado de contêiner e
controles criptográficos offline; **A0 continua aberto e A1 não começou**.
Não houve operação no aparelho nem decisão de desbloqueio.

## O resultado concreto

O [montador](../scripts/capture_a0_container.py) substitui payloads inteiros
de **mesmo tamanho** em boot/vendor_boot v3, preservando as coordenadas e
todos os demais bytes, inclusive cabeçalho Android, padding, extensão opaca
e rodapé AVB. A etapa de laboratório atualiza o digest, a chave embutida e
a autenticação do vbmeta com SHA256_RSA4096, mantendo o cabeçalho AVB.
Não muda para algoritmo NONE nem habilita flags de desativação.

O [runner](../scripts/check_capture_a0_container.py) aplicou uma mutação
sintética de um byte ao fim do kernel de boot e do ramdisk de vendor_boot.
Esses payloads são **controles de bytes, não kernels/ramdisks executáveis**.
O segundo pode inclusive deixar de ser um gzip válido. O objetivo é testar
as camadas do contêiner, não reconstruir a proposta de 274 módulos.

| Variante, nas duas imagens | Digest do payload | RSA com chave embutida | avbtool verify_image |
|---|---|---|---|
| Stock sem alterações | Confere | Confere | 0 |
| Payload alterado; vbmeta original | Diverge | Confere | 1: digest divergente |
| Digest atualizado; autenticação original | Confere | Diverge | 1: assinatura divergente |
| Digest/chave/autenticação de laboratório | Confere | Confere | 0, chave de laboratório explícita |
| Outro byte alterado após a assinatura de laboratório | Diverge | Confere | 1: digest divergente |

O verificador local usa a chave serializada AVB, confere a aritmética
Montgomery com o [leitor existente](../scripts/inspect_lk_embedded_key.py)
e verifica RSA/PKCS#1 v1.5/SHA256. A implementação AOSP fixada fez a
conferência externa ao montador. Essa independência é de implementação,
na mesma sessão do assistente; não é uma reprodução no computador do usuário.

## Preservação e reprodução

Os controles sem alterações conservaram os 67108864 bytes de cada boot e
vendor_boot. Seus hashes são os [pins stock](references/capture-a0-pins-hzc2.json).
dtbo também passou a conferência AOSP, mas foi somente referência de leitura:
o montador novo não modifica dtbo.

As extensões assinadas pelo descriptor têm 800 bytes em boot e 784 em
vendor_boot; o intervalo opaco completo até vbmeta tem 4096 em cada um.
Esses bytes foram preservados. O vbmeta mantém 2112 bytes, autenticação de
576 e auxiliar de 1280; algoritmo 2, SHA256_RSA4096. O rodapé e o intervalo
hasheado original não mudam. Dentro do vbmeta só digest, chave e autenticação
são reescritos; flags, rollback, release string e layout permanecem originais.
A release string preservada é informação herdada do template, não a versão
da ferramenta que produziu a variante de laboratório.

| Variante assinada com a fixture de chave de teste AOSP | SHA-256 da imagem completa |
|---|---|
| boot.img | `23dbfab8d4b18457a4e4ea4286f98fa2ffa6b015dfd5d2794a22614e10502960` |
| vendor_boot.img | `fe92f8dfd1c6f4e1b8da0f4d931b94332c4bec2ffc9f9350fe300f137214bf4b` |

Cada assinatura foi repetida sobre os mesmos bytes com a mesma chave e o
resultado foi idêntico. A execução completa foi repetida em outro diretório:
os hashes das variantes e os resultados dos controles coincidiram.
Os hashes dos logs nativos podem mudar com os caminhos; não são o critério
de reprodução da imagem. O relatório registra também hashes da implementação.

## Ferramentas e entradas fixadas

Fonte primária: [AOSP AVB](https://android.googlesource.com/platform/external/avb/+/25a14f7e3e6493a7f1a42aa9f78209d4dbe848e9/),
tag android-15.0.0_r1, commit `25a14f7e3e6493a7f1a42aa9f78209d4dbe848e9`.
Os [pins do ensaio](references/capture-a0-container-pins-hzc2.json) incluem:

- [avbtool.py](https://android.googlesource.com/platform/external/avb/+/25a14f7e3e6493a7f1a42aa9f78209d4dbe848e9/avbtool.py), 204713 bytes, SHA 78a50c8620985709f2e131cf948dcd66ecc43f09ed735e09d75751a7e21e4eb8;
- [test/data/testkey_rsa4096.pem](https://android.googlesource.com/platform/external/avb/+/25a14f7e3e6493a7f1a42aa9f78209d4dbe848e9/test/data/testkey_rsa4096.pem), 3243 bytes, SHA 6a224754880a57ab9cbd308267cd157d94cf05a1c8cb851aec4090e045d24121.

A chave é uma fixture pública upstream, não uma chave Samsung ou de
produção. Seu blob público AVB tem SHA
7728e30f50bfa5cea165f473175a08803f6a8346642b5aa10913e9d9e6defef6.
OpenSSL 3.0.13 foi usado para assinar; versão e hash do executável estão
no relatório. A verificação de formato/RSA do montador usa Python.

Antes de executar ferramentas ou criar a saída, o runner lê entradas
regulares com limite de tamanho e confere os bytes contra os pins. Usa
essas mesmas cópias verificadas do avbtool/chave e dos três arquivos stock.
O diretório de saída precisa ser novo. Comandos nativos têm timeout de
60 segundos e ambiente PATH/LC_ALL restrito. O runner recebe imagens raw;
a descompressão dos inputs lz4 desta sessão também teve hashes conferidos
antes e depois. Nenhum firmware, chave ou imagem modificada foi adicionado
ao Git; somente código, pins e evidências textuais.

```sh
python3 scripts/test_capture_a0_container.py
python3 scripts/check_capture_a0_container.py \
  --stock-dir /insumos/stock-raw \
  --avbtool /insumos/avbtool.py \
  --test-key /insumos/testkey_rsa4096.pem \
  --output-dir /saida/controle-novo
```

Retorno 2 significa controles concluídos, com A0 ainda aberto; 1 significa
erro/recusa. O [relatório](references/capture-a0-container-hzc2.json) contém
as variantes, resultados locais e onze verificações AOSP. A
[validação](references/capture-a0-container-validation-20261102.json)
registra testes, repetição e baseline. Os 29 testes novos usam RSA real em
fixtures sintéticas geradas localmente, sem rede ou firmware privado;
abrangem recusas de geometria, bytes externos ao payload, chave, assinatura
e inputs não fixados. Estão na CI, que instala OpenSSL explicitamente.

## O que continua faltando para o contêiner real

1. A alteração é sintética e só admite payloads com os comprimentos
   originais. Não foi montada uma Image real nem um vendor ramdisk com os
   274 módulos recompilados; crescimento/relocação de componentes é recusado.
2. Preservar SignerVer03 conserva os bytes recebidos, não sua validade
   diante do payload modificado. O bloco não foi regenerado ou validado.
3. A chave de laboratório difere da chave original. O PASS do AOSP comprova
   assinatura com essa chave fornecida explicitamente, não confiança pelo
   monitor/bootloader Samsung nem aceitação em OEM LOCK ON(U).
4. Nenhum vbmeta pai, cadeia de confiança, rollback ou política de segurança
   em execução foi atualizado/validado. O kernel não foi iniciado.

Portanto, está demonstrado o **repack de laboratório com geometria fixa e
metadados AVB conferidos**, sem fechar o gate do contêiner Samsung utilizável.
O trabalho seguinte em A0 é dimensionar/montar os payloads reais do mesmo
build e fechar a política de assinatura/aceitação da rota escolhida. KMI e
política runtime permanecem pendentes; entrada/cápsula de A1 seguem separadas.

A [continuação de dimensionamento](capture-a0-payload-sizes-hzc2.md) gerou a
Image e protótipos de ramdisk com dados reais. O perfil com strip cabe em
capacidade, mas ambos os payloads menores ainda exigem adaptação de
comprimento validada; o montador de mesmo tamanho continua recusando-os.
