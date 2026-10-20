/* Execute the actual PR #3 primitives on AArch64, including CAS failure.
 * Single CPU smoke test: not an SMP contention or hardware validation. */
#include "../r10_payload/spinlock.c"
static void check(int ok, const char *name)
{
    if (!ok) { printf("ATOMIC FAIL: %s\n", name); park(); }
}
void module_main(unsigned el)
{
    (void)el;
    u32 value = 7, expected;
    check(atomic_fetch_add(&value, 5) == 7 && value == 12, "fetch_add");
    check(atomic_add_fetch(&value, 3) == 15 && value == 15, "add_fetch");
    check(atomic_sub_fetch(&value, 4) == 11 && value == 11, "sub_fetch");
    expected = 10;
    check(!atomic_cas(&value, &expected, 20) && expected == 11 && value == 11, "CAS mismatch");
    check(atomic_cas(&value, &expected, 20) && value == 20, "CAS match");
    value = 0;
    check(!atomic_test_and_set(&value) && value == 1, "TAS free");
    check(atomic_test_and_set(&value) && value == 1, "TAS busy");
    atomic_clear(&value);
    check(value == 0, "clear");
    ticket_lock_t ticket;
    ticket_lock_init(&ticket);
    check(ticket_trylock(&ticket), "ticket free");
    check(!ticket_trylock(&ticket), "ticket busy");
    ticket_unlock(&ticket);
    ticket_lock(&ticket);
    ticket_unlock(&ticket);
    check(ticket.head == 2 && ticket.tail == 2, "ticket counters");
    raw_spinlock_t raw;
    raw_spinlock_init(&raw);
    check(raw_spin_trylock(&raw) && !raw_spin_trylock(&raw), "raw trylock");
    raw_spinunlock(&raw);
    rw_spinlock_t rw;
    rw_spinlock_init(&rw);
    read_lock(&rw);
    check(!write_trylock(&rw), "reader excludes writer");
    read_unlock(&rw);
    check(write_trylock(&rw) && !read_trylock(&rw), "writer excludes reader");
    write_unlock(&rw);
    printf("ATOMIC PASS\n");
    park();
}
void el1_stage(void) { park(); }
void el2_stage(void) { park(); }
