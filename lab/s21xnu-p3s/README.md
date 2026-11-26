# Perfil p3s para o s21xnu

Patch sobre [s21xnu](https://github.com/jimmycarles9991-glitch/s21xnu) em
`a128f07b04987e60f5e13e2ce67b19ae009672cd`: `BOARD=t2s|p3s|p3s-window` no
`shim/build-s21.sh` e `--board=` no `tools/mkadt.py`. Análise e limites em
[docs/xnu-s21xnu-p3s.md](../../docs/xnu-s21xnu-p3s.md).

```bash
git clone https://github.com/jimmycarles9991-glitch/s21xnu && git -C s21xnu checkout a128f07
python3 lab/s21xnu-p3s/verify_p3s_profile.py s21xnu --json resultado.json
# aplicar no clone:
git -C s21xnu apply ../lab/s21xnu-p3s/0001-board-p3s-framebuffer.patch   # ou patch -p1
BOARD=p3s-window bash s21xnu/shim/build-s21.sh
python3 s21xnu/tools/mkadt.py adt.bin --highmem --board=p3s-window
```

O verificador usa o cross-compilador de `tools/root` quando presente. Não
compila XNU nem toca no aparelho.
