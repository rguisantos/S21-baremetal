# Origem dos dois módulos adicionais do HZC2

A captura do SM-G998B ZTO contém 276 nomes distintos em LSMOD. O
[ramdisk de vendor_boot](a0-monsterrom-hzc2.md) pede 274 deles.
A imagem pública de vendor do SM-G998B HZC2 XEO/OXM contém uma segunda
lista, em `/vendor/lib/modules/modules.load`, com exatamente os dois nomes
restantes, na ordem abaixo. A propriedade `ro.vendor.build.fingerprint`
de seu build.prop coincide integralmente com a linha 380232 do bugreport
ZTO. A comparação de fingerprint vincula modelo e build. A identidade
byte a byte entre as partições vendor XEO e ZTO continua sem medição.

## Quem pede a carga

Na imagem XEO, `/vendor/etc/init/init.exynos2100.rc` pede explicitamente
os dois módulos no evento `early-init` (linhas 3, 8 e 9). Cada chamada
usa modprobe com diretório `/vendor/lib/modules` e nome do arquivo.
Há um segundo pedido quando `sys.boot_completed=1` inicia o serviço
oneshot `insmod_sh_common` (linhas 1255–1263). No hardware exynos2100,
as linhas 15 e 16 de `/vendor/etc/init.insmod.exynos2100.cfg` passam os
mesmos nomes a `/vendor/bin/init.insmod.sh`, cujo ramo modprobe usa o mesmo
diretório. A primeira chamada e a configuração do serviço especificam os
nomes diretamente. A presença de uma lista modules.load permite comparar
inventários, mas por si só não identifica o leitor dessa lista.

No dumpstate ZTO, a propriedade ro.hardware vale exynos2100 (linha
380005) e init.svc.insmod_sh_common vale stopped (378823). As linhas
513029–513030 mostram os dois módulos carregados. As entradas de seus
provedores citam os mesmos consumidores nas linhas 513098, 513176,
513278 e 513304. Essa captura não informa qual dos pedidos conseguiu a
primeira inserção nem o código de retorno das chamadas.

| Arquivo em /vendor/lib/modules | Provedores em modinfo e LSMOD¹ | Bytes de .text iguais ao recompilado² | Registros em __versions |
|---|---|---:|---:|
| input_booster_lkm.ko | exynos_pm_qos, exynos_ufcc | 14692 | 52 |
| sec_debug_sched_info.ko | dss, sec_debug_stacktrace | 1804 | 25 |

¹ Exynos UFCC aparece como `exynos-ufcc` em modinfo e com sublinhado em LSMOD.
Cada linha de modules.dep na imagem vendor contém apenas o próprio caminho,
sem alvos após os dois-pontos. Os quatro provedores estão no conjunto do ramdisk.

² Comparação integral da seção antes das relocações. Os dois .ko recompilados
estão no [pacote alinhado](capture-a0-aligned-full-hzc2.md), nos diretórios
`drivers/input/input_boost/` e `drivers/samsung/debug/`, respectivamente.
Em cada par, a seção __versions também é idêntica byte a byte.
Os 52 e 25 pares símbolo/CRC dos módulos XEO coincidem com o Module.symvers
alinhado, inclusive module_layout. São 70 símbolos distintos no total.
O vermagic do original começa em 5.4.242-30958140-abG998BXXSJHZC2 e o do
recompilado em 5.4.242. Os arquivos completos diferem.

**Decisão para A0.** Preservar os 274 arquivos em vendor_boot B e considerar
os dois arquivos da partição vendor ao avaliar o sistema completo. A carga
dos 276 nomes é uma referência observada no Samsung original. Para o
candidato, falta uma captura que identifique o kernel em execução e a
presença dos módulos. A cobertura de CRC não mede a operação dos drivers.

## Reprodução somente leitura

1. Obter G998BXXSJHZC2_vendor.zip na
   [release UN1CA G998BXXSJHZC2_XEO_OXM](https://github.com/UN1CA/proprietary_vendor_samsung_exynos2100/releases/tag/G998BXXSJHZC2_XEO_OXM),
   asset 381259288. Conferir o SHA-256 do ZIP e do membro vendor.img abaixo.
2. Ler o ext4 com um leitor somente leitura (usado dissect.extfs 3.15).
   A raiz da imagem corresponde a /vendor. Ler lib/modules, etc/init,
   etc/init.insmod.exynos2100.cfg, bin/init.insmod.sh e build.prop.
3. Ler os dois .ko de lib/modules e os homônimos do pacote alinhado.
   Usar `elf_sections` e `module` de scripts/capture_a0_modules.py.
   Comparar os bytes de .text e __versions e pesquisar cada par (nome,
   CRC) no Module.symvers do build. Normalizar hífen para sublinhado
   somente na comparação dos nomes dos módulos.
4. Usar o [ZIP e membro principal fixados](bugreport-boot-hzc2.md) para
   verificar os números de linha indicados (linhas LF, a partir de 1).

| Artefato | SHA-256 |
|---|---|
| ZIP XEO | 7c6b28ff527015e4a5faf6713c46e60f7c3017fd933f1a930b071fd7ad36af29 |
| vendor.img XEO (1742929920 bytes) | 2003e33009bb9932960cdfe7ba17e673fcde7d48c9f54643c434da317a8d2465 |
| init.exynos2100.rc XEO | cc4bc593e66f614e1ad2077bf664205ec4f3da005bafa703996cbeaefc0b8fc9 |
| input_booster_lkm.ko XEO | fa4cbc359180c5d934719dbfaf1f867851ba49cbd49448157eca6aba985c35c3 |
| sec_debug_sched_info.ko XEO | bffb878eca04bf0beca0781c1a8c1c6e191dbdb33c2f345ac219e7e862683d73 |
| input_booster_lkm.ko alinhado | b3e84afd464c9d63f21f607ba946d1e6e46e8e150153979f76b624eabab94964 |
| sec_debug_sched_info.ko alinhado | c86891f40a1c3f3b3a57d5fd648db64b6f2f72dc268a5627df2722e2ef5f9b18 |
