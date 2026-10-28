# Carregamento Samsung e instalador Proton: evidências e contrato pendente

Análise estática em 2026-10-20. Código Proton fixado no commit **a0d73239d600d9ec89e7ac4775d2139d4d61290e** (tag v6.1.0); AnyKernel3 r9s fixado no commit **59517ec263b45308349221d2a041689c63557ac0**, consultado nesta análise. A revisão do AnyKernel embutida no ZIP publicado ainda não foi determinada.

## 1. Caminho de build encontrado

[do_build.sh](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/do_build.sh) chama [build/ckbuild.sh](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/build/ckbuild.sh). O script:

1. Usa proton_defconfig e produz a Image AArch64 e módulos.
2. Compila o DTS conforme a variante escolhida (normal, balanced, battery ou OC).
3. Encapsula o DTB em uma tabela Android com mkdtboimg: versão 0, páginas 2048 e campos custom0/custom1.
4. Gera boot.img v3 com Image e ramdisk pré-compilado.
5. Gera vendor_boot.img v3 com a tabela DTB e um vendor ramdisk contendo os módulos e arquivos de build/vboot.
6. Para ZIP, obtém AnyKernel3 no branch r9s e copia **Image + vendor_boot.img** para ele. Para TAR, empacota boot.img.lz4 + vendor_boot.img.lz4.

A referência AnyKernel é um branch, não um SHA fixado no script. Além disso, uma pasta local existente pode ser reutilizada. Portanto, consultar esse branch hoje não demonstra quais scripts foram incluídos no ZIP de janeiro. A publicação lista o arquivo enviado com tamanho **34.652.394 bytes** e digest de release **sha256:3b86a4f0ca1fcf8ac06372a2af27bb0b0b9ca413e3da3b0c055629b087e9c982**. Esse digest é metadado da API GitHub, não comparação já efetuada com o upload.

A [release v6.1.0](https://github.com/ProtonKernel/Proton/releases/tag/v6.1.0) é a origem desse nome/digest. Na etapa inicial só havia consulta textual. Agora o ZIP publicado foi baixado, seu digest conferido e Image/vendor_boot/anykernel.sh inspecionados; veja [proton-binary.md](proton-binary.md). O SHA Git do AnyKernel incluído e a equivalência com uma compilação reproduzida continuam pendentes.

## 2. O que o instalador faz

No [anykernel.sh](https://github.com/ProtonKernel/AnyKernel3/blob/59517ec263b45308349221d2a041689c63557ac0/anykernel.sh) consultado:

- A checagem de dispositivo aceita r9s, o1s, p3s e t2s; o alvo inicial é /dev/block/by-name/boot, sem slots.
- Há tratamento de versão Android para uma alteração da string uname_bpf_spoof na Image.
- O fluxo chama split_boot, flash_boot e depois flash_generic vendor_boot.
- [ak3-core.sh](https://github.com/ProtonKernel/AnyKernel3/blob/59517ec263b45308349221d2a041689c63557ac0/tools/ak3-core.sh) lê o boot atual, separa seus componentes com magiskboot, seleciona a Image fornecida e recompõe/grava boot. O caminho genérico procura e grava o vendor_boot.img fornecido.

Consequência: este caminho ZIP não se limita a “trocar o kernel preservando todo o resto”; inclui uma imagem vendor_boot própria, com DTB e módulos. O bootloader Samsung continua sendo o responsável pelo carregamento no próximo boot. Não foi encontrada substituição de sboot/Harx nesse fluxo. Não houve execução dos scripts ou escrita de partições.

## 3. Cabeçalhos não estabelecem o PC final

O [mkbootimg.py](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/build/mkbootimg/mkbootimg.py) incluído escreve os endereços de vendor_boot como base + offsets. Na chamada principal de ckbuild.sh não há substituição desses parâmetros: os defaults do arquivo consultado são base=0x10000000, kernel_offset=0x8000, ramdisk_offset=0x1000000 e dtb_offset=0x1f00000. Isso geraria campos kernel_addr=0x10008000, ramdisk_addr=0x11000000 e dtb_addr=0x11f00000, se esse caminho for executado sem outras alterações. Vendor pagesize default é 2048.

Já a imagem stock HZC2 examinada anteriormente contém campos 0x80008000, 0x84000000 e 0x81f00000, com vendor pagesize 4096. O script alternativo ckbuild_actions.sh tem outros parâmetros explícitos e não é o chamado por do_build.sh. Esses caminhos não devem ser misturados como se demonstrassem a mesma imagem.

Essas diferenças são um limite de rastreabilidade entre fonte, scripts e artefato publicado. Não provam que o bootloader ignore os campos, nem autorizam escolher um endereço para o R10. Os headers efetivos do ZIP agora foram conferidos e correspondem aos defaults desse caminho; ainda falta observar o comportamento do carregador.

Há três camadas distintas: offsets dentro do contêiner Android, campos de carga no header vendor e endereço onde a CPU realmente executa a Image. O text_offset do header AArch64 também não é um endereço físico absoluto.

## 4. Contrato Linux versus contrato R10

[Documentation/arm64/booting.rst](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/Documentation/arm64/booting.rst) descreve o protocolo esperado por Linux. [head.S](https://github.com/ProtonKernel/Proton/blob/a0d73239d600d9ec89e7ac4775d2139d4d61290e/arch/arm64/kernel/head.S) contém o header AArch64, preserva x0..x3 e trata o nível de exceção na entrada. Isso é evidência do consumidor e seus requisitos, não observação do firmware Samsung.

| Item | Protocolo Linux/código consultado | Estado do R10 ou da evidência |
|---|---|---|
| Formato de entrada | Image com header ARM64, text_offset, image_size e flags | R10 atual é ELF; não há imagem Android/ARM64 de hardware validada |
| Posição | Image em RAM utilizável, text_offset após base alinhada a 2 MiB; reservar image_size | 0x80080000 é hipótese de link, não autorização de RAM |
| Argumentos | x0 aponta ao FDT físico; x1..x3 reservados | R10 preserva x0, mas o ponteiro real no Samsung não foi capturado |
| EL | Linux aceita EL2 ou EL1 não seguro | R10 exige EL2; funcionamento do Proton não prova esse requisito |
| Tradução/coerência | MMU desligada e imagem limpa até PoC; I-cache pode estar ligada | R10 verifica seus requisitos iniciais; manutenção efetiva pelo carregador não foi demonstrada |
| RAM e reservas | Memória descrita e reservas respeitadas | Os DTBs estáticos examinados não fornecem bancos RAM |
| Timer/ICC | Condições de acesso dependem do EL e firmware | QEMU validado; permissões no Exynos permanecem pendentes |

Renomear o ELF como Image ou apenas executar objcopy não fornece um header ARM64 correto, reserva image_size nem demonstra compatibilidade com a cadeia Samsung. O ELF usa p_memsz para BSS/pilhas; uma futura Image bruta precisará declarar sua própria extensão completa corretamente.

## 5. Estado da evidência sboot/ABL/Harx

**Atualização 2026-10-21:** BL HZC2 recebido e inspecionado fora do Git; inventário e instruções candidatas ao handoff em [bootloader-hzc2.md](bootloader-hzc2.md). O relato abaixo descreve a indisponibilidade anterior.

A árvore versionada S21-baremetal foi enumerada sem truncamento e não contém sboot.bin, harx.bin ou abl.img para nova análise binária. As notas antigas mencionam strings TF-A, configure_dtb e Harx, mas não fornecem aqui xrefs/instruções suficientes para comprovar a rotina de handoff, a configuração de caches ou o EL final.

Nomes e strings são pistas. “configure_dtb” não comprova sozinho quais nós de RAM são adicionados; “Harx” não demonstra o estado de HCR/SCTLR; suporte a PSCI/HVC em algum componente não autoriza sondar HVC quando o DTB declara SMC. Não se pressupõe U-Boot, ABL Qualcomm ou um comando fastboot boot disponível no Samsung.

O guia antigo [ABL_EXTRACTION.md](../scripts/kit-assets/ABL_EXTRACTION.md) foi corrigido: usava G981 como S21, tratava AP como contendo todos os bootloaders e afirmava que nada bloqueava flash. O alvo desta investigação é G998B/p3s. O inventário do pacote BL é o ponto de partida para os componentes de firmware de boot; AP fornece boot/vendor_boot/dtbo. A presença exata dos membros deve ser verificada, não presumida.

## 6. Próxima entrega técnica definida

Antes de qualquer teste no telefone:

1. Digest e headers do ZIP público já conferidos em proton-binary.md. Ainda falta atribuir o SHA Git do AnyKernel incluído e reproduzir a compilação.
2. Retomar os binários BL disponíveis com hashes e limites de seções. Localizar xrefs para validação da Image, seleção/ajuste de DTB e salto final; documentar argumentos, endereço e mudança de EL somente quando sustentados por instruções.
3. Preparar e testar no QEMU uma Image de diagnóstico separada, com header ARM64 e extensão total: entrada sem clear amplo de BSS, preservação de x0..x3 e identificação de EL antes de acessar registradores específicos de EL2. Testar caminhos EL1/EL2 e carga relocada.
4. Fechar a reserva prévia da imagem/buffer/pilhas e uma forma de obter o resultado (UART validada ou outro canal demonstrado). Guardar dados em RAM sem forma de lê-los não é evidência observável.
5. Só então decidir se a entrada R10 deve aceitar EL1 e como aplicar o FDT final/reservas. Não inventar bancos de RAM nem relaxar a política para fazer um DTB estático passar.

Nenhum desses testes de Image nova ou binário BL foi executado nesta revisão. Não foram alterados payload, instalador, bootloader ou partições. Esta entrega é análise estática e correção de documentação; os resultados anteriores de regressão continuam descritos em [validation-2026-10-20.md](validation-2026-10-20.md).

## Contêiner e quarentena do shim

O formato S21R10 v1 agora tem produtor e validador offline, em [payload-format.md](payload-format.md). Isso não implementa ainda a próxima Image de diagnóstico descrita acima. O loader legado passava boot_args incompatível com o R10 e foi desativado; a entrada padrão do shim estaciona antes de MMIO. Nenhuma conclusão desta página autoriza fastboot/Odin com esses artefatos.

## Marco posterior: carregador sintético em EL2

O contêiner agora foi carregado no QEMU até a main R10 real em EL1, com conferência da imagem antes do salto e timer depois dele: [qemu-el2-loader.md](qemu-el2-loader.md). O firmware de teste é um ELF que o QEMU carrega diretamente; não é ainda a Image ARM64/Android de diagnóstico para o Samsung descrita na seção 6. O contrato do telefone continua pendente.

## Evidência posterior: entrada LK

A primeira chamada de LK no sboot HZC2 configura/preserva EL1, conforme [sboot-layout-hzc2.md](sboot-layout-hzc2.md). Isso impede usar “Samsung entrega em EL2” como premissa do R10. A Image de diagnóstico descrita nesta página deve tratar EL1/EL2 antes de registradores específicos, e a compatibilidade com o salto final ainda precisa de observação.

## Continuação de 27/10 — método PSCI após a base

O [editor posterior do LK](lk-psci-final-edit-hzc2.md) pode trocar
/psci/method de smc para hvc sob o flag Harx. O bugreport contém a mensagem
do ramo após setprop não negativo. Vinte e quatro casos QEMU conferem
essa rotina; não são captura do FDT final ou execução de serviço PSCI.
A main de uma CPU permanece sem sondagens SMC/HVC.
