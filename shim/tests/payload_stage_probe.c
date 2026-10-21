#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../payload_stage.h"
#define CAPACITY (2U*1024U*1024U)
static unsigned char *read_file(const char *name,size_t *size)
{
    FILE *f=fopen(name,"rb"); if (!f) exit(2);
    if (fseek(f,0,SEEK_END)) exit(2);
    long n=ftell(f); if (n<0 || n>PAYLOAD_MAX_SIZE) exit(2);
    rewind(f); unsigned char *p=malloc((size_t)n+1); if (!p) exit(2);
    if (fread(p,1,(size_t)n,f)!=(size_t)n) exit(2);
    fclose(f); *size=(size_t)n; return p;
}
int main(int argc,char **argv)
{
    if (argc!=5) return 2;
    size_t size,fw_size;
    unsigned char *data=read_file(argv[1],&size), *fw=read_file(argv[2],&fw_size);
    unsigned char *arena=malloc(CAPACITY+2); if (!arena) return 2;
    memset(arena,0xa5,CAPACITY+2);
    struct r10_range protected={0x45000000,0x1000};
    struct payload_environment e={fw,fw_size,0x46000000,0x47000000,0,
                                   &protected,1,arena+1,CAPACITY};
    switch(atoi(argv[3])) {
    case 1:e.source_address=0x80080000;break;
    case 2:protected.base=0x80081000;break;
    case 3:e.firmware_address=0x80080000;break;
    case 4:e.mpidr=0x200;break;
    case 5:e.destination_size=1;break;
    case 6:e.destination=data;break;
    case 7:e.protected_count=9;break;
    case 8:protected.size=UINT64_MAX;break;
    case 9:e.destination=NULL;break;
    case 11:e.protected_count=0;break;
    default:break;
    }
    unsigned char *prior=malloc(size); if (!prior) return 2;
    memcpy(prior,data,size);
    struct payload_plan plan={0};
    struct payload_plan *result=atoi(argv[3])==10?(void *)(arena+16):&plan;
    int rc=payload_stage(data,size,&e,result);
    if (memcmp(prior,data,size)) abort(); /* Never overwrite input. */
    if (rc) {
        if (plan.count || plan.base) abort();
        for (size_t i=0;i<CAPACITY+2;++i) if (arena[i]!=0xa5) abort();
        printf("REJECT %d\n",rc);
    } else {
        if (arena[0]!=0xa5) abort();
        for (size_t i=1+(size_t)plan.memory_size;i<CAPACITY+2;++i)
            if (arena[i]!=0xa5) abort();
        FILE *f=fopen(argv[4],"wb"); if (!f) return 2;
        if (fwrite(arena+1,1,(size_t)plan.memory_size,f)!=(size_t)plan.memory_size) return 2;
        fclose(f); puts("STAGED");
    }
    free(prior);free(data);free(fw);free(arena);return rc?1:0;
}
