# HZC2: binding nominal de 0x31998 até a SMC

Análise **estática, 2026-10-25 (Campo Grande)**, base `a50a1db` / PR #28.
Nenhuma instrução do firmware ou SMC foi executada; o escopo QEMU não mudou.

**Um inicializador de 0x31998 foi ligado a uma tabela concreta, cujo método
+72 aponta nominalmente para `SMC #0; RET`.** Isso resolve uma cadeia
estática dos 15 envios da coluna 1. A segunda origem do binding, sua
preservação e o atendimento dessas chamadas pelo monitor permanecem abertos.

## Entradas e reprodução

Mesmo sboot HZC2 de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs e células são offsets de arquivo. O delta de ponteiros BL2
`0x020ea000` continua **nominal**, não observado no aparelho.

```bash
python3 scripts/inspect_newtime_smc_binding_hzc2.py /caminho/sboot.bin
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
```

[Extrator](../scripts/inspect_newtime_smc_binding_hzc2.py),
[relatório com instruções e pedidos condicionais](references/newtime-smc-binding-hzc2.json)
e [proveniência da convenção de referência](references/newtime-smc-source.json).
O extrator reconfere as 324 palavras do estudo anterior e mais 46 palavras,
três alvos relativos e 14 operandos selecionados nesta cadeia.

## Inicializador concreto

| Aresta | Evidência |
|---|---|
| Preparação em `0x17fbc`–`0x17fc4` | ADRP X4 para página `0x30000`; X3 = X4+0x520+0x2c0 = offset `0x307e0` |
| `0x18000` → `0x1dc90` | BL direto; X3 não recebe outra escrita entre a preparação e essa chamada |
| `0x1dcb4`–`0x1dcbc` | Se X3 não nulo, STR X3 em S+784, S=`0x31688`; célula `0x31998` |
| Célula da entrada +72 | `0x307e0+0x48 = 0x30828`, conteúdo `0x02100420` |
| Tradução nominal | `0x02100420 − 0x020ea000 = 0x16420` |
| `0x16420` / `0x16424` | `SMC #0` / `RET`; a folha não reescreve os argumentos antes da SMC |

O valor nominal fornecido como X3 é `0x0211a7e0`; o ADRP opera sobre o
endereço de execução, enquanto a tabela acima usa offsets de arquivo.
A célula inicialmente zero passa a ter um provedor concreto **nesse
caminho**. Isso não demonstra quando esse caminho roda frente a `0x28808`
nem que outra escrita não substitua o binding ou o método da tabela.

Sob preservação, os 14 BLRs e o BR final da rotina `0x28808` chegam a essa
folha com X0=`0xffffffffffffff9b` (-101), X1=identificador, X2=palavra do
payload, X3=0. O último valor tem extensão de sinal por LDRSW; os primeiros
14 têm extensão por zero. As respostas não são verificadas antes do próximo
envio nessa rotina. Uma SMC pode alterar estado e registradores; a análise
não simula seu retorno nem assume sucesso ou continuidade no aparelho.

## Segunda origem ainda não resolvida

`0x2d364` recebe X0 do chamador e, se não nulo, o publica em `0x31998`
por `0x2d394`. A célula **`0x31580`**, índice **47** de `0x31408`, contém
`0x02117364`, alvo nominal `0x2d364`. No inventário B/BL alinhado do BL2
`[0x16000,0x2fd00)`, não apareceu chamada direta para essa entrada.
O ponteiro aparece em `0x31580`. Isso não identifica o despacho indireto,
a origem de X0 ou exclui outros caminhos. Não foi igualado ao inicializador
concreto de `0x18000` sem essa evidência.

A [auditoria seguinte do slot47](newtime-slot47-hzc2.md) descarta quatro
candidatos de outra base. Ela não resolve o chamador ou a origem de X0.

## Correspondência com uma convenção pública

A [fonte de referência fixada](https://github.com/xfwdrev/android_kernel_samsung_ex2100/blob/756951ae58e9e9eff789ea07bc5a9d07ed5e4ea0/include/soc/samsung/exynos-smc.h)
usa `SMC_CMD_REG=-101` (linha 26) e codifica SFR_W por
`(1 << 30) | (endereço >> 2)` (linhas 114–117).
A revisão é a mesma do [estudo do kernel público](xfwdrev-kernel-reference.md).
Ela não foi identificada como o kernel stock HZC2 ou como fonte de seu
monitor seguro. A correspondência abaixo é uma **inferência sob essa
convenção**, não uma interpretação confirmada pelo monitor.

| Identificador X1 | Endereço candidato | Valor da subtabela 0x12b | Valor da subtabela 0x11b |
|---|---|---|---|
| 0x468d0101 | 0x1a340404 | 0 | 0x100001 |
| 0x468d0104 | 0x1a340410 | 0x7ffff0 | 0x6ffff0 |
| 0x468d0105 | 0x1a340414 | 0 | 0x6ffff0 |
| 0x468d0106 | 0x1a340418 | 0 | 0x800001 |
| 0x468d0107 | 0x1a34041c | 0 | 0x900001 |
| 0x468d010a | 0x1a340428 | 0 | 0x2ffff0 |
| 0x468d010b | 0x1a34042c | 0 | 0x2ffff0 |
| 0x468d010c | 0x1a340430 | 0x33 | 0x330033 |
| 0x468d0110 | 0x1a340440 | 0x1e02 | 0x3e02 |

São os nove pedidos cujos valores diferem; os 15 constam no JSON. Os
endereços candidatos completos vão de `0x1a340400` a `0x1a3404b4`, com
lacunas. Valores são os payloads fornecidos como modelo: o código recarrega
ponteiro e dados entre chamadas, portanto não prova uma sequência estável.

Isso permite substituir a interpretação de “tags sem destino nominal”
por “identificadores compatíveis com SFR_W enviados a uma folha SMC sob
binding nominal”. Não fornece nome físico de campo, política de acesso,
efeito no controlador, resposta de erro ou prova de escrita aceita.
A semântica dos comandos 9/73/57/59 da outra cadeia continua separada.

## Validação e próxima aresta

Relatório reproduzido byte a byte, GNU e operandos conferidos; testes da
inversão da convenção cobrem classes incompatíveis, limites u32 e retorno
à codificação original. Arquivo curto/longo/alterado é recusado pelo hash.
A suíte NEWTIME e links da documentação foram conferidos.

Próximo: rastrear o despacho do slot47 e seu X0, procurar escritores/aliases
do binding e do método e identificar os campos dos endereços candidatos
com fonte correspondente. AP`0x0207365c`, ordem real, monitor e valores do
aparelho continuam pendentes. Não foi ampliada a autorização de execução.
