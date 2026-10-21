# Makefile — kit R8: MMU / exception levels / exceções + GICv3 + timer
# Ambiente userspace (sem root): cross-gcc e QEMU extraídos em tools/root

TOOLS ?= ../tools/root
TOOLS := $(abspath $(TOOLS))
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
ifneq ($(wildcard $(LOCAL_CROSS)gcc),)
CC := bash ../scripts/cross-run.sh $(TOOLS) $(CC)
OBJDUMP := bash ../scripts/cross-run.sh $(TOOLS) $(OBJDUMP)
endif

ifeq ($(wildcard $(LOCAL_QEMU)),)
QEMU ?= qemu-system-aarch64
QENV :=
else
QEMU ?= $(LOCAL_QEMU)
QENV := $(TOOLS)/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 --library-path $(TOOLS)/usr/lib/x86_64-linux-gnu:$(TOOLS)/usr/lib
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
R10_OBJS := $(BUILD)/r10_main.o $(BUILD)/r10_fdt.o $(BUILD)/r10_mmu.o $(BUILD)/r10_gic.o \
            $(BUILD)/r10_uart.o $(BUILD)/r10_mct.o $(BUILD)/r10_timer.o \
            $(BUILD)/r10_psci.o $(BUILD)/r10_spinlock.o $(BUILD)/r10_smp.o \
            $(BUILD)/printf.o $(BUILD)/r10_exceptions.o $(BUILD)/sys.o $(BUILD)/vectors.o $(BUILD)/util.o

$(BUILD)/r10_start.o: r10_payload/start_r10.S | $(BUILD)
	$(CC) $(ASFLAGS) -c $< -o $@

# FDT property data is only 4-byte aligned. With MMU off, never emit
# unaligned multi-byte loads (including compiler byte-load fusion).
$(BUILD)/r10_fdt.o: CFLAGS += -mstrict-align

$(BUILD)/r10_%.o: r10_payload/%.c r10_payload/r10.h r10_payload/fdt.h r10_payload/gic_regs.h r10_payload/percpu.h common/r8lib.h | $(BUILD)
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
	@bash ../scripts/regress.sh
# PR #3: execute the real atomic implementation on QEMU AArch64.
$(BUILD)/atomic_smoke.o: tests/atomic_smoke.c r10_payload/spinlock.c r10_payload/r10.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD)/atomic_smoke.elf: $(BUILD)/start.o $(BUILD)/atomic_smoke.o $(COMMON) common/linker.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(BUILD)/start.o $(BUILD)/atomic_smoke.o $(COMMON)
run_atomic: $(BUILD)/atomic_smoke.elf
	$(QENV) $(QEMU) -L $(QDATA) -M virt,virtualization=on -cpu max -nographic -kernel $<
.PHONY: run_atomic

# QEMU integration of production R10 entry/GIC/timer/exceptions, synthetic loader.
$(BUILD)/r10-test.dtb: ../scripts/test_fdt.py | $(BUILD)
	python3 $< --write-qemu $@
$(BUILD)/r10_test_boot.o: tests/r10_boot.S $(BUILD)/r10-test.dtb | $(BUILD)
	$(CC) $(ASFLAGS) -DR10_TEST_DTB='"$(abspath $(BUILD)/r10-test.dtb)"' -c $< -o $@
$(BUILD)/r10_test_stage.o: tests/r10_stage.c r10_payload/r10.h r10_payload/fdt.h r10_payload/gic_regs.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@
R10_TEST_OBJS = $(BUILD)/r10_test_boot.o $(BUILD)/r10_start.o $(BUILD)/r10_test_stage.o \
    $(BUILD)/r10_gic.o $(BUILD)/r10_timer.o $(BUILD)/r10_exceptions.o $(BUILD)/r10_fdt.o \
    $(BUILD)/uart.o $(BUILD)/printf.o $(BUILD)/util.o $(BUILD)/sys.o $(BUILD)/vectors.o
$(BUILD)/r10_stage_test.elf: $(R10_TEST_OBJS) common/linker_r10.ld
	$(CC) $(CFLAGS) -nostdlib -static -Wl,--defsym,R10_LOAD_ADDR=0x40080000 \
	    -T common/linker_r10.ld -Wl,-e,r10_test_boot -Wl,--build-id=none -o $@ $(R10_TEST_OBJS)
run_r10_stage_test: $(BUILD)/r10_stage_test.elf
	$(QENV) $(QEMU) -L $(QDATA) -M virt,gic-version=3,virtualization=on -cpu max -nographic -kernel $<
.PHONY: run_r10_stage_test

# Real production R10 main with only the UART device backend replaced for QEMU.
$(BUILD)/r10_qemu_uart.o: tests/r10_qemu_uart.c r10_payload/r10.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@
R10_QEMU_OBJS = $(BUILD)/r10_start.o $(BUILD)/r10_main.o $(BUILD)/r10_fdt.o \
    $(BUILD)/r10_gic.o $(BUILD)/r10_timer.o $(BUILD)/r10_exceptions.o \
    $(BUILD)/r10_qemu_uart.o $(BUILD)/uart.o $(BUILD)/printf.o $(BUILD)/util.o \
    $(BUILD)/sys.o $(BUILD)/vectors.o
$(BUILD)/r10_qemu_payload.elf: $(R10_QEMU_OBJS) common/linker_r10.ld
	$(CC) $(CFLAGS) -nostdlib -static -Wl,--defsym,R10_LOAD_ADDR=0x40080000 \
	    -T common/linker_r10.ld -Wl,--build-id=none -o $@ $(R10_QEMU_OBJS)
$(BUILD)/r10_qemu.payload: $(BUILD)/r10_qemu_payload.elf $(BUILD)/r10-test.dtb ../tools/mkpayload.py
	@set -eu; tmp=$$(mktemp -d "$(BUILD)/.r10-payload.XXXXXX"); \
	    trap 'rm -rf "$$tmp"' EXIT; \
	    python3 ../tools/mkpayload.py "$<" --dtb "$(BUILD)/r10-test.dtb" -o "$$tmp/payload"; \
	    mv "$$tmp/payload" "$@"
$(BUILD)/loader_start.o: tests/payload_loader.S $(BUILD)/r10_qemu.payload $(BUILD)/r10-test.dtb | $(BUILD)
	$(CC) $(ASFLAGS) -DR10_LOADER_DTB='"$(abspath $(BUILD)/r10-test.dtb)"' \
	    -DR10_LOADER_PAYLOAD='"$(abspath $(BUILD)/r10_qemu.payload)"' -c $< -o $@
$(BUILD)/loader_main.o: tests/payload_loader.c ../shim/payload_stage.h ../shim/payload.h r10_payload/fdt.h common/r8lib.h | $(BUILD)
	$(CC) $(CFLAGS) -mstrict-align -c $< -o $@
$(BUILD)/loader_%.o: ../shim/%.c ../shim/payload.h ../shim/payload_stage.h r10_payload/fdt.h | $(BUILD)
	$(CC) $(CFLAGS) -mstrict-align -c $< -o $@
LOADER_OBJS = $(BUILD)/loader_start.o $(BUILD)/loader_main.o $(BUILD)/loader_payload.o \
    $(BUILD)/loader_payload_stage.o $(BUILD)/loader_memory.o $(BUILD)/r10_fdt.o $(BUILD)/uart.o
$(BUILD)/r10_loader_test.elf: $(LOADER_OBJS) tests/payload_loader.ld
	$(CC) $(CFLAGS) -nostdlib -static -T tests/payload_loader.ld -Wl,--build-id=none -o $@ $(LOADER_OBJS)
LOADER_VIRTUALIZATION ?= on
run_r10_loader_test: $(BUILD)/r10_loader_test.elf
	$(QENV) $(QEMU) -L $(QDATA) -M virt,gic-version=3,virtualization=$(LOADER_VIRTUALIZATION) -cpu max -smp 1 \
	    -display none -monitor none -serial file:$(SERIAL_LOG) -S -gdb stdio -kernel $<
.PHONY: run_r10_loader_test
