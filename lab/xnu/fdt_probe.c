/* Host-only view of the unchanged production parser, with no boot defaults. */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include "../../r8/r10_payload/fdt.h"

static void ranges(const struct r10_range *items, uint32_t count)
{
    putchar('[');
    for (uint32_t i = 0; i < count; ++i)
        printf("%s[\"0x%" PRIx64 "\",\"0x%" PRIx64 "\"]",
               i ? "," : "", items[i].base, items[i].size);
    putchar(']');
}

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    FILE *file = fopen(argv[1], "rb");
    if (!file) return 2;
    unsigned char *data = malloc(R10_FDT_MAX_SIZE + 1U);
    if (!data) { fclose(file); return 2; }
    size_t size = fread(data, 1, R10_FDT_MAX_SIZE + 1U, file);
    int bad = ferror(file) || size > R10_FDT_MAX_SIZE;
    fclose(file);
    if (bad) { free(data); return 2; }
    struct r10_platform p;
    int rc = r10_fdt_parse(data, size, &p);
    printf("{\"parse\":%d,\"message\":\"%s\"", rc, r10_fdt_error(rc));
    if (!rc) {
        printf(",\"ram\":"); ranges(p.ram, p.ram_count);
        printf(",\"reserved\":"); ranges(p.reserved, p.reserved_count);
        printf(",\"unresolved_reserved\":%u,\"cpus\":[", p.unresolved_reserved);
        for (uint32_t i = 0; i < p.cpu_count; ++i)
            printf("%s\"0x%" PRIx64 "\"", i ? "," : "", p.cpus[i]);
        printf("],\"have_gic\":%u,\"gic\":", p.have_gic);
        struct r10_range gic[] = { p.gic_dist, p.gic_redist };
        ranges(gic, 2);
        printf(",\"gic_phandle\":%u,\"redist_stride\":\"0x%" PRIx64 "\"",
               p.gic_phandle, p.redist_stride);
        printf(",\"have_timer\":%u,\"timer_parent\":%u,\"timer_irq\":%u,"
               "\"timer_frequency\":%u,\"initrd\":", p.have_timer,
               p.timer_parent, p.timer_irq, p.timer_frequency);
        ranges(&p.initrd, p.initrd.size ? 1 : 0);
    }
    puts("}");
    free(data);
    return 0;
}
