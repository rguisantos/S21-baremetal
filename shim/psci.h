#ifndef PSCI_H
#define PSCI_H

#include <stdint.h>

#define PSCI_VERSION		0x84000000UL
#define PSCI_CPU_ON		0xc4000003UL
#define PSCI_CPU_OFF		0x84000002UL
#define PSCI_CPU_SUSPEND	0xc4000001UL
#define PSCI_SYSTEM_RESET	0x84000009UL
#define PSCI_SYSTEM_OFF		0x84000008UL

uint64_t psci_cpu_on(uint64_t mpidr, uint64_t entry, uint64_t ctx);
uint64_t psci_cpu_off(void);
uint64_t psci_system_reset(void);
uint64_t psci_version(void);

#endif