"""Correction for the pinned QEMU ramfb consumer; not an Exynos driver.

QEMU coherent DMA only. Volatile and ordering barriers are not physical
non-coherent cache maintenance.
"""


def patch(source):
    start = source.index('static void\nramfb_phone_screen(void)')
    end = source.index('\nefi_status EFIAPI', start)
    original = source[start:end]
    fixed = original.replace('static void\n', 'static int\n', 1)
    fixed = fixed.replace('\tstatic struct {\n\t\tuint32_t control, length;',
                          '\tstatic volatile struct {\n\t\tuint32_t control, length;')
    fixed = fixed.replace('\t} dma;', '\t} __attribute__((aligned(64))) dma;')
    fixed = fixed.replace('\t\treturn;', '\t\treturn 1;', 1)
    old = '''\t*(volatile uint64_t *)(FW_CFG_BASE + 16) = __builtin_bswap64((uint64_t)(uintptr_t)&dma);
\tif (dma.control != 0) {
\t\tprint("ramfb: control %x after the request\\n", (uint64_t)be32(dma.control));
\t\treturn;
\t}'''
    new = '''    /* Publish cfg and descriptor before triggering coherent QEMU DMA. */
    __asm__ volatile("dsb sy" ::: "memory");
    *(volatile uint64_t *)(FW_CFG_BASE + 16) = __builtin_bswap64((uint64_t)(uintptr_t)&dma);
    uint32_t status = ~0U;
    for (uint32_t attempt = 0; attempt < 1000000; ++attempt) {
        status = be32(dma.control);
        if (status == 0 || (status & 1)) break;
        __asm__ volatile("yield" ::: "memory");
    }
    if (status != 0) {
        print("S21 RAMFB: REJECT DMA status %x\\n", (uint64_t)status);
        return 0; /* Do not hand off a stale GOP buffer after a failed DMA. */
    }
    __asm__ volatile("dmb oshld" ::: "memory");'''
    if fixed.count(old) != 1:
        raise ValueError('ramfb DMA anchor changed')
    fixed = fixed.replace(old, new)
    fixed = fixed.replace('\tSCREEN.stride = PHONE_WIDTH * 4;',
                          '\tSCREEN.stride = PHONE_WIDTH * 4;\n\treturn 1;')
    call = '\t\t\tramfb_phone_screen();'
    if source.count(call) != 1:
        raise ValueError('ramfb call anchor changed')
    source = source[:start] + fixed + source[end:]
    return source.replace(call, '\t\t\tif (!ramfb_phone_screen()) return (efi_status)((1ULL << 63) | 7);')
