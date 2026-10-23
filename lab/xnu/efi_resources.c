#include "efi_resources.h"

static uint32_t u32(const uint8_t *p)
{ return p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
static uint64_t u64(const uint8_t *p)
{ return u32(p) | (uint64_t)u32(p+4)<<32; }
static int zero(const uint8_t *p, uint32_t n)
{ for (uint32_t i=0;i<n;++i) if (p[i]) return 0; return 1; }
static int named(const uint8_t *p, uint32_t n, const char *s)
{
    uint32_t i=0;
    while (s[i]) { if (i>=n || p[i]!=(uint8_t)s[i]) return 0; ++i; }
    return i<n && zero(p+i,n-i);
}
static int span(uint64_t base, uint64_t size)
{ return size && size<=UINT64_MAX-base; }
static int overlap(uint64_t a,uint64_t n,uint64_t b,uint64_t m)
{ return a<b+m && b<a+n; }
struct reader { const uint8_t *data; uint32_t size, at; };
struct prop { const uint8_t *key, *data; uint32_t size; };
struct view { uint32_t count, children; struct prop props[6]; };
static const uint8_t *take(struct reader *r,uint32_t size)
{
    if (size>r->size-r->at) return NULL;
    const uint8_t *p=r->data+r->at; r->at+=size; return p;
}
static const struct prop *get(const struct view *v,const char *key)
{
    for (uint32_t i=0;i<v->count;++i) if (named(v->props[i].key,32,key)) return &v->props[i];
    return NULL;
}
static const uint8_t *value(const struct view *v,const char *key,uint32_t size)
{
    const struct prop *p=get(v,key); return p && p->size==size ? p->data : NULL;
}
static int text(const struct view *v,const char *key,const char *s)
{
    const struct prop *p=get(v,key); return p && named(p->data,p->size,s);
}
static int read_node(struct reader *r,struct view *v,const char *name,uint32_t count,uint32_t children)
{
    const uint8_t *head=take(r,8); if (!head) return 0;
    v->count=u32(head); v->children=u32(head+4);
    if (v->count!=count || count>6 || v->children!=children) return 0;
    for (uint32_t i=0;i<count;++i) {
        const uint8_t *p=take(r,36); if (!p) return 0;
        uint32_t stop=0; while (stop<32 && p[stop]) ++stop;
        if (!stop || stop==32 || !zero(p+stop,32-stop)) return 0;
        for (uint32_t j=0;j<i;++j) if (named(p,32,(const char *)v->props[j].key)) return 0;
        uint32_t size=u32(p+32);
        const uint8_t *data=take(r,size); if (!data) return 0;
        uint32_t padding=(4-size%4)%4;
        const uint8_t *pad=take(r,padding); if (!pad || !zero(pad,padding)) return 0;
        v->props[i]=(struct prop){p,data,size};
    }
    return text(v,"name",name);
}

/* Exactly the canonical one-CPU lab fragment, in its specified node order.
 * This is deliberately not a general Apple DT walker. No MMIO is accessed. */
int s21_resources_decode(const void *data,uint32_t size,struct s21_resources *out)
{
    if (!data || !out || size<8 || size>4096 || size%4) return 0;
    struct reader r={(const uint8_t *)data,size,0}; struct view v;
    struct s21_resources result={0}; const uint8_t *p;
    if (!read_node(&r,&v,"device-tree",1,3) || !read_node(&r,&v,"chosen",2,0)) return 0;
    if (text(&v,"psci-method","hvc")) result.hvc=1;
    else if (!text(&v,"psci-method","smc")) return 0;
    if (!read_node(&r,&v,"cpus",1,1) || !read_node(&r,&v,"cpu0",4,0) || !text(&v,"device_type","cpu")) return 0;
    p=value(&v,"reg",4); if (!p) return 0; result.mpidr=u32(p);
    p=value(&v,"timebase-frequency",8); if (!p) return 0; result.frequency=u64(p);
    if (!read_node(&r,&v,"arm-io",2,2)) return 0;
    p=value(&v,"ranges",24); if (!p || u64(p)) return 0;
    result.io_base=u64(p+8); result.io_size=u64(p+16);
    if (!span(result.io_base,result.io_size)) return 0;
    if (!read_node(&r,&v,"gic",4,0) || !text(&v,"device_type","interrupt-controller") || !text(&v,"compatible","arm,gic-v3")) return 0;
    p=value(&v,"reg",32); if (!p) return 0;
    if (u64(p)>UINT64_MAX-result.io_base || u64(p+16)>UINT64_MAX-result.io_base) return 0;
    result.dist=result.io_base+u64(p); result.dist_size=u64(p+8);
    result.redist=result.io_base+u64(p+16); result.redist_size=u64(p+24);
    if (!read_node(&r,&v,"uart0",4,0) || !text(&v,"device_type","uart") || !text(&v,"compatible","arm,pl011")) return 0;
    p=value(&v,"reg",16); if (!p || u64(p)>UINT64_MAX-result.io_base) return 0;
    result.uart=result.io_base+u64(p); result.uart_size=u64(p+8);
    if (r.at!=r.size) return 0;
    *out=result; return 1;
}
int s21_resources_qemu(const struct s21_resources *p,uint64_t frequency,uint64_t mpidr)
{
    return p && p->io_base==0x08000000 && p->io_size==0x01001000 &&
        p->dist==0x08000000 && p->dist_size==0x10000 &&
        p->redist==0x080a0000 && p->redist_size==0x100000 &&
        p->uart==0x09000000 && p->uart_size==0x1000 &&
        p->hvc==1 && p->mpidr==0 && mpidr==0 &&
        p->frequency==62500000 && frequency==p->frequency;
}

/* Bounds check the pinned Mach-O input before the legacy extent/copy loops.
 * No signature, relocation or general executable authentication is provided. */
static int macho(const uint8_t *data,uint32_t size)
{
    if (size<32 || size>32U*1024*1024 || u32(data)!=0xfeedfacf || u32(data+4)!=0x100000c || u32(data+12)!=2) return 0;
    uint32_t count=u32(data+16), length=u32(data+20), at=32, segments=0;
    uint64_t starts[32], sizes[32], files[32], entry=0; uint32_t executable[32];
    if (!count || count>256 || length>size-32) return 0;
    for (uint32_t i=0;i<count;++i) {
        if (at>32+length || 32+length-at<8) return 0;
        uint32_t cmd=u32(data+at), n=u32(data+at+4);
        if (n<8 || n%8 || n>32+length-at) return 0;
        const uint8_t *p=data+at;
        if (cmd==0x19) {
            if (n<72 || u32(p+64)>(n-72)/80 || 72+u32(p+64)*80!=n) return 0;
            uint64_t va=u64(p+24), mem=u64(p+32), off=u64(p+40), file=u64(p+48);
            if (file>mem || off>size || file>size-off) return 0;
            if (mem) {
                if (segments==32 || !span(va,mem) || va<S21_XNU_VBASE || va+mem>S21_XNU_VBASE+UINT64_C(0x180000000)) return 0;
                for (uint32_t j=0;j<segments;++j) if (overlap(va,mem,starts[j],sizes[j])) return 0;
                starts[segments]=va; sizes[segments]=mem; files[segments]=file;
                executable[segments++]=u32(p+60)&4;
            }
        } else if (cmd==5) {
            if (entry || n!=288 || u32(p+8)!=6 || u32(p+12)!=68) return 0;
            entry=u64(p+272);
        }
        at+=n;
    }
    if (at!=32+length || !entry) return 0;
    for (uint32_t i=0;i<segments;++i) if (executable[i] && entry>=starts[i] && entry-starts[i]<files[i]) return 1;
    return 0;
}
/* Typed, QEMU-only descriptor. No address from an unchecked string is used. */
int s21_resident_decode(const void *raw,uint32_t size,struct s21_resident *out)
{
    const uint8_t *p=raw;
    if (!p || !out || size!=32 || !named(p,8,"S21RDSK") || u32(p+8)!=1 || u32(p+12)) return 0;
    uint64_t base=u64(p+16), n=u64(p+24);
    if (base!=S21_RESIDENT_BASE || !n || n%4096 || n>S21_RESIDENT_LIMIT) return 0;
    *out=(struct s21_resident){base,n}; return 1;
}
/* Header consistency only, not an APFS checksum or image authentication.
 * Caller must establish ownership of the complete descriptor range first. */
int s21_resident_apfs(const void *raw,uint64_t size)
{
    const uint8_t *p=raw;
    return p && size>=4096 && size<=S21_RESIDENT_LIMIT && size%4096==0 &&
        u32(p+32)==0x4253584e && u32(p+36)==4096 && u64(p+40)==size/4096;
}
int s21_payload_decode(const void *raw,uint32_t available,struct s21_payload *out)
{
    const uint8_t *data=raw;
    if (!data || !out || available<32 || u32(data)!=0x50554e58) return 0;
    uint32_t body=u32(data+4), at=8, seen=0;
    if (body>available-8 || body>S21_PAYLOAD_LIMIT-8) return 0;
    uint32_t end=body+8; struct s21_payload result={0};
    while (at<=end && end-at>=24) {
        const uint8_t *p=data+at; at+=24;
        if (!p[0]) {
            if (!zero(p,24) || at!=end || (seen!=15 && seen!=31) || !macho(result.kernel,result.kernel_size)) return 0;
            *out=result; return 1;
        }
        uint32_t size=u32(p+16), bit=0;
        if (!size || u32(p+20) || size>end-at) return 0;
        if (named(p,16,"kernel")) { bit=1; result.kernel=data+at; result.kernel_size=size; }
        else if (named(p,16,"ramdisk")) { bit=2; result.ramdisk=data+at; result.ramdisk_size=size; }
        else if (named(p,16,"cmdline")) {
            bit=4; result.cmdline=(const char *)data+at;
            if (size>608 || !named(data+at,size,"cpus=1 loader_return_after=30")) return 0;
        } else if (named(p,16,"adtres")) { bit=8; result.resource=data+at; result.resource_size=size; }
        else if (named(p,16,"resident")) {
            bit=16; if (!s21_resident_decode(data+at,size,&result.resident)) return 0;
        }
        else return 0;
        if (seen&bit) return 0;
        seen|=bit;
        at+=size; uint32_t padding=(16-size%16)%16;
        if (padding>end-at || !zero(data+at,padding)) return 0;
        at+=padding;
    }
    return 0;
}
int s21_layout_check(uint64_t base,uint64_t size,uint64_t lo,uint64_t hi,
                     uint64_t rd,uint64_t rn,uint64_t dt,uint64_t dn,uint64_t ba,uint64_t top)
{
    if (!span(base,size) || base%0x2000000 || size%0x4000 || hi<=lo ||
        ba%8 || dt%4 || top%0x4000 || top>base+size || dn>0x10000) return 0;
    uint64_t starts[]={lo,rd,dt,ba}, sizes[]={hi-lo,rn,dn,736};
    if (overlap(base,size,0xf0000000,0x4000000)) return 0;
    for (uint32_t i=0;i<4;++i) {
        if (!span(starts[i],sizes[i]) || starts[i]<base || starts[i]+sizes[i]>top) return 0;
        for (uint32_t j=0;j<i;++j) if (overlap(starts[i],sizes[i],starts[j],sizes[j])) return 0;
    }
    return 1;
}

int s21_resident_layout(const struct s21_resident *r,uint64_t base,uint64_t size,
                        uint64_t lo,uint64_t hi,uint64_t rd,uint64_t rn,
                        uint64_t dt,uint64_t dn,uint64_t ba,uint64_t top)
{
    if (!r || !s21_layout_check(base,size,lo,hi,rd,rn,dt,dn,ba,top)) return 0;
    if (!r->size) return r->base==0;
    if (r->base!=S21_RESIDENT_BASE || r->size>S21_RESIDENT_LIMIT || r->size%4096 ||
        base>UINT64_MAX-S21_RESIDENT_OFFSET || r->base!=base+S21_RESIDENT_OFFSET) return 0;
    uint64_t n=(r->size+0x3fff)&~UINT64_C(0x3fff);
    if (!span(r->base,n) || r->base<base || r->base+n>top || r->base+n>base+size) return 0;
    uint64_t starts[]={lo,rd,dt,ba}, sizes[]={hi-lo,rn,dn,736};
    for (uint32_t i=0;i<4;++i) if (overlap(r->base,n,starts[i],sizes[i])) return 0;
    return 1;
}
