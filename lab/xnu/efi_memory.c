#include "efi_memory.h"

static uint32_t le32(const uint8_t *p)
{ return p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
static uint64_t le64(const uint8_t *p)
{ return le32(p) | (uint64_t)le32(p+4)<<32; }
static int bounds(uint64_t base, uint64_t size)
{ return size && size <= UINT64_MAX-base; }
static int metadata(const struct s21_memory_map *m)
{
    return m && m->data && m->version==1 && m->stride>=40 && m->stride<=256 &&
        m->stride%8==0 && m->size && m->size<=S21_MAP_CAPACITY &&
        m->size%m->stride==0 && m->size/m->stride<=S21_MAP_MAX_DESCRIPTORS;
}
int s21_memory_region(const struct s21_memory_map *m, uint64_t index, struct s21_memory_region *r)
{
    if (!metadata(m) || !r || index>=m->size/m->stride) return 0;
    const uint8_t *p=m->data+index*m->stride;
    uint64_t pages=le64(p+24), base=le64(p+8);
    if (!pages || pages>UINT64_MAX/S21_MEMORY_PAGE || base%S21_MEMORY_PAGE ||
        !bounds(base,pages*S21_MEMORY_PAGE) || le32(p)>15) return 0;
    *r=(struct s21_memory_region){base,pages*S21_MEMORY_PAGE,le64(p+32),le32(p)};
    return 1;
}
int s21_memory_valid(const struct s21_memory_map *m)
{
    if (!metadata(m)) return 0;
    for (uint64_t i=0;i<m->size/m->stride;++i) {
        struct s21_memory_region a;
        if (!s21_memory_region(m,i,&a)) return 0;
        for (uint64_t j=0;j<i;++j) {
            struct s21_memory_region b;
            if (!s21_memory_region(m,j,&b)) return 0;
            if (a.base<b.base+b.size && b.base<a.base+a.size) return 0;
        }
    }
    return 1;
}
static int usable(const struct s21_memory_region *r, uint32_t type)
{
    /* Conservative lab policy: WB capability, no runtime/WP/RP/RO flags.
     * Descriptor attributes do not prove the current CPU page permissions. */
    const uint64_t forbidden=UINT64_C(0x8000000000023000);
    return r->type==type && (r->attribute&8) && !(r->attribute&forbidden);
}
int s21_memory_covers(const struct s21_memory_map *m, uint64_t base, uint64_t size, uint32_t type)
{
    if (!metadata(m) || !bounds(base,size) || (type!=2 && type!=7)) return 0;
    uint64_t cursor=base, end=base+size;
    /* No ordering assumption: adjacent compatible descriptors may be merged. */
    for (uint64_t step=0;cursor<end && step<m->size/m->stride;++step) {
        int found=0;
        for (uint64_t i=0;i<m->size/m->stride;++i) {
            struct s21_memory_region r;
            if (!s21_memory_region(m,i,&r)) return 0;
            if (r.base<=cursor && cursor<r.base+r.size) {
                if (!usable(&r,type)) return 0;
                cursor=r.base+r.size;
                found=1;
                break;
            }
        }
        if (!found) return 0;
    }
    return cursor>=end;
}
int s21_memory_largest(const struct s21_memory_map *m, uint64_t limit, uint64_t *base, uint64_t *size)
{
    if (!metadata(m) || !base || !size || !limit || limit%S21_MEMORY_ALIGNMENT) return 0;
    uint64_t best_base=0, best_size=0;
    for (uint64_t i=0;i<m->size/m->stride;++i) {
        struct s21_memory_region r;
        if (!s21_memory_region(m,i,&r)) return 0;
        if (!usable(&r,7) || r.base>UINT64_MAX-(S21_MEMORY_ALIGNMENT-1)) continue;
        uint64_t lo=(r.base+S21_MEMORY_ALIGNMENT-1)&~(S21_MEMORY_ALIGNMENT-1);
        uint64_t hi=(r.base+r.size)&~(S21_MEMORY_ALIGNMENT-1);
        uint64_t n=hi>lo ? hi-lo : 0;
        if (n>limit) n=limit;
        if (n>best_size || (n && n==best_size && lo<best_base)) { best_base=lo; best_size=n; }
    }
    if (!best_size) return 0;
    *base=best_base; *size=best_size; return 1;
}
