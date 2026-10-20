# Referência TWRP para Exynos 2100

Repositório indicado pelo usuário em 2026-10-20: [xfwdrev/android_device_samsung_exynos2100](https://github.com/xfwdrev/android_device_samsung_exynos2100). Consultado o branch `android-12.1`, commit **0d8b294de8ec86963576ea4710f64207824134c4**. Não foram incorporados kernel, módulos ou binários desse repositório ao projeto.

## Conteúdo útil

O [README](https://github.com/xfwdrev/android_device_samsung_exynos2100/blob/0d8b294de8ec86963576ea4710f64207824134c4/README.md) identifica uma árvore de build TWRP, com suporte ao `p3s` (SM-G998B/SM-G998N) e kernel de recovery. Essa expressão Android “device tree” inclui configuração de build e empacotamento; o repositório também contém DTB e DTBO compilados em `p3s/prebuilt/`.

O [BoardConfig comum](https://github.com/xfwdrev/android_device_samsung_exynos2100/blob/0d8b294de8ec86963576ea4710f64207824134c4/BoardConfig.mk) usa kernel e DTB pré-compilados, header de imagem v2, os_version 14.0.0, ramdisk_offset 0x04000000 e dtb_offset 0x100000000. O [arquivo p3s](https://github.com/xfwdrev/android_device_samsung_exynos2100/blob/0d8b294de8ec86963576ea4710f64207824134c4/p3s/BoardConfig.mk) define boot/vendor_boot/recovery de 64 MiB e dtbo de 8 MiB. `mkbootimg.mk` anexa `SEANDROIDENFORCE`.

Esses parâmetros descrevem o empacotamento daquele recovery. Não comprovam seu uso no firmware HZC2, nem PC/EL, RAM livre ou endereço efetivo do FDT. As imagens stock recebidas têm headers boot/vendor_boot v3. Não copiar automaticamente o header v2 e os offsets do TWRP para um payload bare-metal.

## DTB inspecionado

Foi baixado somente `p3s/prebuilt/dtb`: **391.332 bytes**, SHA-256 `1cfc38ff41669f09374388d2ed192c991ab672f8e7de109ab780e14c8951d26d`. Há uma tabela Android de 64 bytes antes de um FDT v17 de 391.268 bytes. A tabela não é um FDT: deve ser separada antes do parser.

| Recurso | DTB TWRP | DTB stock HZC2 |
|---|---|---|
| MPIDRs | 0x000..0x700, passo 0x100 | iguais |
| GICD | 0x10200000 / 0x10000 | igual |
| GICR | 0x10240000 / 0x200000 | igual |
| Timer físico NS | INTID 30 | igual |
| Nós memory | ausentes | ausentes, inclusive após cada overlay |
| Reservas interpretadas pelo parser | 29; descrição incompleta | 29 no base; 31 com cada overlay; descrição incompleta |

O parser C de produção aceitou o FDT separado e a política de boot retornou **R10_FDT_NO_RAM (-4)**. A comparação confirma recursos estáticos, mas não resolve o mapa final de memória. Não foi estabelecida correspondência desse binário de recovery com o build HZC2; as imagens originais enviadas continuam sendo a evidência mais próxima do firmware em uso.

Para DTS/DTSI e implementação de drivers, o próprio README aponta para [android_kernel_samsung_ex2100](https://github.com/xfwdrev/android_kernel_samsung_ex2100). Nesta revisão, os drivers usados para conferência continuam sendo os do pacote Samsung já recebido, com hashes em [samsung-reference.md](samsung-reference.md).
