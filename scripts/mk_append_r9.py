#!/usr/bin/env python3
"""mk_append_r9.py — adiciona o alvo R9 + regress ao r8/Makefile.

Por que um script: o Edit normaliza TABs em espaços e Makefile exige
TAB nas receitas. Aqui escrevemos TABs literais (\\t).
Idempotente: se 'run_r9' já existe, não faz nada.
"""

MK = "/home/z/my-project/r8/Makefile"

with open(MK, "r", encoding="utf-8") as fh:
    mk = fh.read()

if "run_r9" in mk:
    print("Makefile já tem R9 — nada a fazer")
    raise SystemExit(0)

# 1) ELF_D junto dos outros ELF_*
mk = mk.replace(
    "ELF_C   := $(BUILD)/r8c_gic.elf\n",
    "ELF_C   := $(BUILD)/r8c_gic.elf\n"
    "ELF_D   := $(BUILD)/r9_micro.elf\n",
)

# 2) all: inclui ELF_D
mk = mk.replace(
    "all: $(ELF_A) $(ELF_B) $(ELF_C) dis",
    "all: $(ELF_A) $(ELF_B) $(ELF_C) $(ELF_D) dis",
)

# 3) regras do R9 + link + run + regress (TABS literais nas receitas)
BLOCK = """
# ---- r9: microkernel (EL0 + SVC + troca de contexto + preempção) ----
R9_OBJS := $(BUILD)/r9_main.o $(BUILD)/r9_sched.o $(BUILD)/r9_syscall.o \\
           $(BUILD)/r9_tasks.o $(BUILD)/r9_gic.o $(BUILD)/r9_timer.o \\
           $(BUILD)/r9_vectors.o

$(BUILD)/r9_vectors.o: r9_micro/vectors.S | $(BUILD)
\t$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/r9_%.o: r9_micro/%.c r9_micro/r9.h common/r8lib.h | $(BUILD)
\t$(CC) $(CFLAGS) -c $< -o $@

$(ELF_D): $(BUILD)/start.o $(R9_OBJS) $(BUILD)/uart.o $(BUILD)/printf.o \\
          $(BUILD)/util.o $(BUILD)/sys.o common/linker.ld
\t$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(BUILD)/start.o $(R9_OBJS) \\
\t    $(BUILD)/uart.o $(BUILD)/printf.o $(BUILD)/util.o $(BUILD)/sys.o

# ---- regressão: os 4 módulos + assinaturas PASS ----
regress: $(ELF_A) $(ELF_B) $(ELF_C) $(ELF_D)
\t@../scripts/regress.sh
"""
mk = mk.rstrip() + "\n" + BLOCK

# 4) run_r9 junto dos outros run_*
mk = mk.replace(
    "run_r8c: $(ELF_C)\n"
    "\t$(QENV) $(QEMU) -L $(QDATA) -M virt,gic-version=3,virtualization=on -cpu max -nographic -kernel $<\n",
    "run_r8c: $(ELF_C)\n"
    "\t$(QENV) $(QEMU) -L $(QDATA) -M virt,gic-version=3,virtualization=on -cpu max -nographic -kernel $<\n"
    "\n"
    "run_r9: $(ELF_D)\n"
    "\t$(QENV) $(QEMU) -L $(QDATA) -M virt,gic-version=3,virtualization=on -cpu max -nographic -kernel $<\n",
)

# 5) .PHONY
mk = mk.replace(
    ".PHONY: all dis run_r8a run_r8b run_r8c clean",
    ".PHONY: all dis run_r8a run_r8b run_r8c run_r9 regress clean",
)

with open(MK, "w", encoding="utf-8") as fh:
    fh.write(mk)

# sanidade: receitas começam com TAB?
bad = [i for i, l in enumerate(mk.splitlines(), 1)
       if l.startswith("    ") and l.strip().startswith(("$(", "echo", "@"))]
print("OK — Makefile atualizado")
