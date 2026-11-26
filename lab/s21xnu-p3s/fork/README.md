# Série para um fork do s21xnu

Seis commits sobre `a128f07` (o `main` do s21xnu em 26/11/2026), gerados
com `git format-patch`:

1. `0001` shim/mkadt: perfis `p3s` e `p3s-window`;
2. `0002` shim: linhas ENTRY/IMAGE/INITRD/FB na tela do loader;
3. `0003` xnu: patches 0146–0148 copiados para `xnu/patches/`;
4. `0004` mkpayload: termina e alinha a lista NVRAM antes do token de comprimento;
5. `0005` xnu: patch 0149 (enumeração do BCM4389 do p3s) copiado para `xnu/patches/`;
6. `0006` xnu: patch 0150 (firmware do BCM4389 pelo caminho ARM CA7) copiado para `xnu/patches/`.

O workflow `xnu.yml` do s21xnu roda em push no `main` quando
`xnu/patches/**` muda (runner `macos-15-intel`) e publica o artefato
`xnu-kernel`. Um fork com esta série compila o XNU com os patches do S21
Ultra, o que este ambiente não consegue fazer.

```bash
# no GitHub: Fork de jimmycarles9991-glitch/s21xnu para a sua conta e
# habilitar Actions na aba Actions do fork
git clone https://github.com/SEU_USUARIO/s21xnu && cd s21xnu
git am /caminho/S21-baremetal/lab/s21xnu-p3s/fork/000*.patch
git push origin main
```

`check_fork_series.py CLONE` confere que a série reproduz exatamente os
mudanças no shim/mkadt, os patches 0146–0150 e a correção 0004 no
empacotador com seu teste. O teste de NVRAM roda na árvore criada por git am.
