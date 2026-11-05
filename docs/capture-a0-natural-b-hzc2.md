# A0: protótipo B com comprimentos naturais e arquivo de tamanho fixo

Rodada de 04/11/2026 UTC, base 0261215 do PR #90. O usuário delegou a
escolha com "Faca do jeito que for melhor prossiga". A decisão desta rodada
é **B para protótipo offline**: Image e ramdisk nos comprimentos naturais,
274 módulos do build alinhado com strip-debug e arquivos de 67108864 bytes.
Isso não autoriza instalação, decisão OEM, operação no aparelho ou A1.
Os PRs #89/#90 permanecem separados e abertos, sem merge em main.

## Resultado e alcance da decisão

O [montador novo](../scripts/capture_a0_natural.py) implementa outra geometria
interna. Não modifica o montador antigo de igualdade exata. Manter o tamanho
total é uma variante de B; não significa manter as posições internas.
Não se acrescentaram bytes artificiais à Image nem ao gzip. O alinhamento
de páginas e o espaço livre do contêiner são regiões separadas dos payloads.

O [runner](../scripts/check_capture_a0_natural.py) montou os dois arquivos
com payloads reais. Os controles stock reconstruíram cada arquivo byte a
byte, inclusive por reassembly independente dos intervalos. Os protótipos
passaram hashes/RSA com a chave de laboratório; variantes com assinatura
antiga e uma alteração posterior de payload foram recusadas pelo AOSP.
O [relatório completo](references/capture-a0-natural-b-hzc2.json) inclui
todos os intervalos originais/novos, tamanhos, hashes e saídas dos controles.

| Arquivo de laboratório | Bytes | SHA-256 |
|---|---:|---|
| boot.img | 67108864 | ca760185024c4492745413189c28639aa841decbc3bed3cc827c6dbe31c2daf0 |
| vendor_boot.img | 67108864 | 5efffbccc3ecbe616de9e6089cfb5600963189ecf41c27723020001980df4602 |

Image: 29403648 bytes, SHA 9614f9a0ec8e83177ccb2010a585a128fd11f028cb46c417f2c1dbed2c2fd571.
Gzip strip-debug: 11774882 bytes, SHA 7bc62305b3467bd1dbc92acbd346e1db3a96cd7e037367ce4a9e7b94817fbcd9.
A preparação nativa foi novamente executada sobre o tarball preservado e a
fonte Samsung conferidos: 275 entradas seladas, objcopy e 274 strip, sem
recompilar o kernel. Image e ambos os perfis de ramdisk repetiram o PR #86.
Não se refez a conferência individual dos 2133 payloads nem uma conferência
externa no computador do usuário.

## Mapa de intervalos implementado

Coordenadas relativas ao início do arquivo, fim exclusivo. O JSON inclui
também cada hash e o mapa stock completo. Padding é zero e contabilizado;
templates com padding não zero são recusados, em vez de descartá-lo.

| Região | boot.img [início, fim) | vendor_boot.img [início, fim) |
|---|---|---|
| Header Android v3 | [0, 1580) | [0, 2112) |
| Padding do header | [1580, 4096) | [2112, 4096) |
| Kernel | [4096, 29407744) | Não se aplica |
| Padding do kernel | [29407744, 29409280) | Não se aplica |
| Ramdisk | [29409280, 30110838) | [4096, 11778978) |
| Padding do ramdisk | [30110838, 30113792) | [11778978, 11780096) |
| DTB | Não se aplica | [11780096, 12170036) |
| Padding do DTB | Não se aplica | [12170036, 12173312) |
| Extensão opaca completa | [30113792, 30117888) | [12173312, 12177408) |
| VBMeta | [30117888, 30120000) | [12177408, 12179520) |
| Padding até o footer | [30120000, 67108800) | [12179520, 67108800) |
| Footer AVB | [67108800, 67108864) | [67108800, 67108864) |

Somente kernel_size de boot e vendor_ramdisk_size de vendor_boot mudam
nos headers Android; os demais campos são conservados. Ramdisk de boot
701558 bytes e DTB 389940 bytes foram extraídos e conferidos sem alteração.
O deslocamento do DTB é -241664, não o delta bruto -242375 do gzip.

A extensão opaca inteira de 4096 bytes de cada template é movida sem
alteração de conteúdo. O intervalo autenticado termina em 30114592 no
boot e 12174096 no vendor_boot: cobre respectivamente os primeiros 800/784
bytes dessa extensão. O restante não é promovido a cobertura do descriptor.
SignerVer03 continua sendo bytes preservados, sem validação própria.

Os footers atualizam original_image_size e vbmeta_offset, conservam
vbmeta_size=2112, versão e reservados. O descriptor atualiza image_size e
digest. SHA256_RSA4096, salt, nomes das partições, flags, rollback, layout
e header VBMeta permanecem no perfil do template. Chave e autenticação
passam à fixture de laboratório AOSP, diferente da stock. A release string
preservada é metadado herdado, não identificação do montador novo.

## Conferência independente e consumidores

O runner lê stock, payloads, ferramenta e fixture uma vez, verifica os
buffers e usa esses mesmos bytes. As imagens e a ferramenta são fornecidas
ao subprocesso em memfd selado. Um adaptador altera somente a resolução de
nomes ImageHandler para esses descritores e a herança do descritor da chave
nas chamadas OpenSSL. Parsers, hashes, RSA e comparação da chave esperada
continuam sendo os do avbtool fixado.

Trata-se de execução da API upstream Avb.verify_image com adaptador de I/O,
**não uma alegação de CLI upstream sem alterações de ambiente**. O código
do adaptador e seu hash estão no runner/relatório. O montador também faz
RSA local; os controles independentes recusam hash-only na assinatura e
payload adulterado no digest. Foram dez verificações upstream, cinco por
arquivo: stock, metadados antigos, hash-only, laboratório e adulterado.

Os 274 módulos do ramdisk têm tamanhos/hashes strip-debug esperados; os
nomes de dependência declarados estão presentes. Os demais membros CPIO,
incluindo arquivos de carga/dependência, preservam os dados stock.
modules.dep não foi regenerado; essa conferência não valida ordem de carga,
ABI, relocations, CFI, RKP ou comportamento runtime.

## VBMeta pai e fontes fixadas

Na montagem original, o pai não foi fornecido nem modificado. A
[comparação posterior com stock](capture-a0-parent-hzc2.md) recuperou o
candidato do BL HZC2 e conferiu sua identidade e RSA embutida. Os dois
filhos stock passam seus hashes diretos; os dois protótipos B divergem.
Assim, esse pai inalterado não aprova B. A identidade/uso do pai instalado
e a confiança no aparelho continuam sem demonstração. O relatório e o
README dentro do bundle preservam o estado histórico daquela montagem.

- Se o pai contiver um hash descriptor para o componente alterado, o digest
  correspondente precisa ser recalculado e a autenticação do pai refeita.
- Se delegar por chain descriptor, a atualização do filho pode dispensar
  mudança no pai somente mantendo a chave delegada e as condições aplicáveis.
  A chave de laboratório desta rodada é diferente da stock: uma delegação
  para a chave stock não passa a confiar nela automaticamente.
- Se houver ambos os vínculos ou verificações Samsung adicionais, todos
  precisam ser examinados. Hash/RSA local não define confiança no aparelho.

As fontes AVB foram baixadas por Gitiles no commit
25a14f7e3e6493a7f1a42aa9f78209d4dbe848e9, tag android-15.0.0_r1.
Os [pins primários](references/capture-a0-natural-b-primary-pins-20261104.json)
registram SHA-256, tamanho, Git blob e linhas testemunhas dos quatro headers.
Em particular, [avb_vbmeta_image.h](https://android.googlesource.com/platform/external/avb/+/25a14f7e3e6493a7f1a42aa9f78209d4dbe848e9/libavb/avb_vbmeta_image.h)
tem 11913 bytes, SHA 0979deac8902cbcbd0ec1d2f94af6692ab954fe698b1bd2e8b193b7eec3a3607,
blob f9cbac447d0941429d813ca0aadef4401e7ec8d7: é o mesmo blob exibido
na referência main/master citada no chat. VERY IMPORTANT está na linha 266;
a exigência de chave conhecida está nas 268–270 e rollback nas 275–280.
As coordenadas são as linhas do arquivo bruto, não da página HTML.

## Matriz pareada do truncamento

A [anterioridade do pré-registro](references/capture-a0-copy-paired-preregistration-20261104.json)
é **não verificável no remoto**. Segundo o relato da sessão, o plano foi
commitado localmente em 07a10d3 antes dos ensaios e o código local usado foi
78e4d86. Ambos existem no histórico local preservado, mas o GitHub não os
encontra pelos hashes completos. O primeiro commit remoto que reúne plano
e resultados é 681f174; ele não demonstra a ordem entre ambos. Datas de
commits locais tampouco são atestação independente do momento dos ensaios.
Os 30 casos ficam classificados como **resultados observados, sem
pré-registro com anterioridade verificada no remoto**; não constituem
confirmação prospectiva de previsões. A [correção de proveniência](references/capture-a0-copy-registration-provenance-hzc2.json)
preserva os identificadores completos, hashes e a referência ao plano
original em 681f174. Publicar os objetos agora não provaria sua anterioridade
em relação à execução histórica.

Foram cinco condições, duas extensões e três repetições, em ordem sorteada
com Random(210090). Mesmo diretório/nome-base payload, objeto novo a cada
tentativa, mesmo buffer DHD de 51582680 bytes conferido.

| Segunda chamada | .ko íntegros imediatos/tardios | .bin íntegros imediatos/tardios |
|---|---:|---:|
| Ausente, serial | 3/3 e 3/3 | 3/3 e 3/3 |
| Durante escrita, somente espera | 3/3 e 3/3 | 3/3 e 3/3 |
| Durante escrita, espera e nota não relacionada | 3/3 e 3/3 | 3/3 e 3/3 |
| Após fechamento/readback, somente espera | 3/3 e 3/3 | 3/3 e 3/3 |
| Após fechamento/readback, espera e nota | 3/3 e 3/3 | 3/3 e 3/3 |

Os horários registrados situam as chamadas nas fases descritas, sem tentativa descartada; isso não verifica a anterioridade do plano.
Inotify do arquivo/diretório encerrou as 30 janelas sem erro/overflow;
eventos não identificam PID. strace foi tentado e recusado por
PTRACE_TRACEME/SETOPTIONS com Operation not permitted; não houve os dois
ensaios adicionais condicionados à disponibilidade do ptrace.

[Resultados e eventos por caso](references/capture-a0-copy-paired-results-20261104.json).
Todos os buffers imediatos e tardios têm o hash integral esperado. Nenhuma
cópia recusada nova foi produzida. A observação tardia é sete segundos após
o readback, contra quatro no controle anterior. As chamadas exec_command
se sobrepõem dentro de uma mesma execução de orquestração functions.exec;
isso não recompõe todo o estado histórico da sessão/API/filesystem.

**Conclusão: não recorrência nesta matriz.** Não se identifica escritor,
não se estabelece regra de extensão e não se refutam as observações do PR #90.
O mecanismo continua não identificado, inclusive para o Mali de 25 MiB.
Não se troca uma atribuição ausente por uma explicação presumida de sandbox,
sincronização ou Linux Mint. Foram registrados 30 casos, em concordância com a contagem do plano declarado; sua anterioridade continua não verificável no remoto.

## Reprodução, artefato e gates

```sh
python3 scripts/check_capture_a0_sizes.py \
  --stock-dir /insumos/raw --candidate-artifacts /insumos/S21-HZC2-alinhado-completo-20261102.tar.gz \
  --source /insumos/Kernel.tar.gz --tools-root tools/root --output-dir build/medicao-nova
python3 scripts/check_capture_a0_natural.py \
  --stock-dir /insumos/raw --image build/medicao-nova/Image \
  --vendor-ramdisk build/medicao-nova/strip_debug.cpio.gz \
  --avbtool /insumos/avbtool.py --test-key /insumos/testkey_rsa4096.pem \
  --output-dir build/prototipo-b-novo
python3 -m unittest discover -s scripts -p 'test_capture_a0*.py'
python3 scripts/validate_baseline.py --output-dir build/baseline-b-novo
```

Os runners de medição/montagem retornam 2 após concluir com A0 aberto, 1 em
recusa. A [orquestração dos controles](../lab/a0_copy_paired.js) exige a API
de execução da sessão; dois scripts comuns não equivalem a essa fronteira.
O [probe](../scripts/capture_a0_copy_probe.py) pode ser usado isoladamente,
sem transformar essa execução em reprodução da sobreposição da API.

O pacote privado S21-A0-B-prototipo-offline-20261104.tar.gz contém os dois
protótipos, README, relatório e manifesto. Sua
[identidade](references/capture-a0-natural-b-artifact-20261104.json) registra
hashes e conferência dos cinco membros no mesmo buffer do tarball.
Os binários permanecem fora do Git. Não é pacote aprovado para flash.

Validação: 34 controles novos, 346 testes A0 e baseline obrigatório 9/9.
A [validação da rodada](references/capture-a0-natural-b-validation-20261104.json)
fixa resultados, implementações e evidências. A escolha de B resolve a
decisão de protótipo offline da Fase 2, sem fechar os gates de aceitação.
SignerVer03, vbmeta pai, confiança Samsung, dez origens KMI/duas listas e
política runtime continuam abertos. Atribuições históricas continuam não
identificadas; conferência externa do tarball preservado ainda pendente.
A0 aberto, A1 não iniciado, nenhuma decisão OEM ou ação no aparelho.
