# Makefile — kit R8: MMU / exception levels / exceções + GICv3 + timer
# Ambiente userspace (sem root): cross-gcc e QEMU extraídos em tools/root

TOOLS ?= ../tools/root
LOCAL_CROSS := $(TOOLS)/usr/bin/aarch64-linux-gnu-
LOCAL_QEMU := $(TOOLS)/usr/bin/qemu-system-aarch64
export PATH := $(TOOLS)/usr/bin:$(PATH)
ifeq ($(wildcard $(LOCAL_CROSS)gcc),)
CROSS ?= aarch64-linux-gnu-
else
CROSS ?= $(LOCAL_CROSS)
endif
CC      := $(CROSS)gcc
OBJDUMP := $(CROSS)objdump

ifeq ($(wildcard $(LOCAL_QEMU)),)
QEMU ?= qemu-system-aarch64
QENV :=
else
QEMU ?= $(LOCAL_QEMU)
QENV := LD_LIBRARY_PATH=$(TOOLS)/usr/lib/x86_64-linux-gnu:$(TOOLS)/usr/lib
endif
ifeq ($(wildcard $(TOOLS)/usr/share/qemu),)
QDATA ?= /usr/share/qemu
else
QDATA ?= $(TOOLS)/usr/share/qemu
endif


CFLAGS  := -ffreestanding -nostdlib -fno-builtin -fno-stack-protector \
	   -fno-pie -mgeneral-regs-only -march=armv8-a -O2 -std=gnu11 \
	   -Wall -Wextra -Icommon

ASFLAGS := -ffreestanding -nostdlib -march=armv8-a -O2 -Icommon

LDFLAGS := -nostdlib -static -T common/linker.ld -Wl,--build-id=none

BUILD   := build
COMMON  := $(BUILD)/uart.o $(BUILD)/printf.o $(BUILD)/util.o \
	   $(BUILD)/exc.o $(BUILD)/sys.o $(BUILD)/vectors.o

ELF_A   := $(BUILD)/r8a_mmu.elf
ELF_B   := $(BUILD)/r8b_el.elf
ELF_C   := $(BUILD)/r8c_gic.elf
ELF_D   := $(BUILD)/r9_micro.elf
ELF_E   := $(BUILD)/r10_payload.elf

all: $(ELF_A) $(ELF_B) $(ELF_C) $(ELF_D) $(ELF_E) dis

dis: $(ELF_A).dis $(ELF_B).dis $(ELF_C).dis $(ELF_D).dis $(ELF_E).dis

$(BUILD):
	mkdir -p $(BUILD)

# ---- common ----
$(BUILD)/%.o: common/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%.o: common/%.S | $(BUILD)
	$(CC) $(ASFLAGS) -c $< -o $@

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

# ---- r10: Exynos 2100 real hardware payload ----
R10_OBJS := $(BUILD)/r10_main.o $(BUILD)/r10_mmu.o $(BUILD)/r10_gic.o \
            $(BUILD)/r10_uart.o $(BUILD)/r10_mct.o $(BUILD)/r10_timer.o \
            $(BUILD)/r10_psci.o $(BUILD)/r10_spinlock.o $(BUILD)/r10_smp.o \
            $(BUILD)/printf.o $(BUILD)/exc.o $(BUILD)/sys.o $(BUILD)/vectors.o $(BUILD)/util.o

$(BUILD)/r10_start.o: r10_payload/start_r10.S | $(BUILD)
	$(CC) $(ASFLAGS) -c $< -o $@

$(BUILD)/r10_%.o: r10_payload/%.c r10_payload/r10.h common/r8lib.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

# R10 needs different linker script (load at 0x80080000, no EL0)
$(ELF_E): $(BUILD)/r10_start.o $(R10_OBJS) common/linker_r10.ld
	$(CC) $(CFLAGS) -nostdlib -static -T common/linker_r10.ld -Wl,--build-id=none \
	    -o $@ $(BUILD)/r10_start.o $(R10_OBJS)

# ---- execução ----
run_r10: $(ELF_E)
	@echo "R10 ELF built at $<. QEMU virt does not emulate Exynos MMIO; this is not hardware validation."

run_r10_hw: $(ELF_E)
	@echo "UNVALIDATED: do not flash/chainload this experimental ELF on the phone."
	@echo "A verified Samsung-compatible boot path and physical debug console are prerequisites."

# ---- regressão: os 4 módulos + assinaturas PASS ----
regress: $(ELF_A) $(ELF_B) $(ELF_C) $(ELF_D)
	@../scripts/regress.sh