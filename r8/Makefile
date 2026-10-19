# Makefile — kit R8: MMU / exception levels / exceções + GICv3 + timer
# Ambiente userspace (sem root): cross-gcc e QEMU extraídos em tools/root

CROSS   := aarch64-linux-gnu-
CC      := $(CROSS)gcc
OBJDUMP := $(CROSS)objdump

QEMU    := qemu-system-aarch64
QDATA   := /usr/share/qemu
QENV    :=

CFLAGS  := -ffreestanding -nostdlib -fno-builtin -fno-stack-protector \
	   -fno-pie -mgeneral-regs-only -march=armv8-a -O2 -std=gnu11 \
	   -Wall -Wextra -Icommon

LDFLAGS := -nostdlib -static -T common/linker.ld -Wl,--build-id=none

BUILD   := build
COMMON  := $(BUILD)/uart.o $(BUILD)/printf.o $(BUILD)/util.o \
	   $(BUILD)/exc.o $(BUILD)/sys.o $(BUILD)/vectors.o

ELF_A   := $(BUILD)/r8a_mmu.elf
ELF_B   := $(BUILD)/r8b_el.elf
ELF_C   := $(BUILD)/r8c_gic.elf
ELF_D   := $(BUILD)/r9_micro.elf

all: $(ELF_A) $(ELF_B) $(ELF_C) $(ELF_D) dis

dis: $(ELF_A).dis $(ELF_B).dis $(ELF_C).dis $(ELF_D).dis

$(BUILD):
	mkdir -p $(BUILD)

# ---- common ----
$(BUILD)/%.o: common/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%.o: common/%.S | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

# ---- módulos ----
$(BUILD)/r8a_mmu.o: r8a_mmu/mmu.c common/r8lib.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/r8b_el.o: r8b_el/el.c common/r8lib.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/r8c_gic.o: r8c_gic/gic.c common/r8lib.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/r8c_timer.o: r8c_gic/timer.c common/r8lib.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/r8c_main.o: r8c_gic/main.c common/r8lib.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

# ---- link (start.o primeiro: _start na frente) ----
$(ELF_A): $(BUILD)/start.o $(BUILD)/r8a_mmu.o $(COMMON) common/linker.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(BUILD)/start.o $(BUILD)/r8a_mmu.o $(COMMON)

$(ELF_B): $(BUILD)/start.o $(BUILD)/r8b_el.o $(COMMON) common/linker.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(BUILD)/start.o $(BUILD)/r8b_el.o $(COMMON)

$(ELF_C): $(BUILD)/start.o $(BUILD)/r8c_main.o $(BUILD)/r8c_gic.o \
	  $(BUILD)/r8c_timer.o $(COMMON) common/linker.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(BUILD)/start.o $(BUILD)/r8c_main.o \
	    $(BUILD)/r8c_gic.o $(BUILD)/r8c_timer.o $(COMMON)

%.dis: %
	$(OBJDUMP) -d $< > $@

# ---- execução ----
run_r8a: $(ELF_A)
	$(QENV) $(QEMU) -L $(QDATA) -M virt,virtualization=on -cpu max -nographic -kernel $<

run_r8b: $(ELF_B)
	$(QENV) $(QEMU) -L $(QDATA) -M virt,secure=on,virtualization=on -cpu max -nographic -kernel $<

run_r8c: $(ELF_C)
	$(QENV) $(QEMU) -L $(QDATA) -M virt,gic-version=3,virtualization=on -cpu max -nographic -kernel $<

run_r9: $(ELF_D)
	$(QENV) $(QEMU) -L $(QDATA) -M virt,gic-version=3,virtualization=on -cpu max -nographic -kernel $<

clean:
	rm -rf $(BUILD)

.PHONY: all dis run_r8a run_r8b run_r8c run_r9 regress clean

# ---- r9: microkernel (EL0 + SVC + troca de contexto + preempção) ----
R9_OBJS := $(BUILD)/r9_main.o $(BUILD)/r9_sched.o $(BUILD)/r9_syscall.o \
           $(BUILD)/r9_tasks.o $(BUILD)/r9_gic.o $(BUILD)/r9_timer.o \
           $(BUILD)/r9_vectors.o

$(BUILD)/r9_vectors.o: r9_micro/vectors.S | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/r9_%.o: r9_micro/%.c r9_micro/r9.h common/r8lib.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(ELF_D): $(BUILD)/start.o $(R9_OBJS) $(BUILD)/uart.o $(BUILD)/printf.o \
          $(BUILD)/util.o $(BUILD)/sys.o common/linker.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(BUILD)/start.o $(R9_OBJS) \
	    $(BUILD)/uart.o $(BUILD)/printf.o $(BUILD)/util.o $(BUILD)/sys.o

# ---- regressão: os 4 módulos + assinaturas PASS ----
regress: $(ELF_A) $(ELF_B) $(ELF_C) $(ELF_D)
	@../scripts/regress.sh
