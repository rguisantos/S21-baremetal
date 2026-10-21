/* Freestanding compiler support; strict alignment selected by build.sh. */
#include <stddef.h>
void *memcpy(void *destination,const void *source,size_t size)
{
    unsigned char *d=destination; const unsigned char *s=source;
    while (size--) *d++=*s++;
    return destination;
}
void *memset(void *destination,int value,size_t size)
{
    unsigned char *d=destination;
    while (size--) *d++=(unsigned char)value;
    return destination;
}
