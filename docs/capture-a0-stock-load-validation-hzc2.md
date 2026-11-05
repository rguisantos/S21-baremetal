# A0: arquivos de carga do vendor_boot stock conferidos

Validação de 05/11/2026, base `6067fa0`, com o vendor_boot.img.lz4 enviado
pelo usuário nesta sessão. Fecha a pendência de verificar os arquivos reais
de controle do stock que ficou no PR #92. Não verifica o protótipo B ou
o comportamento de carga no aparelho.

## Identidade e resultado

O arquivo LZ4 tem 12320188 bytes e SHA-256
`179c36e8fbcd9163f800dd9ab5a169cbbed702f1390bd45f05ed602b3916e736`.
A saída limitada a 67108864 bytes tem SHA-256
`f5b18d6b18230702cef98d80f4543a0f452cddb5829310b3acdafd6d600a60b5`.
Ambos coincidem com os [pins HZC2](references/capture-a0-pins-hzc2.json).
O LZ4 é lido e conferido em um buffer; a descompressão consome esse buffer.
A saída é conferida antes de salvar e novamente após salvar.

O verificador consome um buffer conferido do raw e exige que os metadados
dos 274 ELFs coincidam integralmente com o inventário anterior. O resultado
foi reproduzido em duas execuções, com JSON byte a byte idêntico e exit 0.

| Checagem | Resultado |
|---|---|
| Módulos e metadados iguais ao inventário fixado | 274/274 |
| Dependências declaradas em modinfo | 569, todas presentes |
| Ciclos no grafo declarado | Nenhum |
| Pedidos em modules.load | 274 únicos; nenhum módulo omitido |
| Chaves em modules.dep | Todos os 274 módulos |
| Arestas em modules.dep | 3654; todas apontam a arquivos presentes |
| Dependências declaradas omitidas no arquivo | Nenhuma |
| Ciclos ou dependentes bloqueados no arquivo | Nenhum |
| Dependências posteriores ao consumidor na lista literal | 151 |

modules.load tem 4399 bytes, SHA-256
`90b8d756be8b59552a4c63972ffd728a6dca2e27f55641738c24e3f4107acbb9`.
modules.dep tem 115402 bytes, SHA-256
`253239a24749aaafc108f1478a4fd0a7edf626f8f3c176565ac2f66017f30200`.
Essas identidades também coincidem com o inventário anterior.

O [relatório textual completo](references/capture-a0-stock-load-validation-hzc2.json)
lista as 151 relações, sem publicar módulos ou ramdisk. Por exemplo,
exynos2100-itmon pede sec_debug_extra_info, que aparece depois na lista.
Preservar e executar modules.load como uma sequência simples de insmod
não equivale a resolver suas dependências. Isso não prova que o stock
execute dessa forma nem que seu boot falhe.

Uma travessia offline das dependências de modules.dep, na ordem do arquivo,
antes de cada raiz de modules.load, escalonou 274 arquivos únicos e colocou
todas as 3654 arestas antes do consumidor. O relatório conserva essa ordem
como **modelo de resolução**, não como captura do loader real ou proposta
de substituir a lista stock. Nenhum arquivo do pacote foi alterado.

## Fronteira seguinte

O CPIO tem 296 entradas. A única entrada .rc/.sh é
etc/init/init.exynos2100.usb.rc; nela não foram encontradas referências a
modprobe, insmod, modules.load ou modules.dep. Não há arquivo regular
com nome contendo modprobe ou terminado em init nesse ramdisk. Esse censo
se limita ao vendor ramdisk fornecido: não cobre o ramdisk de boot,
o userspace de system/vendor, scripts com outras extensões ou comandos
construídos dinamicamente.

Logo, a coerência estrutural stock está verificada; a implementação e os
argumentos do loader userspace continuam não identificados nesta rodada.
Para a comparação seguinte, o boot.img.lz4 stock já fixado permite analisar
o ramdisk de boot sem nova coleta do telefone. Ele não foi fornecido nesta
sessão. Não se atribui ao modprobe AOSP um comportamento Samsung sem prova.

O resultado não demonstra CFI/RKP, init de drivers, ABI, identidade do pai
vbmeta instalado, confiança AVB ou SignerVer03. A0 continua aberto e A1
não começou. Nenhuma operação foi realizada no aparelho.

## Reprodução

A partir da raiz do repositório, com destino novo:

```sh
python3 scripts/check_capture_a0_load_plan.py \
  --vendor-boot build/load-plan-stock/vendor_boot.img \
  --output build/load-plan-stock/resultado-novo.json
python3 scripts/test_capture_a0_load_plan.py
```

O raw deve ser obtido com read_checked, lz4_frame e checked_buffer, usando
os pins stock_lz4/vendor_boot.img.lz4 e stock_raw/vendor_boot.img. A função
lz4_frame em check_capture_a0_parent.py limita a saída e recusa concatenação
ou truncagem. Os 16 controles existentes passaram. Não houve alteração de
código executável nem novo build; a baseline R10 9/9 e os 394 testes A0 do
PR #92 são validações anteriores, não testes reexecutados nesta rodada.
