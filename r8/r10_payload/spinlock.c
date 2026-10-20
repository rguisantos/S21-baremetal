/* spinlock.c — R10: Ticket spinlocks and raw spinlocks for SMP */

#include "r10.h"

/* ================================================================
 * AArch64 atomic primitives using LDXR/STXR (ARMv8-A baseline)
 * ================================================================ */

static inline u32 atomic_fetch_add(u32 *ptr, u32 val)
{
    u32 old, new_value, status;
    asm volatile(
        "1: ldxr %w0, [%3]\n"
        "   add %w1, %w0, %w4\n"
        "   stxr %w2, %w1, [%3]\n"
        "   cbnz %w2, 1b\n"
        : "=&r" (old), "=&r" (new_value), "=&r" (status)
        : "r" (ptr), "r" (val)
        : "memory", "cc"
    );
    return old;
}

static inline u32 atomic_load_acquire(const u32 *ptr)
{
    u32 val;
    asm volatile(
        "ldar %w0, [%1]\n"
        : "=r" (val)
        : "r" (ptr)
        : "memory"
    );
    return val;
}

static inline u32 atomic_load_relaxed(const u32 *ptr)
{
    u32 val;
    asm volatile(
        "ldr %w0, [%1]\n"
        : "=r" (val)
        : "r" (ptr)
        : "memory"
    );
    return val;
}

static inline void atomic_store_release(u32 *ptr, u32 val)
{
    asm volatile(
        "stlr %w1, [%0]\n"
        :
        : "r" (ptr), "r" (val)
        : "memory"
    );
}

static inline bool atomic_cas(u32 *ptr, u32 *expected, u32 desired)
{
    u32 old, status;
    u32 expected_value = *expected;
    asm volatile(
        "1: mov %w1, #1\n"
        "   ldxr %w0, [%2]\n"
        "   cmp %w0, %w3\n"
        "   b.ne 2f\n"
        "   stxr %w1, %w4, [%2]\n"
        "   cbnz %w1, 1b\n"
        "   b 3f\n"
        "2: clrex\n"
        "3:\n"
        : "=&r" (old), "=&r" (status)
        : "r" (ptr), "r" (expected_value), "r" (desired)
        : "memory", "cc"
    );
    *expected = old;
    return old == expected_value && status == 0;
}

static inline bool atomic_test_and_set(u32 *ptr)
{
    u32 old, status, one;
    asm volatile(
        "   mov %w2, #1\n"
        "1: mov %w1, #1\n"
        "   ldxr %w0, [%3]\n"
        "   cbnz %w0, 2f\n"
        "   stxr %w1, %w2, [%3]\n"
        "   cbnz %w1, 1b\n"
        "   b 3f\n"
        "2: clrex\n"
        "3:\n"
        : "=&r" (old), "=&r" (status), "=&r" (one)
        : "r" (ptr)
        : "memory", "cc"
    );
    return old != 0;
}

static inline void atomic_clear(u32 *ptr)
{
    asm volatile(
        "stlr %w1, [%0]\n"
        :
        : "r" (ptr), "r" ((u32)0)
        : "memory"
    );
}

static inline u32 atomic_add_fetch(u32 *ptr, u32 val)
{
    u32 old, new_value, status;
    asm volatile(
        "1: ldxr %w0, [%3]\n"
        "   add %w1, %w0, %w4\n"
        "   stxr %w2, %w1, [%3]\n"
        "   cbnz %w2, 1b\n"
        : "=&r" (old), "=&r" (new_value), "=&r" (status)
        : "r" (ptr), "r" (val)
        : "memory", "cc"
    );
    return new_value;
}

static inline u32 atomic_sub_fetch(u32 *ptr, u32 val)
{
    u32 old, new_value, status;
    asm volatile(
        "1: ldxr %w0, [%3]\n"
        "   sub %w1, %w0, %w4\n"
        "   stxr %w2, %w1, [%3]\n"
        "   cbnz %w2, 1b\n"
        : "=&r" (old), "=&r" (new_value), "=&r" (status)
        : "r" (ptr), "r" (val)
        : "memory", "cc"
    );
    return new_value;
}

/* ================================================================
 * Ticket Lock (fair FIFO ordering)
 * ================================================================ */

void ticket_lock_init(ticket_lock_t *lock)
{
    lock->head = 0;
    lock->tail = 0;
}

void ticket_lock(ticket_lock_t *lock)
{
    u32 my_ticket = atomic_fetch_add(&lock->tail, 1);
    while (atomic_load_acquire(&lock->head) != my_ticket) {
        asm volatile("wfe" ::: "memory");
    }
}

int ticket_trylock(ticket_lock_t *lock)
{
    u32 head = atomic_load_acquire(&lock->head);
    u32 tail = atomic_load_acquire(&lock->tail);
    
    if (head == tail) {
        u32 expected = tail;
        if (atomic_cas(&lock->tail, &expected, tail + 1)) {
            return 1;
        }
    }
    return 0;
}

void ticket_unlock(ticket_lock_t *lock)
{
    atomic_store_release(&lock->head, lock->head + 1);
    asm volatile("sev" ::: "memory");
}

/* ================================================================
 * Raw Spinlock (simple test-and-set, not fair)
 * ================================================================ */

void raw_spinlock_init(raw_spinlock_t *lock)
{
    lock->lock = 0;
}

void raw_spinlock(raw_spinlock_t *lock)
{
    while (atomic_test_and_set(&lock->lock)) {
        while (atomic_load_relaxed(&lock->lock)) {
            asm volatile("wfe" ::: "memory");
        }
    }
}

int raw_spin_trylock(raw_spinlock_t *lock)
{
    return !atomic_test_and_set(&lock->lock);
}

void raw_spinunlock(raw_spinlock_t *lock)
{
    atomic_clear(&lock->lock);
    asm volatile("sev" ::: "memory");
}

/* ================================================================
 * RW Spinlock (readers-writer, writers exclusive)
 * ================================================================ */

void rw_spinlock_init(rw_spinlock_t *lock)
{
    lock->readers = 0;
    lock->writer = 0;
    lock->waiting_writers = 0;
    raw_spinlock_init(&lock->lock);
}

void read_lock(rw_spinlock_t *lock)
{
    raw_spinlock(&lock->lock);
    while (lock->writer || lock->waiting_writers) {
        raw_spinunlock(&lock->lock);
        asm volatile("wfe" ::: "memory");
        raw_spinlock(&lock->lock);
    }
    atomic_add_fetch(&lock->readers, 1);
    raw_spinunlock(&lock->lock);
}

int read_trylock(rw_spinlock_t *lock)
{
    raw_spinlock(&lock->lock);
    if (lock->writer || lock->waiting_writers) {
        raw_spinunlock(&lock->lock);
        return 0;
    }
    atomic_add_fetch(&lock->readers, 1);
    raw_spinunlock(&lock->lock);
    return 1;
}

void read_unlock(rw_spinlock_t *lock)
{
    raw_spinlock(&lock->lock);
    atomic_sub_fetch(&lock->readers, 1);
    if (lock->readers == 0 && lock->waiting_writers) {
        asm volatile("sev" ::: "memory");
    }
    raw_spinunlock(&lock->lock);
}

void write_lock(rw_spinlock_t *lock)
{
    raw_spinlock(&lock->lock);
    atomic_add_fetch(&lock->waiting_writers, 1);
    while (lock->readers > 0 || lock->writer) {
        raw_spinunlock(&lock->lock);
        asm volatile("wfe" ::: "memory");
        raw_spinlock(&lock->lock);
    }
    atomic_sub_fetch(&lock->waiting_writers, 1);
    lock->writer = 1;
    raw_spinunlock(&lock->lock);
}

int write_trylock(rw_spinlock_t *lock)
{
    raw_spinlock(&lock->lock);
    if (lock->readers > 0 || lock->writer) {
        raw_spinunlock(&lock->lock);
        return 0;
    }
    lock->writer = 1;
    raw_spinunlock(&lock->lock);
    return 1;
}

void write_unlock(rw_spinlock_t *lock)
{
    raw_spinlock(&lock->lock);
    lock->writer = 0;
    raw_spinunlock(&lock->lock);
    asm volatile("sev" ::: "memory");
}

/* ================================================================
 * Seqlock (for read-mostly data)
 * ================================================================ */

void seqlock_init(seqlock_t *lock)
{
    lock->sequence = 0;
    raw_spinlock_init(&lock->lock);
}

unsigned read_seqbegin(const seqlock_t *lock)
{
    unsigned seq;
    do {
        seq = atomic_load_acquire(&lock->sequence);
    } while (seq & 1);
    return seq;
}

int read_seqretry(const seqlock_t *lock, unsigned seq)
{
    return atomic_load_acquire(&lock->sequence) != seq;
}

void write_seqlock(seqlock_t *lock)
{
    raw_spinlock(&lock->lock);
    atomic_add_fetch(&lock->sequence, 1);
}

void write_sequnlock(seqlock_t *lock)
{
    atomic_add_fetch(&lock->sequence, 1);
    raw_spinunlock(&lock->lock);
}