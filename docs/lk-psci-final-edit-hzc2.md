# HZC2: alteração de PSCI no FDT após os bancos

Continuação de **2026-10-27 (Campo Grande)**, base `8f88999` após PR #43.
**O DTB base declara PSCI SMC, mas uma edição posterior do LK pode escrever
`/psci/method = "hvc"`. O bugreport recebido registra a mensagem impressa
após sucesso local dessa escrita.** A propriedade do DTB estático não pode
ser usada como se fosse a propriedade após todas as edições do bootloader.

Isso corrige a lacuna das descrições anteriores de PSCI. Não demonstra
execução bem-sucedida de um serviço PSCI, estado de EL/HCR ou captura do FDT
final. A main de uma CPU e a sonda não foram alteradas ou executadas no S21.

## Ordem rastreada depois dos bancos

PCs são offsets do sboot HZC2 bruto de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.

| Chamada | Operação identificada | Limite |
|---|---|---|
| 0xfb404, 0xfb42c, 0xfb4d8 | chosen/bootargs e início/fim initrd | conteúdo de bootargs depende de helpers e estado |
| 0xfb4f0 → 0x148c38 | percorre memory/reg e encaminha intervalos ao uH | percurso já delimitado; não certifica aceitação |
| 0xfb4fc → 0x148a80 | tenta criar reservas, inclusive el2_code/earlymem | earlymem depende de HVC; valores efetivos abertos |
| 0xfb504 → 0x148a30 | gate de temperatura: acima de 85 chama editor de limites de frequência | temperatura vem de callback indireto; caminho real não medido aqui |
| 0xfb52c → 0xf9470 | verifica flag Harx e tenta mudar método PSCI | esta rotina foi executada em fixtures nesta entrega |
| 0xfb544 → 0xf1240(0) | verifica header e arredonda totalsize para múltiplo de quatro | escreve campo do header; não é fdt_pack nem filtro de bancos |
| 0xfbcb8 → 0xfbf48 | tenta escrever ddi_id sob /panel_0 | não é limpeza de nós memory |
| 0xfbe0c / 0xfbe14 | W0=0x8b080000, X1=X2=X3=0, BLR X4 | alvo é a base nominal da Image mais deslocamento; não foi executado aqui |

O wrapper chama o construtor em 0xfbcb4. Depois dele há chamadas adicionais,
serviços seguros e callbacks ainda opacos antes do salto final. A tabela
identifica operações locais, sem certificar ausência de efeitos transitivos
sobre o FDT em toda a cadeia. O ponteiro global do editor foi inicializado
com 0x8b080000 em 0xfbc40; o salto usa novamente essa constante.

O banco zero permaneceu inalterado em todas as fixtures da rotina PSCI.
Isso resolve seu efeito **nessa rotina**, sem provar preservação até o kernel
por todos os outros callees. O tamanho zero continua sem autorizar RAM livre.

## Condição, comparação e escrita de PSCI

0xf9470 lê o byte relativo 0x487c90. Zero retorna -1. Não zero permite
buscar `/psci` e `method` no FDT fornecido. Esse é o flag Harx cujo escritor
em 0xf90d8 o marca antes do HVC de registro do callback/buffer de crash;
o byte isolado não certifica o sucesso desse HVC.

A comparação em 0xf94e0 usa o **comprimento da propriedade**, lido com sinal,
como limite para a string `smc`. Se a comparação dá zero, o trecho
0xf9530–0xf9554 escreve quatro bytes `68 76 63 00` por 0x11fb48.
Retorno negativo da edição vira -1. Caso contrário, imprime `Change PSCI
method to HVC` em 0xf9564 e retorna zero.

Se a primeira comparação diverge, compara com `hvc` usando o mesmo
comprimento. Igual retorna zero sem editar; outro valor retorna -1.
O chamador em 0xfb530 apenas escolhe imprimir um aviso quando W0 não zero,
e segue para o helper do header. Esse retorno não interrompe o boot por si só.

## Observação no registro recebido

A linha **409533** do membro `dumpstate-2026-10-27-18-23-28.txt` contém o
evento permitido `Change PSCI method to HVC`, no tempo relativo **2.946751**.
O SHA-256 do ZIP é `5a8e98c0f6dd657e87d099bfa7b26f1dd512ba39220ad85aecded709d79c40ef`.
O corpo LAST KMSG continua com SHA-256
`dc155d60764ad35dba56eafb9c6f10167ae2b6a2adaaa5e91219440096e1d931`,
igual ao corpo da [análise do bugreport](bugreport-boot-hzc2.md).

O novo extrato emite somente tipo de evento, linha, tempo e hashes; o ZIP e
as linhas completas permanecem fora do Git. Não modifica o extrato anterior
de 24 eventos. Pela correspondência entre a string e o ramo do código,
a mensagem testemunha **retorno não negativo do setprop local** e a passagem
pelo ramo de alteração. Não revela o conteúdo depois de outros escritores,
não data um boot novo e não prova execução PSCI por HVC.

## Ensaio com código original no QEMU

Foram executados 0xf9470, a implementação FDT e os helpers de comparação,
cópia e comprimento originais em árvores sintéticas. Somente o printf de
diagnóstico foi substituído; nenhum SMC/HVC foi invocado. O flag Harx foi
fornecido pelo harness, sem inicializar Harx ou acessar o telefone.

| Condição fornecida | Método após a rotina | W0 assinado |
|---|---|---:|
| Flag zero, method=smc | smc, sem alteração | -1 |
| Flag ativo, smc com NUL | hvc com NUL | 0 |
| Já hvc com NUL | sem alteração | 0 |
| Método desconhecido foo | sem alteração | -1 |
| Nó /psci ausente | ausente | -1 |
| Propriedade method ausente | ausente | -1 |
| Ponteiro FDT nulo | fixture não tocada | -1 |
| Propriedade vazia, com espaço | hvc com NUL | 0 |
| Um byte `s`, sem NUL | hvc com NUL | 0 |
| Dois bytes `hv`, sem NUL | continua `hv` sem NUL | 0 |
| `smc` + NUL + cauda | hvc com NUL | 0 |
| Propriedade vazia, sem espaço para crescer | continua vazia | -1 |

Os casos curtos mostram por que retorno zero não é um validador de string
PSCI completa. São entradas artificiais; não há evidência de método malformado
no aparelho. Não extrapolamos para comprimento negativo ou dados corrompidos.

**24/24 casos passaram**, doze em cada delta de laboratório 0x40000000 e
0x40200000. A árvore resultante foi comparada propriedade a propriedade,
incluindo o banco zero; casos sem edição conservaram todos os bytes. Também
foram conferidos SP/X19..X29, sentinelas do FDT/pilha/flag, flag inalterado,
bytes originais carregados e igualdade dos hashes entre as duas posições.
Há limites de 16 paradas, 15 s por caso e timeout de transporte de 10 s.

A CPU é iniciada por uma Image de laboratório e parada antes de sua primeira
instrução. O ensaio não é uma execução do diagnóstico no telefone, nem uma
reprodução de todo o carregamento Samsung.

## Reprodução e consequência para os contratos

```sh
python3 scripts/inspect_lk_psci_final.py /caminho/sboot.bin \
  --bugreport /caminho/bugreport-s21.zip
python3 scripts/emulate_lk_psci_final_qemu.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p test_lk_psci_final.py
```

[Extrato estático e evento permitido](references/lk-psci-final-hzc2.json),
[24 casos QEMU](references/lk-psci-final-qemu-hzc2.json) e
[validação](references/lk-psci-final-validation-20261027.json).
São 238 palavras e 60 destinos relativos conferidos contra GNU e decoder
independente. O scanner do ZIP fixa o mesmo hash e limites da coleta anterior;
os cinco testes novos verificam proveniência, lista de permissão e recusas.

Para um futuro consumidor, o método deve vir do FDT efetivamente entregue
sob um contrato de entrada conhecido. A constatação não habilita o fallback
experimental SMC→HVC do código legado nem autoriza sondar ambos. O R10 atual
em uma CPU continua sem chamadas PSCI. Faltam o FDT final, o estado de entrada
e a implementação/viabilidade do serviço; essas lacunas seguem separadas da
edição local agora comprovada pelo binário, QEMU e mensagem do boot stock.
