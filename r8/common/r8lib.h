#ifndef R8LIB_H
#define R8LIB_H

/*
 * r8lib.h — infraestrutura comum dos três módulos R8 (bare-metal QEMU virt)
 *
 * Convenções de plataforma (qemu-system-aarch64 -M virt):
 *   DRAM base ....... 0x40000000   (imagem ligada em 0x40080000)
 *   PL011 UART0 ..... 0x09000000
 *   GICv3 GICD ...... 0x08000000   (r8c; igual ao v2 — o ITS fica em
 *                    0x08080000, endereço que já nos enganou: ver gic.c)
 *   GICv3 GICR ...... 0x080A0000   (r8c)
 *   generic timer ... CNTFRQ/CNTP_* + INTID 30 (r8c)
 */

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef unsigned long  u64;

/* ---- uart.c ---- */
void uart_init(void);
void uart_putc(char c);

/* ---- printf.c (printf minimalista, sem libc) ---- */
int  printf(const char *fmt, ...);
int  putchar(int c);
int  puts(const char *s);

/* ---- util.c ---- */
unsigned get_current_el(void);
void vbar_install(void);           /* instala a tabela de vetores em VBAR_EL1 */
void park(void) __attribute__((noreturn));
void shutdown(void) __attribute__((noreturn));  /* PSCI SYSTEM_OFF */
void *memset(void *d, int c, u64 n);
void *memcpy(void *d, const void *s, u64 n);
int   memcmp(const void *a, const void *b, u64 n);

/* ---- sys.S ---- */
u64 get_pc(void);
void drop_from_el3_to_el2(u64 target_pc);  /* ERET sintetizado p/ EL2h */
void drop_from_el2_to_el1(u64 target_pc);  /* ERET sintetizado p/ EL1h */

/* ---- start.S ---- */
extern char el2_trampoline[];      /* alvos do ERET (arrumam SP e chamam) */
extern char el1_trampoline[];

/* ---- vetores / exceções ---- */
extern char vectors[];             /* tabela 16 slots (vectors.S) */

struct exc_frame {
    u64 x[31];        /* x0..x30  — offset 8*i            */
    u64 elr;          /* offset 248                        */
    u64 spsr;         /* offset 256                        */
    u64 esr;          /* offset 264                        */
    u64 far;          /* offset 272                        */
    u64 sp_orig;      /* offset 280 — SP antes da entrada  */
};

enum { KIND_SYNC = 0, KIND_IRQ = 1, KIND_FIQ = 2, KIND_SERROR = 3 };

void exc_dispatch(struct exc_frame *f, u64 kind);
void exc_unexpected_c(unsigned from_vector);
void __attribute__((weak)) irq_hook(struct exc_frame *f);

/* ---- mmio ---- */
static inline void mmio_w(u64 addr, u32 v) { *(volatile u32 *)addr = v; }
static inline u32 mmio_r(u64 addr)          { return *(volatile u32 *)addr; }

/* ---- acessos a system registers (inline asm) ---- */
#define MRS(reg) ({ u64 __v; asm volatile("mrs %0, " #reg : "=r"(__v)); __v; })
#define MSR(reg, val) asm volatile("msr " #reg ", %0" :: "r"((u64)(val)) : "memory")

/* ---- pontos de entrada de cada módulo ---- */
void module_main(unsigned entry_el);
void el2_stage(void);
void el1_stage(void);

#endif /* R8LIB_H */
