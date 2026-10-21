/*
 * S21R10 Payload Validator
 * Validates payload.bin format matches shim's loader expectations.
 * Compile: aarch64-linux-gnu-gcc -o validate_payload validate_payload.c
 * Run: ./validate_payload payload.bin
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PAYLOAD_MAGIC "S21R10  "
#define PAYLOAD_HDR_FMT_SIZE 0x2a8  // 680 bytes
#define PAGE_SIZE 4096

struct payload_hdr {
    char magic[8];
    uint32_t version;
    uint32_t nsegs;
    uint64_t virt_base;
    uint64_t entry_va;
    uint64_t dtb_off;
    uint64_t dtb_size;
    uint64_t kernel_end;
    uint64_t phys_base;
    uint64_t mem_size;
    char cmdline[608];
};

struct payload_seg {
    uint64_t vmaddr;
    uint64_t vmsize;
    uint64_t file_off;
    uint64_t file_size;
};

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <payload.bin>\n", argv[0]);
        return 1;
    }

    FILE *f = fopen(argv[1], "rb");
    if (!f) {
        perror("fopen");
        return 1;
    }

    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);

    void *buf = malloc(fsize);
    if (!buf) {
        perror("malloc");
        return 1;
    }

    if (fread(buf, 1, fsize, f) != fsize) {
        perror("fread");
        return 1;
    }
    fclose(f);

    printf("=== S21R10 Payload Validation ===\n");
    printf("File size: %ld bytes (%.1f KB)\n", fsize, fsize / 1024.0);

    struct payload_hdr *hdr = (struct payload_hdr *)buf;
    
    // Check magic
    if (memcmp(hdr->magic, "S21R10  ", 8) != 0) {
        printf("FAIL: Invalid magic: %.8s\n", hdr->magic);
        return 1;
    }
    printf("PASS: Magic = '%.8s'\n", hdr->magic);

    printf("Version: %u\n", hdr->version);
    printf("Segments: %u\n", hdr->nsegs);
    printf("Virt base:  0x%016lx\n", hdr->virt_base);
    printf("Entry VA:   0x%016lx\n", hdr->entry_va);
    printf("DTB off:    0x%lx (%zu bytes)\n", hdr->dtb_off, hdr->dtb_size);
    printf("Kernel end: 0x%lx\n", hdr->kernel_end);
    printf("Phys base:  0x%lx\n", hdr->phys_base);
    printf("Mem size:   0x%lx (%zu MB)\n", hdr->mem_size, hdr->mem_size / (1024*1024));
    printf("Cmdline:    %.60s%s\n", hdr->cmdline, strlen(hdr->cmdline) > 60 ? "..." : "");

    if (hdr->version != 1) {
        printf("WARN: Unexpected version %u\n", hdr->version);
    }

    if (hdr->nsegs == 0) {
        printf("FAIL: No segments\n");
        return 1;
    }

    // Check segments
    struct payload_seg *segs = (struct payload_seg *)((char *)buf + sizeof(struct payload_hdr));
    for (uint32_t i = 0; i < hdr->nsegs; i++) {
        printf("\nSegment %u:\n", i);
        printf("  vmaddr:   0x%lx\n", segs[i].vmaddr);
        printf("  vmsize:   0x%lx\n", segs[i].vmsize);
        printf("  file_off: 0x%lx\n", segs[i].file_off);
        printf("  file_size:0x%lx\n", segs[i].file_size);

        if (segs[i].file_off + segs[i].file_size > fsize) {
            printf("FAIL: Segment extends past file end\n");
            return 1;
        }
    }

    // Check DTB at dtb_off
    if (hdr->dtb_off + hdr->dtb_size > fsize) {
        printf("FAIL: DTB extends past file end\n");
        return 1;
    }

    uint32_t *dtb_magic = (uint32_t *)((char *)buf + hdr->dtb_off);
    if (*dtb_magic == 0xedfe0dd0) {  // byte-swapped DTB magic
        printf("PASS: DTB magic valid at offset 0x%lx\n", hdr->dtb_off);
    } else {
        printf("FAIL: DTB magic invalid (0x%08x)\n", *dtb_magic);
        return 1;
    }

    printf("\n=== ALL CHECKS PASSED ===\n");
    return 0;
}