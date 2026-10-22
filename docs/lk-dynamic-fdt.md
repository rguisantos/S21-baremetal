# Initrd, reservas e origem do tamanho de RAM no LK

Análise de 2026-10-21 do sboot HZC2 já identificado por SHA-256. Os offsets
são do arquivo. Complementa o [pipeline DTB/DTBO/DPM](lk-dtb-pipeline.md).
Não foi recuperado o conteúdo do FDT final no aparelho.

## Initrd ligado às cópias v3

| Escrita | Evidência no sboot |
|---|---|
| linux,initrd-start | 0xfb408 passa 0x84080000 ao formatador com `<0x%x>`; 0xfb42c chama o editor 0xf13b0 |
| Tamanho vendor | 0xfb49c → 0x12e9b8 lê u32 de 0x98000000+0x18 |
| Tamanho boot v3 | 0xfb4a4 → 0x12dff8 → 0x12e9c8 lê u32 de 0x94000000+0x0c |
| linux,initrd-end | 0xfb4a8 soma os tamanhos; 0xfb4b4 adiciona 0x84080000; 0xfb4d8 chama o editor |
| Células | 0xf14ac faz REV W0 e 0xf14b4 grava quatro bytes por valor textual |

Os dois tamanhos são somados sem padding, com aritmética em registradores W.
Nos arquivos stock, são 12.017.257 + 701.558 = **12.718.815 bytes**:

| Propriedade modelada | Valor | Bytes big-endian |
|---|---|---|
| linux,initrd-start | 0x84080000 | 84 08 00 00 |
| linux,initrd-end | 0x84ca12df | 84 ca 12 df |

O fim é o primeiro byte após as cópias concatenadas. O modelo limita os
componentes e os destinos para manter a soma em 32 bits; não generaliza essa
aritmética para qualquer endereço/tamanho. O deslocamento do kernel não
altera essas propriedades. Os valores são inferidos das instruções e headers,
sem observação do resultado no telefone.

O DTB estático tem início 0x84000000 e fim 0x841fffff. Os oito candidatos
placa+DPM mantiveram esses valores na análise de host e foram recusados pelo
novo comparador de initrd. Isso é esperado para árvores anteriores às edições
do LK; não significa que o firmware tenha rejeitado essas imagens.

## Comparação parcial com um FDT fornecido

```bash
python3 scripts/check_lk_v3_layout.py /caminho/sboot.bin \
  /caminho/boot.img /caminho/vendor_boot.img --offset 0 --fdt /caminho/candidato.dtb
```

O relatório normal inclui `chosen_initrd`. `--fdt` é opcional, lê no máximo
2 MiB e exige as duas propriedades como células de quatro bytes iguais às
do escritor rastreado. Uma codificação de oito bytes pode representar o mesmo
endereço, mas fica fora dessa comparação de bytes com o ramo Samsung.
Conteúdo ausente, desatualizado ou malformado é recusado; o arquivo não é editado.

Uma correspondência permanece marcada como `scope=chosen_initrd_only`,
`is_final_fdt=false`, `memory_map_verified=false` e `reservations_verified=false`.
Não valida bancos, reservas, assinaturas, estado de entrada ou bootabilidade.

O leitor Python comum antes substituía propriedades e caminhos duplicados no
dicionário. Agora os recusa. Os testes constroem uma segunda propriedade ou
um segundo nó chosen que esconderiam um valor antigo da primeira definição.

## Escritores condicionais de reservas

0xfb4fc chama 0x148a80. Após encontrar `/reserved-memory`, o código tenta
criar nós pelo helper 0x148770, com estes argumentos:

| Nome / compatible | Base, tamanho | Condição adicional |
|---|---|---|
| el2_code / el2,uh | 0xc1400000, 0x200000 | caminho comum após lookup da raiz |
| el2_earlymem / el2,uh | dois buffers locais, sem conteúdo observado | chamada HVC 0x83000004; handler de alocação rastreado no uH |
| kaslr / kernel-kaslr | 0x80001000, 0x1000 | caminho comum após earlymem |
| sboot / sboot,rmem | 0xe8000000, 0x1800000 | getter 0x12dbc8(0x11) retorna 5 |
| mz_zeroisation / sboot,mz | 0xfb400000, 0x1000 | mesmo ramo de valor 5 |
| bootloader_fb / sboot,fb | 0xfa000000, 0x1194000 | ramo de valor 5 e ausência do nó consultado |

Não se atribuiu semântica de download/recovery ao modo 5 nem se confirmou o
sucesso das tentativas de escrita. Esta tabela não é o mapa completo das
reservas finais e não autoriza considerar o restante como memória livre.

0x148b1c passa ao HVC ponteiros de dois buffers previamente zerados. Em
0x148b20, seus conteúdos são carregados como base/tamanho. O estado inicial
zero não comprova o resultado do serviço; esse HVC também não estabelece
conduíte PSCI alternativo. O DTB continua declarando PSCI SMC.

Atualização de 2026-10-22 UTC: o [handler no uH do pacote BL](el2-earlymem-hzc2.md)
foi identificado. Pode calcular, alocar e inicializar a região, dependendo de
uma lista de intervalos e de seu estado de inicialização. Não é uma consulta
pura; base e tamanho efetivos permanecem desconhecidos.

O [chamador que fornece os intervalos](lk-uh-range-registration.md) também
foi ligado: 0xfb4f0 percorre nomes com prefixo memory e envia a primeira
tupla de reg de cada nó ao comando uH 2, antes do pedido earlymem. Ainda
faltam os valores que alimentam a construção dinâmica desses bancos.

0x1486a0 consulta `#address-cells`/`#size-cells`. Com uma célula grava quatro
bytes big-endian; com duas, oito. Nos oito candidatos de host, reserved-memory
tem **2 células de endereço e 1 de tamanho**, resultando em reg de 12 bytes
para esses argumentos. O construtor escreve reg e compatible; isso não fecha
as demais propriedades ou reservas. A tabela não foi inserida no R10.

## Origem e possível limitação do tamanho total de RAM

0xfad60 chama 0x11b758. Quando seu cache não está marcado, o getter constrói
**0x02038848**, lê 64 bits e guarda o valor no global relativo 0xaa7e98;
um campo derivado por shift de 29 bits serve ao estado do cache. O chamador
consome x25 como tamanho total ao construir bancos, inclusive laços de
512 MiB acima de 0x880000000.

O helper 0x11b798 converte seu argumento em bytes por shift de 30 bits e
pode atualizar o tamanho em cache se o limite for compatível com o valor
lido. A chamada 0x147310 passa um nibble, em um caminho com as mensagens
`setting DRAM SIZE to 0x%x` e `DRAMSIZE%x`. Esse caminho de configuração foi
localizado, mas não se observou seu valor ou execução. Não se deve fixar
x25 em 12 GiB apenas pelo modelo comercial do aparelho.

O endereço no código não é uma solicitação de leitura MMIO pelo Android.
Seu contrato completo com estágios anteriores permanece aberto. Um tamanho
total também não determina bancos/furos: a construção depende de retornos
SMC e ramos descritos em [bootloader-hzc2.md](bootloader-hzc2.md#ram-e-reservas-dependem-do-estado-de-boot).

Um desses intervalos agora tem retornos constantes rastreados no Harx:
[0xc0000000–0xc1400000, omitido em ramo do construtor](lk-harx-memory-gap.md).
A condição de execução e o restante dos bancos ainda não foram observados.

Continuação em 2026-10-22 (Campo Grande): a [aritmética das chamadas ao
construtor de bancos](lk-memory-bank-constructor.md) foi modelada com nove
entradas fornecidas e conferida em 268 cenários com as instruções originais
no Unicorn. Inclui os ramos baixos, os recortes Harx/SEC_PGTBL e os blocos
altos de 512 MiB. Isso fecha esses argumentos condicionais, preservando a
pendência dos valores reais, das edições bem-sucedidas e do mapa final.

## Reprodução e resultado

```bash
python3 -m unittest discover -s scripts -p 'test_lk*.py' -v
python3 scripts/inspect_sboot_hzc2.py /caminho/sboot.bin
```

**19 testes de host passaram**, incluindo chosen, duplicidades e as recusas
anteriores. A CLI foi conferida com as imagens stock e um FDT sintético:
somente chosen pode corresponder, mantendo memória/reservas explicitamente
sem validação. O limite de leitura e a recusa de chosen antigo também foram
conferidos. Não houve execução no telefone nem repetição de coleta rish.

O relatório HZC2 inclui `dynamic_fdt_writes`, com chamadas, palavras e strings.
Intervalos para desassemblagem independente: 0xfb408:0xfb4dc,
0x12dff8:0x12e048, 0x12e9b8:0x12e9d4, 0xf147c:0xf14e4,
0x1486a0:0x148770, 0x148a80:0x148c34, 0x11b758:0x11b794 e
0x1472e0:0x147330. O material recebido basta para continuar seguindo os
serviços e ramos que definem o mapa efetivo.
