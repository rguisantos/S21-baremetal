# Passo a passo no aparelho: sonda e XNU no SM-G998B

Guia para executar no telefone, do desbloqueio ao primeiro boot do XNU,
com um PC **Linux Mint** (Heimdall) e a recovery **Fox R13** (OrangeFox
R12.0 de malick186). Vale para a main de 27/11/2026 em diante e para o
kernel candidato do fork `2300193` (run 46028220411).

Ordem: testes com o **Android stock HZC2** primeiro; a ROM MonsterROM
(Android 17) só depois, porque ela troca o vendor_boot e os kits contam com
o stock (seção 9).

Ferramentas de gravação:
- **Heimdall** no Mint, já usado aqui para ler a PIT do aparelho em 30/10
  ([observação](download-pit-observation-hzc2.md)). Grava imagens cruas por
  nome de partição da PIT: `BOOT`, `RECOVERY`, `VBMETA` (entradas 13, 15 e
  23).
- **Fox R13** e ADB para trocar a BOOT sem modo download
  (`s21xnu-switch.sh`).
- Odin no Windows continua valendo: os kits trazem os `.tar.md5`.

> **Riscos, antes de começar**
> - Desbloquear o bootloader **apaga todos os dados** e queima o Knox
>   (0x1) para sempre: Samsung Pay/Wallet, Pasta Segura e Samsung Health
>   protegido param de funcionar, mesmo travando de novo.
> - **Nunca trave o bootloader** com boot, vbmeta, recovery ou qualquer
>   imagem que não seja a stock: o aparelho para em "Custom binary blocked".
>   Para travar um dia, grave antes o firmware stock completo.
> - **Não atualize o firmware** pelo celular. Os kits só aceitam o HZC2.
> - A sonda e o XNU só gravam a partição BOOT. RECOVERY e VBMETA mudam uma
>   vez (passo 3). A volta é sempre o boot stock.

## 0. O que preparar

No telefone:
- SM-G998B com **G998BXXSJHZC2**: Configurações → Sobre o telefone →
  Informações do software → "Versão de banda base" terminando em `HZC2`.
- Bateria acima de 60%, cabo USB-C de dados.

No Mint:

    sudo apt install heimdall-flash adb git python3 openssl liblz4-1 lz4 \
        patch build-essential gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu unzip
    git clone https://github.com/rguisantos/S21-baremetal
    git clone https://github.com/jimmycarles9991-glitch/s21xnu
    git -C s21xnu checkout a128f07b04987e60f5e13e2ce67b19ae009672cd

Firmware HZC2 do SM-G998B (`BL_`, `AP_`, `CP_`, `CSC_`) e a Fox R13
([release](https://github.com/malick186/s21-ultra-fox-recovery/releases/tag/r13.0-p3s-stable)):
confira o SHA-256 dela com o que o autor publica.

    mkdir AP_HZC2 && cd AP_HZC2
    tar -xf ../AP_G998BXXSJHZC2_*.tar.md5 boot.img.lz4 vendor_boot.img.lz4
    tar -xf ../BL_G998BXXSJHZC2_*.tar.md5 vbmeta.img.lz4
    cd ..

O `tar` reclama do MD5 no fim dos arquivos; é normal. Os kits conferem boot,
vendor_boot e vbmeta pelos hashes fixados do HZC2 e recusam outro firmware.

Modo download (usado várias vezes): telefone desligado, segure **Volume+ e
Volume−** e conecte o cabo ao PC; na tela de aviso, **aperte** Volume+ uma
vez. Confira com `sudo heimdall detect`.

## 1. Backup

Tudo vai ser apagado no passo 2: fotos, conversas, contas (Smart Switch ou
Google). Anote a senha da conta Google; o aparelho pede depois do reset.

## 2. Desbloquear o bootloader

1. Sobre o telefone → Informações do software → toque 7 vezes em "Número
   de compilação".
2. Opções do desenvolvedor → **Desbloqueio OEM**: ligar. Se não aparecer:
   internet, data e hora automáticas, e espere.
3. Desligue. Segure Volume+ e Volume− e conecte o cabo. Na tela de aviso,
   **segure** Volume+ (pressão longa) e confirme com Volume+.
4. O telefone apaga tudo e reinicia. Configuração mínima, **conecte à
   internet** e confira nas Opções do desenvolvedor: Desbloqueio OEM ligado e
   cinza.

## 3. vbmeta desativado e Fox R13

Gere o vbmeta (só o do BL HZC2 é aceito):

    cd S21-baremetal
    python3 lab/s21xnu-p3s/vbmeta_disabled.py \
        --vbmeta ../AP_HZC2/vbmeta.img.lz4 --out ../kit-vbmeta

A saída deve mostrar `flags 0 -> 0x3, 1 byte(s) alterado(s)` e descritores
com `boot` e `vendor_boot`. Os guias do TWRP para o S21 Exynos gravam esse
vbmeta junto com a recovery, porque sem ele o S-Boot recusa imagem que não é
assinada pela Samsung.

Tire a `recovery.img` do tar da Fox (se vier `recovery.img.lz4`, rode
`lz4 -d recovery.img.lz4 recovery.img`):

    mkdir ../fox && tar -xf ../<arquivo-da-Fox>.tar -C ../fox && ls ../fox

Modo download e, no Mint:

    sudo heimdall flash --RECOVERY ../fox/recovery.img \
        --VBMETA ../kit-vbmeta/vbmeta.img --no-reboot

Quando terminar, segure **Volume− e Power** até a tela apagar e, logo em
seguida, **Volume+ e Power com o cabo no PC**: tem de abrir a Fox. Se o
Android ligar antes, o sistema stock pode trocar a recovery de volta;
regrave. Siga também o que o autor da Fox pede no primeiro boot dela. Se o
Android pedir "Falha na verificação, redefinir", aceite (os dados já foram
apagados).

**Observado em 27/11:** depois do vbmeta desativado, o Android stock entra em
loop para a recovery (`decryptWithKeystoreKey fail`; o `init` pede
`reboot recovery`). Na Fox: Wipe → **Format Data** (`yes`) e depois Reboot →
System. Isso apaga os dados do usuário. Sempre que o vbmeta mudar, formate de
novo.

## 4. Backup das partições stock pela Fox

Na Fox, com o cabo no PC (se o `adb devices` não listar, alterne o MTP na
Fox, como diz a release):

    adb shell 'for p in boot vendor_boot dtbo vbmeta vbmeta_system; do dd if=/dev/block/by-name/$p of=/tmp/$p.img; done'
    mkdir backup-stock && cd backup-stock
    for p in boot vendor_boot dtbo vbmeta vbmeta_system; do adb pull /tmp/$p.img; done
    sha256sum *.img

O `boot.img` e o `vendor_boot.img` devem dar os hashes dos pins
(`28818995…` e `f5b18d6b…`). O `vbmeta.img` vai diferir do pin: é a cópia já
desativada do passo 3, com a partição inteira. **Mande os hashes.**

**Observado em 27/11:** no primeiro start a Fox recompactou o ramdisk do
boot (kernel e arquivos iguais, hash `9d405a0c…`). Se o `boot.img` não der
`28818995…`, regrave o boot do firmware antes do passo 5:

    lz4 -dc ../AP_HZC2/boot.img.lz4 > /tmp/boot-hzc2.img
    adb push /tmp/boot-hzc2.img /tmp/stock-boot.img
    adb shell 'dd if=/tmp/stock-boot.img of=/dev/block/by-name/boot bs=4096 conv=fsync && sync; sha256sum /dev/block/by-name/boot'

## 5. Kit da sonda e o teste

    cd ../S21-baremetal
    python3 lab/s21xnu-p3s/prepare_first_boot.py \
        --stock-dir ../AP_HZC2 --s21xnu ../s21xnu --out ../kit-sonda
    (cd ../kit-sonda && sha256sum -c SHA256SUMS)

Guarde o `kit-sonda/lab-key.pem`: o kit do XNU usa a mesma chave.

Gravar pela Fox (caminho A). Primeiro garanta que a `/cache` está montada
(sem ela o backup ficaria na RAM; o script recusa):

    adb shell 'mount /cache 2>/dev/null; grep " /cache " /proc/mounts'

Tem de aparecer uma linha. Se não, monte a Cache no menu Mount da Fox.

    adb push ../kit-sonda/boot.img ../kit-sonda/s21xnu-switch.sh /tmp/
    adb shell sh /tmp/s21xnu-switch.sh install /tmp/boot.img
    adb shell sh /cache/s21xnu/s21xnu-switch.sh to-xnu --no-reboot
    adb shell sh /cache/s21xnu/s21xnu-switch.sh status
    adb reboot

O `install` guarda a BOOT stock em `/cache/s21xnu` e confere o hash; o
`to-xnu` grava a sonda, relê e confere. Reinicie com `adb reboot` e **não
toque nos botões**: com Volume− e Power o S-Boot lê as teclas e abre a Fox
(`sbl_check_keypad`, observado em 27/11). O botão Reboot da tela da Fox
também é evitado, porque ela tem rotinas que mexem no boot ao reiniciar.

Caminho B, modo download: `sudo heimdall flash --BOOT ../kit-sonda/boot.img`.

O telefone reinicia na sonda: **tela vermelha** por uns 25 s, depois o
diagnóstico (MMU, PSCI, GIC) e um reinício sozinho depois de uns 40 s, de
volta à sonda. **Fotografe a tela vermelha** (nítida; vale filmar):

| Linha | Esperado |
|---|---|
| `LOADER` | `no SWEETXNU payload` |
| `ENTRY` | `el=00000001 x0=8B080000` |
| `IMAGE` | `at=` entre 80080000 e 80278000, múltiplo de 8000 |
| `INITRD` | `start=84080000` e o `end=` do `kit-sonda/ROTEIRO.md` |
| `FB` | `w=000005A0 stride=00001680` |

Tela preta, outra cor ou números diferentes também são resultado: fotografe
do mesmo jeito.

**Observado em 27/11:** o logo "Samsung Galaxy" ficou na tela por mais de 2
minutos, sem tela vermelha e sem reinício. Nesse caso use a sonda cega
(5b).

## 5b. Sonda cega (sem tela)

A sonda cega grava marcas nos registradores INFORM do PMU e pede reset para
a recovery; o resultado aparece no log do S-Boot, que se lê na Fox. Detalhes
em [s21xnu-sonda-cega-p3s.md](s21xnu-sonda-cega-p3s.md).

    cd ~/S21-baremetal && git pull
    python3 lab/s21xnu-p3s/prepare_first_boot.py --cega entrada \
        --stock-dir ../AP_HZC2 --s21xnu ../s21xnu \
        --lab-key ../kit-sonda/lab-key.pem --out ../kit-cega-entrada
    python3 lab/s21xnu-p3s/prepare_first_boot.py --cega etapas \
        --stock-dir ../AP_HZC2 --s21xnu ../s21xnu \
        --lab-key ../kit-sonda/lab-key.pem --out ../kit-cega-etapas

Na Fox, com a BOOT em stock (`status`), para cada kit (entrada primeiro):

    adb shell mount /cache
    adb push ../kit-cega-entrada/boot.img /tmp/cega.img
    adb shell sh /cache/s21xnu/s21xnu-switch.sh to-android --no-reboot
    adb shell sh /cache/s21xnu/s21xnu-switch.sh install /tmp/cega.img
    adb shell sh /cache/s21xnu/s21xnu-switch.sh to-xnu --no-reboot
    adb shell 'sync; echo b > /proc/sysrq-trigger'

O `sysrq` reinicia pelo kernel, sem as rotinas de reinício da Fox. Cada
entrada na Fox recompacta a BOOT stock (volta a `9d405a0c…`, o `status` mostra
`desconhecido`); o `to-android --no-reboot` regrava o stock conferido. Sem
tocar no aparelho. Esperado: volta sozinho à Fox em segundos. Se ficar
no logo mais de 2 minutos: Volume− e Power até apagar e, se não abrir a Fox
sozinho, Volume+ e Power. Então:

    adb shell 'grep -a -E "show_reset_reason_rawdata|sbl_check_reboot_mode" /proc/sec_log'

O último par de linhas é o boot que entrou na Fox. `inform2: 0x5101` = o
shim rodou; a tabela está no `ROTEIRO.md` do kit. **Observado em 27/11:**
entrada deu `0x5101` e etapas `0x510F`, as duas com `PINFORM = 12345604`. O
variante `--cega relogio` deu `0x5113` em 57 s: o PSCI não reinicia e o
contador é de 26 MHz. Com `--cega tela` o usuário viu vermelho e depois verde
(`inform2: 0x6C5F`): o painel mostra o framebuffer depois de desmascarar o
trigger do DECON0. O patch 0004 leva isso à sonda padrão e ao XNU. Refaça o
kit do passo 5 (`git pull`) e grave: agora a tela vermelha tem de mostrar as
linhas, e a sonda volta sozinha à Fox depois de ~70 s.

Para sair da Fox para o Android, use **Reboot → System** no menu. Com root no
Android (Magisk), os testes podem rodar pelo Android com `su`, sem a Fox.

## 6. Voltar ao Android

Segure **Volume− e Power** até apagar e, logo em seguida, **Volume+ e Power
com o cabo no PC** (Fox). Então:

    adb shell mount /cache
    adb shell sh /cache/s21xnu/s21xnu-switch.sh to-android --no-reboot
    adb reboot

Sem a Fox: modo download e
`sudo heimdall flash --BOOT ../backup-stock/boot.img` (ou Odin com
`AP_stock_boot.tar.md5`).

**Mande as fotos** antes do passo 7.

## 7. Segundo boot: o XNU

1. Baixe o artefato `xnu-kernel` do run
   [46028220411](https://github.com/rguisantos/s21xnu/actions/runs/46028220411)
   (logado no GitHub) e confira:

       unzip xnu-kernel.zip -d xnu-kernel
       sha256sum xnu-kernel/kernel.development.sweet
       # e0c75c109c90288504606cb8062da5c2397ec61024bd91620fe60475a57320d4

2. Gere o kit (1 CPU, sem raiz, sem Wi-Fi):

       python3 lab/s21xnu-p3s/prepare_xnu_boot.py \
           --stock-dir ../AP_HZC2 --s21xnu ../s21xnu \
           --kernel xnu-kernel/kernel.development.sweet \
           --lab-key ../kit-sonda/lab-key.pem --out ../kit-xnu

   O `ROTEIRO-XNU.md` deve dizer `build: fork 2300193, run 46028220411,
   patches até 0151`.
3. Na Fox, com o Android de volta na BOOT:

       adb shell mount /cache
       adb push ../kit-xnu/boot.img /tmp/xnu-boot.img
       adb shell sh /cache/s21xnu/s21xnu-switch.sh to-android --no-reboot
       adb shell sh /cache/s21xnu/s21xnu-switch.sh install /tmp/xnu-boot.img
       adb shell sh /cache/s21xnu/s21xnu-switch.sh to-xnu

   Caminho B: `sudo heimdall flash --BOOT ../kit-xnu/boot.img`.
4. Deve aparecer a tela do loader **achando** o payload SWEETXNU, depois o
   log do XNU em texto, em tela cheia. Sem raiz, o kernel para procurando o
   disco de sistema: **esse já é o marco.**
5. Fotografe cada tela, principalmente a última. Volte como no passo 6.

## 8. Depois

Com o kernel subindo, os próximos testes usam o mesmo kit com `--filefrag`
(raiz iOS `iosroot.img` em `/data`, sobreposição em RAM, sem gravar no
armazenamento; o `filefrag -v` pode rodar na Fox, que monta o `/data`) e
`--sweetwifi 3` e depois `4`, com os arquivos de
`wifi/prepare_wifi_files.py` em `/usr/local/etc/wifi`.

## 9. Instalar a ROM MonsterROM depois

Com os testes feitos e o Android stock de volta (`to-android`):
- instale a ROM pela Fox, como o autor indica. O instalador dela exige o
  bootloader HZC2 revisão 19 desbloqueado e uma recovery personalizada;
- ela grava boot, vendor_boot, dtbo, vbmeta (já com verificação
  desativada) e vbmeta_system. **Não grave o vbmeta do passo 3 por cima**;
- com a ROM, **não use** o boot stock nem o `AP_stock_boot.tar.md5`: o
  kernel stock não combina com o vendor_boot dela;
- os kits do XNU contam com o vendor_boot stock (o endereço do payload
  depende do tamanho dele). Para testar com a ROM instalada, os kits precisam
  receber o vendor_boot da ROM; isso ainda não existe. Para voltar tudo ao
  stock, grave o HZC2 completo.

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| `heimdall detect` não acha o telefone | Outro cabo ou porta, modo download de novo, `sudo` |
| Heimdall para com erro no meio | Não desligue; refaça o modo download e regrave a mesma imagem |
| `adb devices` vazio na Fox | Alterne o MTP na Fox; confira o cabo |
| Tela "Custom binary blocked by…" | Imagem não stock com bootloader travado: grave o HZC2 completo |
| Loop na sonda ou no XNU | Passo 6 |
| Android não inicia depois do passo 3 | Redefinição pela recovery ou HZC2 completo |
| Kit recusa o firmware | Não é o HZC2 fixado; confira o telefone e o AP/BL |
