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

## Continuação: origem do destino e construção da memória

Segunda análise em 2026-10-21 UTC, no mesmo sboot identificado acima. Mantém-se a convenção de offsets e a hipótese de mapeamento comum código/dados; não são endereços físicos do sboot demonstrados. Não foi executado firmware.

### Deslocamento do kernel: produtor encontrado

O caminho de `load_boot_images` contém comparação com `ANDROID!` e, após ela, o seguinte trecho:

```asm
0xfb9a4  mov   x0, #0x101c
0xfb9a8  mov   x3, #0
0xfb9ac  mov   x2, #0
0xfb9b0  mov   x1, #0
0xfb9b4  movk  x0, #0xc200, lsl #16
0xfb9b8  dsb   sy
0xfb9bc  smc   #0
0xfb9c0  cbnz  x0, #0xfbb70
0xfb9c4  ubfiz w2, w2, #0xf, #6
0xfb9c8  adrp  x1, #0x4a0000
...
0xfb9e0  str   w2, [x1, #0x48]
```

Serviço chamado: **0xc200101c**. Se x0 retorna zero, o campo gravado é `(w2_retornado & 0x3f) << 15`. Se x0 não é zero, `0xfbb70–0xfbb90` imprime a mensagem em `0x216770` (`[KASLR] KASLR failed to get random number...`), força w2=0 e retorna ao armazenamento em 0xfb9c8. Portanto, neste caminho, há **64 deslocamentos possíveis**, de zero a **0x1f8000**, em passos de **0x8000 (32 KiB)**. A nomenclatura KASLR agora tem apoio na mensagem referenciada pelo ramo de erro; o retorno efetivo do serviço não foi capturado.

O campo é o mesmo lido no BLR de 0xfbe14. A fórmula desse caminho passa a ser:

`destino = 0x80080000 + ((w2_SMC & 63) << 15)` no sucesso, e `0x80080000` no ramo de erro observado.

Intervalo aritmético: **0x80080000 a 0x80278000**, somente para esses caminhos. Não é uma faixa de RAM livre. Não foi demonstrado que não existam outros escritores/alias ou caminhos. Em 0xfb9e8 grava-se ainda 0xcdefcdef em 0x80001000; em 0xfba00 o deslocamento é gravado em 0x80001004. Essas gravações são pistas do contrato, não instruções para o R10 acessar tais locais.

A função em 0x12e214 também lê o campo ao calcular limites a partir de 0x80080000. Seu rastreamento completo até a cópia/relocação da imagem permanece pendente. O R10 atual é ligado em endereço fixo e não deve ser considerado compatível com esse deslocamento apenas por ter o mesmo endereço base nominal.

### Ponteiro comum ao FDT e construtor de nós RAM

Em `0xfbc30`, o chamador carrega **0x8b080000**; em `0xfbc40`, armazena-o no global relativo **0x4740f8** antes de chamar `load_boot_images`. Helpers de árvore usam esse mesmo global:

- `0xf12c8`: valida a árvore, procura um caminho e chama uma rotina de adição de nó.
- `0xf13b0`: trata valores textuais/células (distingue primeiro caractere `<`), valida a árvore e escreve uma propriedade.
- `0xf1240`: lê o campo de tamanho em +4 com conversão big-endian, ajusta-o e escreve de volta.
- `0xf1570`: formata `memory@%lx` e `/memory@%lx`, adiciona nó, monta `reg` com o formato **`<0x%x 0x%x 0x%x>`** usando endereço alto, endereço baixo e tamanho de 32 bits, e escreve `device_type = memory`.

As identificações dos helpers são inferências de instruções, argumentos e strings, não símbolos recuperados de ELF. A ligação entre o ponteiro usado na edição da árvore e o x0 do salto é agora mais forte; o conteúdo final desse endereço ainda não foi lido em execução.

### RAM e reservas dependem do estado de boot

O chamador `0xfad60` começa obtendo um valor em `0x11b758` para x25. Também usa SMC via `0xf6088`, inclusive x0=-0x12e e x1=2, preservando um retorno em x26. Não foi atribuída semântica final a esses serviços sem seguir seus handlers.

Exemplos de construção observada:

| Offset da chamada | Endereço/tamanho passados ao construtor 0xf1570 |
|---|---|
| 0xfaf34 | endereço 0x80000000; tamanho de 32 bits calculado com w26 |
| 0xfaf50 | endereço/tamanho dependentes de x19 e valores locais retornados por outra rotina |
| 0xfb678 / 0xfb690 | faixas divididas usando x19, x21 e x27 |
| 0xfb7a8 | laço a partir de **0x880000000**, com nós de **0x20000000 (512 MiB)** e quantidade dependente de x25 |

Não foi selecionado o ramo efetivamente usado pelo aparelho de 12 GB. Não converter esses exemplos em um DTS com bancos presumidos ou usar MemTotal como substituto. As chamadas dão evidência de montagem dinâmica e divisão de bancos; não enumeram por si só as reservas finais.

A rotina `0x148a80` procura `/reserved-memory` e chama `0x148770` com nomes como `el2_code`, `el2,uh` e `kaslr`. Em `0x148b1c` chama o wrapper `0x209a28`, que decodifica como **HVC #0; RET**, com identificador 0x83000004 e endereços de buffers locais; os valores desses buffers são usados em uma chamada posterior. Isso demonstra participação de outra interface de firmware nesse caminho. **Não demonstra que PSCI use HVC**: o DTB stock continua declarando PSCI SMC, e não foi habilitada sondagem de conduíte alternativo.

### Limites e próxima etapa

Avanços: produtor do deslocamento encontrado, ramo de falha com zero, ponteiro de edição ligado ao argumento do salto e construção dinâmica de nós de memória localizada. Ainda faltam mapeamento/relocação completos do sboot, handlers dos serviços, fluxo de cópia da Image, reservas efetivas e EL/cache final. As verificações de cache da primeira etapa continuam condicionais; nenhuma alteração no driver ou no contrato de entrada R10 foi feita a partir de uma hipótese.

Para reproduzir a leitura, use o snippet anterior variando o intervalo: `0xfb9a4:0xfba20` (SMC e campo), `0xfbb70:0xfbb94` (erro), `0xfbc2c:0xfbc48` (ponteiro), `0xf1570:0xf164c` (nós), `0xfad60:0xfaf88` e `0xfb670:0xfb7cc` (ramos RAM), `0x148a80:0x148b74` (reservas). Nenhum arquivo extra é necessário para continuar esta análise estática.

## PR #4 — consulta posterior e resolução

A consulta anterior sem PR aberto foi superada: o [PR #4](https://github.com/rguisantos/S21-baremetal/pull/4) foi criado às 02:14:23 UTC de 2026-10-21. Nesta continuação ele foi revisado e **encerrado como substituído, sem merge**, mantendo o branch. Head: `9dca3969cc6e6ff571cbfd1cc440f7b27ac93143`. Não houve incorporação do empacotador defeituoso sobre a main.

A revisão do diff (dois commits/quatro arquivos) confirmou as falhas já descritas em [branch-packer-review.md](branch-packer-review.md). Reproduzido novamente `heap-buffer-overflow` no `memcmp` do validador do PR com entrada de quatro bytes e ASan/UBSan. Na main, `scripts/test_payload.py`: **60 PASS**; `scripts/test_payload_loader.py`: **um handoff real com 25 IRQs e cinco recusas PASS**. Esses testes verificam o software do projeto, não executam sboot/Harx.
