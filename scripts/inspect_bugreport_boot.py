#!/usr/bin/env python3
"""Allowlisted boot evidence from the exact private S21 bugreport; no raw logs."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

ARCHIVE_SHA256 = '5a8e98c0f6dd657e87d099bfa7b26f1dd512ba39220ad85aecded709d79c40ef'
MAX_ARCHIVE = 64 << 20
MAX_MEMBER = 192 << 20
MAX_LINE = 4 << 20
MAX_SECTION = 2 << 20
HEADING = b'------ LAST KMSG (/proc/last_kmsg) ------'
PROPERTIES = {
    'ro.boot.bootloader': r'G998B[A-Z0-9]+',
    'ro.boot.flash.locked': r'[01]',
    'ro.boot.vbmeta.device_state': r'(?:locked|unlocked)',
    'ro.boot.verifiedbootstate': r'(?:green|yellow|orange|red)',
}
MESSAGES = {
    '[BLDP] build_version[] = G998BXXSJHZC2': 'boot_log_build_hzc2_message',
    'DRAM Size = 12.000000GB': 'dram_size_12gb_message',
    "[I]get_token_mode:316 Token doesn't exist": 'token_prefix_mismatch_message',
    '[H-Arx] Loading done': 'harx_loading_done',
    '[H-Arx] Complete to initialization': 'harx_initialization_message',
    '[H-ARX] EL2 crash buffer and FP is delivered successfully': 'harx_crash_registration_message',
    '[H-Arx Plug-in] UH plug-in registration done': 'uh_registration_message',
    'Send info to CP secure table 21': 'cp_table_21_message',
    'set_tzpc_secureport_fps: TEEGRIS - successfully protected in Fingerprint 0x00000007': 'fingerprint_success_message',
    '[UFDT] Little Find DTB Entry[0]: Rev:(S:0, E:255, X:0, D:22)': 'dtb_entry_0_message',
    '[UFDT] Little Find DTBO Entry[7]: Rev:(S:22, E:32, X:0, D:22)': 'dtbo_entry_7_message',
    '[UFDT] DT Overlay Complete!': 'dt_overlay_complete_message',
    "read_edtbo : edtbo doesn't exist.": 'edtbo_absent_message',
    'init_cmdline: default: console=ram loglevel=4': 'default_console_ram_message',
    'Starting kernel...': 'starting_kernel_message',
    'avb_slot_verify.c:566: DEBUG: boot: hash verification succeed.': 'boot_hash_success_message',
    'avb_slot_verify.c:566: DEBUG: harx: hash verification succeed.': 'harx_hash_success_message',
    'avb_slot_verify.c:566: DEBUG: vendor_boot: hash verification succeed.': 'vendor_boot_hash_success_message',
}
MEMORY = re.compile(r'(SEC_DRAM_BASE|SEC_DRAM_SIZE|SEC_PGTBL_BASE|SEC_PGTBL_SIZE|HARX_BASE|HARX_SIZE)\[(0x[0-9a-f]{1,16})\]')
STAMP = re.compile(r'\[0:\s+([0-9]+\.[0-9]+) \] (.*)')


def parse_boot(data, first_line):
    events, values = [], {}
    for offset, raw in enumerate(data.splitlines()):
        text = raw.decode('utf-8', errors='replace')
        match = STAMP.fullmatch(text)
        stamp, text = match.groups() if match else (None, text)
        text = text.rstrip()
        memory = MEMORY.fullmatch(text)
        if memory:
            key, value = memory.groups()
            if key in values:
                raise ValueError('duplicate boot memory field')
            values[key] = int(value, 16)
            event = dict(kind=key, value=hex(values[key]))
        elif text in MESSAGES:
            event = dict(kind=MESSAGES[text])
        else:
            continue
        event.update(source_line=first_line + offset, boot_seconds=stamp)
        events.append(event)
    expected = {'SEC_DRAM_BASE', 'SEC_DRAM_SIZE', 'SEC_PGTBL_BASE',
                'SEC_PGTBL_SIZE', 'HARX_BASE', 'HARX_SIZE'}
    if set(values) != expected:
        raise ValueError('missing boot memory fields')
    intervals = {}
    for name in ('SEC_DRAM', 'SEC_PGTBL', 'HARX'):
        base, size = values[name + '_BASE'], values[name + '_SIZE']
        if size == 0 or base + size >= 1 << 64:
            raise ValueError('invalid logged interval')
        intervals[name] = dict(base=hex(base), size=hex(size), end_exclusive=hex(base + size))
    return dict(events=events, logged_intervals=intervals,
                derived_relations=dict(sec_dram_end_equals_harx_base=(
                    values['SEC_DRAM_BASE'] + values['SEC_DRAM_SIZE'] == values['HARX_BASE'])))


def parse_main(stream):
    digest = hashlib.sha256()
    size = 0
    section, props = bytearray(), {}
    first_line = end_line = None
    active = False
    for number in range(1, 2_000_001):
        raw = stream.readline(MAX_LINE + 1)
        if not raw:
            break
        size += len(raw)
        if size > MAX_MEMBER or len(raw) > MAX_LINE:
            raise ValueError('main report exceeds host bounds')
        digest.update(raw)
        line = raw.rstrip(b'\r\n')
        if line == HEADING:
            if first_line is not None:
                raise ValueError('duplicate LAST KMSG section')
            first_line, active = number + 1, True
            continue
        if active and line.startswith(b'------ '):
            end_line, active = number - 1, False
        if active:
            section.extend(raw)
            if len(section) > MAX_SECTION:
                raise ValueError('boot section exceeds host bound')
        if not line.startswith(b'[ro.boot.'):
            continue
        text = line.decode('utf-8', errors='replace')
        for key, pattern in PROPERTIES.items():
            match = re.fullmatch(r'\[' + re.escape(key) + r'\]: \[(' + pattern + r')\]', text)
            if match:
                value = match.group(1)
                if key in props and props[key]['value'] != value:
                    raise ValueError('conflicting boot property')
                props[key] = dict(value=value, source_line=number)
    else:
        raise ValueError('main report exceeds line bound')
    if first_line is None or end_line is None or active:
        raise ValueError('missing or unterminated LAST KMSG section')
    if set(props) != set(PROPERTIES):
        raise ValueError('missing boot properties')
    return dict(main_member_bytes=size, main_member_sha256=digest.hexdigest(),
                properties=props, section=dict(first_line=first_line, last_line=end_line,
                    bytes=len(section), sha256=hashlib.sha256(section).hexdigest()),
                boot=parse_boot(bytes(section), first_line))


def inspect(path):
    with open(path, 'rb') as stream:
        data = stream.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE or hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('requires exact received bugreport SHA-256')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or names.count('main_entry.txt') != 1:
            raise ValueError('duplicate members or missing main_entry')
        if archive.getinfo('main_entry.txt').file_size > 256:
            raise ValueError('main_entry exceeds host bound')
        name = archive.read('main_entry.txt').decode('ascii').strip()
        if not re.fullmatch(r'dumpstate-[0-9-]+\.txt', name):
            raise ValueError('unexpected main report name')
        if archive.getinfo(name).file_size > MAX_MEMBER:
            raise ValueError('main report exceeds host bound')
        with archive.open(name) as stream:
            report = parse_main(stream)
    return dict(mode='allowlisted_bugreport_boot_observation', archive_sha256=ARCHIVE_SHA256,
                main_member=name, **report, raw_logs_published=False,
                final_fdt_captured=False, payload_executed=False,
                limits=['Log messages are observations, not a trace of register values or secure services',
                        'LAST KMSG capture time is not the boot time; persistence across reset is untested',
                        'Recovery cache logs from other builds are excluded',
                        'Token-prefix message is not proof of an empty partition or zero global bitmap',
                        'No arbitrary memory acquisition, final FDT or diagnostic record recovered'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bugreport')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(Path(args.bugreport)), indent=2))
    except (OSError, ValueError, KeyError, UnicodeError, zipfile.BadZipFile, RuntimeError) as error:
        parser.exit(2, f'inspect_bugreport_boot: {error}\n')
