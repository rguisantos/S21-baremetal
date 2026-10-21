# BL stock HZC2 — inventário e primeira análise estática

Recebido do usuário em 2026-10-21 UTC: `BL_G998BXXSJHZC2_G998BXXSJHZC2_MQB107295400_REV01_user_low_ship_MULTI_CERT.tar.md5`. Análise somente de leitura, sem instalar componentes, executar firmware ou publicar seus binários.

## Integridade e inventário

- Tamanho: **10.936.433 bytes**.
- SHA-256 do anexo: `5b48c27798b103ec906112fc4baad1aacd8d39c970dae6c478d3bd559e2cf31f`.
- TAR ocupa os primeiros **10.936.320 bytes**; trailer textual de 113 bytes.
- MD5 declarado e recalculado sobre esses bytes: `91ed463e696634f1fd11e3685093a9a8`, coincidentes. Isso verifica integridade do transporte/formato; não é validação criptográfica das assinaturas Samsung.
- Doze membros regulares LZ4; todos descompactados. Não há `abl.img` neste pacote.

| Componente descompactado | Bytes LZ4 | Bytes brutos | SHA-256 bruto |
|---|---:|---:|---|
| `sboot.bin` | 1963522 | 4194304 | `a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91` |
| `up_param.bin` | 3957356 | 4638720 | `e8f7f2d34b3657e24b8c32bbcc72099ee2317d138b3970c1393e87268a5f9028` |
| `ldfw.img` | 358429 | 8388608 | `9d52a013bffde6f3d734e02a359ce9323a7db75878fce60569f5989b63e057fd` |
| `tzsw.img` | 650712 | 1572864 | `83eedef172714cc2e24624a12e77ab7e7a2e04891fe98366f653b3e3a6c533c0` |
| `keystorage.bin` | 5485 | 524288 | `c4e455a7f2c5872b14f64f816a2167a8aec36a5126a58bc380f337c1fa984c4c` |
| `dpm.img` | 1663 | 8192 | `e4f80e53094bdcadb3e379cdf91a37bd295979c8ea251505a311a8294eec0f8d` |
| `uh.bin` | 54070 | 93832 | `c2f7cd2708be9c8ea3a4ff22f8bbf224f726107633e5b70b09b8f352784fe407` |
| `vbmeta.img` | 3793 | 10128 | `cd86d91b22e4e273abb65189cadea1c6d76683822e4fefa0c5407110462917ea` |
| `harx.bin` | 59851 | 3145728 | `5564dcb1f59c4a66a4c69f7042fb30ee14c97a31ba5a77427c4a08612e1dc21e` |
| `tzar.img` | 2828406 | 7340816 | `791c8818555e64d0e060c406e68748e869c7d53fbc9c9bbc893a1dd4f65a2077` |
| `vddcal_fw.bin` | 540518 | 2097152 | `2bac8e0eedc9395d7f5630442130a9ccae5a9201e700299a0a60a9565e886e39` |
| `ssp.img` | 495557 | 496640 | `f6be169ac04d7e8bed383143df0036c5bfabba5af5e2fc67d4160e15a9733380` |

## Identificação observada

Offsets abaixo são **offsets no arquivo descompactado**, não endereços físicos confirmados.

| Arquivo | Offset | Conteúdo |
|---|---|---|
| sboot.bin | 0x20dab8 | G998BXXSJHZC2 |
| sboot.bin | 0x4540 e 0x36c1b8 | v1.5(release):Athens-RP1A-1A19R1-1-gbfac7c7 |
| sboot.bin | 0x2169d8 | Starting kernel... |
| sboot.bin | 0x216a80 | configure_dtb |
| sboot.bin | 0x256028 | prepare_jump_to_kernel |
| harx.bin | 0xf1d0 | I818f7b22f Athens-RP1A-1504R1-1-g466e64b |
| harx.bin | 0x200020 | G998BXXSJHZC2 |
| tzsw.img | 0x100020 | G998BXXSJHZC2 |

`dpm.img` começa com magic FDT `d00dfeed` e totalsize 0x884; isso não o identifica como árvore final do kernel nem fornece por si só RAM utilizável. `vbmeta.img` começa por AVB0. Não foram auditadas assinaturas, cadeia AVB ou semântica completa desses componentes.

## Referências de código e salto encontrado

Decodificação AArch64 com Capstone 5.0.7; referências ADRP+ADD calculadas com origem de arquivo zero, assumindo que o trecho código/dados tenha o mesmo deslocamento de mapeamento, alinhado a página. Esse procedimento localiza candidatos; a base real do sboot e relocação ainda precisam ser estabelecidas.

- `0xfb454/0xfb458` referencia `configure_dtb` em `0x216a80`.
- `0xfbde8/0xfbdec` referencia `Starting kernel...` em `0x2169d8`.
- `0x170570/0x170578` referencia `prepare_jump_to_kernel` em `0x256028`.

Após a mensagem Starting kernel, o bloco decodificado é:

```asm
0xfbdf4  adrp x0, #0x4a0000
0xfbdf8  mov  x4, #0x80080000
0xfbdfc  mov  w3, #0
0xfbe00  mov  w2, #0
0xfbe04  mov  w1, #0
0xfbe08  ldr  w5, [x0, #0x48]
0xfbe0c  mov  w0, #-0x74f80000
0xfbe10  add  x4, x5, x4
0xfbe14  blr  x4
```

Bytes de 0xfbdf4 até 0xfbe17:
`201d00b00401b0d2030080520200805201008052054840b90061b152a400048b80003fd6`.

Escrever w0 zera a metade superior de x0: seu valor nesse ponto é **0x8b080000**. x1/x2/x3 ficam zerados. O destino é **0x80080000 + zero_extend(valor de 32 bits lido)**. A referência relativa 0x4a0048 fica além dos 4 MiB do arquivo: não é possível ler seu valor como se estivesse no binário recebido; base/mapeamento e inicialização desse estado continuam pendentes. Não presumir deslocamento zero, ASLR ou outra finalidade sem rastrear sua origem.

O padrão é compatível com passagem de um argumento de boot, mas **o conteúdo de 0x8b080000 não foi observado**. Não tratar esse endereço como FDT validado nem como autorização para carregar R10. Este bloco usa BLR, não ERET: por si só não muda o EL.

## Preparação de MMU/cache: evidência e condição

No mesmo caminho, `0xfbddc` chama `0x18a3a8` antes do bloco de salto. Essa rotina chama `0x189404`, que lê CurrentEL e desloca por dois. Seleciona leitura SCTLR_EL1/EL2/EL3 (`0x189420`, `0x189428`, `0x189430`). Se o bit M estiver ligado, chama `0x18997c` e segue para `0x189db8`.

- `0x18997c`: trecho inspecionado começa salvando DAIF, mascarando IRQ, ISB/DSB e lendo CLIDR_EL1 para percorrer níveis de cache. Ainda não foi concluída a auditoria de todo o percurso e de suas subrotinas.
- `0x189db8`: seleciona SCTLR do EL atual, limpa os bits **M (0)** e **C (2)**, escreve o registrador e faz ISB.
- A chamada é condicional ao bit M; isso **não demonstra C=0 em todos os estados possíveis**.
- Há chamadas posteriores antes do salto; não foi provado que nenhuma reabilite tradução/cache.
- Há seleção explícita de EL1/EL2/EL3, portanto a presença dessa função **não prova que o caminho real use EL2**, nem que os registradores do EL inferior satisfaçam o contrato R10.

`0xf6088` decodifica como `smc #0; ret`; há chamadas antes da preparação. A semântica completa desses serviços não foi determinada. Não inferir transição de EL/estado persistente apenas pela instrução SMC.

## O que este arquivo resolveu e o que falta

Resolvido: disponibilidade do BL exato, integridade do pacote, inventário real, identificação HZC2 e primeira sequência de código candidata ao handoff. A antiga pendência “enviar BL” foi atendida; **nenhum novo envio é necessário para a próxima análise estática**.

Próximas verificações neste mesmo material: estabelecer mapeamento do sboot; rastrear escrita do valor usado no destino; seguir construção/ajustes do FDT e reservas; auditar o caminho completo de cache e EL; separar condições dos caminhos normal/recovery. Somente depois avaliar alterações no contrato R10. RAM disponível, FDT final, EL real, permissões ICC/timer e configuração USI ainda não foram capturados em execução. Não foi produzido artefato para flash.

## Reprodução mínima

Use Python 3, `lz4==4.4.5` e `capstone==5.0.7` em ambiente isolado. O trecho abaixo lê somente sboot, sem extrair nomes/caminhos arbitrários do TAR:

```python
import tarfile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
import lz4.frame

with tarfile.open("BL_G998BXXSJHZC2_G998BXXSJHZC2_MQB107295400_REV01_user_low_ship_MULTI_CERT.tar.md5") as archive:
    compressed = archive.extractfile("sboot.bin.lz4").read()
sboot = lz4.frame.decompress(compressed)
assert len(sboot) == 4194304
for insn in Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(sboot[0xfbdf4:0xfbe18], 0xfbdf4):
    print(hex(insn.address), insn.mnemonic, insn.op_str)
```

Este snippet reproduz a decodificação de um pacote identificado por hash; não é um parser genérico endurecido para arquivos arbitrários. Não foram modificados drivers nesta etapa; a regressão de software anterior não constitui teste destes binários.

## Pull requests conferidos

Na consulta de 2026-10-21 UTC, busca do conector e endpoint GitHub `/repos/rguisantos/S21-baremetal/pulls?state=open` retornaram **zero PRs abertos**. [PR #2](https://github.com/rguisantos/S21-baremetal/pull/2) e [PR #3](https://github.com/rguisantos/S21-baremetal/pull/3) foram consultados individualmente: ambos `closed`, `merged=true`. O #3 foi mergeado no branch kilo; sua integração corretiva posterior à main está em [PR_INTEGRATION.md](../PR_INTEGRATION.md). Não havia PR novo a integrar nesta consulta.
