#include "payload_stage.h"
static int span(uint64_t base,uint64_t size)
{ return size && base<=UINT64_MAX-size; }
static int overlap(uint64_t a,uint64_t n,uint64_t b,uint64_t m)
{ return n && m && a<b+m && b<a+n; }
int payload_stage(const void *data,size_t size,const struct payload_environment *e,
                  struct payload_plan *out)
{
    if (!out) return PAYLOAD_BAD_WIRE;
    /* Do not invalidate an aliased output by writing into an input/window. */
    if (overlap((uintptr_t)out,sizeof(*out),(uintptr_t)data,size) ||
        (e && e->destination && span((uintptr_t)e->destination,e->destination_size) &&
         overlap((uintptr_t)out,sizeof(*out),(uintptr_t)e->destination,e->destination_size)))
        return PAYLOAD_BAD_DESTINATION;
    *out=(struct payload_plan){0};
    struct payload_plan p;
    if (!e || payload_validate(data,size,e->source_address,&p)) return PAYLOAD_BAD_WIRE;
    if (!e->firmware_fdt || !span(e->firmware_address,e->firmware_size) ||
        e->firmware_size!=p.dtb_size) return PAYLOAD_BAD_FDT;
    static struct r10_platform firmware; /* Parser already requires one CPU. */
    if (r10_fdt_parse(e->firmware_fdt,e->firmware_size,&firmware) ||
        firmware.blob_size!=e->firmware_size) return PAYLOAD_BAD_FDT;
    const unsigned char *source=data, *fdt=e->firmware_fdt;
    for (size_t i=0;i<e->firmware_size;++i)
        if (source[p.dtb_offset+i]!=fdt[i]) return PAYLOAD_BAD_FDT;
    if (r10_fdt_range_usable(&firmware,p.base,p.memory_size)) return PAYLOAD_BAD_RAM;
    if (r10_fdt_check_boot(&firmware,p.dtb_address,p.base,p.kernel_end,e->mpidr))
        return PAYLOAD_BAD_FDT;
    if (overlap(p.base,p.memory_size,e->firmware_address,e->firmware_size) ||
        !e->protected_count || e->protected_count>8 || (e->protected_count && !e->protected_ranges))
        return PAYLOAD_PROTECTED;
    for (size_t i=0;i<e->protected_count;++i) {
        const struct r10_range *r=&e->protected_ranges[i];
        if (!span(r->base,r->size) || overlap(p.base,p.memory_size,r->base,r->size))
            return PAYLOAD_PROTECTED;
    }
    uint64_t dst=(uintptr_t)e->destination, fw=(uintptr_t)e->firmware_fdt, src=(uintptr_t)data;
    if (!e->destination || e->destination_size<p.memory_size || !span(dst,p.memory_size) ||
        !span(src,size) || !span(fw,e->firmware_size) ||
        overlap(dst,p.memory_size,src,size) || overlap(dst,p.memory_size,fw,e->firmware_size) ||
        !span((uintptr_t)out,sizeof(*out)) ||
        overlap(dst,p.memory_size,(uintptr_t)out,sizeof(*out))) return PAYLOAD_BAD_DESTINATION;
    /* Window was fully checked. Zero BSS, holes, padding and future FDT bytes,
     * then copy exact byte counts: no word rounding beyond file/memory bounds. */
    unsigned char *destination=e->destination;
    for (uint64_t i=0;i<p.memory_size;++i) destination[i]=0;
    for (uint32_t i=0;i<p.count;++i) {
        const struct payload_segment *s=&p.segments[i];
        for (uint64_t j=0;j<s->file_size;++j)
            destination[s->address-p.base+j]=source[s->file_offset+j];
    }
    for (uint64_t i=0;i<p.dtb_size;++i)
        destination[p.dtb_address-p.base+i]=source[p.dtb_offset+i];
    *out=p;
    return 0;
}
