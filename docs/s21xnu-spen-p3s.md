# S Pen no XNU do S21 Ultra (p3s)

Estado em 27/11/2026: decodificador dos pacotes pronto e conferido contra o
driver Samsung no host. Falta o driver XNU (barramento, interrupção) e a
publicação como caneta no HID. Nada executado no aparelho.

## O que o Android do aparelho mostra

Relato do usuário a partir do Android do próprio SM-G998B (não reproduzido
aqui): `sec_e-pen` é um dispositivo STYLUS separado do toque, associado à
tela de 1440 x 3200, com as faixas abaixo.

| Grandeza | Faixa |
|---|---|
| X | 0 a 7099 |
| Y | 0 a 15776 |
| Pressão | 0 a 4095 |
| Distância | 0 a 255 |
| Inclinação X e Y | -63 a +63 |

O driver Samsung declara ABS_X até `max_y` e ABS_Y até `max_x` quando os
eixos são trocados (`wacom_i2c.c`, `input_set_abs_params`). Os máximos
brutos do controlador são, portanto, x = 15776 e y = 7099.

## Hardware pelo device tree (FlopKernel `dc17ad0`)

| Revisão | `dtbo-hw_rev` | Barramento | Estado |
|---|---|---|---|
| r17 | 0x11 | `hsi2c_35` | disabled |
| r18 | 0x12 | `hsi2c_35` | disabled |
| r19 a r21 | 0x13 a 0x15 | `hsi2c_9` | okay |
| r22 | 0x16 a 0x20 | `hsi2c_9` | okay |

Os aparelhos de varejo caem no r22. Nele:
- `wacom@56`, `compatible = "wacom,w90xx"`, `ic_type = 0x233c` (W9020),
  `wacom,invert = <1 0 1>` (x invertido, eixos trocados), `max_pressure =
  0xfff`, `max_tilt = <63 63>`, `max_height = 0xff`;
- `hsi2c_9` = `hsi2c@105E0000`, pinos **gpp4-2 e gpp4-3**: o mesmo banco
  GPIO do toque (gpp4-0/gpp4-1, PERIC0 +0x80 = 0x10430080), que o driver
  de toque do s21xnu já usa em I2C por bit-bang;
- interrupção em **gpa2-4** (`epen-int-active`, função 0xf); pino FWE em
  gpm25-0 (gravação de firmware; fica em 0);
- alimentação `wacom_avdd` = LDO20 do S2MPS24, 3,3 V, `regulator-boot-on`:
  o bootloader deixa ligada;
- `w9020_p3_c*.bin` é o firmware do controlador, que já está gravado nele;
  o driver não precisa carregá-lo.

**O r17 que usei no contrato de placas não é o do varejo.** Refiz o contrato
p3s × t2s com o r22: 0 itens diferentes do r17, mesma janela de RAM do XNU
([evidência](references/s21xnu-board-contract-p3s-t2s-r22-20261127.json)).
Só a S Pen muda entre essas revisões.

## Pacote de coordenadas e decodificador

Pacote de 16 bytes (id 1 no nibble baixo do byte 0), como em
`wacom_i2c_coord_handler()`:
- byte 0: 0x80 pronto (caneta em alcance), 0x40 borracha, 0x20 botão
  lateral, 0x10 ponta encostada;
- x e y em big endian (bytes 1 a 4), pressão de 12 bits (5 e 6), altura
  (7), inclinação x e y com sinal (8 e 9).

Transformação: origem, inversão (que também nega a inclinação daquele
eixo), troca dos eixos, tudo em 16 bits sem sinal. O primeiro pacote pronto
só marca a caneta em alcance, sem publicar nada. Os seguintes publicam. Um
pacote pronto fora do painel depois da transformação é descartado sem
mudar o estado. Um pacote sem "pronto" encerra a caneta.

[`spen/sweet_wacom.h`](../lab/s21xnu-p3s/spen/sweet_wacom.h) implementa
isso em C puro, para o driver XNU usar, e converte para pixels.
[`spen/test_spen_decode.py`](../lab/s21xnu-p3s/spen/test_spen_decode.py),
no CI:
- busca o `wacom_i2c.c` do FlopKernel no commit fixado (SHA-256
  conferido);
- extrai sem mudança `epen_location_detect()`, `wacom_i2c_coord_modify()` e
  `wacom_i2c_coord_handler()`, grava os eventos Linux que eles publicam e
  compara com os do `sweet_wacom.h` pacote a pacote;
- compila com `-funsigned-char`, porque no arm64 o `char *data` do driver
  é sem sinal.

| Caso | Pacotes | Resultado |
|---|---|---|
| Roteiro: longe → aproximação → 5 movimentos sem tocar → 4 contatos → botão lateral → solta a ponta → solta o botão → 2 fora do painel → borracha → saída → longe | 19 | iguais; a aproximação não publica; a saída solta ponta, botão e ferramenta |
| Quatro cantos e centro, com inclinação | 15 | iguais; x do painel = y bruto, y do painel = 15776 − x bruto, inclinação (ty, −tx) |
| Aleatórios (semente fixa), metade fora do painel | 20 000 | iguais |

Quatro mutações no decodificador são detectadas: sem negar a inclinação,
sem descarte fora do painel, bit do botão trocado e estado não zerado na
saída. [Evidência](references/s21xnu-p3s-spen-decode-20261127.json).

## Falta

1. Driver XNU: I2C por bit-bang em gpp4-2/gpp4-3 no endereço 0x56 (ordem
   SDA/SCL a confirmar, como no toque, testando as duas), leitura de 17
   bytes na interrupção gpa2-4 (ou por varredura, como o toque faz) e
   escolha do barramento pela revisão da placa.
2. Publicar como caneta no SweetHID: o caminho de entrada do s21xnu só
   publica dedo (seção abaixo). O construtor do evento com inclinação foi
   corrigido no 0151.
3. No aparelho: o primeiro pacote, a ordem dos pinos e a resposta do iOS.

## Evento de caneta no XNU: patch 0151

O SweetHID do fork publica o toque como dedo
(`digitizerEvent(..., kIOHIDDigitizerTransducerTypeFinger, ...)` no
`sweet_touch`). Para a caneta, o evento com pressão e inclinação é
`IOHIDEvent::digitizerEventWithTiltOrientation()`, que o 0058 trouxe em
`iokit/Kernel/arm/hid/IOHIDEvent.cpp` (nenhum outro patch da série muda o
arquivo). Ele e os construtores Polar e Quality têm o mesmo defeito:
chamam `digitizerEvent()` sem o argumento `z`, então tudo depois de `y`
anda uma posição. O de inclinação ainda grava `xTilt` nos dois eixos.

| Campo | Entrada | Antes | Com 0151 |
|---|---|---|---|
| z | 11 | 22 | 11 |
| Pressão da ponta | 22 | 33 | 22 |
| Pressão da ponta, auxiliar 0 | 22 | 0 | 22 |
| Pressão auxiliar | 33 | 44 | 33 |
| Twist | 44 | 0 (vinha de `options`) | 44 |
| Inclinação (x, y) | (12, −34) | (12, 12) | (12, −34) |

Com pressão auxiliar zero, a caneta encostada chegaria ao iOS com pressão
de ponta zero. O [0151](../lab/s21xnu-p3s/xnu/0151-s21-hid-digitizer-orientation-args.patch)
passa `z` nas três chamadas e usa `yTilt`.

[`verify_hid_0151.py`](../lab/s21xnu-p3s/xnu/verify_hid_0151.py), no CI:
- recria o `IOHIDEvent.cpp` a partir do 0058 e aplica o 0151;
- extrai os quatro construtores reais, antes e depois, e compila em C++ no
  host com o `IOHIDDigitizerEventData` do próprio 0058;
- confere que o código antigo reproduz o defeito e que o novo entrega cada
  campo no lugar, nos construtores Tilt, Polar e Quality;
- com `options = 0x40` pedido pelo chamador, o código antigo perde o bit
  (o valor cai em `twist`, que vira 64, e o evento fica só com 0x01, posição
  absoluta); com o 0151 os três entregam 0x41 (ensaio da sessão paralela,
  agora no CI). 20 checagens.

No fork, `6a02361` e run
[46022394450](https://github.com/rguisantos/s21xnu/actions/runs/46022394450):
sucesso, 0151 aplicado, nenhum aviso nas linhas mudadas.

O 0151 não deixa texto no binário, então as marcas do kit do segundo boot
param no 0150. O workflow do fork agora imprime o SHA-256 do kernel no log
(série `0008`, `2300193`): o run
[46028220411](https://github.com/rguisantos/s21xnu/actions/runs/46028220411)
gerou o `kernel.development.sweet` de 17.505.040 bytes com SHA-256
`e0c75c10…20d4`, com 0146–0151. Esse é o candidato.
[`s21xnu-fork-kernels.json`](references/s21xnu-fork-kernels.json) guarda a
tabela, e o `prepare_xnu_boot.py` diz no roteiro e no relatório se o
kernel recebido está nela; fora dela, avisa que a correção do HID não é
identificável. [Evidência](references/s21xnu-hid-0151-20261127.json). A análise do defeito
veio de uma sessão paralela (tabela de z, pressão e inclinação), que
reproduzi aqui.

Do decodificador ao HID, quando o driver existir:
- `SWEET_PEN_IN_RANGE` e `SWEET_PEN_REPORT` viram
  `digitizerEventWithTiltOrientation(..., kIOHIDDigitizerTransducerTypeStylus,
  inRange = true, ...)`, com toque pela ponta, botão lateral em
  `buttonState`, pressão normalizada de 0..4095 e inclinação de −63..63;
- `SWEET_PEN_OUT` vira o mesmo evento com `inRange = false`.

A escala das grandezas (IOFixed) e o que o iOS espera da caneta ficam para
o teste no aparelho.
