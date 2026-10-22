# Intervalos enviados pelo LK ao uH

Análise estática de 2026-10-22 UTC do sboot HZC2 já identificado por hash.
O chamador que alimenta a lista usada por [uH earlymem](el2-earlymem-hzc2.md)
foi localizado: o LK percorre a árvore FDT corrente e entrega o primeiro
intervalo de cada nó cujo nome começa com `memory` ao comando 0x83000002.
O conteúdo dessa árvore após as edições dinâmicas continua desconhecido.

## Cadeia ligada no binário

Os offsets abaixo são do arquivo sboot.bin. A análise não executa serviços.

| Etapa | Evidência |
|---|---|
| Preparação | 0xfb4dc carrega o FDT corrente; 0xfb4e0/0xfb4e8 constroem o callback 0x209a38; 0xfb4ec seleciona a string `memory` em 0x20e560 |
| Percurso | BL em 0xfb4f0 → 0x148c38, guardando o callback em x24 |
| Próximo nó | 0x148c6c, 0x148c9c e 0x148d3c chamam 0x11e9f8, equivalente ao percurso fdt_next_node com profundidade |
| Nome e filtro | 0x148cbc obtém o nome; 0x148cc8 obtém comprimento do prefixo; 0x148cd8 compara esse prefixo; 0x148cdc pula nomes diferentes |
| Propriedade | 0x148cf0 busca `reg`, string 0x20e558; 0x148d04 pula o nó se a propriedade estiver ausente |
| Decodificação | 0x148d08 copia os primeiros oito bytes; 0x148d10 lê mais quatro; REV X2 e REV W1 produzem base de 64 bits e tamanho de 32 bits big-endian |
| Callback | 0x148d20 passa base em x0; 0x148d24 deixa tamanho em w1; 0x148d2c faz BLR x24 |
| HVC | 0x209a38 converte argumentos para x1=base/x2=tamanho, x0=0x83000002; 0x209a5c chama 0x209a28, HVC #0 |
| Próxima fase | Depois do percurso, 0xfb4fc chama 0x148a80, que inclui o pedido earlymem 0x83000004 |

No uH do mesmo pacote, a entrada u64 em 0x16010 é 0xc1402004. Com a base
inferida 0xc1400000, corresponde ao handler 0x2004, aplicação 0/comando 2.
Esse handler recusa se o flag de inicialização já estiver marcado ou se
base/tamanho forem zero; caso contrário, encaminha-os à lista em 0x171f8
por 0x4574. O estado dessa lista fica na BSS, relativo à base da imagem.
Nem a aceitação pelo uH nem o conteúdo efetivo da lista foram observados.

O wrapper LK **sempre grava w0=0** em 0x209a60 após o HVC. O percurso
também segue diretamente ao próximo nó após BLR, sem testar o retorno.
Portanto, o retorno desse callback não demonstra aceitação de um intervalo.

## Critérios reais do percurso

- Seleciona pelo prefixo do nome do nó, incluindo o nome antes de `@`.
  `memory-extra` também corresponde; `ram@...` com device_type=memory não.
- Percorre a estrutura FDT em ordem, inclusive nós aninhados. Não aplica
  tradução por `ranges` de um barramento pai aos argumentos do callback.
- Não consulta `device_type` ou `status`. Um nó com status=disabled ainda
  pode fornecer argumentos se seu nome corresponder e tiver `reg`.
- Lê **somente os primeiros 12 bytes** de `reg`, sem laço por suas tuplas.
  Duas tuplas em um único nó não equivalem a dois nós para esse percurso.
- Não consulta as larguras de células nesse trecho. Não se atribuem ao LK
  as validações de tamanho/células implementadas pela ferramenta de host.

Esses detalhes descrevem a interface Samsung rastreada. Não mudam a
semântica geral de FDT nem o parser do payload. Um leitor genérico de bancos
RAM não substitui a reprodução desse callback.

## Checagem offline de uma árvore fornecida

```bash
python3 scripts/check_lk_uh_ranges.py /caminho/sboot.bin /caminho/arvore.dtb
python3 -m unittest discover -s scripts -p 'test_lk*.py' -v
python3 -m unittest discover -s scripts -p 'test_el2_hzc2.py' -v
```

O sboot deve ter o SHA-256 HZC2 já inventariado; a leitura é limitada ao
tamanho esperado mais um byte. A entrada FDT raw é limitada a 2 MiB e passa
pelo leitor estrito comum, inclusive a recusa de propriedades/nós duplicados.
Não são aceitos tabelas Android DT, LZ4 ou árvores sem intervalos submetidos.

O modelo de host exige células **explicitamente 2/1 no pai** de cada nó com
reg selecionado, tuplas completas de 12 bytes e fim sem overflow de 64 bits.
São limites deliberados da ferramenta para evitar representar entradas fora
do perfil. O binário não possui essas mesmas verificações no trecho acima.
Uma codificação diferente ou malformada é recusada, sem simular leituras
além da propriedade.

Para cada nó, o relatório registra os argumentos do primeiro intervalo,
quantas tuplas adicionais foram ignoradas e o resultado apenas da condição
base/tamanho não zero. Não une, ordena por endereço ou desconta reservas:
preserva a ordem dos callbacks. A condição inicial verdadeira não comprova
que o uH aceitaria o intervalo ou que ele esteja disponível para um payload.

O resultado mantém `runtime_observed=false`, `uh_acceptance_verified=false`,
`allocation_simulated=false`, `memory_map_verified=false`,
`free_memory_verified=false` e `is_final_fdt=false`. Nenhuma chamada SMC/HVC
é feita, e nenhum arquivo de firmware/FDT fornecido é alterado.

## Validação e consequência

Oito testes novos passaram, cobrindo ordem, endereços acima de 4 GiB,
prefixo versus propriedades, barramento aninhado, primeira tupla, larguras,
truncamento, overflow, bancos ausentes, argumentos zero e identidade da CLI.
Com os 19 testes LK anteriores e três do inspetor EL2, são **30 testes de
host aprovados**. Não houve alteração de código executado no telefone.

A CLI foi conferida com uma árvore sintética: dois callbacks, um deles com
tupla adicional corretamente ignorada. O DTB base stock de 389.876 bytes,
extraído da entrada 0 da região DT do vendor_boot HZC2, foi recusado por não
ter nós memory com reg. Isso concorda com o resultado anterior dos oito
candidatos placa+DPM e com a construção dinâmica de bancos localizada no LK.

O inspetor `inspect_el2_hzc2.py` agora inclui `lk_range_registration` e o
ponteiro do handler do comando 2. Seu [relatório reproduzível](references/el2-hzc2.json)
preserva chamadas e palavras que sustentam essa cadeia.

A origem imediata dos argumentos está fechada no caminho estático:
**FDT corrente → callback LK → comando 2 → lista uH → comando 4**.
Faltam os valores e ramos usados para construir os bancos nessa árvore,
incluindo os retornos soc_info/SMC, a limitação de tamanho de RAM e eventuais
edições posteriores. Essa é a próxima prioridade; o material recebido basta
para continuar, sem repetir as coletas rish já bloqueadas.
