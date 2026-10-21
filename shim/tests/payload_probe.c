/* Native consumer of the wire ABI. Deliberately unaligned input. */
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include "../payload.h"
int main(int argc,char **argv)
{
    if (argc!=2 && argc!=3) return 2;
    FILE *f=fopen(argv[1],"rb"); if (!f) return 2;
    if (fseek(f,0,SEEK_END)) return 2;
    long n=ftell(f); if (n<0 || n>PAYLOAD_MAX_SIZE) return 2;
    rewind(f);
    unsigned char *buffer=malloc((size_t)n+1); if (!buffer) return 2;
    unsigned char *data=buffer+1;
    if (fread(data,1,(size_t)n,f)!=(size_t)n) return 2;
    fclose(f);
    struct payload_plan plan;
    uint64_t source=argc==3?strtoull(argv[2],NULL,0):UINT64_C(0x47000000);
    int rc=payload_validate(data,(size_t)n,source,&plan);
    if (!rc) {
        printf("{\"base\":\"0x%" PRIx64 "\",\"entry\":\"0x%" PRIx64
               "\",\"kernel_end\":\"0x%" PRIx64 "\",\"memory_size\":%" PRIu64
               ",\"segments\":%u}\n",plan.base,plan.entry,plan.kernel_end,plan.memory_size,plan.count);
    } else if (plan.count || plan.base || plan.entry) abort();
    free(buffer); return rc?1:0;
}
