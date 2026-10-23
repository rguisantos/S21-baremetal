/* Included only in the pinned, rebuilt QEMU loader, after its print/EFI helpers. */
#ifndef S21_MEMORY_TEST
#define S21_MEMORY_TEST 0
#endif
#if S21_MEMORY_TEST < 0 || S21_MEMORY_TEST > 3
#error Unsupported laboratory fault
#endif
_Static_assert(sizeof(efi_memory_descriptor)==40, "UEFI descriptor ABI");
_Static_assert(offsetof(efi_memory_descriptor,phys_start)==8 &&
               offsetof(efi_memory_descriptor,pages)==24 &&
               offsetof(efi_memory_descriptor,attribute)==32, "UEFI descriptor offsets");
struct s21_snapshot {
    uint8_t bytes[S21_MAP_CAPACITY];
    uint64_t size, stride, key, status;
    uint32_t version, captured;
};
static struct s21_snapshot s21_maps[4];
static uint64_t s21_payload_status=UINT64_MAX, s21_payload_claim;
static uint64_t s21_window_status=UINT64_MAX, s21_window_claim;
#ifndef S21_VIDEO_TEST
#define S21_VIDEO_TEST 0
#endif
static uint64_t s21_frame_base, s21_frame_size;
static void s21_video_bind(uint64_t base, uint64_t bytes)
{
    s21_frame_base=base; s21_frame_size=(bytes+4095)&~UINT64_C(4095);
}
static int s21_video_boot(const struct boot_video *v)
{
    if (!s21_frame_base)
        return v->v_baseAddr==0 && v->v_display==0 && v->v_rowBytes==0 &&
               v->v_width==0 && v->v_height==0 && v->v_depth==0;
    uint64_t size;
    if (!s21_video_geometry(v->v_baseAddr,v->v_display,v->v_rowBytes,v->v_width,
                            v->v_height,v->v_depth,&size) ||
        v->v_baseAddr!=s21_frame_base || size!=s21_frame_size) {
        print("S21 VIDEO: REJECT boot arguments\n"); return 0;
    }
    print("S21 VIDEO: boot arguments PASS\n");
    return 1;
}


static struct s21_memory_map
s21_map_view(unsigned stage)
{
    const struct s21_snapshot *s=&s21_maps[stage];
    return (struct s21_memory_map){s->bytes,s->size,s->stride,s->version};
}
static int
s21_snapshot(unsigned stage)
{
    struct s21_snapshot *s=&s21_maps[stage];
    s->size=sizeof(s->bytes);
    s->status=BS->get_memory_map(&s->size,s->bytes,&s->key,&s->stride,&s->version);
    struct s21_memory_map m=s21_map_view(stage);
    if (s->status!=0 || !s21_memory_valid(&m)) {
        print("S21 UEFI: REJECT map stage %d status %x size %x stride %x version %x\n",
              (uint64_t)stage,s->status,s->size,s->stride,(uint64_t)s->version);
        return 0;
    }
    s->captured=1;
    return 1;
}
static int
s21_claim_payload(void)
{
#if S21_MEMORY_TEST == 1
    uint64_t busy=PAYLOAD_BASE;
    efi_status status=BS->allocate_pages(AllocateAddress,4,PAYLOAD_MAX_SIZE>>12,&busy);
    print("S21 UEFI TEST: payload-busy status %x\n",status);
    if (status!=0 || busy!=PAYLOAD_BASE) return 0;
#endif
    if (!s21_snapshot(0)) return 0;
    struct s21_memory_map m=s21_map_view(0);
    if (!s21_memory_covers(&m,PAYLOAD_BASE,PAYLOAD_MAX_SIZE,7)) {
        print("S21 UEFI: REJECT payload not free\n");
        return 0;
    }
    s21_payload_claim=PAYLOAD_BASE;
    s21_payload_status=BS->allocate_pages(AllocateAddress,EfiLoaderData,PAYLOAD_MAX_SIZE>>12,&s21_payload_claim);
    if (s21_payload_status!=0 || s21_payload_claim!=PAYLOAD_BASE) {
        print("S21 UEFI: REJECT payload allocation\n");
        return 0;
    }
    return 1;
}
static int
s21_choose_window(void)
{
    if (win_size || !s21_snapshot(1)) return 0;
    struct s21_memory_map m=s21_map_view(1);
    uint64_t base,size;
    if (!s21_memory_covers(&m,PAYLOAD_BASE,PAYLOAD_MAX_SIZE,2) ||
        !s21_memory_largest(&m,MAX_MEM_SIZE,&base,&size) ||
        !s21_memory_covers(&m,base,size,7)) {
        print("S21 UEFI: REJECT window selection\n");
        return 0;
    }
    s21_window_claim=base;
    s21_window_status=BS->allocate_pages(AllocateAddress,EfiLoaderData,size>>12,&s21_window_claim);
    if (s21_window_status!=0 || s21_window_claim!=base) {
        print("S21 UEFI: REJECT window allocation\n");
        return 0;
    }
    win_base=base; win_size=size;
    print("phys window %x size %x, claim status %x\n",base,size,s21_window_status);
    return 1;
}
static int
s21_owned(unsigned stage)
{
#if S21_MEMORY_TEST == 2 || S21_MEMORY_TEST == 3
    if (stage==2) {
        /* Fault injection changes only memory allocated by this lab application,
         * before it copies anything into the window. Never a production path. */
        uint64_t page=S21_MEMORY_TEST==2 ? win_base+0x1000 : PAYLOAD_BASE;
        efi_status status=BS->free_pages(page,1);
        if (S21_MEMORY_TEST==2 && status==0)
            status=BS->allocate_pages(AllocateAddress,4,1,&page);
        print("S21 UEFI TEST: %s status %x\n",S21_MEMORY_TEST==2 ? "window-busy" : "payload-released",status);
        if (status!=0) return 0;
    }
#endif
#if S21_VIDEO_TEST != 0
    if (stage==2 && s21_frame_base) {
#if S21_VIDEO_TEST == 1
        SCREEN.stride++;
#elif S21_VIDEO_TEST == 2
        SCREEN.base=PAYLOAD_BASE;
#elif S21_VIDEO_TEST == 3
        uint64_t page=s21_frame_base;
        efi_status status=BS->free_pages(page,1);
        if (status==0) status=BS->allocate_pages(AllocateAddress,4,1,&page);
        print("S21 VIDEO TEST: page-busy status %x\n",status);
        if (status!=0) return 0;
#endif
    }
#endif
    if (!s21_snapshot(stage)) return 0;
    struct s21_memory_map m=s21_map_view(stage);
    if (SCREEN.base || s21_frame_base) {
        uint64_t size;
        if (!s21_video_geometry(SCREEN.base,1,SCREEN.stride,SCREEN.width,SCREEN.height,32,&size) ||
            SCREEN.base!=s21_frame_base || size!=s21_frame_size ||
            (SCREEN.base<win_base+win_size && win_base<SCREEN.base+size) ||
            (SCREEN.base<PAYLOAD_BASE+PAYLOAD_MAX_SIZE && PAYLOAD_BASE<SCREEN.base+size) ||
            !s21_memory_covers(&m,SCREEN.base,size,2)) {
            print("S21 VIDEO: REJECT framebuffer stage %d\n",(uint64_t)stage); return 0;
        }
    }
    if (!s21_memory_covers(&m,PAYLOAD_BASE,PAYLOAD_MAX_SIZE,2)) {
        print("S21 UEFI: REJECT payload ownership stage %d\n",(uint64_t)stage);
        return 0;
    }
    if (!s21_memory_covers(&m,win_base,win_size,2)) {
        print("S21 UEFI: REJECT window ownership stage %d\n",(uint64_t)stage);
        return 0;
    }
    return 1;
}
static void
s21_memory_dump(void)
{
    /* Emit only after run_kernel returned (or refused). No output/allocation
     * is interposed between the final successful snapshot and cache handling. */
    if (s21_frame_base)
        print("S21 VIDEO ALLOCATION %x %x\n",s21_frame_base,s21_frame_size);
    print("S21 UEFI CLAIM payload %x %x %x %x\n",PAYLOAD_BASE,PAYLOAD_MAX_SIZE,s21_payload_status,s21_payload_claim);
    print("S21 UEFI CLAIM window %x %x %x %x\n",win_base,win_size,s21_window_status,s21_window_claim);
    for (unsigned stage=0;stage<4;++stage) {
        const struct s21_snapshot *s=&s21_maps[stage];
        if (!s->captured) continue;
        print("S21 UEFI MAP %d %x %x %x %x\n",(uint64_t)stage,s->size,s->key,s->stride,(uint64_t)s->version);
        /* All descriptor bytes, including padding/extensions, without filtering. */
        for (uint64_t off=0;off<s->size;off+=s->stride) {
            print("S21 UEFI DESC %d %x ",(uint64_t)stage,off/s->stride);
            for (uint64_t i=0;i<s->stride;++i) {
                put_char("0123456789abcdef"[s->bytes[off+i]>>4]);
                put_char("0123456789abcdef"[s->bytes[off+i]&15]);
            }
            put_char('\n');
        }
        print("S21 UEFI END %d\n",(uint64_t)stage);
    }
}
