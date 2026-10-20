/* Native inspector for the production, allocation-free parser. */
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include "../r10_payload/fdt.h"
int main(int argc,char **argv)
{
    if (argc!=2 && argc!=6) return 2;
    FILE *file=fopen(argv[1],"rb"); if (!file) return 2;
    if (fseek(file,0,SEEK_END)) return 2;
    long size=ftell(file); if (size<0 || size>R10_FDT_MAX_SIZE) return 2;
    rewind(file);
    unsigned char *data=malloc((size_t)size+1); if (!data) return 2;
    if (fread(data,1,(size_t)size,file)!=(size_t)size) return 2;
    fclose(file);
    struct r10_platform p;
    int rc=r10_fdt_parse(data,(size_t)size,&p);
    printf("{\"parse\":%d,\"message\":\"%s\"",rc,r10_fdt_error(rc));
    if (!rc) {
        uint64_t start=argc==6?strtoull(argv[2],0,0):UINT64_C(0x80080000);
        uint64_t end=argc==6?strtoull(argv[3],0,0):UINT64_C(0x800c0000);
        uint64_t fdt=argc==6?strtoull(argv[4],0,0):UINT64_C(0x81f00000);
        uint64_t cpu=argc==6?strtoull(argv[5],0,0):0;
        printf(",\"boot\":%d,\"ram\":[",r10_fdt_check_boot(&p,fdt,start,end,cpu));
        for (uint32_t i=0;i<p.ram_count;++i)
            printf("%s[\"0x%" PRIx64 "\",\"0x%" PRIx64 "\"]",i?",":"",p.ram[i].base,p.ram[i].size);
        printf("],\"reserved_count\":%u,\"unresolved_reserved\":%u,\"cpus\":[",p.reserved_count,p.unresolved_reserved);
        for (uint32_t i=0;i<p.cpu_count;++i) printf("%s\"0x%" PRIx64 "\"",i?",":"",p.cpus[i]);
        printf("],\"gic_dist\":\"0x%" PRIx64 "\",\"gic_redist\":\"0x%" PRIx64 "\",\"redist_size\":\"0x%" PRIx64 "\",\"timer_irq\":%u}",
            p.gic_dist.base,p.gic_redist.base,p.gic_redist.size,p.timer_irq);
    } else printf("}");
    putchar('\n'); free(data);
    return 0;
}
