# HZC2: ACK inicial e publicação posterior das máscaras DMC

Análise estática sobre `faed93b`, sboot de 4194304 bytes, SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
O ACK do handshake inicial **não certifica a publicação posterior das
máscaras** no caminho selecionado. Há duas áreas de dados e dois sinais
diferentes. Esta entrega delimita ordem de programa, não cronologia medida,
visibilidade entre núcleos ou ausência de uma barreira adicional.

## Dois sinais e duas áreas

| Etapa | Testemunho de código | Consequência delimitada |
|---|---|---|
| Publicação DVFS | Thumb0x56ef2 escreve0x38e00 em local0xa5900108 | ACPM passa a esperar zero |
| Configuração AP | BL2 espera não zero em0x179e4 e relê em0x179f8; chama0x19038 em0x17a40 | Seleção/configuração anterior ao ACK |
| ACK AP | 0x17a50 zera AP0x15900108; retorna em0x17a5c | A chamada0x17eb0 retorna ao chamador |
| Retomada ACPM | 0x56ef6..0x56efa sai com zero;0x56f00/0x56f0a publicam bases0x38e00/0x3a600 | Inicia a continuação de DVFS7 |
| Outro sinal | Init7 publica0x1234abcd em local0xa590010c,0x56e6e, antes do POP0x56e70 | Distingue-se do ACK de0x108 |
| Espera AP | Após voltar de0x17eb0,0x17ecc espera0x1234abcd em AP0x1590010c | Ainda antecede a entrada posterior0x18000 |
| Construção posterior | 0x18000 chama0x1dc90; seu caminho selecionado alcança NEWTIME/slot24 | Contém as stores de máscaras já identificadas |

Core0x38e00 é a área dos registros por domínio usados pela inicialização
DVFS. Core0x3a600 é o cabeçalho/diretório correspondente ao registro BL2
sob o alias. Elas não podem ser tratadas como uma única publicação.
A [origem das máscaras](newtime-dmc-bl2-producer-hzc2.md) continua
correta sob suas condições; o ACK de0x108 não acrescenta uma prova de que
a etapa posterior já terminou.

A função0x17e14 chama0x17974 em0x17eb0, depois faz o poll de0x10c e outras
operações/gates, atualiza o ponteiro NEWTIME em0x17fe8 e só então chama
0x1dc90. Nesta função, a chamada nominal de slot24 em0x1e2e0 pode chegar a
0x2d568 e às stores0x2d82c/0x2d840/0x2d850. Outras passagens/escritores
anteriores não foram excluídos; esta é a ordem desse caminho selecionado.

## Init7, init9 e o que ainda não está ordenado

O loop ACPM0x38e6a..0x38ebe avança o índice e o ponteiro em48 bytes por
entrada. Sob contagem, enabled, callbacks e estado preservados, o callback
do descritor7 retorna antes de chamar o descritor9 em0x38e90. O inicializador
DMC0x5f600 instala a tabela de métodos em desc9+12.

O sinal0x1234abcd é gravado **antes** do retorno de init7. A partir daí,
o modelo delimitado contém dois caminhos: o AP pode progredir pela entrada
tardia0x18000, e o ACPM pode retornar do callback7 e avançar para init9.
As evidências selecionadas não ordenam init9 versus a publicação tardia
das máscaras. O JSON apresenta duas ordenações abstratas que respeitam as
arestas selecionadas e invertem esse par. São controles do modelo, não
execuções observadas nem prova de que ambas sejam viáveis no hardware.

Em0x18018, o AP ainda zera **0x15900104**, após retornar de0x1dc90.
Nenhum consumidor ACPM dessa store foi demonstrado nesta entrega. Não se
converte esse endereço numa barreira final sem seguir o seu leitor.
A [continuação do canal direto3](newtime-fast-channel-hzc2.md) identifica
esse endereço como palavra1 do buffer candidato, mas o método +0 DVFS
consulta0x10c e compara outro magic. O trecho local não estabelece uma
dependência do clear0x104 para o consumo DMC.
As chamadas intermediárias, outros sinais e efeitos opacos podem impor
restrições adicionais. Tampouco foi provada corrida entre os núcleos.

## Condições das relações entre AP e ACPM

As arestas entre os lados exigem o alias dos registradores e amostras
atribuídas às escritas desta invocação. O zero do poll ACPM precisa ser
atribuído ao ACK0x17a50, e não ao clear inicial0x179a8 ou a outro escritor.
O magic lido pelo AP precisa vir da publicação atual de init7, não de
estado anterior. A leitura que encerra o primeiro poll AP e sua recarga
posterior também não são garantidamente iguais.

Assim, o resultado positivo é a separação das etapas e a ordem local
selecionada. Alias físico, correlação das amostras, coerência/visibilidade,
alcançabilidade completa, frescor das máscaras até comandos8/9 e
slot47/X0 continuam abertos. A continuação investiga o gate do canal3;
outras condições que liberam o consumo posterior DMC permanecem abertas.

## Reprodução

```sh
python3 scripts/inspect_newtime_dmc_init_order_hzc2.py /caminho/sboot.bin --json /tmp/dmc-order.json
python3 -m unittest discover -s scripts -p 'test_newtime_dmc_init_order.py'
```

[Extrator](../scripts/inspect_newtime_dmc_init_order_hzc2.py),
[13 testes](../scripts/test_newtime_dmc_init_order.py),
[JSON](references/newtime-dmc-init-order-hzc2.json).
GNU confere76 palavras A64/9 alvos e115 instruções Thumb/19 alvos,
14 literais e30 operandos selecionados. As recusas por tamanho/hash
ocorrem antes do GNU, com exit2 sem JSON. O relatório é determinístico.

Avaliadores das palavras reais cobrem os polls, publicação0x38e00, magic
exato, ACK zero, raízes após o poll e instalação de métodos DMC. O loop do
framework é exercitado com manager/flags/callbacks explícitos e hooks que
alteram registradores voláteis. Orçamentos são do host; não são timeouts de
firmware. As ordenações abstratas apenas conferem o modelo de precedência.
A suíte NEWTIME passou com586 testes. Sem novo QEMU ou execução Samsung.
