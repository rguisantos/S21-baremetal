# uH earlymem e soc_info no pacote BL HZC2

Análise estática de 2026-10-22 UTC. A cadeia de `el2_earlymem` agora chega
do LK ao handler do uH fornecido no mesmo pacote BL. Esse handler tem efeitos
de alocação e inicialização. Não se executou firmware nem qualquer SMC/HVC.
Os offsets de código/tabelas abaixo são de arquivo. O estado BSS é indicado
por deslocamento relativo à base inferida da imagem, sem bytes correspondentes
no arquivo. Nenhum desses valores é um endereço observado no telefone.

## Entradas e reprodução

O pacote é o BL HZC2 já recebido, SHA-256
`5b48c27798b103ec906112fc4baad1aacd8d39c970dae6c478d3bd559e2cf31f`.
Os membros LZ4 foram descomprimidos localmente, com consumo completo de cada
frame. Os binários permanecem fora do Git.

| Imagem raw | Bytes | SHA-256 |
|---|---:|---|
| sboot.bin | 4.194.304 | a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91 |
| uh.bin | 93.832 | c2f7cd2708be9c8ea3a4ff22f8bbf224f726107633e5b70b09b8f352784fe407 |
| harx.bin | 3.145.728 | 5564dcb1f59c4a66a4c69f7042fb30ee14c97a31ba5a77427c4a08612e1dc21e |

```bash
python3 scripts/inspect_el2_hzc2.py /caminho/sboot.bin \
  /caminho/uh.bin /caminho/harx.bin
python3 -m unittest discover -s scripts -p 'test_el2_hzc2.py' -v
```

O verificador usa apenas a biblioteca padrão, limita cada leitura ao tamanho
esperado mais um byte e exige os três hashes. Emite palavras de instrução,
alvos BL decodificados e os ponteiros selecionados. Não é um emulador ou
desassemblador geral. A interpretação foi conferida com Capstone 5.0.7;
a saída reproduzível está em [el2-hzc2.json](references/el2-hzc2.json).

## LK → dispatcher uH → comando 4

| Etapa | Evidência |
|---|---|
| Chamador LK | sboot 0x148b00–0x148b1c: x0=0x83000004, x1/x2 apontam dois buffers zerados, x3/x4/x5=0 |
| Instrução | BL em 0x148b1c → 0x209a28, que contém HVC #0 e RET |
| Registro no uH | uh 0x7c9c–0x7cac: callback 0x6c3c e intervalo 0x83000000–0x8300ffff |
| Seleção | 0x6c54 usa bits 7:0 como comando; 0x6c60 usa bits 15:8 como aplicação |
| Aplicação 0 | construtor apontado em 0x12568 → 0x3368; publica tabela 0x16000 e limite de comandos 9 |
| Entrada selecionada | u64 em 0x16020 = 0xc1401708; com base inferida 0xc1400000, handler em 0x1708 |
| Argumentos | 0x6c68/0x6c6c salvam x1..x4; 0x6ce0 passa o frame local ao handler |
| Consumo LK | 0x148b20 lê os dois buffers; 0x148b38 chama o construtor de reserva 0x148770 |

A base de ponteiros é uma inferência estática consistente com os arrays de
construtores e os ponteiros de funções desta imagem. O verificador aceita
apenas a imagem identificada e exige que o ponteiro selecionado tenha bytes
alinhados dentro dela; não confunde ponteiros para arrays com funções.
Não se atribuiu semântica às outras entradas da tabela.

O fonte Samsung `include/linux/uh.h` confirma o namespace: prefixo 0x83000000,
aplicação nos bits 15:8 e comando combinado por OR. Seu hash é
`c0b0511666481b5dc726b9303c43ca4cfaa32c04e5d0d27201dbcd5f4959f973`,
extraído do Kernel.tar.gz já inventariado, SHA-256
`c5ad9994240e67ebdc40878c191be040bf30db398bc8513ea1f156eaebd86bf2`.
Essa concordância não prova execução do callback no boot observado.

## O comando altera estado

O handler 0x1708 testa o flag em 0x17218 e pode recusar uma nova inicialização.
Recebe os ponteiros de saída em frame+0x10/+0x18 e o terceiro argumento em
frame+0x20. O caminho do LK fornece base e tamanho iniciais zero e terceiro
argumento zero; alcança o ramo de cálculo automático se as validações passarem.

O estado em 0x171f8 contém uma lista de intervalos. Antes da inicialização,
o comando 2, handler 0x2004, pode adicionar base/tamanho por 0x4574.
Existe no LK um wrapper 0x209a38 que monta 0x83000002 e chama o mesmo HVC;
seu chamador foi posteriormente ligado ao [percurso memory do FDT](lk-uh-range-registration.md).
Os valores efetivamente registrados continuam desconhecidos.

| Operação no comando 4 | Offsets uH |
|---|---|
| Valida/traduz os ponteiros de saída | 0x1910–0x1930, chamadas a 0x3194 |
| Ramo de tamanho automático | 0x1938 → 0x1a08, consulta e percorre a lista |
| Acumulação e arredondamento do tamanho | 0x1c10 acrescenta 0x100000 por iteração selecionada; 0x1c20–0x1c28 somam 0xdfffff e aplicam máscara 0xffe00000 |
| Seleção na lista em ordem reversa | 0x1c60–0x1cc8, desconta tamanho/alinhamento e altera o intervalo |
| Saída de base | 0x1de4 grava 64 bits no primeiro ponteiro traduzido |
| Saída de tamanho | 0x1e04 grava 32 bits no segundo ponteiro traduzido |
| Flag e inicialização posterior | 0x1e08 marca o estado; chamadas e callbacks continuam até 0x1ff0 |

A aritmética de tamanho equivale a arredondar o acumulador mais 12 MiB para
múltiplo de 2 MiB, enquanto não houver overflow de W. O acumulador depende do
percurso de cobertura em unidades de 1 GiB da lista, e não foi observado.
Não se fixa um tamanho para o aparelho nem se reproduz toda a política de
alocação com esse resumo. O handler também possui ramo para base solicitada.

O LK zera oito bytes em cada buffer. O tamanho escrito pelo uH tem quatro
bytes; se esse caminho completar, os quatro bytes superiores continuam zero
quando o LK carregar o tamanho com LDP X2,X3. Não se inferiu sucesso a partir
de x0: o dispatcher e os callbacks têm tratamento próprio de retorno.

Portanto, chamar esse serviço no Android para “consultar earlymem” seria uma
interpretação incorreta do handler. O avanço é identificar a origem e a
dependência de estado dos valores usados pelo LK.

## Harx, soc_info e limites dos nomes de headers

Harx é outra imagem do pacote. Sua função 0x22d4 consulta **0x8200012e**
por SMC e exige versão **0x66001000**. Strings em 0xd19c/0xd1d1 dizem
`SOC_INFO_VERSION` e `secure soc_info`. O serviço é chamado com x1=0 para
versão e x1=índice nos demais ramos, com cache por campo. As chamadas em
0x2308/0x23dc chegam a 0x9aa4: DSB SY, SMC #0, RET.

O LK exige a mesma versão ao chamar o identificador legado **-0x12e** em
0xfada0. A concordância sugere ABI relacionada, mas a tradução entre os IDs
não foi rastreada. Não se igualam os serviços nem se atribuem valores aos
campos de bancos de RAM. O HVC 0x83000004 pertence ao dispatcher uH acima;
não foi confundido com o namespace OEM 0xc600... encontrado no Harx.

Há uma colisão de nomes a preservar: `include/soc/samsung/exynos-smc.h`
chama 0x8200012e de `SMC_CMD_GET_SJTAG_STATUS`. Hash desse header:
`c896ed8086009ae3055c6ac6b3164744c9e7cf7286a0ad993eba2b4792b7db49`.
O nome isolado não descreve a sequência observada neste BL; não se inferiu
estado SJTAG ou política de segurança a partir dele.

O getter Harx em 0x2268 também lê **0x02038848**, como o getter LK já
documentado. Exige tamanho múltiplo de 1 GiB e, sem cache, evita a leitura
quando SCTLR_EL2.M está ligado. Isso reforça a procedência do campo entre
componentes, mas seu conteúdo efetivo continua desconhecido.

O serviço OEM separado 0xc6000020 teve os retornos de versão/base/tamanho
decodificados posteriormente: [intervalo Harx e condição do LK](lk-harx-memory-gap.md).
Essa informação fecha um caso condicional, sem resolver os retornos soc_info.

## Resultado e próxima lacuna

Três testes de limites/identidade passaram, junto dos 19 testes LK existentes.
A CLI foi executada com as três imagens originais; o relatório permanece com
`runtime_values_observed=false`, `memory_map_verified=false` e
`is_final_fdt=false`. Não houve nova coleta rish ou mudança nos drivers.

Atualização: a origem imediata dos intervalos foi ligada ao percurso de nós
memory do FDT corrente, antes da chamada earlymem. A checagem e a validação
ampliada estão em [Intervalos LK → uH](lk-uh-range-registration.md).
O próximo ponto são os valores/ramos que constroem esses bancos e a tradução
soc_info. O material já recebido basta para continuar. O mapa completo, o
resultado da alocação e o estado final de entrada ainda impedem declarar o
payload pronto para execução física.
