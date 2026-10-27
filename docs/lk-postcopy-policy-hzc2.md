# HZC2: configuração após a cópia e fronteira do monitor

Análise estática de 2026-10-27 (Campo Grande), continuação do PR #38.
**A rotina 0x151b10 contém configuração de segurança e chamadas ao monitor,
com ações descritas pelas strings como CP debug e proteção de fingerprint.**
Não é correto tratá-la como uma transformação identificada da Image. Também
não está provada a ausência de transformações transitivas: serviços seguros,
outros callees e valores reais continuam abertos.

## Fonte e reprodução

Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets de arquivo; globais são relativos ao modelo do LK.
Nenhuma instrução Samsung foi executada, nem SMC, MMIO ou ação no telefone.

```sh
python3 scripts/inspect_lk_postcopy_policy.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p test_lk_payload_return.py
python3 -m unittest discover -s scripts -p test_lk_final_edges.py
```

O [extrato](references/lk-postcopy-policy-hzc2.json) confere 201 palavras e
60 destinos relativos GNU contra bytes e decoder independente, com oito
grafos locais e nove strings. O [registro de validação](references/lk-postcopy-policy-validation-20261027.json)
conserva reprodução, regressões e recusas. Chamadas opacas só têm continuação
se retornarem normalmente; estes grafos não demonstram viabilidade física.

## Chamadores e resultado

Os caminhos v2/v3 chamam 0x151b10 em 0x12e3e8/0x12e860, depois dos trechos
de cópia já documentados em [cópia da Image](lk-kernel-copy.md).
Preparam X0 com o contêiner, X1 com [X29+80] e W2 com [X29+88]. Porém não
se pode inferir que a rotina autentique ou transforme esses bytes apenas
porque esses argumentos estão presentes.

O primeiro callee, 0x150320, substitui X0 pelo ponteiro lido de 0xcd61c8 e
retorna o u32 em ponteiro+80. A rotina testa esse estado e outras consultas.
Não preserva o X0 de entrada num registro callee-saved ou na pilha local.
Isso não é uma análise completa dos fluxos de X1/X2 ou efeitos indiretos.

Ambos os RET locais de 0x151b10 seguem W0=0. Os dois chamadores também
sobrescrevem W0 com zero depois da chamada. **Esse zero não certifica
aceitação da Image:** alguns ramos chamam serviços e caminhos de erro antes
dele, e seu retorno normal não é garantido.

## Serviços concretos delimitados

| Trecho | Argumentos nominais no wrapper 0xf6088 | Evidência e limite |
|---|---|---|
| 0x151248, chamado se consulta 5 não zero | X0=0x82000701, X1=1, X2=X3=0 | String `Enable CP debug logging`; retorno não zero imprime falha |
| 0x151298, índices 20, 21 e 23 neste dispatcher | X0=0x82000702, X1=sign_extend_32(1 << (índice & 31)), X2=X3=0 | String `Send info to CP secure table %d`; retorno não zero imprime falha |
| 0x159028, primeira chamada | X0=0xb2000201, X1=100, X2=1, X3=0 | Testa X0 & 0xf0; ramo não zero imprime falha e converge para segunda chamada |
| 0x159028, segunda chamada | X0=0xb2000201, X1=100, X2=6, X3=0 | Testa X0 & 0xf0; zero imprime sucesso, outro ramo anuncia desligamento |

O wrapper contém exatamente `SMC #0; RET`. Os argumentos são evidência do
chamador, não implementação dos serviços. Os três índices de CP produzem
0x100000, 0x200000 e 0x800000; não lhes atribuímos significados físicos não
comprovados. No helper geral o deslocamento usa W e depois SXTW: não é um
shift irrestrito de 64 bits.

A string que nomeia o último helper é `set_tzpc_secureport_fps`. A primeira
mensagem menciona `fp_set_poweroff_regs`; a segunda `TEEGRIS` e `Fingerprint`.
Isso sustenta a identificação nominal, sem provar configuração do hardware.
O ramo da segunda falha imprime mensagens, chama 0x11db58/0x11e040,
0xef3a8 e 0x147730(28). Não declaramos que o aparelho efetivamente desligue:
os efeitos desses helpers e do monitor não foram executados. Se retornarem,
o epílogo também devolve zero.

## Decisão e próxima fronteira

Esta entrega resolve parte da identidade de 0x151b10, antes inteiramente
opaca no [contrato Samsung](samsung-diagnostic-contract.md). Não há nessa
análise um validador completo de assinatura, um descompressor demonstrado ou
um canal que recupere os 128 bytes da sonda. O corpo local faz stores de
pilha; isso não prova ausência de escrita na Image por callees/monitor.

Próxima investigação: separar os validadores anteriores à cópia das consultas
e ações restantes de 0x151b10, começando por 0x157230 e seus chamadores, com
origem dos estados. O percurso físico permanece pendente sob o último estado
informado; retorno zero de uma rotina de configuração não muda essa decisão.

Continuação: [origem imediata do bitmap](lk-policy-bitmap-hzc2.md) liga workspace+0x29f68 → response+0x120 → 0xcd6618 → 0x157230. O produtor é get_token_mode; produção do workspace, token ativo e autenticação da Image seguem abertos.
