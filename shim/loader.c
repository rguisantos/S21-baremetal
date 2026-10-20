/*
 * S21 Ultra R10 payload loader.
 *
 * Finds payload in /chosen initrd, validates, copies segments to phys_base,
 * places DTB and boot args behind kernel, jumps to entry with x0 = boot_args_pa.
 */
#include <stdint.h>
#include "console.h"
#include "fdt.h"
#include "loader.h"

#define BOOT_LINE_LENGTH	608
#define PAGE_4K		0x1000UL

struct payload_seg {
	uint64_t vmaddr, vmsize, file_off, file_size;
};

struct payload {
	char magic[8];
	uint32_t version, nsegs;
	uint64_t virt_base, entry_va, dtb_off, dtb_size, kernel_end;
	uint64_t phys_base, mem_size;
	char cmdline[608];
	struct payload_seg segs[];
};

struct boot_video {
	uint64_t v_baseAddr, v_display, v_rowBytes, v_width, v_height, v_depth;
};

struct boot_args {
	uint16_t Revision, Version;
	uint64_t virtBase, physBase, memSize, topOfKernelData;
	struct boot_video Video;
	uint32_t machineType;
	uint64_t deviceTreeP;
	uint32_t deviceTreeLength;
	char CommandLine[608];
	uint64_t bootFlags, memSizeActual;
};

static void copy64(uintptr_t dst, uintptr_t src, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	volatile const uint64_t *s = (volatile const uint64_t *)src;
	for (uint64_t i = 0; i < (n + 7) / 8; i++)
		d[i] = s[i];
}

static void zero64(uintptr_t dst, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	for (uint64_t i = 0; i < n / 8; i++)
		d[i] = 0;
}

static int magic_ok(const char *m)
{
	static const char want[] = "S21R10  ";
	for (int i = 0; i < 8; i++)
		if (m[i] != want[i]) return 0;
	return 1;
}

typedef void (*entry_t)(uint64_t boot_args_pa);

const char *loader_boot(uintptr_t dtb)
{
	uint64_t rd_start, rd_end;

	if (!fdt_chosen_u64(dtb, "linux,initrd-start", &rd_start) ||
	    !fdt_chosen_u64(dtb, "linux,initrd-end", &rd_end))
		return "no initrd in /chosen";
	con_hex2("INITRD", "lo=", rd_start, "hi=", rd_end);

	const struct payload *p = (const struct payload *)rd_start;
	if (!magic_ok(p->magic))
		return "no S21R10 payload";
	if (p->version != 1 || (p->dtb_off & 7) || (rd_start & 7))
		return "bad payload header";

	uint64_t pa_of_va_base = p->phys_base - p->virt_base;
	con_hex2("PHYS", "base=", p->phys_base, "size=", p->mem_size);
	con_hex("VIRT", p->virt_base);
	con_hex("ENTRY", p->entry_va);

	if (rd_start + (rd_end - rd_start) > p->phys_base &&
	    rd_start < p->phys_base + p->mem_size)
		return "ramdisk overlaps kernel memory";

	for (uint32_t i = 0; i < p->nsegs; i++) {
		const struct payload_seg *s = &p->segs[i];
		uintptr_t dst = s->vmaddr + (p->phys_base - p->virt_base);
		copy64(dst, rd_start + s->file_off, s->file_size);
		if (s->vmsize > s->file_size)
			zero64(dst + ((s->file_size + 7) & ~7UL), s->vmsize - ((s->file_size + 7) & ~7UL));
	}

	uintptr_t adt_pa = p->kernel_end + (p->phys_base - p->virt_base);
	copy64(adt_pa, rd_start + p->dtb_off, p->dtb_size);
	uintptr_t ba_pa = (adt_pa + p->dtb_size + 4095) & ~4095;
	uintptr_t top = ba_pa + 4096;

	zero64(ba_pa, 4096);
	volatile struct boot_args *ba = (volatile struct boot_args *)ba_pa;
	ba->Revision = 2;
	ba->Version = 2;
	ba->virtBase = p->virt_base;
	ba->physBase = p->phys_base;
	ba->memSize = p->mem_size;
	ba->topOfKernelData = p->kernel_end + (p->phys_base - p->virt_base) + p->dtb_size + 4096;
	ba->Video.v_baseAddr = 0x8f000000;	/* from DTB */
	ba->Video.v_display = 1;
	ba->Video.v_rowBytes = 1920;
	ba->Video.v_width = 480;
	ba->Video.v_height = 800;
	ba->Video.v_depth = 32;
	ba->deviceTreeP = adt_pa;	/* physical, MMU off when XNU reads it */
	ba->deviceTreeLength = p->dtb_size;
	for (int i = 0; i < 608; i++)
		ba->CommandLine[i] = p->cmdline[i];
	ba->memSizeActual = p->mem_size;

	uintptr_t entry_pa = p->entry_va + (p->phys_base - p->virt_base);
	con_hex("JUMP", entry_pa);
	con_str("PAYLOAD", "jumping");

	__asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
	((void (*)(uint64_t))entry_pa)(ba_pa);
	return "payload returned";
}