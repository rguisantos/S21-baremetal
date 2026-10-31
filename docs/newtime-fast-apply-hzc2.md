# HZC2: percurso do helper DVFS direto e dependências

Continuação de 30/10/2026 (Campo Grande), após a integração das PRs #51/#52.
Base da análise: `f7caa3e`; árvore de base também presente na main
`3ab54d1`. Sboot: 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
PCs são offsets do arquivo; dados core usam a tradução selecionada
`file=core+0x2d800`. Não se afirma um alias físico observado.

**O helper `0x5a938` pode terminar com retorno zero e limpar o sinal mesmo
quando seus callees retornam erro.** Seu laço visita quinze entradas;
as dependências podem selecionar o domínio 0, apesar de ele ser pulado
pelo laço externo. Isso não demonstra que o canal direto libere DMC8/9.

## Laço e conclusão

O [método +0](newtime-fast-channel-hzc2.md) chama o helper somente quando
a leitura local de `0xa590010c` é exatamente `0xabcd1234`. Esse valor
continua distinto do magic `0x1234abcd` publicado por init7.

O helper começa em índice 0, pula essa entrada e os índices 8–10, visita
**1–7 e 11–18** em ordem e termina antes de ler o descritor 19. A base
é core `0x2f44c`, com stride de 48 bytes. Para cada entrada `D`:

| Etapa | Instruções e comportamento local |
|---|---|
| Seleção | `0x5a95a/0x5a95c` leem `P=M32[D+12]` e `M16[P+22]` |
| Halfword não zero | `0x5a972` chama `0x5ba90(D,M32[D+32]>>8)` |
| Halfword zero | `0x5a97a` chama `0x5baa4(D)` para dependências |
| Após o retorno | `0x5a986` relê `M32[D+32]>>8` e chama `0x59a8c(índice,valor)` |
| Folha `0x59a8c` | Um `BX LR`; não publica nada no corpo local |
| Final do percurso | `0x5a998` grava zero em `0xa590010c`; `0x5a99a` coloca R0=0 |

O laço não testa os retornos dessas chamadas. O clear depende de o percurso
chegar ao fim: memória ilegível, callee sem retorno, alteração das raízes
ou dos registradores preservados podem impedir a conclusão. Não há uma
garantia física de sucesso ou timeout obtida desse retorno zero.

Os dados são lidos durante o percurso. Um callee pode mudar o valor relido
da entrada corrente ou o seletor de uma entrada futura. Os testes
distinguem essas releituras de uma fotografia inicial de todos os dados.

## Wrapper, dependências e domínio 0

`0x5ba90` lê o ponteiro em `D+44`. Se não zero, chama-o com os argumentos
entrada/valor; se zero, chama `0x5b790(D,valor,2)`. O wrapper devolve o
resultado desse callee. Seu chamador no laço não usa esse resultado.

`0x5baa4` captura **uma vez** a contagem u8 em `M32[D+12]+9`. Para cada
posição `j`, relê o ponteiro do header do pai e busca o ID u8 em
`header+36+j`. Calcula `T=u32(0x2f44c+48*ID)`, lê o **u32 inteiro** em
`M32[T+12]+24` e chama `0x5ba90(T,valor)`. Não aplica o shift de oito bits
usado pelo laço direto. Depois das chamadas, retorna zero sem agregar
erros. Contagem zero não lê a lista.

Esse corpo não elimina duplicatas nem aplica os skips do laço externo.
Um teste com ID 255 fornece memória explícita e confirma o endereço
calculado, sem promover esse ID a um domínio válido do dispositivo.
A alteração da contagem depois da primeira chamada não muda o limite
capturado; a alteração do ponteiro do header afeta os IDs posteriores.
O corpo local não chama recursivamente `0x5baa4`; os efeitos de callbacks
e do fallback não estão excluídos por essa observação.

Sob preservação da tabela inicial, o callback `+44` do domínio 0 é
core `0x2c1ed`, Thumb no arquivo `0x599ec`. Portanto uma dependência de
ID 0 pode chegar a esse callback mesmo com o skip externo. O teste
integrado interpreta wrapper, tradução de endereço e callback com
palavras cruas. O callback chama, em ordem:

1. `0x59e34`, com os argumentos recebidos.
2. `0x5a004`, recebendo R0 retornado pela primeira chamada.
3. `0x5a2b8`, após colocar R0=2.

Ao retornar da terceira chamada, sobrescreve R0 com zero. Esses três
corpos ficam como fronteiras opacas nesta entrega. Não se conclui que
eles executem a transição DMC do [caminho FVP/domínio0](newtime-dmc-method12-hzc2.md).

O fallback `0x5b790` foi conferido estaticamente, incluindo a chamada a
`0x5adb0` e os despachos pelos métodos `+16/+20` de core `0x2eccc`.
Os alvos iniciais são `0x57b20/0x572f8`, condicionados à tabela preservada.
Os testes param nessa fronteira; os demais branches/callees não são
apresentados como execução completa. O retorno local final é zero após
os callees selecionados retornarem.

## Produtor do magic e limites

A busca exata dos quatro bytes little-endian de `0xabcd1234` em todos
os 4 MiB encontrou somente `0x56eb0`, o literal usado na comparação.
Isso **não identifica um escritor** e não exclui construção aritmética,
transporte, código externo ou valores de outro momento. O produtor
continua aberto. O clear AP `0x15900104` continua sem ligação demonstrada
a uma barreira de consumo DMC; os testes integrados não precisam mapear
os bytes locais de `0xa5900104`.

Os corpos `0x59e34`/`0x5a004` e trechos de `0x5a2b8` foram delimitados
na [continuação do callback0](newtime-domain0-callees-hzc2.md), incluindo
uma rota nominal ao DMC17. Restam o restante de `0x5a2b8`, o carregador e
o produtor do magic com evidência de store e origem. Permanecem abertos
alias/frescor/visibilidade físicos, ordem init9 versus máscaras tardias,
efeitos transitivos e slot47/X0. Sem execução Samsung ou ampliação QEMU
do firmware; o baseline QEMU do código R10 foi reexecutado separadamente.

## Reprodução e validação

```sh
python3 scripts/inspect_newtime_fast_apply_hzc2.py /caminho/sboot.bin --json /tmp/fast-apply.json
python3 -m unittest discover -s scripts -p 'test_newtime_fast_apply.py'
python3 -m unittest discover -s scripts -p 'test_newtime*.py'
python3 scripts/validate_baseline.py --output-dir build/baseline-fast-apply-novo
```

[Extrator](../scripts/inspect_newtime_fast_apply_hzc2.py),
[20 testes](../scripts/test_newtime_fast_apply.py),
[JSON reproduzível](references/newtime-fast-apply-hzc2.json) e
[registro de validação](references/newtime-fast-apply-validation-20261030.json).
GNU: 383 instruções, 420 halfwords, 68 alvos relativos, 17 literais e
36 operandos selecionados. A suíte NEWTIME passou em 623 testes, incluindo
80 listas aleatórias de dependências. Avaliador ganhou somente LDRH
imediato, com zero-extension e memória ausente recusada.
JSON reproduzido exatamente; imagens curta, longa e alterada recusadas
com exit 2, stdout vazio e nenhum JSON criado. Baseline completo passou
nas nove etapas: host 43/60/17, diagnóstico 12, loader 1+5 e leitor 17.

Continuação de31/10: o [produtor local do magic](newtime-dmc-magic-hzc2.md) foi delimitado em0x369a0, com publicação/campainha/poll e sem alegação de escritor global único ou EL3 efetivo. Aliases físicos, ordem ACPM e slot47/X0 continuam abertos.
