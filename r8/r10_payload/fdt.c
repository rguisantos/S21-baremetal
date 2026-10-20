/* DTSpec v17-compatible header, reservations and structure walk.
 * This is a deliberate subset, not a replacement for libfdt/bus translation.
 * Standard resources must be at the root. Unsupported memory descriptions
 * never become permission to write RAM or touch a device. */
#include "fdt.h"
#define MAX_DEPTH 32
#define BEGIN_NODE 1U
#define END_NODE 2U
#define PROP 3U
#define NOP 4U
#define END 9U
struct value { const uint8_t *p; uint32_t n; };
struct node {
    const char *name;
    uint32_t ac, sc, parent_ac, parent_sc, irq_parent, phandle, regions;
    uint32_t seen, children, disabled, reserved, cpus, chosen;
    uint32_t irq_cells, irq_controller;
    struct value reg, compatible, type, ranges, dynamic_size, interrupts;
    uint64_t stride, init_start, init_end;
    uint32_t init_seen, frequency;
};
static struct node stack[MAX_DEPTH];
static void clear(void *p, size_t n) { uint8_t *b = p; while (n--) *b++ = 0; }
static uint32_t be32(const uint8_t *p)
{ return (uint32_t)p[0]<<24 | (uint32_t)p[1]<<16 | (uint32_t)p[2]<<8 | p[3]; }
static uint64_t be64(const uint8_t *p)
{ return (uint64_t)be32(p)<<32 | be32(p+4); }
static int eq(const char *a, const char *b)
{ while (*a && *a == *b) { ++a; ++b; } return *a == *b; }
static int string(struct value v, const char *s)
{
    uint32_t n=0; while (s[n]) ++n;
    return v.n==n+1 && !v.p[n] && eq((const char *)v.p,s);
}
static int list_valid(struct value v)
{
    if (!v.n || v.p[v.n-1]) return 0;
    for (uint32_t n=0; n<v.n;) {
        uint32_t start=n;
        while (n<v.n && v.p[n]) ++n;
        if (start==n) return 0;
        ++n;
    }
    return 1;
}
static int compatible(struct value v, const char *s)
{
    for (uint32_t n=0; n<v.n;) {
        if (eq((const char *)v.p+n,s)) return 1;
        while (v.p[n]) ++n;
        ++n;
    }
    return 0;
}
static int span(uint64_t start, uint64_t size)
{ return size && start <= UINT64_MAX-size; }
static int overlap(uint64_t a, uint64_t n, uint64_t b, uint64_t m)
{ return n && m && a < b+m && b < a+n; }
static int add_range(struct r10_range *r, uint32_t *count, uint32_t cap,
                     uint64_t base, uint64_t size, int ram)
{
    if (!span(base,size)) return R10_FDT_INVALID;
    if (*count == cap) return R10_FDT_LIMIT;
    if (ram) for (uint32_t i=0;i<*count;++i)
        if (overlap(base,size,r[i].base,r[i].size)) return R10_FDT_INVALID;
    r[*count]=(struct r10_range){base,size}; ++*count;
    return 0;
}
static int cells(const uint8_t *p, uint32_t n, uint64_t *out)
{
    if (!n || n>2) return R10_FDT_UNSUPPORTED;
    *out=n==2?be64(p):be32(p); return 0;
}
static int tuples(struct node *n, struct r10_range *r, uint32_t *count,
                  uint32_t cap, int ram)
{
    uint32_t ac=n->parent_ac, sc=n->parent_sc;
    if (!ac || ac>2 || !sc || sc>2) return R10_FDT_UNSUPPORTED;
    uint32_t width=(ac+sc)*4;
    if (!n->reg.n || n->reg.n%width) return R10_FDT_INVALID;
    for (uint32_t i=0;i<n->reg.n;i+=width) {
        uint64_t base,size;
        cells(n->reg.p+i,ac,&base); cells(n->reg.p+i+ac*4,sc,&size);
        int rc=add_range(r,count,cap,base,size,ram); if (rc) return rc;
    }
    return 0;
}
static int finish(struct node *n, uint32_t depth, struct r10_platform *p)
{
    if (n->disabled) return 0;
    int rc;
    if (string(n->type,"memory")) {
        if (depth!=1) return R10_FDT_UNSUPPORTED;
        return tuples(n,p->ram,&p->ram_count,R10_FDT_MAX_RAM,1);
    }
    if (string(n->type,"cpu")) {
        if (depth!=2 || !stack[1].cpus || n->parent_sc ||
            !n->parent_ac || n->parent_ac>2 || n->reg.n!=4*n->parent_ac)
            return R10_FDT_UNSUPPORTED;
        uint64_t cpu; cells(n->reg.p,n->parent_ac,&cpu);
        if (cpu & ~UINT64_C(0xff00ffffff)) return R10_FDT_INVALID;
        for (uint32_t i=0;i<p->cpu_count;++i) if (p->cpus[i]==cpu) return R10_FDT_INVALID;
        if (p->cpu_count==R10_FDT_MAX_CPUS) return R10_FDT_LIMIT;
        p->cpus[p->cpu_count++]=cpu;
    }
    if (n->reserved && depth>1) {
        if (n->reg.p) {
            rc=tuples(n,p->reserved,&p->reserved_count,R10_FDT_MAX_RESERVED,0);
            if (rc) return rc;
            /* Nested Samsung groupings are not a generic bus binding. Keep
             * their extents for inspection, but do not certify free memory. */
            if (depth>2) p->unresolved_reserved=1;
        } else if (n->dynamic_size.p) p->unresolved_reserved=1;
    }
    if (n->reserved && depth==1 && (!n->ranges.p || n->ranges.n))
        return R10_FDT_UNSUPPORTED;
    if (compatible(n->compatible,"arm,gic-v3")) {
        if (depth!=1 || n->regions!=1 || n->irq_cells!=3 ||
            !n->irq_controller || p->have_gic) return R10_FDT_UNSUPPORTED;
        struct r10_range regs[8]; uint32_t count=0;
        rc=tuples(n,regs,&count,8,0); if (rc) return rc;
        if (count<2 || !n->phandle) return R10_FDT_INVALID;
        if ((regs[0].base & 0xffff) || regs[0].size<0x10000 ||
            (regs[1].base & 0xffff) || regs[1].size<0x20000 ||
            (n->stride && (n->stride<0x20000 || (n->stride & 0xffff))))
            return R10_FDT_INVALID;
        p->gic_dist=regs[0]; p->gic_redist=regs[1]; p->redist_stride=n->stride;
        p->gic_phandle=n->phandle; p->have_gic=1;
    }
    if (compatible(n->compatible,"arm,armv8-timer")) {
        if (depth!=1 || p->have_timer || n->interrupts.n<24 || n->interrupts.n%12)
            return R10_FDT_UNSUPPORTED;
        /* Binding order: secure physical, non-secure physical, virtual, hyp. */
        const uint8_t *irq=n->interrupts.p+12;
        uint32_t trigger=be32(irq+8)&15U;
        if (be32(irq)!=1 || be32(irq+4)>=16 || (trigger!=4 && trigger!=8))
            return R10_FDT_UNSUPPORTED;
        p->timer_irq=16+be32(irq+4); p->timer_parent=n->irq_parent;
        p->timer_frequency=n->frequency; p->have_timer=1;
    }
    if (n->chosen && n->init_seen) {
        if (n->init_seen!=3 || n->init_end<=n->init_start) return R10_FDT_INVALID;
        p->initrd=(struct r10_range){n->init_start,n->init_end-n->init_start};
    }
    return 0;
}
static int property(struct node *n,const char *key,struct value v)
{
    /* Duplicate fields affecting interpretation are rejected. Unrelated
     * device properties are skipped without attempting their bindings. */
    const char *keys[]={"#address-cells","#size-cells","reg","compatible",
        "device_type","status","ranges","size","interrupts","interrupt-parent",
        "redistributor-stride","#redistributor-regions","clock-frequency",
        "linux,initrd-start","linux,initrd-end","phandle","linux,phandle",
        "#interrupt-cells","interrupt-controller"};
    uint32_t id=19;
    for (uint32_t i=0;i<19;++i) if (eq(key,keys[i])) { id=i; break; }
    if (id==19) return 0;
    if (n->seen & (1U<<id)) return R10_FDT_INVALID;
    n->seen|=1U<<id;
    switch(id) {
    case 0: case 1: case 9: case 11: case 12: case 15: case 16: case 17:
        if (v.n!=4) return R10_FDT_INVALID;
        break;
    default: break;
    }
    switch(id) {
    case 0: n->ac=be32(v.p); if (n->ac>4) return R10_FDT_UNSUPPORTED; break;
    case 1: n->sc=be32(v.p); if (n->sc>4) return R10_FDT_UNSUPPORTED; break;
    case 2: n->reg=v; break;
    case 3: if (!list_valid(v)) return R10_FDT_INVALID; n->compatible=v; break;
    case 4: if (!v.n || v.p[v.n-1]) return R10_FDT_INVALID; n->type=v; break;
    case 5:
        if (!v.n || v.p[v.n-1]) return R10_FDT_INVALID;
        if (!string(v,"okay") && !string(v,"ok")) n->disabled=1;
        break;
    case 6: n->ranges=v; break;
    case 7: n->dynamic_size=v; break;
    case 8: n->interrupts=v; break;
    case 9: n->irq_parent=be32(v.p); break;
    case 10: if (v.n!=8) return R10_FDT_INVALID; n->stride=be64(v.p); break;
    case 11: n->regions=be32(v.p); break;
    case 12: n->frequency=be32(v.p); break;
    case 13: case 14: {
        uint64_t value; int rc=cells(v.p,v.n/4,&value);
        if (v.n%4 || rc) return R10_FDT_INVALID;
        if (id==13) { n->init_start=value; n->init_seen|=1; }
        else { n->init_end=value; n->init_seen|=2; }
        break;
    }
    case 17: n->irq_cells=be32(v.p); break;
    case 18: if (v.n) return R10_FDT_INVALID; n->irq_controller=1; break;
    case 15: case 16: {
        uint32_t handle=be32(v.p);
        if (!handle || handle==UINT32_MAX || (n->phandle && n->phandle!=handle))
            return R10_FDT_INVALID;
        n->phandle=handle; break;
    }
    }
    return 0;
}
int r10_fdt_parse(const void *blob,size_t available,struct r10_platform *out)
{
    if (!out) return R10_FDT_INVALID;
    clear(out,sizeof(*out));
    if (!blob || available<40) return R10_FDT_INVALID;
    const uint8_t *b=blob;
    if (be32(b)!=0xd00dfeed) return R10_FDT_INVALID;
    uint32_t total=be32(b+4), so=be32(b+8), ss=be32(b+12), ro=be32(b+16);
    uint32_t ver=be32(b+20), last=be32(b+24), sn=be32(b+32), stn=be32(b+36);
    if (ver<17 || last>17 || last>ver) return R10_FDT_UNSUPPORTED;
    if (total<40 || total>available || total>R10_FDT_MAX_SIZE ||
        so<40 || (so&3) || so>total || stn>total-so || (stn&3) ||
        ss<40 || ss>total || sn>total-ss ||
        ro<40 || (ro&7) || ro>total ||
        overlap(so,stn,ss,sn)) return R10_FDT_INVALID;
    /* The reservation list ends at a zero pair, before either other block. */
    uint32_t stop=total;
    if (so>=ro && so<stop) stop=so;
    if (ss>=ro && ss<stop) stop=ss;
    uint32_t rp=ro; int terminated=0;
    while (rp<=stop && stop-rp>=16) {
        uint64_t addr=be64(b+rp), size=be64(b+rp+8); rp+=16;
        if (!addr && !size) { terminated=1; break; }
        int rc=add_range(out->reserved,&out->reserved_count,R10_FDT_MAX_RESERVED,addr,size,0);
        if (rc) return rc;
    }
    if (!terminated || overlap(ro,rp-ro,so,stn) || overlap(ro,rp-ro,ss,sn))
        return R10_FDT_INVALID;
    out->blob_size=total;
    uint32_t pos=so,end=so+stn,depth=0,root_seen=0,root_closed=0;
    while (pos<end) {
        uint32_t token=be32(b+pos); pos+=4;
        if (token==BEGIN_NODE) {
            if (root_closed) return R10_FDT_INVALID;
            if (depth==MAX_DEPTH) return R10_FDT_LIMIT;
            uint32_t name=pos;
            while (pos<end && b[pos]) { if (b[pos]=='/') return R10_FDT_INVALID; ++pos; }
            if (pos==end || (depth && pos==name) || (!depth && pos!=name)) return R10_FDT_INVALID;
            if (!depth && root_seen++) return R10_FDT_INVALID;
            pos=(pos+4)&~3U; if (pos>end) return R10_FDT_INVALID;
            struct node *n=&stack[depth]; clear(n,sizeof(*n));
            n->name=(const char *)b+name; n->ac=2; n->sc=1; n->regions=1;
            if (depth) {
                struct node *parent=&stack[depth-1]; parent->children=1;
                n->parent_ac=parent->ac; n->parent_sc=parent->sc;
                n->irq_parent=parent->irq_parent; n->disabled=parent->disabled;
                n->reserved=parent->reserved;
            }
            if (depth==1) {
                n->reserved=eq(n->name,"reserved-memory");
                n->cpus=eq(n->name,"cpus"); n->chosen=eq(n->name,"chosen");
            }
            ++depth;
        } else if (token==PROP) {
            if (!depth || end-pos<8) return R10_FDT_INVALID;
            uint32_t len=be32(b+pos), no=be32(b+pos+4); pos+=8;
            if (len>end-pos || no>=sn || stack[depth-1].children) return R10_FDT_INVALID;
            uint32_t ne=no; while (ne<sn && b[ss+ne]) ++ne;
            if (ne==sn || no==ne) return R10_FDT_INVALID;
            int rc=property(&stack[depth-1],(const char *)b+ss+no,(struct value){b+pos,len});
            if (rc) return rc;
            pos+=(len+3)&~3U; if (pos>end) return R10_FDT_INVALID;
        } else if (token==END_NODE) {
            if (!depth) return R10_FDT_INVALID;
            --depth; int rc=finish(&stack[depth],depth,out); if (rc) return rc;
            if (!depth) root_closed=1;
        } else if (token==END) {
            return !depth && root_seen && root_closed && pos==end ? 0 : R10_FDT_INVALID;
        } else if (token!=NOP) return R10_FDT_INVALID;
    }
    return R10_FDT_INVALID;
}
int r10_fdt_range_usable(const struct r10_platform *p,uint64_t start,uint64_t size)
{
    if (!span(start,size)) return R10_FDT_INVALID;
    if (!p->ram_count) return R10_FDT_NO_RAM;
    if (p->unresolved_reserved) return R10_FDT_INCOMPLETE;
    int contained=0;
    for (uint32_t i=0;i<p->ram_count;++i)
        if (start>=p->ram[i].base && start+size<=p->ram[i].base+p->ram[i].size) contained=1;
    if (!contained) return R10_FDT_CONFLICT;
    for (uint32_t i=0;i<p->reserved_count;++i)
        if (overlap(start,size,p->reserved[i].base,p->reserved[i].size)) return R10_FDT_CONFLICT;
    if (overlap(start,size,p->initrd.base,p->initrd.size)) return R10_FDT_CONFLICT;
    return 0;
}
int r10_fdt_check_boot(const struct r10_platform *p,uint64_t address,
                       uint64_t start,uint64_t end,uint64_t mpidr)
{
    if (end<=start || !span(address,p->blob_size)) return R10_FDT_INVALID;
    int rc=r10_fdt_range_usable(p,start,end-start); if (rc) return rc;
    if (overlap(start,end-start,address,p->blob_size)) return R10_FDT_CONFLICT;
    if (!p->have_gic || !p->have_timer || p->timer_irq!=30 ||
        p->timer_parent!=p->gic_phandle) return R10_FDT_RESOURCES;
    if (overlap(p->gic_dist.base,p->gic_dist.size,p->gic_redist.base,p->gic_redist.size) ||
        overlap(p->gic_dist.base,p->gic_dist.size,address,p->blob_size) ||
        overlap(p->gic_redist.base,p->gic_redist.size,address,p->blob_size)) return R10_FDT_CONFLICT;
    for (uint32_t i=0;i<p->ram_count;++i)
        if (overlap(p->gic_dist.base,p->gic_dist.size,p->ram[i].base,p->ram[i].size) ||
            overlap(p->gic_redist.base,p->gic_redist.size,p->ram[i].base,p->ram[i].size))
            return R10_FDT_CONFLICT;
    uint64_t affinity=mpidr & UINT64_C(0xff00ffffff);
    for (uint32_t i=0;i<p->cpu_count;++i) if (p->cpus[i]==affinity) return 0;
    return R10_FDT_RESOURCES;
}
const char *r10_fdt_error(int rc)
{
    switch(rc) {
    case 0: return "ok";
    case R10_FDT_INVALID: return "invalid/truncated FDT or range";
    case R10_FDT_LIMIT: return "FDT capacity exceeded";
    case R10_FDT_UNSUPPORTED: return "unsupported FDT binding/layout";
    case R10_FDT_NO_RAM: return "FDT has no usable RAM description";
    case R10_FDT_INCOMPLETE: return "unresolved reserved-memory layout";
    case R10_FDT_CONFLICT: return "payload overlaps reserved/live data or is outside RAM";
    case R10_FDT_RESOURCES: return "boot CPU, GIC or timer contract missing";
    default: return "unknown FDT error";
    }
}
