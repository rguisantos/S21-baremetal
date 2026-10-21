# Log do LK na região debug-snapshot

Análise estática de 2026-10-21 do mesmo sboot HZC2 (SHA-256
`a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`)
e do Kernel.tar.gz já recebido. Complementa [UART e callbacks](lk-console-handoff.md).
Não foi obtido um dump dessa memória do telefone.

## Identificação do callback

O objeto em offset 0x2ef138 registra seu callback em 0xff948. O ponteiro em
0x2ef148 é 0xe80136c8: usando o delta LK anteriormente corroborado,
corresponde à rotina no arquivo **0xff6c8**. A lista é percorrida antes do
teste que pode bloquear o fallback UART. Assim, bloquear a UART nesse caminho
não bloqueia automaticamente este callback.

| Elemento | Observação no LK | Correspondência na fonte |
|---|---|---|
| Cabeçalho | Inicialização pode zerar 0x1000 bytes em 0xf0000000 | Região header começa em 0xf0000000, tamanho 0x10000 |
| Cursor | u32 lido/escrito em 0xf0000200 | DSS_OFFSET_LAST_LOGBUF = 0x200 |
| Indicador de volta | escreve 1 em 0xf0000208 | DSS_OFFSET_CHECK_EOB = 0x208 |
| Início do log | 0xf0010000 | reserved-memory/debug_snapshot/log_kernel |
| Limite exclusivo | 0xf0210000 | tamanho log_kernel = 0x200000 (2 MiB) |
| Região seguinte | não usada como buffer pelo callback analisado | log_platform começa em 0xf0210000 |

Isso identifica um **log em memória compatível com debug-snapshot**, e não
um transmissor externo. Não demonstra persistência após power-off ou acesso
pelo shell. Os endereços são do caminho analisado e da fonte correspondente;
não fornecem propriedade da região para o payload.

## Comportamento da gravação

0xff6c8 recebe o ponteiro dos bytes em x1 e o tamanho em x2. Lê o cursor
u32 do cabeçalho. No caminho com cursor dentro do intervalo e dados que cabem,
chama 0x1af3c0 (rotina de cópia confirmada por loads/stores) e atualiza o cursor.
Se os dados ultrapassam o fim com cursor admitido pelo ramo de wrap, zera a
cauda, escreve o indicador de volta e reinicia a cópia em 0xf0010000.
Cursor fora dos limites também leva ao início do buffer. Os testes de faixa
usam aritmética de 32 bits; não generalizar isso como um validador robusto para
comprimentos arbitrários. Não portar essa rotina sem validar tamanho e destino.

Em 0xff928 a inicialização testa bit 16 de 0x15860404; conforme o ramo, zera
os primeiros 0x1000 bytes do cabeçalho antes de registrar o callback.
Também lê uma estrutura em 0x021b5000; se o primeiro u32 é 0x000b1109,
chama 0xff788, que encaminha faixas daquela estrutura ao mesmo callback.
Isso é evidência de incorporação de logs anteriores, mas não identifica todos
os produtores nem demonstra que o ramo seja usado no aparelho.

## Preservação e leitura no kernel Samsung

No DTS consultado, `debug-snapshot` referencia o header e log_kernel por
`memory-region`. O driver `debug-snapshot.c`:

- Mantém os primeiros `DSS_KEEP_HEADER_SZ = 768` bytes do header ao inicializar;
  portanto os offsets 0x200/0x208 ficam na parte preservada nesse passo.
- `dbg_snapshot_fixmap()` aceita o cursor se estiver entre início e fim
  inclusivos da região configurada. Se inválido, reinicia o cursor e zera o log.
- `dbg_snapshot_init_proc()` usa o indicador de volta para copiar o log em
  ordem cronológica para `last_kmsg`, antes de inicializar o novo log.
- Cria `/proc/last_kmsg` somente se o item estiver habilitado, houver tamanho
  e a alocação funcionar. A chamada usa modo 0; não atribuir acesso público
  efetivo sem examinar o sistema.
- Sob CONFIG_SEC_PM_DEBUG, pode criar `/proc/sec_log` com modo 0440,
  expondo o log atual. A existência e as permissões reais não foram coletadas.

O defconfig recebido tem CONFIG_DEBUG_SNAPSHOT=m e CONFIG_SEC_PM_DEBUG=m.
Isso é configuração de referência; módulos carregados e estado de boot podem
mudar o resultado. SELinux e permissões podem impedir leitura pelo Shizuku,
como já aconteceu com outros arquivos. Nenhum desbloqueio de acesso é inferido.

## Leitor offline e testes

```bash
python3 scripts/test_snapshot_log.py
python3 scripts/inspect_snapshot_log.py snapshot.bin
python3 scripts/inspect_snapshot_log.py snapshot.bin --output log.bin
```

O leitor requer um dump **contíguo e exato de 0x210000 bytes**, correspondente
a [0xf0000000, 0xf0210000), sem prefixo. Valida tamanho, cursor e indicador
0/1; reconstrói o anel em ordem cronológica e emite metadados/hashes.
Não adquire memória, não aceita endereço arbitrário e não autentica a origem.
`--output` cria um arquivo novo e recusa sobrescrever. Sem essa opção, não
imprime o conteúdo potencialmente privado do log. Não fornecer o sboot como
dump: ele é código e não contém os bytes dessa região em execução.

Testes sintéticos: **6 casos de reconstrução/limites e 7 recusas PASS**.
Incluem log parcial com cauda antiga, anel com wrap, cursor nos dois extremos,
tamanho incorreto, cursor fora da região e flag inválido. Isso valida o leitor,
sem demonstrar o estado físico da RAM ou executar o firmware.

## Decisão para o R10

Não usar essa região como área livre nem escrever um marcador do diagnóstico
nela: a fonte a reserva para logs e não foi obtido contrato de posse/handoff.
O diagnóstico continua mantendo seu registro dentro da própria imagem.

A alternativa de observação agora tem mecanismo identificado, mas ainda falta
um meio autorizado e disponível de ler/preservar os bytes. A coleta UART já
recebida não responde isso. Não é necessário reenviar os pacotes nem repetir
as leituras de FDT/iomem/cmdline que falharam. A próxima análise pode acompanhar
as rotinas de dump que exportam a memória, sem presumir acesso pelo Android.

## Proveniência das fontes adicionais

| Arquivo no Kernel.tar.gz | SHA-256 |
|---|---|
| drivers/soc/samsung/debug/debug-snapshot.c | `158602ffb2c6d09503cdaaae9e1e6158bb2d3425b0b4894d1e26a1b43bb4f24e` |
| drivers/soc/samsung/debug/debug-snapshot-local.h | `a77f20ad7bcfed361ffb164322d2245f6019c5716fa16a0777c79f9d7916d0b7` |
| arch/arm64/boot/dts/exynos/exynos2100.dts | `586ca56987bbaacce0a38ddaee8a852721caaaeb9096ada6bfde8bc8c0d88ca8` |
