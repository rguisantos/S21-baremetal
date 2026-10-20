/*
 * S21 Ultra Exynos 2100 boot shim - main entry
 *
 * Samsung BL2 (TF-A) hands off at EL2 with x0 = FDT pointer.
 * We drop to EL1, set up MMU, initialize hardware, then chainload R10 payload.
 */
#include <stdint.h>
#include "console.h"
#include "mmu.h"
#include "loader.h"
#include "psci.h"
#include "gic.h"
#include "timer.h"
#include "uart.h"
#include "asm.h"

/* Exynos 2100 hardware addresses (from firmware DTB) */
#define GICD_BASE		0x10200000UL
#define GICR_BASE		0x10240000UL
#define MCT_BASE		0x10040000UL
#define UART1_BASE		0x10840000UL
#define CHIPID_BASE		0x10000000UL

#define NR_CPUS			8

/* ICC_SGI1R_EL1 value targeting the calling core only. */
static uint64_t sgi_self(unsigned id)
{
	uint64_t m = rsr("mpidr_el1");
	return ((m >> 16) & 0xff) << 32 |	/* Aff2 */
	       ((m >> 8) & 0xff) << 16 |	/* Aff1 */
	       (uint64_t)id << 24 |
	       (1U << (m & 0xf));		/* target list: Aff0 */
}

/* PSCI via SMC (primary) or HVC (fallback) */
static uint64_t psci_call(uint64_t fn, uint64_t a1, uint64_t a2, uint64_t a3)
{
	register uint64_t x0 __asm__("x0") = fn;
	register uint64_t x1 __asm__("x1") = a1;
	register uint64_t x2 __asm__("x2") = a2;
	register uint64_t x3 __asm__("x3") = a3;
	__asm__ volatile("smc #0"
			 : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)
			 :
			 : "memory");
	if (x0 == (uint64_t)(-1)) {
		__asm__ volatile("hvc #0"
				 : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)
				 :
				 : "memory");
	}
	return x0;
}

/* UART debug putc (physical before MMU, virtual after) */
static void uart_putc_phys(char c)
{
	volatile uint32_t *utxh = (volatile uint32_t *)(UART1_BASE + 0x20);
	*utxh = (uint32_t)(unsigned char)c;
}

static void uart_putc_virt(char c)
{
	volatile uint32_t *utxh = (volatile uint32_t *)(UART1_BASE + 0x20);
	*utxh = (uint32_t)(unsigned char)c;
}

void debug_putc(char c)
{
	if (mmu_enabled)
		uart_putc_virt(c);
	else
		uart_putc_phys(c);
}

/* ---- Exceptions ---- */

static void irq_handler(void)
{
	uint64_t iar = rsr("icc_iar1_el1");
	uint32_t id = iar & 0xffffff;

	if (id >= 1020 && id <= 1023)
		return;	/* spurious */

	if (id == 30) {		/* CNTP - architected timer */
		wsr("cntp_tval_el0", rsr("cntfrq_el0") / 100);	/* 10 ms */
	} else if (id >= 224 && id <= 227) {	/* MCT */
		/* MCT handled separately */
	}
	wsr("icc_eoir1_el1", iar);
	isb();
}

extern const char *stage;

void exc_handler(uint64_t slot, uint64_t *regs)
{
	if (slot == 5) {	/* IRQ */
		irq_handler();
		return;
	}
	con_clear(COL_BLUE);
	switch (slot & 3) {
	case 0: con_str("PANIC", "SYNC"); break;
	case 1: con_str("PANIC", "IRQ"); break;
	case 2: con_str("PANIC", "FIQ"); break;
	default: con_str("PANIC", "SERROR"); break;
	}
	con_hex2("SLOT", "n=", slot, "cpu=", rsr("mpidr_el1"));
	con_str("STAGE", stage);
	con_hex("ESR", rsr("esr_el1"));
	con_hex("ELR", rsr("elr_el1"));
	con_hex("FAR", rsr("far_el1"));
	con_hex("SPSR", rsr("spsr_el1"));
	con_hex("X0", regs[0]);
	con_hex("X1", regs[1]);
	con_hex("X30", regs[29]);
	reset(40);
}

/* ---- PSCI ---- */

static uint64_t smc(uint64_t fn, uint64_t a1, uint64_t a2, uint64_t a3)
{
	register uint64_t x0 __asm__("x0") = fn;
	register uint64_t x1 __asm__("x1") = a1;
	register uint64_t x2 __asm__("x2") = a2;
	register uint64_t x3 __asm__("x3") = a3;
	__asm__ volatile("smc #0"
			 : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)
			 :
			 : "memory");
	return x0;
}

static uint64_t hvc(uint64_t fn, uint64_t a1, uint64_t a2, uint64_t a3)
{
	register uint64_t x0 __asm__("x0") = fn;
	register uint64_t x1 __asm__("x1") = a1;
	register uint64_t x2 __asm__("x2") = a2;
	register uint64_t x3 __asm__("x3") = a3;
	__asm__ volatile("hvc #0"
			 : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)
			 : : "memory");
	return x0;
}

uint64_t psci_cpu_on(uint64_t mpidr, uint64_t entry, uint64_t ctx)
{
	return psci_call(PSCI_CPU_ON, mpidr, entry, ctx);
}

uint64_t psci_cpu_off(void)
{
	return psci_call(PSCI_CPU_OFF, 0, 0, 0);
}

uint64_t psci_system_reset(void)
{
	return psci_call(PSCI_SYSTEM_RESET, 0, 0, 0);
}

uint64_t psci_version(void)
{
	return psci_call(PSCI_VERSION, 0, 0, 0);
}

/* ---- Secondary CPU ---- */

extern char secondary_entry[];

static volatile uint64_t sec_mpidr[8];

void secondary_main(uint64_t idx)
{
	/* Report our MPIDR */
	sec_mpidr[idx] = rsr("mpidr_el1") | (1ULL << 63);
	
	/* Initialize CPU interface */
	gic_cpu_interface_init();
	
	/* Signal ready and wait for work */
	__asm__ volatile("dsb sy; sev" ::: "memory");
	
	/* Power off - BL2 will restart us if needed */
	psci_cpu_off();
}

/* ---- SMP ---- */

static void test_smp(void)
{
	con_str("SMP", "bringing up secondaries");
	
	uint64_t mpidr_table[8] = {
		0x00, 0x01, 0x02, 0x03,  /* A55 cluster */
		0x04, 0x05, 0x06,        /* A78 cluster */
		0x07                     /* X1 */
	};
	
	uint64_t self = rsr("mpidr_el1") & 0xffffff;
	
	for (int i = 1; i < 8; i++) {
		if (mpidr_table[i] == self) {
			con_str("CPU", "is boot cpu");
			continue;
		}
		
		uint64_t ret = psci_cpu_on(mpidr_table[i], (uintptr_t)secondary_entry, i);
		con_hex2("CPU", "i=", i, "ret=", ret);
	}
	
	/* Wait a bit for secondaries to start */
	for (volatile int i = 0; i < 1000000; i++);
	
	for (int i = 1; i < 8; i++) {
		char label[] = "CPU0";
		label[3] = '0' + i;
		con_hex2(label, "mpidr=", (uint32_t)sec_mpidr[i], "", 0);
	}
}

/* ---- GICv3 ---- */

static void gicd_wait_rwp(void)
{
	for (int i = 0; i < 1000000 && (rd32(GICD_BASE) & (1U << 31)); i++)
		;
}

void gic_cpu_interface_init(void)
{
	/* Enable system register access */
	uint64_t sre = rsr("icc_sre_el1");
	if (!(sre & 1)) {
		wsr("icc_sre_el1", sre | 1);
		isb();
	}
	
	/* CPU interface control: EOI mode + Common Binary Point */
	uint64_t ctlr = rsr("icc_ctlr_el1");
	wsr("icc_ctlr_el1", ctlr | 1);	/* EOImode = 1 */
	
	/* Priority mask: allow all */
	wsr("icc_pmr_el1", 0xff);
	
	/* Binary point */
	wsr("icc_bpr1_el1", 3);
	
	/* Enable Group 1 NS + Group 0 */
	wsr("icc_igrpen1_el1", 1);
	wsr("icc_igrpen0_el1", 1);
	isb();
}

void gic_init(void)
{
	con_str("GIC", "initializing distributor");
	
	/* Disable distributor */
	wr32(GICD_BASE + 0x0000, 0);
	
	/* Enable ARE_NS, DS, Group 0, Group 1 NS */
	wr32(GICD_BASE + 0x0000, (1<<4) | (1<<6) | (1<<0) | (1<<1));
	gicd_wait_rwp();
	
	/* All SPIs -> Group 1 NS, level-triggered */
	for (int i = 32; i < 1020; i += 32) {
		wr32(GICD_BASE + 0x0080 + i/32*4, 0xffffffff);	/* Group 1 */
		wr32(GICD_BASE + 0x0c00 + i/16*4, 0x55555555);	/* Level */
	}
	
	/* Priority for SPIs */
	for (int i = 32; i < 1020; i++)
		wr32(GICD_BASE + 0x400 + i, 0xa0);
	
	/* Enable SPIs */
	for (int i = 32; i < 1020; i += 32)
		wr32(GICD_BASE + 0x100 + i/32*4, 0xffffffff);
	
	/* Wake up redistributors */
	for (int cpu = 0; cpu < 8; cpu++) {
		uint64_t rbase = GICR_BASE + cpu * 0x20000;
		uint32_t waker = rd32(rbase + 0x14);
		wr32(rbase + 0x14, waker & ~2);
		for (int i = 0; i < 100000 && (rd32(rbase + 0x14) & 4); i++)
			;
		wr32(rbase, 0x3);	/* GICR_CTLR: Group 0 + Group 1 NS */
	}
	
	/* CPU interface */
	gic_cpu_interface_init();
	
	con_str("GIC", "done");
}

static void test_gic(void)
{
	con_str("GIC", "self-test");
	/* Simple self-test: send SGI to self */
	uint64_t sgi = sgi_self(0);
	wsr("icc_sgi1r_el1", sgi);
	isb();
	con_str("GIC", "self-test done");
}

/* ---- Timer ---- */

void timer_init(void)
{
	uint64_t freq = rsr("cntfrq_el0");
	if (!freq) freq = 26000000;	/* 26 MHz fallback */
	
	/* CNTP: 10 ms tick */
	wsr("cntp_tval_el0", freq / 100);
	wsr("cntp_ctl_el0", 1);		/* ENABLE=1, IMASK=0 */
	
	/* Enable PPI 30 (CNTP) */
	/* GIC enable handled by GIC init */
	
	con_hex2("TIMER", "freq=", freq, "tick=10ms", 0);
}

volatile int mmu_enabled = 0;

/* ---- UART ---- */

void uart_init(void)
{
	/* USI v2 UART init */
	wr32(UART1_BASE + 0xC4, 1);		/* USI_CON: set reset */
	for (volatile int i = 0; i < 1000; i++);
	wr32(UART1_BASE + 0xC4, 0);		/* USI_CON: clear reset */
	for (volatile int i = 0; i < 1000; i++);
	wr32(UART1_BASE + 0xC8, 2);		/* USI_OPTION: HWACG_CLKREQ_ON */
	
	/* Line control: 8N1 */
	wr32(UART1_BASE + 0x00, 3);
	/* Baud: 115200 @ 26 MHz */
	wr32(UART1_BASE + 0x28, 14);	/* UBRDIV */
	/* FIFO */
	wr32(UART1_BASE + 0x08, 0x07);
	/* Enable */
	wr32(UART1_BASE + 0x04, 7);		/* UART, TX, RX enable */
}

void uart_putc(char c)
{
	wr32(UART1_BASE + 0x20, (uint32_t)c);
	
	if (c == '\n') {
		while (!(rd32(UART1_BASE + 0x10) & (1<<1))) ; /* TX empty */
		wr32(UART1_BASE + 0x20, '\r');
	}
}

/* ---- Console ---- */

#define CON_W	80
#define CON_H	25

static volatile uint32_t *fb = 0;
static uint32_t fb_phys = 0;
static int con_x = 0, con_y = 0;
static uint32_t con_bg = 0xff000000, con_fg = 0xffffffff;
static char con_buf[CON_H][CON_W + 1];

static const uint8_t iso_font[128 * 16] = {
#include "font.h"
};

void con_init(uint32_t phys)
{
	fb_phys = phys;
	fb = (uint32_t *)phys;	/* identity mapped */
	
	/* Clear screen */
	for (int i = 0; i < 800 * 480; i++)
		fb[i] = con_bg;
	con_x = con_y = 0;
}

void con_putc(char c)
{
	if (!fb) return;
	
	if (c == '\n') {
		con_x = 0;
		con_y += 16;
		if (con_y >= 480) con_y = 0;
		/* Clear line */
		for (int y = 0; y < 16; y++) {
			uint32_t *row = fb + (con_y + y) * 800;
			for (int x = 0; x < 800; x++) row[x] = con_bg;
		}
		return;
	}
	
	if (c == '\r') {
		con_x = 0;
		return;
	}
	
	if (c < 32 || c >= 127) return;
	
	const uint8_t *glyph = &iso_font[(c - 32) * 16];
	for (int y = 0; y < 16; y++) {
		uint8_t bits = glyph[y];
		uint32_t *row = fb + (con_y + y) * 800 + con_x;
		for (int x = 0; x < 8; x++) {
			if (bits & (1 << x)) row[x] = con_fg;
		}
	}
	
	con_x += 8;
	if (con_x >= 800) {
		con_x = 0;
		con_y += 16;
		if (con_y >= 480) con_y = 0;
	}
}

void con_puts(const char *s)
{
	while (*s) con_putc(*s++);
}

void con_hex(const char *label, uint64_t v)
{
	char buf[20];
	buf[0] = '0'; buf[1] = 'x';
	for (int i = 0; i < 16; i++)
		buf[2+i] = "0123456789abcdef"[(v >> (60 - i*4)) & 0xf];
	buf[18] = '\0';
	con_puts(label);
	con_puts(": ");
	con_puts(buf);
	con_putc('\n');
}

void con_hex2(const char *l1, const char *prefix1, uint64_t v1, const char *prefix2, uint64_t v2)
{
	con_puts(l1); con_putc(' ');
	con_puts(prefix1);
	con_hex("", v1);
	con_puts(prefix2);
	con_hex("", v2);
	con_putc('\n');
}

void con_str(const char *l1, const char *l2)
{
	con_puts(l1); con_puts(": "); con_puts(l2); con_putc('\n');
}

void con_skip(void) { con_putc('\n'); }
void con_clear(uint32_t color) {
	if (!fb) return;
	for (int i = 0; i < 800 * 480; i++) fb[i] = color;
	con_x = con_y = 0;
}

/* ---- Main ---- */

const char *stage = "init";

void shim_main(uint64_t dtb)
{
	con_str("SHIM", "Exynos 2100 S21 Ultra shim");
	con_hex("DTB", dtb);
	
	/* Initialize UART early */
	uart_init();
	con_str("UART", "initialized");
	
	/* Initialize UART console */
	con_init(0x8f000000);	/* Framebuffer phys from DTB (placeholder) */
	con_str("CON", "framebuffer console ready");
	
	/* Enable MMU */
	con_str("MMU", "enabling");
	struct mmu_info mi;
	if (mmu_enable(&mi) == 0) {
		mmu_enabled = 1;
		con_str("MMU", "enabled");
	} else {
		con_str("MMU", "FAILED");
	}
	
	/* Initialize hardware */
	con_str("UART", "re-init after MMU");
	uart_init();
	
	con_str("GIC", "initializing");
	gic_init();
	
	con_str("TIMER", "initializing");
	timer_init();
	
	/* Test PSCI */
	con_hex("PSCI", psci_version());
	
	/* GIC self-test */
	test_gic();
	
	/* SMP bringup */
	test_smp();
	
	/* Load payload from FDT initrd */
	stage = "loader";
	const char *err = loader_boot(dtb);
	con_str("LOADER", err ? err : "ok");
	
	/* If no payload, stay here */
	for (;;) {
		__asm__ volatile("wfe");
	}
}

void reset(unsigned after_s)
{
	psci_system_reset();
	for (;;) __asm__ volatile("wfe");
}

void reset(unsigned after_s) __attribute__((noreturn));