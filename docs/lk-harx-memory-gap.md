# Intervalo Harx omitido pelo construtor de RAM

Análise de 2026-10-22 UTC das imagens HZC2 identificadas em
[uH earlymem e Harx soc_info](el2-earlymem-hzc2.md). Os offsets são de arquivo,
exceto os estados relativos à imagem explicitamente indicados. Não houve
execução do firmware ou recuperação de novos valores do telefone.

Um dos serviços que afeta a construção dos bancos tem retornos constantes
decodificados no Harx: **base 0xc0000000, tamanho 0x01400000 (20 MiB)**.
No ramo correspondente, o LK deixa de descrever esse intervalo como RAM.
A execução desse ramo continua condicional; isso não fecha o mapa do aparelho.

## LK pede informação do Harx

O construtor 0xfad60 chama 0xf9320 em 0xfaee8, passando ponteiros para base
e tamanho em sua pilha. A função consulta o serviço HVC **0xc6000020**:

| Etapa no sboot | Efeito |
|---|---|
| 0xf9340–0xf934c | lê o flag relativo 0x487c90; zero segue para saídas zero e retorno -1 |
| 0xf9350–0xf9368 | consulta índice 0, por wrapper 0xedff0: DSB SY, HVC #0, RET |
| 0xf936c–0xf9378 | exige resultado 0xe1200100; divergência retorna erro |
| 0xf937c–0xf9394 | consulta índice 1, guardado como base; retorno -1 é erro |
| 0xf93a4–0xf93bc | consulta índice 2, guardado como tamanho; retorno -1 é erro |
| 0xf93cc–0xf93d4 | escreve os dois resultados de 64 bits e retorna zero |
| 0xfaeec / 0xfaef0 | sucesso conserva buffers; erro leva o chamador a zerar ambos |

Não se confundiu esse namespace OEM Harx com o comando uH 0x83000002 ou
com o conduíte PSCI. Os wrappers e identificadores estão separados no binário.

## Handler e tabela do Harx

O dispatcher 0x1534 preserva x1 em x28. A comparação em 0x15f0–0x15fc
reconhece 0xc6000020 e desvia para 0x1aec. Esse trecho limita o índice a 5,
lê um halfword na tabela **0xc9c0** e faz extensão de sinal, multiplicação
por quatro e soma à base **0x1b0c**. Foram seguidos apenas os índices usados
por esse chamador LK:

| Índice | Halfword assinado | Alvo | Valor construído em x28 |
|---|---:|---|---|
| 0 | 386 | 0x2114 | 0xe1200100 por MOVZ + MOVK |
| 1 | 0 | 0x1b0c | 0xc0000000 por MOVZ |
| 2 | 2 | 0x1b14 | 0x01400000 por MOVZ |

Os três caminhos terminam por B para 0x2124, que carrega o ponteiro de
contexto salvo e grava x28 por STR em 0x2128. Não se inferiu que o RET local
de 0x2148 entregue diretamente x0: o resultado passa pelo contexto.

O intervalo derivado é **[0xc0000000, 0xc1400000)**. São constantes desse
handler, não valores recuperados de logs ou conteúdo inicial presumido da
BSS. O fim coincide com a base do nó el2_code criado pelo LK, mas isso não
une os dois intervalos ou prova disponibilidade do que fica fora deles.

## Efeito condicional na criação de nós RAM

Antes desse ponto, x19 é calculado como o retorno de -0x12e/índice 2 mais
os 32 bits baixos do retorno de -0x12e/índice 1. São dependências ainda sem
valores observados; mensagens do LK as identificam como SEC_DRAM_BASE/SIZE.

Depois de criar o primeiro nó iniciado em 0x80000000, o trecho
0xfaf38–0xfaf58 verifica se a base e o tamanho Harx são ambos não zero:

1. Em 0xfaf48, forma tamanho de 32 bits `base_Harx - x19` e, em 0xfaf50,
   chama 0xf1570 para criar um nó iniciado em x19.
2. Em 0xfaf54/0xfaf58, muda x19 para `base_Harx + tamanho_Harx`.
3. Os próximos nós começam a partir desse novo x19, com divisão adicional
   condicionada à informação de tabela de páginas segura.

Com os retornos constantes acima, o novo x19 desse ramo é **0xc1400000**.
O intervalo Harx é omitido entre os nós; não se trata de uma nova entrada
reg inserida por esse trecho em `/reserved-memory`. Os valores anteriores
de x19 e dos demais serviços precisam ser válidos para interpretar as faixas;
uma subtração em W não é uma validação de ordem ou ausência de sobreposição.
Não foi produzido um DTS com bancos presumidos a partir desse exemplo.

## O flag não comprova inicialização bem-sucedida

O escritor localizado em 0xf90d8 grava 1 no flag 0x487c90 depois do caminho
de carga e da chamada SMC 0x82000480 retornar zero. Porém, essa gravação
ocorre **antes** do HVC 0xc6000040 em 0xf90dc. O ramo de erro desse HVC não
limpa o flag no trecho inspecionado. Assim, flag=1 isoladamente não comprova
que toda a inicialização Harx foi bem-sucedida; o caminho de consulta ainda
precisa produzir a versão e os dois resultados esperados.

## Dependências que permanecem abertas

| Entrada usada pelo LK | Procedência rastreada | Falta |
|---|---|---|
| Tamanho total x25 | getter 0x11b758, leitura de 0x02038848 e possível limite por configuração | conteúdo e limite efetivos |
| Base/quantidade para x19 inicial | SMC legado -0x12e, índices 2/1, versão 0x66001000 | respostas e tradução para a interface positiva usada pelo Harx |
| Divisão SEC_PGTBL | SMC 0x82002060, índices 1/2 | respostas e ramo efetivo; os dois componentes também consultam esse serviço |
| Intervalo Harx | HVC 0xc6000020, constantes descritas acima | execução do caminho LK/Harx e resposta efetiva |
| Caminho adicional do construtor | leitura em 0x15860810 e comparação com 0xfd | valor efetivo; sem atribuir nome de modo de boot |

O Harx dá contexto aos nomes de soc_info: índice 2 é impresso como base de
Secure DRAM; índice 1 como quantidade reservada para segurança; índice 20
como tamanho de Secure DRAM. As chamadas são 0x3a0/0x3c0/0x3b4 e as strings
ficam em 0xc19e/0xc169/0xc1be, respectivamente. Não se igualaram quantidade
reservada e tamanho
da região segura nem se transferiram esses nomes automaticamente ao ID
legado do LK. A tradução entre interfaces continua sem prova.

## Reprodução e validação

```bash
python3 scripts/inspect_el2_hzc2.py /caminho/sboot.bin \
  /caminho/uh.bin /caminho/harx.bin
python3 -m unittest discover -s scripts -p 'test_el2_hzc2.py' -v
python3 -m unittest discover -s scripts -p 'test_lk*.py' -v
```

O inspetor exige os três hashes originais. Seu novo decodificador limitado
segue a tabela e aceita apenas MOVZ X28, MOVK X28 opcionais e B ao ponto de
saída conhecido. Rejeita loads dinâmicos, chamadas, outro registrador,
destino de saída diferente, truncamento, desalinhamento e caminhos longos.
Isso verifica esses retornos constantes; não emula o dispatcher ou o boot.

O [relatório reproduzível](references/el2-hzc2.json) agora contém
`harx_memory_info` e `lk_harx_gap`. Três testes novos cobrem imediatos de
64 bits, branches assinados, tabelas assinadas, limites e recusas. Com os
seis testes EL2 e 27 testes LK, **33 testes de host passaram**. A CLI foi
conferida nas três imagens recebidas e o JSON regenerado.

O próximo ponto continua sendo os valores/ramos soc_info e SEC_PGTBL que
determinam o restante dos bancos. O material recebido basta para seguir a
análise estática; não há novo arquivo necessário ou autorização de boot físico
derivada deste marco.
