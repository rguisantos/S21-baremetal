# A0: prefixo truncado e decomposição do delta da Image

Rodada de 03/11/2026, Campo Grande, continuação do PR #86 / `0a5c9ec`.
As investigações distinguem evidência dos bytes, integridade das cópias,
identidade de processos e causa no build. **Nem o autor do truncamento
histórico nem a causa produtora do tamanho do kernel foram identificados.**
Não se adotou padding, strip como política final ou outra geometria.

## 1. Pacote preservado e o arquivo truncado

O [runner](../scripts/check_capture_a0_layout.py) conferiu o tarball completo
de 430051580 bytes, SHA
d649de92e904eff21fd0cf40af0d10b5a10b67a54de54b5b6f234df628e10015.
Os 2133 payloads foram lidos e comparados ao manifesto: 2133 OK, zero
divergências, 1290269017 bytes de payload. O manifesto tem SHA
dc9fa0410b3dc211f47e2c94cae4af0d6607041b5443b657bf2b32172a7ebcbf.
É uma nova execução na sessão do assistente; a revisão externa do usuário
continua separada. Integridade não valida conteúdo técnico, ABI ou carga.

| Evidência de mali_kbase.ko | Valor |
|---|---|
| Membro preservado | 30998000 bytes, SHA 5f9453abfb10849b04bf8916c21fcd3125df6d92788fdbc9f2b30d6134a43062 |
| Prefixo calculado nesta rodada | 26214400 bytes, exatamente 25 MiB |
| SHA do prefixo | ffac0a4f38e5ffa7c92a2ad39d98b26a33795b13ddd2b43a7eb74ae28f129099 |
| SHA registrado na cópia recusada | Igual ao SHA desse prefixo |
| Cauda ausente | 4783600 bytes |
| Tabela de headers de seções ELF | Offset 30993072, tamanho 4928; termina em 30998000 |

A evidência criptográfica vincula o registro da cópia recusada a um prefixo
do módulo íntegro, sem precisar supor outra compilação. A tabela de headers
de seções apontada pelo próprio ELF está inteira fora desse prefixo.
Uma cópia **sintética e declarada** dos mesmos 25 MiB reproduziu a classe
de erro do GNU strip 2.44, file format not recognized. O original permaneceu
íntegro. Esse controle explica a falha de parsing, não quem produziu o corte.

A cópia defeituosa e seu log temporário já não estavam disponíveis nesta
sessão. O registro Git retém tamanho, SHA e resumo da recusa, sem trilha
de processo suficiente para atribuição. As consultas locais não forneceram
um audit de escritor para aquela operação. Não se atribui a causa ao
compilador, ao pacote preservado, a cache, ao mecanismo de cópia ou à
plataforma de execução sem evidência adicional.

Três novas cópias com nomes .ko/.bin/.copy conservaram os bytes em verificações
posteriores, inclusive entre chamadas da sessão. O runner repete cópias
verificadas e uma checagem posterior; isso não é reprodução espontânea do
incidente nem uma garantia de estabilidade futura ou de independência da extensão.

## Releitura do destino e fronteiras de consumo

O extrator anterior conferia o hash do fluxo lido do tar durante a escrita.
Esse hash, isoladamente, não comprova os bytes que ficaram no destino.
[copy_checked](../scripts/capture_a0_copy.py) agora:

1. Confere contagem e SHA da origem, recusando excesso, falta e short write.
2. Faz flush/fsync e confere o tamanho do arquivo escrito.
3. Reabre o destino, confere seus bytes por SHA e verifica estabilidade da
   identidade/tamanho/mtime/ctime antes e depois da releitura.

As 275 cópias selecionadas (vmlinux + 274 módulos) passaram a releitura real.
O [runner de dimensionamento](../scripts/check_capture_a0_sizes.py) usa o novo
copiador e mantém a conferência do módulo antes/depois de strip; acrescenta
conferência do vmlinux antes/depois de objcopy. Releitura não impede mudanças
posteriores, por isso as verificações de consumo continuam necessárias.

O registro contém PID do copiador **atual**, dispositivo, inode e timestamps.
Esses valores são voláteis e não são critérios de reprodução dos bytes nem
identificam o autor do incidente anterior. Testes injetam truncamento e
alteração de mesmo tamanho no destino, mesmo com a origem correta, e
exigem recusa. A origem histórica da mutação permanece aberta.

## 2. Onde estão os 64 KiB

O [leitor de layout](../scripts/capture_a0_layout.py) compara o header ARM64
e os dois descritores PE/COFF, com a fonte Samsung fixada. Em efi-header.S,
a região PE .text usa __initdata_begin - efi_header_end; PE .data começa em
__initdata_begin. Esta PE .text é uma região composta anterior a initdata,
**não somente a seção .text do ELF nem uma única função**.

| Medida em bytes/coordenadas relativas | Stock | Candidato | Delta |
|---|---:|---:|---:|
| Headers / efi_header_end | 4096 | 4096 | 0 |
| PE .text, tamanho de arquivo e virtual | 27906048 | 27840512 | -65536 |
| Início PE .data / __initdata_begin | 27910144 | 27844608 | -65536 |
| PE .data, bytes em arquivo | 1559040 | 1559040 | 0 |
| PE .data, tamanho virtual | 6066176 | 6066176 | 0 |
| Fim dos bytes em arquivo / _edata | 29469184 | 29403648 | -65536 |
| Fim runtime / _end | 33976320 | 33910784 | -65536 |
| Cauda virtual sem bytes em arquivo | 4507136 | 4507136 | 0 |

Assim, separadamente:

```text
arquivo = 4096 + PE.text.file_bytes + PE.data.file_bytes
runtime = 4096 + PE.text.virtual_bytes + PE.data.virtual_bytes
```

A mesma redução da primeira região explica integralmente os dois deltas;
não há redução da parte de dados nem da cauda virtual que justificasse
tratar o header runtime como uma segunda anomalia independente. Também
não há um trailer de 64 KiB apenas omitido ao final: o início de .data e
os limites finais mudam, com tamanho de .data conservado.

O branch primário do header aponta para 26869760 no stock e 26804224 no
candidato; a entrada EFI passa de 26870608 para 26805072. Ambos mudam
-65536. No candidato, oito símbolos do ELF conferem com esses campos:
_head/_text, efi_header_end, __initdata_begin, _edata, _end, stext e
__efistub_entry. image.h define o tamanho ARM64 por _end - _text; o tamanho
PE usa _end - _head, com _head e _text iguais no ELF conferido.

Isso localiza e decompõe o delta no layout. **Não identifica a opção,
objeto, função ou diferença do build que reduziu a região anterior.**
A interpretação do stock segue o formato observado e as mesmas equações;
não demonstra que a fonte/configuração candidatas reproduzem seu build.
O endereço de link não mede memória física e o handoff não foi executado.

## Validação e limites

[Relatório](references/capture-a0-copy-image-delta-hzc2.json) e
[validação](references/capture-a0-copy-image-delta-validation-20261103.json).
São 21 controles novos de destino, prefixo, manifesto e PE, além dos 251
anteriores: 272 A0 aprovados. Baseline obrigatório 9/9 passou; a CI inclui o conjunto.
A Image gerada mantém o SHA publicado no PR #86 e o mapeamento independente
confere seus bytes. Não houve recompilação do kernel, novo dimensionamento
dos ramdisks ou alteração dos relatórios históricos. Os registros de cópia
voláteis não devem ser usados para exigir igualdade do relatório inteiro.

```sh
python3 scripts/test_capture_a0_layout.py
python3 scripts/check_capture_a0_layout.py \
  --stock-boot /insumos/stock/boot.img \
  --candidate-artifacts /insumos/S21-HZC2-alinhado-completo-20261102.tar.gz \
  --source /insumos/Kernel.tar.gz --tools-root tools/root \
  --output-dir /saida/auditoria-nova
```

Retorno 2 indica auditoria concluída com questões abertas; 1 indica erro/recusa.
Nenhum firmware ou payload binário é publicado no Git.

A0 permanece aberto: autor/causa do corte histórico, causa produtora da
redução pré-initdata, política de pacote/dependências e comprimento,
assinatura/aceitação Samsung/SignerVer03/vbmeta pai, KMI e política runtime.
A1 não começou; sem decisão OEM ou operação no aparelho.
