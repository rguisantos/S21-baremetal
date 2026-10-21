# DTB vendor → seleção → DTBO → DPM → buffer do kernel

Análise e desenvolvimento em 2026-10-21. Firmware: sboot HZC2 já recebido,
SHA-256 `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91`.
Os offsets abaixo são do arquivo, não endereços de execução observados.
Complementa o [modelo de cópias v3](lk-v3-layout.md).

## Cadeia estática ligada ao ponteiro registrado

| Etapa | Evidência no sboot |
|---|---|
| Registrar a região DTB vendor | 0x12e850 chama 0x149188; store em 0x14918c salva x0 no global relativo 0xcd3560 |
| Consumir esse ponteiro | 0x149214 chama 0x149030 com string DTB; 0x149074 lê o mesmo global |
| Copiar a tabela de trabalho | 0x149084 copia 32 bytes para 0xfb400000; após checks de magic/tamanho, 0x1490c0 copia a tabela |
| Selecionar entrada | 0x1490c4 obtém revisão via 0xed9e8; tail branch 0x1490d4 chega a 0x148d68 |
| Combinar base com DTBO | 0x14935c chama 0x17a900 com base, tamanho base, overlay e tamanho overlay; 0x149384 copia o resultado para 0x8b080000 |
| Combinar com DPM | 0x1493a0 verifica header no buffer 0xf0005000; no caminho não negativo, 0x1493d0 chama a mesma rotina de merge e 0x1493ec copia o resultado para 0x8b080000 |

A identificação de merge UFDT é sustentada pelos argumentos e mensagens
`[UFDT] DT Overlay Complete!` e `DPM: Merge Complete`, não por símbolos ELF
recuperados. Não foi executada a rotina Samsung 0x17a900.

O DTBO pode vir do carregamento da partição para o buffer de trabalho ou do
ponteiro previamente registrado, conforme o ramo em 0x14922c/0x149438. Não se
determinou no aparelho o valor do flag que escolhe esses caminhos. Ambos usam
o seletor rastreado. O getter de revisão 0xed9e8 consulta um valor em cache e
chama outro helper se necessário; o valor efetivo não foi capturado.

O buffer **0x8b080000** coincide com o ponteiro usado pelos helpers de edição
e com x0 no salto final já documentado. Isso fecha a ligação estática entre
a região vendor e o buffer do kernel, sem capturar seu conteúdo final.
O LK ainda modifica chosen, RAM e reservas depois das etapas acima.

## Seleção por revisão: primeira correspondência inclusiva

0x148d68 começa as entradas em `header_size`, avança **32 bytes** por entrada
e usa custom0/custom1 como limites mínimo/máximo. A primeira entrada em que
`mínimo <= revisão <= máximo` é escolhida. Os campos Android id/rev não são
esses limites. Não se escolhe a entrada mais específica entre várias válidas.

A endianness tem uma condição própria do firmware: quando custom1 convertido
de big-endian é <=0xff, ele converte ambos os limites; caso contrário usa os
valores dos loads little-endian diretamente. O novo auditor reproduz essa
condição, inclusive seu comportamento pouco intuitivo para valores maiores.
Não substituir por um decoder incondicionalmente big-endian.

As tabelas stock conferidas usam o caminho big-endian de limites pequenos:

| Entrada DTBO | Revisão mínima | Revisão máxima |
|---|---:|---:|
| 0 | 0x02 | 0x0f |
| 1 | 0x10 | 0x10 |
| 2 | 0x11 | 0x11 |
| 3 | 0x12 | 0x12 |
| 4 | 0x13 | 0x13 |
| 5 | 0x14 | 0x14 |
| 6 | 0x15 | 0x15 |
| 7 | 0x16 | 0x20 |

A tabela base tem uma entrada de 389.876 bytes, em offset 64 da região,
cobrindo 0x00..0xff. O cenário explícito **revisão 0x10** seleciona base 0 e
DTBO 1. Não é uma identificação da revisão do telefone. As revisões 0/1 e
acima de 0x20 não encontram DTBO nessa tabela; não extrapolar um fallback.

## DPM recebido e teste de aplicação no host

`dpm.img` do BL tem 8.192 bytes e SHA-256
`e4f80e53094bdcadb3e379cdf91a37bd295979c8ea251505a311a8294eec0f8d`.
Sua árvore ocupa os primeiros **2.180 bytes / 0x884**. O restante não é
interpretado como parte do FDT nem como prova de assinatura verificada.

Os oito símbolos de fixup existem no DTB base: dpm, dss, log_arrdumpreset,
log_arrdumppanic, log_fatal, ehld_dbgc, itmon e memlogger_policy. Foram
aplicados os oito overlays de placa, cada um seguido pelo DPM, com
**fdtoverlay/libfdt, DTC 1.7.2**, fora do Git:

- **8/8 candidatos passaram** na aplicação do host;
- em cada candidato, o DPM alterou **35 propriedades**;
- UARTs, GIC, timer e PSCI conservaram as propriedades que tinham após o
  overlay da placa; UART1 continuou okay;
- nenhum candidato passou a ter nó device_type=memory;
- os nós log_arrdumpreset, log_arrdumppanic e log_fatal ficaram disabled;
- os seis campos de `/dpm/security`, incluindo seclog_enable, ficaram zero.

O [relatório da matriz](references/lk-dtb-host-overlay-matrix.json) registra
hashes das entradas/candidatos, intervalos e resultados. São candidatos
produzidos por **libfdt no host**, sem demonstração de equivalência byte a
byte com UFDT Samsung ou com o FDT do aparelho. Os DTBs gerados não foram
publicados como árvores prontas para R10.

Essas políticas não demonstram por que os nós proc/sysfs estavam inacessíveis
ao shell, nem liberam regiões reserved-memory para outro código. Também há
`fastboot-support=1` sob a configuração dump-mode do DPM; esse valor não
comprova suporte ao comando genérico fastboot boot ou a um caminho de flash.

## Auditoria reutilizável e testes

```bash
python3 scripts/check_lk_dtb_selection.py /caminho/sboot.bin \
  /caminho/vendor_boot.img /caminho/dtbo.img /caminho/dpm.img --revision 0x10
python3 scripts/test_lk_dtb_selection.py -v
```

O auditor faz somente leituras e imprime JSON. Exige sboot/DPM HZC2 de hashes
conhecidos e revisão explícita; limita os arquivos a 64 MiB. Valida intervalos
das tabelas e FDTs, seleciona entradas e resolve os símbolos DPM na base.
Sua política aceita tabelas v0 com header/entry/entries_offset de 32 bytes,
até 128 entradas. Esses limites e validações são conservadores do host,
**não uma emulação de todos os checks do firmware**. A ferramenta não aplica
overlays, não gera DTB e marca `is_final_fdt=false`.

Resultado: **6 testes de host passaram**, cobrindo inclusividade, primeira
correspondência, lacunas, revisão unsigned, dois encodings, o limiar 0xff,
truncamento, contagem/offset/tamanho inválidos, FDT inválido e símbolos ausentes.
Também foi executado o CLI com os arquivos stock, sem repetir coletas rish.
Na execução conjunta, **13/13 testes de layout e seleção passaram**. Foram
conferidos os 31 cenários stock de revisão 0x02..0x20 e as recusas CLI de
DPM incorreto e revisão sem entrada correspondente.

O [relatório do cenário 0x10](references/lk-dtb-stock-rev10.json) é reproduzível
pelo comando acima. Para reproduzir a aplicação de host, com fdtoverlay 1.7.2
disponível no PATH, pode-se usar os helpers do auditor para separar as entradas:

```python
# Executar da raiz do repositório; caminhos abaixo apontam aos arquivos raw.
import sys, subprocess, tempfile
from pathlib import Path
sys.path.insert(0, 'scripts')
from check_lk_dtb_selection import audit, entry_blob
v = Path('/caminho/vendor_boot.img').read_bytes()
d = Path('/caminho/dtbo.img').read_bytes()
p = Path('/caminho/dpm.img').read_bytes()
r = audit(v, d, p, 0x10)  # somente cenário; CLI acima confere hashes
region = v[int(r['vendor_region_offset'], 16):]
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    base, dpm = tmp/'base.dtb', tmp/'dpm.dtb'
    base.write_bytes(entry_blob(region, r['selected_base']))
    dpm.write_bytes(p[:r['dpm']['fdt_size']])
    for e in r['overlay_table']['entries']:
        overlay, board, candidate = tmp/'overlay.dtbo', tmp/'board.dtb', tmp/'candidate.dtb'
        overlay.write_bytes(entry_blob(d, e))
        subprocess.run(['fdtoverlay', '-i', str(base), '-o', str(board), str(overlay)], check=True, timeout=30)
        subprocess.run(['fdtoverlay', '-i', str(board), '-o', str(candidate), str(dpm)], check=True, timeout=30)
```

`inspect_sboot_hzc2.py` inclui `dtb_pipeline` com os destinos das chamadas e
as palavras dos registradores/seletores. Intervalos para desassemblagem:
0x149030:0x149188, 0x148d60:0x148f78 e 0x1491e0:0x14944c.

## Próximo bloqueio

A seleção da revisão no telefone, o FDT após todas as edições dinâmicas e as
reservas efetivas continuam desconhecidos. O próximo rastreio deve ligar os
argumentos de initrd/memória/reservas às propriedades escritas no buffer final.
Não se altera a entrada R10 ou seu mapa de RAM com base nesses candidatos.
