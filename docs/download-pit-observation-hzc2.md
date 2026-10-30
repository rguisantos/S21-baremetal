# Download USB e PIT observados no SM-G998B — 2026-10-30

O usuário forneceu uma transcrição do Heimdall no Mint 22.3/x86_64:
inicialização do protocolo, início de sessão, leitura bem-sucedida da PIT,
48 entradas, encerramento da sessão e liberação da interface. Isso demonstra
um canal físico de consulta pelo Linux no modo Download, sob o estado de
bloqueio informado. **Não houve demonstração de carga de imagem própria,
execução do diagnóstico/R10 no telefone ou aquisição de RAM.**

## Origem e alcance

- Texto recebido em 30/10/2026, 15.301 bytes, SHA-256
  `d418207fe970c4a6d19c7cf17f7980e3256e3dc4315e40da68fb2c144054b973`.
- A transcrição bruta permanece fora do Git. O
  [extrato estruturado](references/download-pit-observation-20261030.json)
  conserva os 12 campos de cada entrada e os rótulos numéricos exibidos.
- O comando solicitado foi `sudo heimdall print-pit --no-reboot`. Sua
  invocação e a versão do cliente não aparecem no trecho recebido. A operação
  [print-pit na referência Heimdall](https://github.com/Benjamin-Dobell/Heimdall/blob/3997d5cc607e6c603c6e7c0d07e42e9868c62af2/heimdall/source/PrintPitAction.cpp)
  inicializa a sessão, solicita a PIT e encerra a sessão; não chama o fluxo
  de envio de imagem. Essa referência não identifica a revisão instalada.
- O arquivo PIT binário não foi recebido. O hash acima identifica o texto,
  não os bytes originais da PIT nem uma imagem de partição.
- A mensagem `Resetting device...` é preservada no contexto do protocolo;
  não comprova reset do SoC, estado de RAM ou retenção através de reinício.

Os marcadores presentes, uma vez cada, são `Protocol initialisation
successful.`, `Session begun.`, `PIT file download successful.`,
`Ending session...` e `Releasing device interface...`. Não há mensagem de
erro no trecho fornecido; o código de saída do processo não foi capturado.

## Estado informado antes da consulta

ADB reconheceu SM-G998B/p3s e HZC2, com uid=2000(shell),
`ro.boot.flash.locked=1`, `ro.boot.vbmeta.device_state=locked` e
`ro.boot.verifiedbootstate=green`. O usuário informou a opção de desbloqueio
OEM ativa nas configurações e transcreveu `OEM LOCK: ON(U)` na tela Download.
A permissão da opção não foi tratada como desbloqueio efetivo.

O USB enumerou `04e8:685d`. A mesma tela foi transcrita com
`CURRENT BINARY: Samsung Official`, `KG STATE: COMPLETED (00)`,
Secure Download habilitado, `WARRANTY VOID: 1 (0x0e03)` e DDR de 12G.
São campos reportados, sem decodificação de `0x0e03`, certificação dos bytes
instalados ou alteração inferida do bloqueio OEM. FRP não foi informado.

## Mapeamento útil ao carregamento

O cabeçalho impresso contém `COM_TAR2`, tag CPU/bootloader `LSI9830`,
48 entradas e contagem de unidades lógicas 5. A tag não é uma identificação
medida do SoC e não substitui a identificação Exynos 2100 do projeto.

| Entrada na PIT | Identifier | Nome | Flash Filename | Block Count bruto |
|---:|---:|---|---|---:|
| 0 | 80 | BOOTLOADER | sboot.bin | 1024 |
| 4 | 91 | VDDCAL_FW | vddcal_fw.bin | 512 |
| 5 | 92 | VDDCAL_DATA | vazio | 64 |
| 6 | 93 | DDI | vazio | 256 |
| 16 | 8 | HARX | harx.bin | 768 |
| 17 | 9 | UH | uh.bin | 512 |
| 19 | 11 | DTBO | dtbo.img | 2048 |
| 21 | 13 | BOOT | boot.img | 16384 |
| 22 | 14 | VENDOR_BOOT | vendor_boot.img | 16384 |
| 23 | 15 | RECOVERY | recovery.img | 16384 |
| 31 | 23 | VBMETA | vbmeta.img | 16 |
| 32 | 24 | VBMETA_SYSTEM | vbmeta_system.img | 16 |
| 44 | 36 | LDFW | ldfw.img | 2048 |
| 45 | 37 | TZSW | tzsw.img | 384 |
| 46 | 38 | TZAR | tzar.img | 1920 |

Os nomes boot/vendor_boot/dtbo correspondem às
[imagens stock já examinadas](stock-firmware-hzc2.md). Sob a hipótese de uma
unidade de 4096 bytes, suas contagens equivaleriam a 64/64/8 MiB, os tamanhos
dos arquivos recebidos. Essa é uma comparação condicionada; o tamanho do
bloco lógico UFS não foi medido nesta coleta. Nenhum limite de bytes para
gravação é certificado por essa conta.

## Limites e próxima fronteira

- Foram conferidos 48 índices consecutivos, 48 identificadores e nomes
  únicos, 576 campos, tipo binário AP e dispositivo UFS em todas as entradas.
  Não é uma validação do formato binário PIT.
- `File Offset (Obsolete)` conserva os valores impressos 0..4. Não foi
  promovido a offset absoluto de uma imagem única ou a campo LUN decodificado.
  Regiões não devem ser unificadas ou classificadas como sobrepostas a partir
  desse rótulo sem o contrato UFS/PIT correspondente.
- UL_KEYS e USERDATA têm Block Count zero; isso não demonstra tamanho nulo,
  ausência de dados ou espaço disponível. O rótulo `Read/Write` de Attributes
  é metadado exibido pelo cliente, não autorização de gravação do bootloader.
- A entrada PIT #47 é SSP/Identifier 39. Esse índice pertence a esta tabela
  de partições e não resolve o slot47 da investigação NEWTIME.
- Uma sessão que lê PIT não demonstra leitura arbitrária de partições/RAM,
  serviço RDX, aceitação de assinatura, transporte de boot temporário ou
  execução de Image própria. A [matriz do diagnóstico](samsung-diagnostic-contract.md)
  continua aberta para carga, memória/coerência e recuperação do registro.

A consulta está concluída. Não é necessário repeti-la para confirmar as
mesmas entradas. O próximo trabalho é vincular os destinos observados ao
contrato de contêiner/validação e a um plano verificável de carga e recuperação,
antes de propor desbloqueio ou gravação. Não foram solicitados comandos de
flash, reparticionamento, limpeza ou desbloqueio neste procedimento.
