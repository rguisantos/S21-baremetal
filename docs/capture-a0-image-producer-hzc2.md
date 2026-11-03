# A0: mecanismo de alinhamento da diferença de 64 KiB

Rodada de 03/11/2026, Campo Grande, base PR #87 / b090537.
**Mecanismo demonstrado: 24576 bytes a menos antes do alinhamento e 40960
bytes a menos de padding somam os 65536 bytes.** A opção, objeto ou função
que originou a diferença anterior ao alinhamento não foi identificada.
Esse nível de causa continua aberto; nenhum preenchimento ou geometria
foi autorizado/adotado por esta decomposição.

## Símbolos stock recuperados, com controle no candidato

O novo [leitor kallsyms](../scripts/capture_a0_kallsyms.py) implementa somente
o formato observado Linux 5.4: offsets relativos unsigned, base fixa, sem
absolute-percpu. A fonte Samsung fixada por SHA
c5ad9994240e67ebdc40878c191be040bf30db398bc8513ea1f156eaebd86bf2
fornece scripts/kallsyms.c e kernel/kallsyms.c para ordem/expansão dos campos.
Fonte, boot, tarball e membros são verificados; parsers recebem os mesmos
buffers imutáveis conferidos, sem hash seguido de reabertura do caminho.

O localizador usa a sequência dos dez dígitos apenas para achar candidatos.
Exige uma única tabela com todos os 256 offsets/terminadores coerentes;
valida contagem limitada, ordem/alcance dos endereços, todos os nomes,
todos os marcadores de blocos de 256 e geometria completa das tabelas.
Limites de entrada, initdata, arquivo e runtime precisam concordar com os
headers ARM64/PE. Não há fallback para outro formato.

| Controle | Resultado |
|---|---|
| Stock HZC2 | 131783 símbolos; marcadores e limites conferem |
| Candidato preservado | 131799 símbolos; marcadores e limites conferem |
| Conferência no candidato | Todos os 131799 registros endereço/tipo/nome constam no System.map preservado |
| System.map candidato | SHA bb66bf96a5b801e14874862a5494a4fd3e598e225557d89b164f1157f5859f11 |

O stock não tem ELF/mapa de link disponível nesta investigação. Símbolos
embutidos delimitam intervalos, **não reconstituem sua tabela ELF de seções**.
Interpretar o formato pela fonte não prova proveniência completa do build stock.

## O ponto em que a diferença passa a 64 KiB

Coordenadas relativas a _text, sem inferência de RAM física livre:

| Limite ou intervalo | Stock | Candidato | Delta candidato − stock |
|---|---:|---:|---:|
| _etext / __start_rodata | 15532032 | 15532032 | 0 |
| __end_rodata | 26681344 | 26656768 | -24576 |
| __stop_notes | 26797080 | 26772504 | -24576 |
| Fim de swapper_pg_dir + PAGE_SIZE, antes de ALIGN | 26820608 | 26796032 | -24576 |
| Padding zero até __init_begin | 49152 | 8192 | -40960 |
| __init_begin / stext | 26869760 | 26804224 | -65536 |
| Intervalo init até __initdata_begin | 1040384 | 1040384 | 0 |
| __initdata_begin / início PE .data | 27910144 | 27844608 | -65536 |

A Image candidata tem 29403648 bytes, SHA
9614f9a0ec8e83177ccb2010a585a128fd11f028cb46c417f2c1dbed2c2fd571,
contra 29469184 no stock. Runtime: 33910784 contra 33976320, respectivamente.

memory.h define SEGMENT_ALIGN=SZ_64K quando CONFIG_DEBUG_ALIGN_RODATA está
desativado. IKCONFIG stock e .config candidato confirmam esse estado e
páginas de 4 KiB. vmlinux.lds.S reserva os intervalos observados para idmap,
reserved_pg_dir e swapper_pg_dir; em seguida executa:

```text
. = ALIGN(SEGMENT_ALIGN);
__init_begin = .;
```

Nos dois arquivos, init é o próximo múltiplo de 65536 após essas reservas.
Todos os bytes dos intervalos de padding da tabela são zero. A diferença
de 24576 anterior à operação é ampliada para 65536 ao cruzar esse limite.
Não se demonstrou mudança da opção de alinhamento: ambos seguem a mesma regra.

O limite _etext igual **não prova código idêntico ou mesmo tamanho não
alinhado da seção .text**. O intervalo init→initdata de mesmo comprimento
também não prova igualdade de bytes. Essas equivalências não são pressupostos.

## Receita, seções e hipóteses

Receita candidata da fonte recebida:
objcopy -O binary -R .note -R .note.gnu.build-id -R .comment -S.
O runner aplica o mapeador independente já validado no PR #86 aos mesmos
bytes do vmlinux preservado e mantém o SHA publicado. Retém no relatório
as 29 seções file-backed emitidas do candidato, incluindo .notes; não
confunde .notes com os nomes removidos. Sem recompilação ou repetição do
ensaio nativo de objcopy já concluído. A receita efetivamente usada para
produzir o stock não está disponível.

| Hipótese | Conclusão sustentada |
|---|---|
| Apenas trailer de 64 KiB omitido ao final | Excluída como explicação única: limites internos mudam antes de init/data |
| Novo alinhamento de 64 KiB escolhido no candidato | Sem evidência de troca: fonte/config e ambos os layouts seguem a mesma regra |
| Padding do linker contribui para o delta | Demonstrado: -40960, somados aos -24576 anteriores |
| Mapeador/receita candidata omitiu uma seção de 64 KiB | Nenhuma omissão adicional observada no mapeamento já conferido com objcopy; sem tabela ELF stock para comparar todas as suas seções |
| Objeto/função/opção ou ordem de link produziu os -24576 anteriores | Não identificada; igualdade de alguns limites não atribui a mudança |

O [relatório](references/capture-a0-image-producer-hzc2.json) fixa hashes
das tabelas, limites, fonte, configurações, Image e implementação. Reprodução
nos comandos da [investigação de cópia](capture-a0-copy-origin-hzc2.md).
Os 24 testes novos cobrem formatos corrompidos/ambíguos, todos os marcadores,
System.map divergente, padding não zero, buffers e limites de cópia.
[Validação](references/capture-a0-handoff-validation-20261103.json).

**Encerramento desta rodada:** amplificação por alinhamento demonstrada;
origem produtora anterior não identificada. Atribuição exige alvo concreto
adicional: mapa/ELF stock ou comparação controlada de objeto/opção de build.
Não se deduz a causa das duas listas KMI ausentes ou de CRC/vermagic.
A [origem do corte](capture-a0-copy-origin-hzc2.md) permanece sem atribuição.
A0 aberto, A1 não iniciado, sem decisão OEM ou ação no aparelho; assinatura/
aceitação Samsung, SignerVer03, vbmeta pai, KMI e política runtime pendentes.
Somente código e relatórios textuais no Git.
