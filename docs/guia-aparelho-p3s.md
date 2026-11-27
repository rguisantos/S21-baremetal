# Passo a passo no aparelho: sonda e XNU no SM-G998B

Guia para executar no telefone, do desbloqueio ao primeiro boot do XNU.
Vale para o repositório na main de 27/11/2026 (kits r21 em diante) e para
o kernel candidato do fork `2300193` (run 46028220411).

Caminho escolhido: só **Odin** para gravar e voltar. O TWRP é opcional: a
compatibilidade dele com o HZC2 (One UI 7) não foi conferida aqui, e o
Odin basta para tudo abaixo.

> **Riscos, antes de começar**
> - Desbloquear o bootloader **apaga todos os dados** e queima o Knox
>   (0x1) para sempre: Samsung Pay/Wallet, Pasta Segura e Samsung Health
>   protegido param de funcionar, mesmo travando de novo.
> - **Nunca trave o bootloader** com boot, vbmeta ou qualquer imagem que não
>   seja a stock: o aparelho para em "Custom binary blocked". Para travar um
>   dia, grave antes o firmware stock completo.
> - **Não atualize o firmware** pelo celular. Os kits só aceitam o HZC2, e
>   o desbloqueio deixou de existir no One UI 8 (que o S21 Ultra não
>   recebe).
> - A sonda e o XNU não gravam nada fora da partição BOOT; o vbmeta muda uma
>   vez (passo 3). A volta é sempre o boot stock pelo Odin.

## 0. O que preparar

No telefone:
- SM-G998B com **G998BXXSJHZC2**: Configurações → Sobre o telefone →
  Informações do software → "Versão de banda base" ou "Número de
  compilação" terminando em `HZC2`. Se for outro, grave antes o firmware
  HZC2 completo (BL, AP, CP, CSC) pelo Odin.
- Bateria acima de 60%, cabo USB-C de dados.

No PC:
- **Windows** com Odin 3.14.x e o driver USB da Samsung (para gravar).
- **Linux** (ou WSL2 com Ubuntu no Windows) para gerar os kits:

      sudo apt install git python3 openssl liblz4-1 patch build-essential \
          gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu unzip

      git clone https://github.com/rguisantos/S21-baremetal
      git clone https://github.com/jimmycarles9991-glitch/s21xnu
      git -C s21xnu checkout a128f07b04987e60f5e13e2ce67b19ae009672cd

- O firmware HZC2 do SM-G998B (os quatro arquivos `BL_`, `AP_`, `CP_`,
  `CSC_`), da mesma região do telefone.

Extraia do `AP_…HZC2….tar.md5` (o `tar` reclama do MD5 no fim; é normal):

    mkdir AP_HZC2 && cd AP_HZC2
    tar -xf ../AP_G998BXXSJHZC2_*.tar.md5 boot.img.lz4 vendor_boot.img.lz4
    tar -xf ../BL_G998BXXSJHZC2_*.tar.md5 vbmeta.img.lz4

O `vbmeta.img.lz4` vem do BL. Os kits conferem boot, vendor_boot e vbmeta
pelos hashes fixados do HZC2 e recusam qualquer outro firmware.

## 1. Backup

Tudo vai ser apagado no passo 2. Copie fotos, conversas e contas
(Samsung Smart Switch ou Google). Anote a senha da conta Google: o
aparelho pede depois do reset.

## 2. Desbloquear o bootloader

1. Configurações → Sobre o telefone → Informações do software → toque 7
   vezes em "Número de compilação" (modo desenvolvedor).
2. Configurações → Opções do desenvolvedor → **Desbloqueio OEM**: ligar.
   Se a opção não aparecer: telefone conectado à internet, data e hora
   automáticas, e espere; não continue sem ela.
3. Desligue o telefone. Segure **Volume+ e Volume−** e conecte o cabo
   ligado ao PC. Na tela de aviso, **segure Volume+** (pressão longa) para
   o modo de desbloqueio e confirme com **Volume+**.
4. O telefone apaga tudo e reinicia. Faça a configuração inicial mínima,
   **conecte à internet** e volte às Opções do desenvolvedor: o Desbloqueio
   OEM deve aparecer ligado e cinza ("bootloader já desbloqueado").

## 3. vbmeta com verificação desativada

Os guias de TWRP para o S21 Exynos gravam esse vbmeta junto, porque sem ele
o S-Boot recusa boot que não é assinado pela Samsung. No Linux:

    cd S21-baremetal
    python3 lab/s21xnu-p3s/vbmeta_disabled.py \
        --vbmeta ../AP_HZC2/vbmeta.img.lz4 --out ../kit-vbmeta

A saída mostra `flags 0 -> 0x3, 1 byte(s) alterado(s)` e os descritores
(devem aparecer `boot` e `vendor_boot`). Leve `kit-vbmeta/` ao Windows.

No Odin:
1. Telefone em **modo download**: desligado, segure Volume+ e Volume− e
   conecte o cabo; na tela de aviso, **aperte** Volume+ uma vez (pressão
   curta). A caixa `ID:COM` do Odin fica azul.
2. **USERDATA** = `vbmeta_disabled.tar.md5`. Nada nos outros slots.
3. Start. Deve terminar em **PASS** e reiniciar.

Se o Android pedir "Falha na verificação, redefinir o telefone", aceite a
redefinição (os dados já foram apagados no passo 2). Confira que o Android
inicia antes de seguir.

## 4. Gerar o kit da sonda

    python3 lab/s21xnu-p3s/prepare_first_boot.py \
        --stock-dir ../AP_HZC2 --s21xnu ../s21xnu --out ../kit-sonda

Saem, entre outros: `AP_s21xnu_sonda.tar.md5`, `AP_stock_boot.tar.md5`,
`ROTEIRO.md`, `lab-key.pem` e `SHA256SUMS`. Confira com
`cd ../kit-sonda && sha256sum -c SHA256SUMS`. **Guarde o `lab-key.pem`**:
o kit do XNU usa a mesma chave.

## 5. Gravar a sonda e fotografar

1. Modo download (como no passo 3). No Odin, **AP** =
   `AP_s21xnu_sonda.tar.md5`, os outros slots vazios. Start → PASS.
2. O telefone reinicia na sonda: **tela vermelha** por uns 25 s com
   linhas de texto, depois o diagnóstico (MMU, PSCI, GIC) e um reinício
   sozinho depois de uns 40 s, voltando à sonda.
3. **Fotografe a tela vermelha** (nítida, inteira; vale filmar). A tabela
   do `ROTEIRO.md` diz o que cada linha deve mostrar:

| Linha | Esperado |
|---|---|
| `LOADER` | `no SWEETXNU payload` |
| `ENTRY` | `el=00000001 x0=8B080000` |
| `IMAGE` | `at=` entre 80080000 e 80278000, múltiplo de 8000 |
| `INITRD` | `start=84080000` e o `end=` do seu `ROTEIRO.md` |
| `FB` | `w=000005A0 stride=00001680` |

Tela preta, outra cor ou números diferentes também são resultado:
fotografe do mesmo jeito.

## 6. Voltar ao Android

A sonda reinicia nela mesma. Para sair:
1. Segure **Volume− e Power** até a tela apagar (uns 7 s) e, logo em
   seguida, **Volume+ e Volume−** com o cabo conectado ao PC: modo
   download.
2. No Odin, **AP** = `AP_stock_boot.tar.md5` (do kit da sonda). Start →
   PASS. O Android volta como estava.

**Mande as fotos** antes do passo 7: elas confirmam os endereços que o
XNU vai usar.

## 7. Segundo boot: o XNU

1. Baixe o artefato `xnu-kernel` do run
   [46028220411](https://github.com/rguisantos/s21xnu/actions/runs/46028220411)
   (logado no GitHub), descompacte e confira:

       unzip xnu-kernel.zip -d xnu-kernel
       sha256sum xnu-kernel/kernel.development.sweet
       # e0c75c109c90288504606cb8062da5c2397ec61024bd91620fe60475a57320d4

2. Gere o kit (1 CPU, sem raiz, sem Wi-Fi: o primeiro marco é o kernel
   subir):

       python3 lab/s21xnu-p3s/prepare_xnu_boot.py \
           --stock-dir ../AP_HZC2 --s21xnu ../s21xnu \
           --kernel xnu-kernel/kernel.development.sweet \
           --lab-key ../kit-sonda/lab-key.pem --out ../kit-xnu

   O `ROTEIRO-XNU.md` deve dizer `build: fork 2300193, run 46028220411,
   patches até 0151`. Confira o `SHA256SUMS` do kit.
3. Modo download; no Odin, **AP** = `AP_s21xnu_xnu.tar.md5`. Start → PASS.
4. O que deve aparecer:
   - a tela do loader com ENTRY/IMAGE/INITRD/FB, agora **achando** o
     payload SWEETXNU;
   - o log do XNU em texto, em tela cheia;
   - sem raiz, o kernel para procurando o disco de sistema. **Esse já é o
     marco.**
5. Fotografe cada tela, principalmente a última antes de parar ou
   reiniciar. Volte como no passo 6.

## 8. Depois

Com o kernel subindo, os próximos testes usam o mesmo kit com:
- `--filefrag`: a raiz iOS (`iosroot.img` em `/data`, montado com
  sobreposição em RAM, sem gravar no armazenamento). Pede a imagem do
  sistema iOS montada à parte e a saída do `filefrag -v` dela;
- `--sweetwifi 3` (identifica o chip do Wi-Fi) e depois `4` (carrega o
  firmware), com os arquivos de `wifi/prepare_wifi_files.py` em
  `/usr/local/etc/wifi`.

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| Odin não vê o telefone | Driver USB da Samsung, outro cabo ou porta, modo download de novo |
| Odin: `FAIL` com "Only official released binaries" ou `Auth` | Bootloader travado ou vbmeta não gravado: refaça os passos 2 e 3 |
| Tela "Custom binary blocked by…" | Bootloader travado com imagem não stock: grave o firmware HZC2 completo |
| Loop na sonda ou no XNU | Passo 6 (Volume− e Power, depois modo download, boot stock) |
| Android não inicia depois do passo 3 | Redefinição pelo recovery (Volume+ e Power ao ligar, com o cabo no PC) ou firmware HZC2 completo pelo Odin |
| Kit recusa o firmware | O arquivo não é o HZC2 fixado; confira a versão do telefone e do AP |
