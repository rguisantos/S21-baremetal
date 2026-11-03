# A0: investigação da origem do corte de 25 MiB

Rodada de 03/11/2026, Campo Grande, base PR #87 / b090537.
**Conclusão: origem histórica não identificada.** A investigação limitada
abaixo foi encerrada com resultados por hipótese. Não se atribui o corte
à plataforma, transferência, compilador, processo ou cota.

## Insumos e fronteiras de consumo

O [relatório anterior](capture-a0-copy-image-delta-hzc2.md) já vinculou o
hash recusado ao prefixo do módulo íntegro. Não se repetiram a auditoria
individual dos 2133 payloads, as três cópias por extensão ou o controle de
parsing ELF no strip. A cópia defeituosa e o log temporário continuam
indisponíveis. Os registros Git não contêm o audit de escritor ou o
ambiente do processo histórico.

O [runner](../scripts/check_capture_a0_handoff.py) lê o tarball uma vez,
verifica os 430051580 bytes por SHA-256 e processa **esse mesmo buffer**.
A referência é d649de92e904eff21fd0cf40af0d10b5a10b67a54de54b5b6f234df628e10015;
manifesto dc9fa0410b3dc211f47e2c94cae4af0d6607041b5443b657bf2b32172a7ebcbf.
Confere os quatro membros consumidos contra o manifesto: vmlinux,
System.map, .config e drivers/gpu/arm/bv_r38p0/mali_kbase.ko. É execução do
assistente, sem conferência externa do usuário ou certificação dos demais
consumidores do pipeline.

O módulo tem 30998000 bytes, SHA
5f9453abfb10849b04bf8916c21fcd3125df6d92788fdbc9f2b30d6134a43062.
Nos controles nativos, esse buffer é colocado em memfd com selos que
impedem escrita, crescimento e redução; cp lê esse descritor. Os destinos
são lidos em buffers verificados. Um hash anterior do caminho não é usado
como garantia dos bytes que outra abertura processaria depois.

## Busca nos scripts e registros versionados

Dois snapshots fixos: 0a5c9ec, extrator do PR #86, e b090537, após a
correção de releitura. A busca cobre grafias decimais/hexadecimais e
expressões inteiras de 25*1024*1024 em Python/shell/workflows. O leitor AST
reconhece aritmética limitada sem executar código. São 311 e 315 arquivos,
respectivamente; zero ocorrência desse limite no escopo pesquisado.
Inventários por SHA e corpo exato de extract_selected estão no
[relatório](references/capture-a0-copy-origin-hzc2.json).

O laço do PR #86 lê blocos de 1 MiB até EOF e exige contagem/hash completos
da origem. Não contém saída programada em 25 MiB. Não relia o destino nem
conferia o retorno de write: lacuna de detecção, sem prova de que um short
write causou o incidente. O PR #87 adicionou essas verificações, sem
descobrir retroativamente o escritor.

Também se pesquisaram 42/45 documentos e referências A0, incluindo o
worklog. As ocorrências são os registros conhecidos de tamanho/prefixo,
não uma configuração de limite ou log de escrita que atribua a causa.
Nenhum .log estava versionado nesses diretórios dos snapshots. A busca
não cobre ferramentas externas ou condições históricas não registradas.

## Controles de ferramentas e limite de processo

| Controle atual | Resultado |
|---|---|
| GNU cp 9.4, sem limite injetado, reflink/sparse desativados | Retorno 0, 30998000 bytes, SHA integral correto |
| shutil.copyfileobj com fluxo em memória verificado | 30998000 bytes, SHA integral correto |
| copy_checked do repositório | 30998000 bytes, releitura correta; consumidor confere seu buffer |
| Mesmo cp, filho com RLIMIT_FSIZE=26214400 e SIGXFSZ ignorado | Retorno 1, File too large, destino de 26214400 bytes |

O último controle é **sintético e deliberado**. O destino tem SHA
ffac0a4f38e5ffa7c92a2ad39d98b26a33795b13ddd2b43a7eb74ae28f129099,
igual ao prefixo histórico. Demonstra um mecanismo compatível com erro
explícito; não demonstra que cp foi usado ou que esse limite/erro existiu
no processo histórico.

## Encerramento por hipótese

| Hipótese | Evidência e alcance |
|---|---|
| Corte codificado nos scripts/workflows inspecionados | Busca negativa nas duas revisões; nenhum limite encontrado nesse escopo |
| Ferramentas testadas sempre cortam o módulo em 25 MiB | Excluída nas versões/operações atuais; cópias completas passaram |
| Limite global ativo de 25 MiB no destino/processo atual | Excluído nesses controles; arquivo maior foi escrito/lido, RLIMIT_FSIZE atual é ilimitado |
| Limite de processo no incidente | Compatível com o controle, mas não identificado; estado histórico não retido |
| Interrupção, escrita parcial ou alteração posterior | Permanecem possíveis; faltam logs e identidade do escritor histórico |
| Cota, filesystem, buffer ou transferência histórica | Sem atribuição ou exclusão histórica; controles atuais não reconstituem aquelas condições |

Uma cota agregada não foi medida historicamente. Espaço livre e cópia
maior atuais não provam ausência de cota noutro momento, usuário, diretório
ou processo. O hash do tarball ancora a origem; cada consumidor deve
verificar os bytes que efetivamente processa.

Reabrir a atribuição exige material novo: cópia defeituosa preservada,
trilha de escrita/transferência ou recorrência com identidade/limites/erros
capturados. Repetir cópias bem-sucedidas sozinho não identifica a origem.
Segue a [investigação do mecanismo de layout](capture-a0-image-producer-hzc2.md).
Não se adotou preenchimento, strip como política nem outra geometria.

## Reprodução

```sh
python3 scripts/test_capture_a0_handoff.py
python3 scripts/check_capture_a0_handoff.py \
  --stock-boot /insumos/boot.img \
  --candidate-artifacts /insumos/S21-HZC2-alinhado-completo-20261102.tar.gz \
  --source /insumos/Kernel.tar.gz --output-dir /saida/nova
```

Linux com memfd/seals, GNU cp, Python e objetos Git das duas revisões.
Runner offline; retorno 2 significa investigações concluídas com A0 aberto,
1 significa recusa/erro. Produz copy-origin.json e image-producer.json.
Versão do cp, resultados e hashes de implementação/insumos constam nos JSON.
Espaço livre e caminhos dos diagnósticos são voláteis; não se exige igualdade
do relatório inteiro entre execuções. [Validação da rodada](references/capture-a0-handoff-validation-20261103.json).

A0 permanece aberto para causas sem atribuição, pacote/comprimentos,
assinatura/aceitação Samsung, SignerVer03, vbmeta pai, KMI e política runtime.
A1 não começou; sem decisão OEM ou ação no aparelho. Somente texto no Git.
