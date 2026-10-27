# Log Harx: fonte e coleta bloqueada

Evidência de 2026-10-22 UTC, usando as fontes Samsung e imagens stock HZC2
já recebidas. Foi identificado um atributo novo, **exynos_el2_log**, distinto
dos três nós proc que estavam ausentes/ocultos na coleta anterior. O relatório
recebido confirmou o atributo, mas a sessão shell não teve permissão de
leitura. Nenhuma página de log foi capturada nesta tentativa.

## O que sustenta essa tentativa

| Evidência | Resultado |
|---|---|
| Fonte `drivers/soc/samsung/exynos-el2.c` | cria DEVICE_ATTR exynos_el2_log com modo 0644, callback show e callback store separados |
| Header `exynos-hvc.h` | GET_EL2_LOG_BUF = 0xc6000043; GET_HARX_INFO = 0xc6000020 |
| Configuração embutida na Image stock | CONFIG_EXYNOS_EL2=m, CONFIG_ARM64_4K_PAGES=y, CONFIG_IKCONFIG=y |
| DTB base stock | nó /el2_dynamic_lv3, compatible samsung,exynos-el2-dynamic-lv3, sem propriedade status nessa base |
| Harx recebido | índices 3/4 retornam RAM log 0xc1200000, tamanho 0x200000; getter 0x1cf0 pede página de 0x1000 bytes |

O getter do driver aloca uma página zerada, passa seu endereço físico ao HVC
0xc6000043 com os demais argumentos zero e devolve uma string de no máximo
PAGE_SIZE-1 bytes. O modo 0644 previsto no fonte agora também aparece no ls
do relatório recebido, sem que isso tenha permitido a leitura pelo shell.

CONFIG_EXYNOS_EL2=m também não prova que o módulo tenha sido carregado.
A criação dos atributos depende da inicialização e do probe, que antes
registram buffers, IRQ e dados com o Harx. A presença do atributo corrobora
esse caminho de criação, mas não comprova todo o estado do driver/firmware.
O mecanismo exato do bloqueio e as alterações finais do DTB continuam abertos.

O caminho confirmado no relatório é:

```text
/sys/devices/platform/el2_dynamic_lv3/exynos_el2_log
```

Há uma segunda forma de localizar o mesmo atributo pelas ligações do driver
em /sys/bus/platform/drivers/exynos-el2. O coletor escolhe **um** caminho e
não lê seus aliases em sequência.

## A leitura tem estado no firmware

O Harx copia o log por 0xbb0. Entre 0xc40–0xc48 atualiza o cursor de leitura;
o ramo de wrap também atualiza esse estado em 0xc6c. Portanto, ler esse
atributo pode avançar o cursor, mesmo sem escrever em sysfs.

O callback store do driver é diferente: chama o mesmo serviço com argumento
de reset igual a 1. O handler Harx segue por 0xb8c e pode voltar o cursor a
0xc1200000. **O coletor nunca escreve nesse atributo ou solicita reset.**
Ele faz uma captura limitada, sem laço por páginas ou nova tentativa automática.

O caminho Harx 0x38c imprime informações de DRAM, reserva para segurança e
base/tamanho Secure DRAM. Se essas mensagens ainda estiverem disponíveis na
página retornada, poderão trazer valores que a análise estática não fechou.
O log pode estar vazio, já consumido ou com wrap; uma página não garante
mensagens de boot, o mapa completo ou o estado atual desses valores.

## Procedimento da tentativa concluída

Esta execução já foi concluída e retornou UNREADABLE. O procedimento abaixo
fica como registro; não é uma solicitação de repetir a coleta nas mesmas
condições.

Salve [collect_el2_log.sh](../scripts/collect_el2_log.sh) em Download e,
na sessão rish já usada, execute:

```sh
sh /sdcard/Download/collect_el2_log.sh
```

Será criada **Download/s21-el2-log**, recusando sobrescrever uma pasta
existente. O script consulta apenas o atributo novo identificado pelo fonte,
faz uma captura de até **4096 bytes com timeout de 5 segundos**, quando
legível, e grava os resultados nessa pasta. Não muda permissões, carrega
módulos, reinicia o aparelho ou acessa FDT, iomem e os logs já bloqueados.

Foi recebido **s21-el2-log/report.txt**. O relatório registra
existência, permissões, caminho escolhido, retorno da captura e bytes.
O ramo de leitura não foi executado, portanto não há **el2-log.txt** desta
captura a solicitar. Em outras condições, esse arquivo conteria texto do
firmware, sujeito a revisão antes de compartilhar; erro/timeout poderia
deixar uma captura parcial. Não se confunde isso com o resultado atual.

Se aparecer ABSENT/UNREADABLE ou negação na leitura, o resultado encerra essa
tentativa nas condições atuais. Não repetir automaticamente, mudar permissões
ou pedir root. Um acesso bem-sucedido abriria um canal de evidência; não
autoriza boot/flash nem substitui o FDT final.

## Resultado recebido — 2026-10-22 UTC

Relatório de 807 bytes, SHA-256
`9aacaa65650eba56609b1f5755073dee98742c2b28c6181fd4ed9a21a3f7fead`.
Timestamp informado: 2026-10-22 01:21:21 UTC, equivalente a 2026-10-21
21:21:21 em Campo Grande; relógio não verificado independentemente.

| Campo | Resultado observado |
|---|---|
| Modelo / build / bootloader | SM-G998B / AP3A.240905.015.A2.G998BXXSJHZC2 / G998BXXSJHZC2 |
| Sessão | uid=2000(shell), gid=2000, contexto u:r:shell:s0 |
| Atributo | /sys/devices/platform/el2_dynamic_lv3/exynos_el2_log existe |
| Metadados ls | -rw-r--r--, root:root, tamanho exibido 4096 |
| Resultado do teste de acesso | UNREADABLE |
| Captura de conteúdo | não iniciada; nenhum READ_EXIT ou bytes de log registrados |

O tamanho 4096 exibido em sysfs não é uma medição do conteúdo do log. Os
bits 0644 também não garantem acesso para esse domínio: o teste de leitura
foi recusado. O relatório não inclui contexto do arquivo ou decisão de
auditoria que permita atribuir a causa especificamente a SELinux ou a outro
mecanismo. Registra-se a restrição, sem escolher uma causa por hipótese.

Pelo fluxo do coletor v1, o ramo UNREADABLE não abre o atributo e não chama
o getter Harx. Assim, esta execução não consumiu uma página pelo coletor;
não se conclui nada sobre leituras feitas por outros processos ou o cursor
global. A presença do nó corrobora a ligação fonte/DT, sem revelar valores
de DRAM, SEC_PGTBL, FDT final ou estado de entrada no payload.

Os [metadados conferidos](references/harx-log-runtime-20261022.json) foram
registrados separadamente da evidência estática; o relatório original não
foi publicado no Git. **Decisão:** esse canal está indisponível para a sessão
observada. Não repetir a coleta, solicitar um log não capturado ou pedir
mudanças de privilégio como próximo passo automático.

## Reprodução offline das evidências

```bash
python3 scripts/check_harx_log_evidence.py /caminho/Kernel.tar.gz \
  /caminho/boot.img /caminho/vendor_boot.img
python3 scripts/inspect_el2_hzc2.py /caminho/sboot.bin \
  /caminho/uh.bin /caminho/harx.bin
python3 -m unittest discover -s scripts -p 'test_harx_log.py' -v
```

O primeiro comando exige os hashes dos três arquivos recebidos, lê apenas
seis membros esperados do TAR sem extrair caminhos, verifica seus hashes e
liga fonte, configuração embutida e nó da árvore base. O resultado fica em
[harx-log-evidence.json](references/harx-log-evidence.json). Esse relatório
não contém código ou dados privados do telefone.

A configuração extraída tem 203.018 bytes, SHA-256
`55dde3bb7c52e99eccdb82b925a4b831c03fd32a19a2b64bdf7bda993e92a2e1`.
O marcador IKCFG_ST está em Image+0xed2130. O leitor exige um par único de
marcadores e um único stream gzip completo, com limite de saída de 2 MiB;
recusa cauda, concatenação, truncamento e definições de configuração duplicadas.

O inspetor BL foi ampliado para índices 3/4 de GET_HARX_INFO e para os
offsets que sustentam o avanço/reset do cursor. Sua saída está em
[el2-hzc2.json](references/el2-hzc2.json). São instruções inspecionadas,
não chamadas executadas no aparelho.

## Correção de nomenclatura e validação

O header também identifica **0xc6000040** como
SET_EL2_CRASH_INFO_FP_BUF. O handler Harx termina por 0x1bc8 → 0xda0 e
grava o callback em 0xe10. A descrição anterior de “inicialização Harx”
para essa chamada era ampla demais; foi corrigida para registro de callback
e buffer de crash. A observação de que o flag LK é marcado antes do HVC
permanece válida, agora limitada ao resultado desse registro.

Sete testes novos passaram: config gzip e duplicidades; atributo ausente;
recusa de pasta existente; captura exata com limite; seleção de um único
caminho/alias; permissões da saída; fallback do driver; timeout sem retry.
São **40 testes de host** com as suítes LK/EL2 anteriores. Os testes não
emulam SELinux, o driver ou o serviço Harx e não provam acesso pelo rish.

O relatório do telefone já foi recebido e analisado. Os 40 testes de host
citados validam as ferramentas, não o acesso no aparelho; não foram repetidos
para esta atualização de documentação e metadados. O pacote já recebido
basta para continuar a investigação estática, incluindo soc_info e SEC_PGTBL,
que permanecem sem valores efetivos observados.

## Atualização de 2026-10-27 — observação por dumpstate

A [nova análise do bugreport HZC2](bugreport-boot-hzc2.md) conserva os
valores impressos de SEC_DRAM/SEC_PGTBL/Harx e a mensagem de prefixo do
token. Isso atualiza as lacunas históricas acima: há texto do bootloader
recuperado pelo serviço, mas o shell direto continua restrito. Não é dump
físico, FDT final ou prova de execução/aquisição do diagnóstico próprio.
