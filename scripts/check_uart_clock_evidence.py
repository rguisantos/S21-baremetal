#!/usr/bin/env python3
"""Cross-check nominal UART0 clocks using exact HZC2 sboot and pinned sources.
Read-only evidence check, not a clock probe, MMIO writer or UART driver.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import struct
from inspect_sboot_hzc2 import inspect

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT/'docs/references/exynos-2100-37c14d8.json'
NODE = 'drivers/soc/samsung/cal-if/exynos2100/cmucal-node.c'
CLOCK = 'drivers/clk/samsung/clk-exynos2100.c'


def checked_source(root, path, entries):
    data = (root/path).read_bytes()
    if hashlib.sha256(data).hexdigest() != entries[path]['reference_sha256']:
        raise ValueError('source hash mismatch: '+path)
    return data.decode()


def match(pattern, text):
    result = re.search(pattern, text, re.S)
    if not result:
        raise ValueError('expected source declaration missing')
    return result


def wide(data, offset):
    word = struct.unpack_from('<I', data, offset)[0]
    if word & 0x7f800000 not in (0x52800000, 0x72800000):
        raise ValueError('expected MOVZ/MOVK at '+hex(offset))
    return ((word >> 5) & 0xffff) << (((word >> 21) & 3)*16)


def audit(sboot, source_root):
    evidence = inspect(sboot)  # Requires the exact HZC2 image before decoding.
    data = sboot.read_bytes()
    manifest = json.loads(MANIFEST.read_text())
    entries = {e['path']: e for e in manifest['files']}
    node = checked_source(source_root, NODE, entries)
    clock = checked_source(source_root, CLOCK, entries)
    oscillator = int(match(r'FRATE\(OSCCLK,\s*"fin_pll",\s*NULL,\s*0,\s*(\d+)\)', clock)[1])
    table = match(r'pll_shared2_rate_table\[\]\s*=\s*\{(.*?)\};', node)[1]
    rate, m, p, s = map(int, match(r'PLL_RATE_MPS\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)', table).groups())
    if p == 0 or Fraction(oscillator*m, p*(1 << s)) != rate:
        raise ValueError('PLL nominal table does not match oscillator and M/P/S')
    parents = [n.strip() for n in match(r'cmucal_mux_clkcmu_peric0_ip0_parents\[\]\s*=\s*\{(.*?)\};', node)[1].split(',') if n.strip()]
    selection = wide(data, 0x169a4)
    if selection >= len(parents) or parents[selection] != 'PLL_SHARED2_D2':
        raise ValueError('CMU_TOP selects a different parent')
    # Encoding zero is written with STR WZR at the decoded TOP divisor write.
    store = struct.unpack_from('<I', data, 0x1699c)[0]
    if store & 0xffc0001f != 0xb900001f:
        raise ValueError('TOP divisor write is not STR WZR')
    local_parents = [n.strip() for n in match(r'cmucal_mux_clk_peric0_uart_dbg_parents\[\]\s*=\s*\{(.*?)\};', node)[1].split(',') if n.strip()]
    local_selection = evidence['uart_clock_stages']['primary_mux_bytes'][0]
    if local_selection >= len(local_parents) or local_parents[local_selection] != 'MUX_CLKCMU_PERIC0_IP0_USER':
        raise ValueError('UART mux selects a different parent')
    user_parents = [n.strip() for n in match(r'cmucal_mux_clkcmu_peric0_ip0_user_parents\[\]\s*=\s*\{(.*?)\};', node)[1].split(',') if n.strip()]
    if len(user_parents) < 2 or user_parents[1] != 'CLKCMU_PERIC0_IP0':
        raise ValueError('unexpected IP0_USER parent mapping')
    fixed_encoded = int(match(r'FIXEDFACTOR\(PLL_SHARED2_D2,\s*PLL_SHARED2,\s*(\d+),', node)[1])
    local_encoded = evidence['uart_clock_stages']['primary_div_u16'][0]
    # CAL uses encoded divisor + 1 for fixed factors and dividers.
    nominal = Fraction(rate, (fixed_encoded+1)*(0+1)*(local_encoded+1))
    wrapper = wide(data, 0x1d4b8) | wide(data, 0x1d4c0)
    baud = wide(data, 0x1d4b4) | wide(data, 0x1d4bc)
    if nominal != wrapper or baud == 0:
        raise ValueError('clock path and BL2 wrapper disagree')
    divisor = wrapper//(16*baud)-1
    lk = wide(data, 0xef474)
    if divisor != lk:
        raise ValueError('nominal baud divisor disagrees with LK')
    return dict(source_commit=manifest['commit'], oscillator_hz=oscillator,
                pll_shared2=dict(nominal_hz=rate, m=m, p=p, s=s),
                cmu_top_parent=parents[selection],
                divisors=[fixed_encoded+1, 1, local_encoded+1],
                uart_nominal_hz=int(nominal), requested_baud=baud,
                bl2_ubrdiv=divisor, lk_ubrdiv=lk, runtime_observed=False,
                unresolved=['Actual PLL/mux/divider values at handoff',
                            'UART gate and QCH state', 'Physical routing and access'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot', type=Path)
    parser.add_argument('source_dir', type=Path, help='kernel source root matching the recorded hashes')
    args = parser.parse_args()
    try:
        result = audit(args.sboot, args.source_dir)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'check_uart_clock_evidence: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
