#include "payload.h"
#include "../r8/r10_payload/fdt.h"
static uint32_t le32(const unsigned char *p)
{ return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
static uint64_t le64(const unsigned char *p)
{ return (uint64_t)le32(p) | (uint64_t)le32(p+4)<<32; }
static int span(uint64_t a,uint64_t n) { return n && a<=UINT64_MAX-n; }
static int overlaps(uint64_t a,uint64_t n,uint64_t b,uint64_t m)
{ return n && m && a<b+m && b<a+n; }
static int file_range(uint64_t off,uint64_t n,size_t size)
{ return off<=size && n<=size-off; }
int payload_validate(const void *data,size_t size,uint64_t source,struct payload_plan *out)
{
    static const unsigned char magic[8]={'S','2','1','R','1','0',' ',' '};
    if (!out) return -1;
    struct payload_plan plan={0};
    *out=plan;
    if (!data || size<PAYLOAD_HEADER_SIZE || size>PAYLOAD_MAX_SIZE || !span(source,size)) return -1;
    const unsigned char *p=data;
    for (unsigned i=0;i<8;++i) if (p[i]!=magic[i]) return -1;
    uint32_t count=le32(p+12);
    if (le32(p+8)!=1 || !count || count>PAYLOAD_MAX_SEGMENTS) return -1;
    uint64_t table=PAYLOAD_HEADER_SIZE+(uint64_t)count*PAYLOAD_SEGMENT_SIZE;
    if (table>size) return -1;
    plan.count=count; plan.base=le64(p+16); plan.entry=le64(p+24);
    plan.dtb_offset=le64(p+32); plan.dtb_size=le64(p+40);
    plan.kernel_end=le64(p+48); plan.memory_size=le64(p+64);
    if (le64(p+56)!=plan.base || (plan.base&4095) ||
        !span(plan.base,plan.memory_size) || plan.memory_size>PAYLOAD_MAX_SIZE ||
        overlaps(source,size,plan.base,plan.memory_size)) return -1;
    unsigned terminated=0;
    for (unsigned i=0;i<608;++i) if (!p[72+i]) terminated=1;
    if (!terminated) return -1;
    if ((plan.dtb_offset&7) || plan.dtb_offset<table ||
        !file_range(plan.dtb_offset,plan.dtb_size,size) ||
        plan.dtb_size<40 || plan.dtb_size>R10_FDT_MAX_SIZE) return -1;
    uint64_t last=plan.base, first=UINT64_MAX; unsigned entry_found=0;
    for (uint32_t i=0;i<count;++i) {
        const unsigned char *r=p+PAYLOAD_HEADER_SIZE+i*PAYLOAD_SEGMENT_SIZE;
        struct payload_segment *s=&plan.segments[i];
        s->address=le64(r); s->memory_size=le64(r+8);
        s->file_offset=le64(r+16); s->file_size=le64(r+24);
        if (!span(s->address,s->memory_size) || s->address<plan.base ||
            s->address+s->memory_size>plan.base+plan.memory_size ||
            s->file_size>s->memory_size || (s->file_offset&7) || s->file_offset<table ||
            !file_range(s->file_offset,s->file_size,size) ||
            overlaps(s->file_offset,s->file_size,plan.dtb_offset,plan.dtb_size)) return -1;
        for (uint32_t j=0;j<i;++j) {
            const struct payload_segment *old=&plan.segments[j];
            if (overlaps(s->address,s->memory_size,old->address,old->memory_size) ||
                overlaps(s->file_offset,s->file_size,old->file_offset,old->file_size)) return -1;
        }
        if (s->address<first) first=s->address;
        if (s->address+s->memory_size>last) last=s->address+s->memory_size;
        if (plan.entry>=s->address && plan.entry-s->address<s->file_size) entry_found=1;
    }
    /* Require the exact page-rounded ELF extent, including NOLOAD stacks. */
    if (first!=plan.base || !entry_found || last>UINT64_MAX-4095 || plan.kernel_end!=((last+4095)&~UINT64_C(4095))) return -1;
    plan.dtb_address=plan.kernel_end;
    if (!span(plan.dtb_address,plan.dtb_size) ||
        plan.dtb_address+plan.dtb_size>plan.base+plan.memory_size) return -1;
    static struct r10_platform platform;
    if (r10_fdt_parse(p+plan.dtb_offset,(size_t)plan.dtb_size,&platform) ||
        platform.blob_size!=plan.dtb_size) return -1;
    *out=plan;
    return 0;
}
