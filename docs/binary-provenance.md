# Proveniência dos binários grandes já versionados

O [inventário](references/large-binary-provenance.json) cobre os **17 arquivos
regulares rastreados com pelo menos 5 MiB**, por caminho, modo/blob Git,
tamanho e SHA-256. Foram encontrados **396820992 bytes somados por caminho**;
isso não é o tamanho do banco de objetos Git. Há conteúdo idêntico em aliases,
que o Git pode armazenar como o mesmo blob; os grupos estão no manifesto.

Os arquivos já existiam no histórico. Esta entrega não adiciona binários,
não os remove e não reescreve o histórico. A pendência de manifesto foi
resolvida para o escopo acima; não se declara um SBOM de todas as dependências.

| Grupo | Evidência de origem |
|---|---|
| 13 executáveis/bibliotecas extraídos | SHA-256 coincide com o conteúdo de membros dos .deb locais identificados, com pacote/versão/arquitetura e hash do arquivo de origem |
| Três .deb grandes | Arquivos locais inventariados com SHA-256 e campos de controle; servem de origem para os matches de payload |
| scripts/magiskboot/magisk.apk | Coincide com o digest publicado do asset oficial **app-debug.apk**, Magisk **v30.7**, asset ID 360657865 |

O último veio dos metadados da
[release oficial](https://github.com/topjohnwu/Magisk/releases/tag/v30.7),
consultados nesta auditoria: SHA-256
`40729525e298a11dad6e13586a29efa48a48e97cbf00203798e8047d1c710cb2`.
É o asset de debug, não o APK de release com outro nome/tamanho. O manifesto
conserva a URL exata e a identidade do asset; não infere a versão instalada
no telefone a partir dessa ferramenta legada do repositório.

Os matches Debian demonstram identidade de bytes com **os pacotes locais**.
Não foi feita autenticação independente dos .deb por Release/InRelease,
assinatura ou download de um snapshot remoto. Os campos de controle são
metadados desses próprios arquivos. Essa fronteira fica explícita em cada
entrada, sem inventar uma origem verificada além da evidência disponível.

```bash
python3 scripts/audit_large_binaries.py --check docs/references/large-binary-provenance.json
```

O script recusa um arquivo grande cujo conteúdo de trabalho difira do blob
indexado. Lê os pacotes sem extrair seus caminhos no filesystem e não baixa
executáveis. Próxima organização: preparar bootstrap por versões/hashes
fixados, validar a reprodução e então retirar dependências vendorizadas da
árvore em uma alteração própria, preservando builds e histórico.
