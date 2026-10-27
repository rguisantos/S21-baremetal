# HZC2: panic, parada e recuperação de contexto

Análise estática de 2026-10-27 (Campo Grande), sobre a main `0d80be2`.
**Conclusão: o ramo de falha examinado oferece parada ou retorno por contexto
salvo; não fornece uma entrada fixa de aquisição RDX.** A palavra “recover”
nas mensagens significa restaurar o contexto registrado. Não demonstra
recuperação de um dump nem preservação da RAM após reset.

Complementa o [retorno da Image](lk-payload-return-hzc2.md): o retorno nominal
termina em `thread_exit`; só uma continuação inesperada do scheduler chega
a este `panic`. Não se deve chamar esse caminho de consequência obrigatória
do retorno da Image. A sonda continua em WFE, sem patch de RET.

## Origem e reprodução

`sboot.bin`: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Todos os PCs são offsets no arquivo; endereços globais são relativos ao mesmo
modelo, com delta nominal LK `0xe7f14000`. `0xd08490` e `0xd08498` ficam fora
dos bytes do arquivo; seus valores em execução não foram lidos.

```sh
python scripts/inspect_lk_panic_recovery.py /caminho/privado/sboot.bin
python -m unittest discover -s scripts -p test_lk_payload_return.py
python -m unittest discover -s scripts -p test_lk_final_edges.py
```

[JSON reproduzível](references/lk-panic-recovery-hzc2.json): palavras e operandos
GNU, destinos relativos conferidos com decoder independente, strings e sete
grafos locais. Chamadas opacas conservam uma aresta **condicionada ao retorno
normal**, não uma garantia de que retornam. Nenhuma instrução do firmware foi
executada. [Validação](references/lk-panic-recovery-validation-20261027.json).

## A decisão do panic

| PC | Evidência | Consequência local |
|---|---|---|
| `0x18f930` | chama `0x205788`, que lê W0 de `0xd08490` | obtém contador de contextos |
| `0x18f934` | `CBNZ W0,0x18f944` | contador não zero tenta recuperação |
| `0x18f940` | chama `0x17d880` | contador zero segue parada |
| `0x17d890` | imprime `HALT: spinning forever... (reason = %d)` | impressão ainda é chamada opaca |
| `0x17d894` / `0x17d898` | `DAIFSet #2`; `B 0x17d898` | mascara IRQ e laço, sem RET local |
| `0x18f948` | chama `0x205818` | tenta contexto registrado |
| `0x18f94c` | `B 0x18f938` | se recuperação retornar normalmente, segue parada |

`DAIFSet #2` não significa mascarar todas as classes de exceção. O laço
local não exclui reset, intervenção externa, falha de execução ou efeitos
de chamadas opacas. Não há passagem normal do laço para a aquisição RDX.

## O produtor do contexto e o destino recuperado

`0x202800` salva registros numa moldura de `0x110` bytes. Em `0x202844`
guarda X30 e o SP anterior em +`0xf0`/+`0xf8`; em `0x202864`, guarda o X30
de entrada como PC em +`0x100` e o estado construído de CurrentEL, DAIF e
SPSel em +`0x108`. Depois seleciona SPSel=1 e mascara IRQ antes de passar
SP como X2 a `0x205798`. Isso descreve o código, não prova que uma chamada
com qualquer SP/EL seja válida: a troca de SPSel pode mudar a pilha ativa.

`0x205798` consulta o contador e compara com 2. Se igual, imprime recusa
sem chamar a função. No outro ramo, usa stride 16 em `0xd08498`, grava
X2 (ponteiro de contexto) em +0 e X1 (callback opcional) em +8, incrementa
o contador e chama a função em X0. No retorno normal decrementa o contador.
Não interpretar a comparação `==2` como validação geral de limites.

`0x205818` seleciona o slot `contador−1`. Se contador ou ponteiro de
contexto forem zero, imprime `Unrecoverable context!` pela cauda. Caso
contrário, chama o callback se não nulo, relê o contador/slot, imprime
estado, decrementa o contador e salta para `0x2028e0` com o contexto em X0.
O callback é uma fronteira: pode alterar estado e não foi presumido puro.

`0x2028e0` muda SP para o contexto e carrega PC/estado de +`0x100`/+`0x108`.
Seleciona ELR/SPSR de EL1, EL2 ou EL3 segundo CurrentEL; o ramo restante
cai também no código EL1, sem provar suporte a EL0. Restaura registradores,
recupera SP de +`0xf8`, força X0=`−1` em `0x202970` e executa `ERET` em
`0x202974`. **O PC vem do contexto, nominalmente o X30 salvo do chamador
de `0x202800`; não é uma constante RDX.** A saída normal do wrapper usa
X0=0; a saída recuperada distingue-se por X0=−1.

Isso fecha a semântica local que estava opaca no relatório anterior:
`0x205788` é leitura do contador; `0x17d880` é parada; `0x205818` é tentativa
de restaurar contexto. Não é necessário tratar essas três rotinas como
uma suposta rotina genérica de upload.

## Decisão para o diagnóstico

Acrescentar RET à Image ou provocar panic não constitui um mecanismo de
captura demonstrado. Para uma captura cooperativa será preciso estabelecer
um produtor explícito que execute no contexto correto, preserve o registro
e faça uma transferência observável. Para usar um contexto já registrado,
seria necessário demonstrar qual slot está ativo, seu PC, callback e efeitos
do chamador naquele percurso. Nada disso foi observado no aparelho.

A fronteira seguinte é o contrato de aquisição e carregamento. Esta entrega
resolve a identidade e o comportamento local das três rotinas; não declara
resolvidos o boot físico, a disponibilidade USB, a retenção após reset ou a
possibilidade de retornar com segurança ao LK. Não houve MMIO, SMC, comandos
no telefone, modificação da sonda ou ampliação do ensaio NEWTIME.
