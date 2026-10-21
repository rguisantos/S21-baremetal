/* Legacy loader quarantined: it passed XNU boot_args to an FDT consumer and
 * performed unchecked writes. Inspection lives in payload.c. A future loader
 * must prove memory ownership, EL, cache and raw-FDT handoff before copying. */
#include "loader.h"
const char *loader_boot(uintptr_t dtb)
{
    (void)dtb;
    return "chainload disabled: R10 requires a validated EL2/raw-FDT handoff";
}
