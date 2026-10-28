# HZC2: log de boot e intervalos observados no bugreport

Análise de **2026-10-27 (Campo Grande)**, base `436b539` após PR #41.
A nova coleta por ADB/dumpstate conserva um LAST KMSG com mensagens EPBL,
BL2 e LK até `Starting kernel...`. Ela estende a [coleta de 24/10](dram-observed-hzc2.md),
que já havia recuperado texto do bootloader. Não constitui o primeiro canal
de log stock nem demonstra um novo boot independente da captura anterior.
Nenhum Odin, Download, desbloqueio ou flash foi realizado nesta entrega.

## Origem e reprodução sem publicar o relatório privado

| Artefato privado | SHA-256 |
|---|---|
| bugreport-s21.zip | `5a8e98c0f6dd657e87d099bfa7b26f1dd512ba39220ad85aecded709d79c40ef` |
| Membro dumpstate-2026-10-27-18-23-28.txt | `f24e96c70d4ed17098b3bb470d15380f5466efb357011e41759cfcd4b1451673` |
| Corpo LAST KMSG, linhas 408667–409664 | `dc155d60764ad35dba56eafb9c6f10167ae2b6a2adaaa5e91219440096e1d931` |

O corpo tem 56417 bytes. O nome do membro indica o horário da coleta,
não data cada mensagem persistida. O extrator usa `main_entry.txt`, exige
o hash exato do ZIP e emite somente quatro propriedades e 24 eventos por
lista de permissão, com linhas de origem e timestamps quando presentes.
Não emite cmdline, identificadores, histórico, dados de aplicativos ou logs
completos. Os arquivos de recovery HZA6 não são usados como boot HZC2.

```sh
python3 scripts/inspect_bugreport_boot.py /caminho/bugreport-s21.zip
python3 -m unittest discover -s scripts -p test_bugreport_boot.py
python3 -m unittest discover -s scripts -p test_lk_memory_banks.py
python3 scripts/check_lk_memory_banks.py /caminho/sboot.bin \
  --scenario docs/references/bugreport-bank-inputs-20261027.json
```

[Extrato público](references/bugreport-boot-20261027.json),
[cenário condicional](references/bugreport-bank-scenario-20261027.json) e
[validação](references/bugreport-boot-validation-20261027.json).
Limites de host: ZIP 64 MiB, membro 192 MiB, linha 4 MiB, seção 2 MiB e
dois milhões de linhas. O ZIP contém uma linha alheia ao boot de cerca de
3 MiB; ela é consumida para o hash, sem exportar conteúdo. O extrator não
extrai caminhos no filesystem. Hash fixa identidade, não autentica o telefone.

## Identidade e acesso

As propriedades no relatório informam bootloader `G998BXXSJHZC2`,
flash.locked=1, vbmeta.device_state=locked e verifiedbootstate=green.
O próprio LAST KMSG inclui BLDP build_version=G998BXXSJHZC2. São fontes
observadas distintas dentro do mesmo artefato, não medições independentes.

A [coleta ADB anterior](references/adb-access-20261027.json) conseguiu listar os links de partição: steady→sda3,
harx→sda8, uh→sda9, boot→sda13 e vendor_boot→sda14. Não demonstrou leitura
dos dispositivos de bloco. `dmesg` direto retornou `klogctl: Permission denied`;
os outros arquivos vazios não conservaram stderr, e a negação foi relatada
pelo usuário. O acesso do serviço dumpstate não se transfere ao domínio shell.
Não repetir os nós negados nem solicitar Odin como continuação deste trabalho.

## Valores do LK e comparação com a análise estática

| Mensagem | Base | Tamanho | Fim exclusivo calculado |
|---|---|---|---|
| SEC_DRAM | 0xb8a00000 | 0x07600000 (118 MiB) | 0xc0000000 |
| Harx | 0xc0000000 | 0x01400000 (20 MiB) | 0xc1400000 |
| SEC_PGTBL | 0xe0000000 | 0x01300000 (19 MiB) | 0xe1300000 |

As mensagens SEC_DRAM correspondem aos formatos em sboot+0x216268/0x216280,
impressos em 0xfae18/0xfae28 depois das consultas soc_info. SEC_PGTBL usa
0x216408/0x216420 em 0xfaec8/0xfaed8, após o tratamento local do retorno.
Logo, os logs expõem valores formatados pelo LK; tamanho em W não conserva
os bits altos do retorno X0 do serviço. Não equivalem a uma captura de todos
os registradores SMC ou à execução do provedor seguro pelo analisador.

Harx coincide com as constantes de GET_HARX_INFO já decodificadas na
[análise do intervalo omitido](lk-harx-memory-gap.md). O log também anuncia
inicialização e entrega do callback/buffer de crash, corroborando o caminho
nominal que antes tinha apenas evidência estática. A mensagem não fornece os
registradores de entrada do kernel, nem demonstra sucesso de todo serviço Harx.

SEC_DRAM termina exatamente na base Harx. Aplicando esses campos ao
[modelo do construtor](lk-memory-bank-constructor.md), com as hipóteses
explícitas do cenário, as primeiras solicitações seriam:

| Chamada no arquivo | Base | Tamanho |
|---|---|---|
| 0xfaf34 | 0x80000000 | 0x38a00000 |
| 0xfaf50 | 0xc0000000 | **0** |
| 0xfb678 | 0xc1400000 | 0x1ec00000 |
| 0xfb690 | 0xe1300000 | 0x1ed00000 |

O zero decorre de base_Harx − (base_SEC_DRAM + tamanho_SEC_DRAM).
O trecho não suprime essa chamada por tamanho zero. Isso é uma consequência
condicional da aritmética já conferida; não prova que o editor criou um nó
vazio, que o FDT final seja inválido ou que haja RAM disponível para a sonda.
Com 12 GiB fornecidos ao getter, seguem vinte solicitações altas de 512 MiB;
a mensagem `12.000000GB` é observada, mas X25/getter não foi capturado.
O cenário conserva `runtime_observed=false` e `is_final_fdt=false`.

## Token e configuração pós-cópia

A mensagem `[I]get_token_mode:316 Token doesn't exist` liga-se ao formato em
sboot+0x242068, com linha 316 carregada em 0x157410. O ramo 0x1572ec vai para
0x157408 quando a comparação do prefixo esperado `ENG` retorna não zero.
Esse caminho segue para limpeza em 0x157420 e evita o despacho do comando 21
e a publicação nominal em 0x1573e0 nessa invocação.

Portanto, a mensagem **não prova partição vazia, inexistência física de um
token, bitmap global zero ou ausência de outros escritores**. Não se pode
tratar a implementação do escritor de modos como um caminho executado neste
registro só porque ela existe no firmware. O parser continua uma investigação
estática separada; a autenticação da Image também não foi resolvida por isso.

Os eventos `Send info to CP secure table 21` e sucesso nominal de fingerprint
coincidem com as strings dos helpers do [dispatcher pós-cópia](lk-postcopy-policy-hzc2.md).
O número 21 aqui é índice da tabela CP, não o comando 21 EM_CMD_GET_MODES_BIT.
Também há mensagens de DTB entrada 0, DTBO entrada 7 e overlay completo.
Elas registram decisões/retornos nominais, sem entregar os bytes do FDT final
ou substituir a verificação de assinatura de uma imagem própria.

## Estado após esta coleta

O log stock foi recuperado; seis valores de intervalos e ramos nominais têm
agora evidência textual do aparelho. Nenhuma Image própria ou R10 foi executado.
Permanecem abertos: FDT final/bancos/reservas, estado de entrada, percurso de
carga compatível e aquisição dos 128 bytes do diagnóstico enquanto válidos.
O log Harx via sysfs continua negado; LAST KMSG do LK é outro canal, e não
um dump da região Harx ou um leitor arbitrário de RAM.

Continuação: o [editor do banco zero](lk-zero-bank-editor-hzc2.md) foi seguido
e executado em fixtures. Com espaço, ele conserva o nó/reg de tamanho zero;
com falhas, pode deixar edições parciais e retornar zero apesar de reg ausente.
Isso resolve a semântica local; transformações posteriores e FDT físico
continuam abertos. Não há nova coleta a solicitar ao usuário nesta etapa.

## Continuação de 27/10 — método PSCI após a base

O [editor posterior do LK](lk-psci-final-edit-hzc2.md) pode trocar
/psci/method de smc para hvc sob o flag Harx. O bugreport contém a mensagem
do ramo após setprop não negativo. Vinte e quatro casos QEMU conferem
essa rotina; não são captura do FDT final ou execução de serviço PSCI.
A main de uma CPU permanece sem sondagens SMC/HVC.
