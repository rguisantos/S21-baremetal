/*
 * Minimal FDT parsing for /chosen properties
 * Based on Linux libfdt, simplified for our needs.
 */
#include <stdint.h>
#include <stddef.h>
#include "fdt.h"

#define FDT_MAGIC		0xd00dfeed
#define FDT_BEGIN_NODE		0x1
#define FDT_END_NODE		0x2
#define FDT_PROP		0x3
#define FDT_NOP		0x4
#define FDT_END		0x9

#define fdt32_to_cpu(x)	__builtin_bswap32(x)

/* Minimal string functions for freestanding */
static size_t strlen(const char *s)
{
	size_t len = 0;
	while (s[len]) len++;
	return len;
}

static char *strchr(const char *s, int c)
{
	while (*s) {
		if (*s == c) return (char *)s;
		s++;
	}
	return (*s == c) ? (char *)s : 0;
}

static int strcmp(const char *s1, const char *s2)
{
	while (*s1 && *s1 == *s2) {
		s1++;
		s2++;
	}
	return (unsigned char)*s1 - (unsigned char)*s2;
}

static int strncmp(const char *s1, const char *s2, size_t n)
{
	while (n && *s1 && *s1 == *s2) {
		s1++;
		s2++;
		n--;
	}
	if (!n) return 0;
	return (unsigned char)*s1 - (unsigned char)*s2;
}

int fdt_check_header(uintptr_t dtb)
{
	uint32_t magic = *(uint32_t *)dtb;
	if (fdt32_to_cpu(magic) != FDT_MAGIC)
		return 0;
	return 1;
}

int fdt_check_compat(uintptr_t dtb, const char *compat)
{
	/* Not needed for our use case */
	return 1;
}

static uintptr_t fdt_advance(uintptr_t p, uint32_t sz)
{
	return (p + sz + 3) & ~3;
}

int fdt_path_offset(uintptr_t dtb, const char *path)
{
	if (!fdt_check_header(dtb))
		return -1;
	
	uint32_t off_dt_struct = __builtin_bswap32(*(uint32_t *)(dtb + 0x24));
	uint32_t off_dt_strings = __builtin_bswap32(*(uint32_t *)(dtb + 0x28));
	uint32_t off_mem_rsvmap = __builtin_bswap32(*(uint32_t *)(dtb + 0x20));
	
	uintptr_t p = dtb + off_dt_struct;
	const char *pathp = path;
	
	if (*pathp == '/') pathp++;
	
	while (1) {
		uint32_t token = fdt32_to_cpu(*(uint32_t *)p);
		p += 4;
		
		if (token == FDT_END)
			return -1;
		
		if (token == FDT_NOP)
			continue;
		
		if (token == FDT_END_NODE) {
			/* Go back up */
			continue;
		}
		
		if (token == FDT_BEGIN_NODE) {
			const char *name = (const char *)p;
			p += strlen(name) + 1;
			p = (p + 3) & ~3;
			
			const char *next = strchr(pathp, '/');
			size_t len = next ? next - pathp : strlen(pathp);
			
			if (strncmp(name, pathp, len) == 0 && name[len] == '\0') {
				if (!next) return p - dtb;	/* Found */
				pathp = next + 1;
			}
		}
	}
}

int fdt_getprop_u64(uintptr_t dtb, int offset, const char *name, uint64_t *out)
{
	if (offset < 0) return 0;
	
	uint32_t off_dt_strings = __builtin_bswap32(*(uint32_t *)(dtb + 0x28));
	uintptr_t p = dtb + offset;
	
	while (1) {
		uint32_t token = fdt32_to_cpu(*(uint32_t *)p);
		p += 4;
		
		if (token == FDT_END || token == FDT_END_NODE)
			break;
		
		if (token == FDT_NOP)
			continue;
		
		if (token == FDT_PROP) {
			uint32_t len = fdt32_to_cpu(*(uint32_t *)p);
			p += 4;
			uint32_t nameoff = fdt32_to_cpu(*(uint32_t *)p);
			p += 4;
			
			const char *prop_name = (const char *)(dtb + off_dt_strings + nameoff);
			if (strcmp(prop_name, name) == 0) {
				if (p - dtb + 8 > 1024*1024) return 0;
				if (len == 8) {
					*out = ((uint64_t)__builtin_bswap32(*(uint32_t *)p) << 32) |
					       __builtin_bswap32(*(uint32_t *)(p + 4));
					return 1;
				}
				return 0;
			}
			p = (p + len + 3) & ~3;
		} else if (token == FDT_BEGIN_NODE) {
			const char *name = (const char *)p;
			p += strlen(name) + 1;
			p = (p + 3) & ~3;
		} else if (token == FDT_END_NODE) {
			break;
		} else if (token == FDT_NOP) {
			continue;
		}
	}
	return 0;
}

int fdt_chosen_u64(uintptr_t dtb, const char *name, uint64_t *out)
{
	int offset = fdt_path_offset(dtb, "/chosen");
	if (offset < 0) return 0;
	return fdt_getprop_u64(dtb, offset, name, out);
}