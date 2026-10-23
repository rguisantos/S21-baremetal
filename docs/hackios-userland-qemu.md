# Userland iOS no QEMU: ensaio de referência em preparação

O runner `scripts/run_hackios_userland.py` usa o ABI upstream de duas
imagens APFS: sistema residente em `0xfc000000` e boot pequeno no payload.
Ele é separado do consumidor EFI restrito do S21-baremetal, que ainda
precisa de uma extensão verificada para o disco residente.

Entradas fixadas: kernel `8e61187098f2c26c5daee8f9f72b6416aa64b9ab`,
userland `906425b75e02b4f99eb5d7bb1ef7c9583472d772`, prebuilts identificados,
loader de referência recompilado com a correção ramfb na fonte e patches
já auditados de preparação. As imagens Apple são geradas localmente e
ficam fora do Git.

A observação usa QMP stdio, capturas PNG nativas a cada 15 segundos,
`status.json` e comandos em `control.json`. Um código de saída 0 significa
que o runner terminou; não confirma interface. O campo
`UI_visually_verified` permanece falso no relatório automático.

Este checkpoint de código não registra SpringBoard visível. Uma tentativa
anterior chegou ao logo Apple e registrou processos de launchd/backboardd/
SpringBoard, mas o ambiente foi restaurado antes da conclusão e os arquivos
da execução não foram preservados. As imagens preparadas serão conservadas
antes da próxima execução longa.
