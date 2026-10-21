# UART0: seleção de console, MUIC e coleta de estado

Continuação de 2026-10-21 da [análise do console LK](lk-console-handoff.md).
Mesmos hashes de sboot e Kernel.tar.gz; análise estática, sem execução física.

## Por que o log pode continuar silencioso

Há quatro condições distintas a resolver: UART0/USI configurada, saída serial
habilitada pelo LK, roteamento do sinal para o exterior e acesso elétrico aos
pads. A fonte identifica gpg0-2/gpg0-3, mas não dá por si só a conexão na placa.

A rotina LK 0x18b560, usada antes de suprimir o fallback serial, referencia a
string **ifconn_get_jig_status** em 0x25eb28. Seu resultado não é um simples
flag fixo de UART. Ela consulta o tipo de interface em 0xd05f7c:

- Zero retorna zero. No chamador 0xedb98–0xedba4, zero provoca a gravação de
  1 no flag 0xd08a20 e bloqueia o fallback UART de 0x20c478.
- Com bit 0 ativo, chama 0x18acf0. A string usada pelo ramo identifica
  **ifconn_is_muic_jig_device**. O retorno é tratado como ADC.
- Na faixa 0x18–0x1d, usa a tabela de seis bytes em 0x25ead4:
  `00 00 f5 f5 00 00`. O salto é `0x18b6b8 + sign_extend(byte)*4`.
  ADC 0x18, 0x19, 0x1c e 0x1d chegam ao retorno 1; 0x1a e 0x1b retornam 0.
- Com bit 0 ausente e bit 1 ativo, chama 0x18b050, ramo identificado pela
  string **ifconn_is_pdic_jig_device**, e aceita retornos de 3 a 6.

Se ambos os bits estiverem ativos, o teste do bit 0 tem prioridade.
0x18acf0 é um dispatcher por objeto: lê o global 0x31fef8 e chama o ponteiro
em +0x88; sem callback, retorna zero após log. Isso não identifica um ADC
medido neste aparelho. A inicialização 0x18b6e8 escreve tipos 1 ou 2 nesse
global de tipo conforme retornos de outras rotinas; o estado real não foi
observado. Não há prova de que esses sejam todos os escritores possíveis.

## O que a fonte Samsung corrobora

O pacote completo contém um caminho específico MAX77705, além do sysfs MUIC
comum. O defconfig p3s consultado seleciona `CONFIG_MUIC_MAX77705=y`,
`CONFIG_MUIC_MAX77705_PDIC=y` e `CONFIG_CCIC_MAX77705=m`;
`CONFIG_MUIC_COMMON_SYSFS` está desativado. Portanto o driver específico
merece prioridade na análise. Isso não comprova os módulos carregados no
telefone nem substitui o DTB ativo.

Em `include/linux/muic/common/muic.h`:

| ADC | Nome na fonte | Comentário resistivo |
|---|---|---|
| 0x18 | ADC_JIG_USB_OFF | 255 kΩ |
| 0x19 | ADC_JIG_USB_ON | 301 kΩ |
| 0x1c | ADC_JIG_UART_OFF | 523 kΩ |
| 0x1d | ADC_JIG_UART_ON | 619 kΩ |

Os valores coincidem com os quatro aceitos pela tabela MUIC do LK. Essa
correspondência aumenta a evidência de controle do console por detecção de
jig; não demonstra um acessório funcional nem estabelece pinagem USB-C.
Não montar um adaptador apenas a partir dos comentários dessa enumeração.

Em `drivers/usb/typec/maxim/max77705-muic.c`:

- `switch_to_ap_uart()` chama `com_to_uart_ap()` somente para dispositivos
  reconhecidos como JIG UART OFF/ON, com ou sem VBUS.
- `com_to_uart_ap()` escolhe COM_OPEN quando `opmode == OPMODE_MUIC` e
  `rustproof_on`, na configuração PDIC consultada; caso contrário, COM_UART.
  Portanto `rustproof_on` não deve ser interpretado isoladamente.
- `uart_sel` exibe AP/CP; seu setter pode alterar o roteamento.
- `uart_en` exibe 1 quando `rustproof_on` está falso. Seu setter altera esse
  campo; sozinho não demonstra clock, pinmux ou transmissão em andamento.
- O grupo sysfs é instalado em `switch_device`. Os atributos específicos
  `uart_sel` e `uart_en` têm modos declarados 0664 e 0660; proprietário,
  SELinux e existência efetiva dependem do sistema em execução.

Não foram realizados writes nesses atributos. O código do kernel executa
depois do LK e não comprova que o roteamento sobreviva a outro handoff.

## Procedimento somente de leitura pelo Shizuku

Novo coletor: `scripts/collect_uart_state.sh`. Ele consulta somente propriedades
de modelo/build e atributos candidatos de `/sys/class/sec/switch/`: `uart_sel`,
`uart_en`, `adc`, `attached_dev`, `usb_state`. Registra ausência e falta de
permissão, sem tentar mudar modos, encaminhar UART ou solicitar root.

Com o script salvo em Download, execute **dentro do shell rish já funcional**:

```sh
sh /sdcard/Download/collect_uart_state.sh
```

Saída: `/sdcard/Download/s21-uart-state.txt`. O script recusa sobrescrever um
arquivo existente; para nova coleta, passe outro nome como primeiro argumento.
Não é necessário conectar acessórios para essa primeira leitura. Um relatório
com campos ausentes/negados é evidência de limite de acesso, não motivo para
repetir a coleta anterior de FDT/iomem/cmdline. O relatório não contém FDT ou
estado de EL/cache e não foi produzido no telefone nesta etapa.

## Verificação e próximos limites

Foram conferidos os saltos diretos e a tabela contra as palavras do sboot,
com desassemblagem Capstone. O inspetor de sboot agora emite a tabela e seus
destinos. A sintaxe do coletor foi verificada com `sh -n`; sua execução no
Android permanece pendente. Os drivers de hardware R10 não foram modificados.

A leitura dos atributos pode indicar a seleção AP/CP e o estado de detecção
no Android atual. Para teste físico do payload ainda faltam contrato de
carregamento e um meio de recuperar o registro. O código recebido permite
continuar a análise estática; não há novo pacote-fonte a solicitar.

### Hashes das referências adicionais

| Arquivo no Kernel.tar.gz | SHA-256 |
|---|---|
| `drivers/usb/typec/maxim/max77705-muic.c` | `bfdb034d7571ca233202221cdc8cdfe68bab3e837afea9c4b5a37378ed7acbab` |
| `include/linux/muic/common/muic.h` | `421c69aea93560473d01b412448ca50395c096346709375720fe7c839b44fd57` |
| `arch/arm64/configs/exynos2100-p3sxxx_defconfig` | `e0d7cfe4c8fceb31a5e44a9ba916c00338834a58011a44494e15120efe76c4fd` |

## Resultado recebido no aparelho

A coleta foi executada em 2026-10-21 no SM-G998B/HZC2 via uid=2000.
`uart_en` existe, modo 0660 system:radio, mas não é legível pelo shell;
`uart_sel`, `adc` e `usb_state` apareceram ausentes ou ocultos. `attached_dev`
retornou `No VPS`. No driver de referência, essa mensagem decorre de índice
negativo na busca da tabela de acessórios; não é prova de desconexão física.

A execução real do coletor está agora confirmada. Nenhum valor de habilitação
UART ou seleção AP/CP foi obtido e nenhum atributo foi alterado. Consulte
[coleta recebida e limites](runtime-collection.md#coleta-uartmuic-recebida--2026-10-21).
Não repetir a mesma coleta esperando obter permissões diferentes.
