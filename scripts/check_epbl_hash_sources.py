#!/usr/bin/env python3
"""Compare HZC2 HASH evidence with pinned ACE and Fireplace source dialects.

References establish their own software definitions, never HZC2 hardware
behavior. No emulator, firmware, crypto trial or MMIO service is executed.
The ACE header is only preprocessed, with system includes disabled.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

from inspect_epbl_protocol import evidence

REFERENCES = {
    'ace': ('meizuosc/m462', 'a2a3737c06577015d8d3f6c6aa36e53c90d57d5b',
            'drivers/crypto/ace_sfr.h', '2e0a915dcc41e599e08bbcc29923f32dddc3f16e',
            '0e388e8f0c81118c6f2a66ac761966da97f4a82e53de3a90eabdb2448f3b7b47'),
    'internal': ('Creeeeger/fireplace', '262ff996ee411f0975cdbdfe059d67b4060bb7d7',
            'emulator/soc/sss/sss_internal.h', '1e002f738c57db1b5aa198914053cc6f36820848',
            'd2f10d230dbbe97e97e6ea69dbd8019441ccdd11b1e756bfa2cb50bb6ec13e6e'),
    'public': ('Creeeeger/fireplace', '262ff996ee411f0975cdbdfe059d67b4060bb7d7',
            'include/fireplace/soc/sss/sss.h', '16388a0e3fd6044c41fe2bec65ccebe708a7eceb',
            '4654a4185da68c9d14c71d5cd259d9c6027f12b67fb437e6cce1b759c687a140'),
    'hash': ('Creeeeger/fireplace', '262ff996ee411f0975cdbdfe059d67b4060bb7d7',
            'emulator/soc/sss/sss_hash.c', 'ef5072ea3f3e10945c728eb8c2f29d19a1a72dd5',
            '57bc72b01e3aa7b4c3db1fcd968f7a97ab30a3643aedcbcfca095c1769e6ecbc'),
    'readme': ('Creeeeger/fireplace', '262ff996ee411f0975cdbdfe059d67b4060bb7d7',
            'README.md', '6fee9ae2416a54a6c68376219ed2df527d3065cf',
            '52723eee95d75166591fe1348c335d027a96d2ed4010e625bdc4ae9b4dc0e8ca'),
}


def read_reference(path, identity):
    repository, commit, name, blob, digest = identity
    with Path(path).open('rb') as stream:
        raw = stream.read(65537)
    actual = hashlib.sha256(raw).hexdigest()
    git = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if len(raw) > 65536 or actual != digest or git != blob:
        raise ValueError('reference size/hash/blob mismatch: ' + name)
    return raw.decode('ascii'), dict(repository=repository, commit=commit, path=name,
        sha256=actual, git_blob_sha=git,
        url=f'https://github.com/{repository}/blob/{commit}/{name}',
        reference_is_HZC2_hardware_specification=False)


def definitions(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r'#define\s+([A-Za-z_]\w*)\s+(.+)', line)
        if match:
            name, value = match.groups()
            if name in result:
                raise ValueError('duplicate macro: ' + name)
            result[name] = value
    return result


def macro_value(macros, name, chain=()):
    """Small integer expression grammar; never eval arbitrary source text."""
    if name in chain or len(chain) >= 32 or name not in macros:
        raise ValueError('unknown/cyclic/deep macro: ' + name)
    expression = re.sub(r'\b(0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]+\b', r'\1', macros[name])
    node = ast.parse(expression, mode='eval')
    if sum(1 for _ in ast.walk(node)) > 128:
        raise ValueError('macro expression too large')

    def visit(item, depth=0):
        if depth >= 32:
            raise ValueError('macro expression too deep')
        if isinstance(item, ast.Expression):
            return visit(item.body, depth + 1)
        if isinstance(item, ast.Constant) and type(item.value) is int:
            value = item.value
        elif isinstance(item, ast.Name):
            value = macro_value(macros, item.id, chain + (name,))
        elif isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == 'UINT32_C' and len(item.args) == 1 and not item.keywords:
            value = visit(item.args[0], depth + 1)
            if value >= 1 << 32:
                raise ValueError('UINT32_C overflow')
        elif isinstance(item, ast.BinOp) and isinstance(item.op, (ast.Add, ast.Sub, ast.Mult, ast.LShift, ast.RShift, ast.BitOr, ast.BitAnd)):
            left, right = visit(item.left, depth + 1), visit(item.right, depth + 1)
            if isinstance(item.op, (ast.LShift, ast.RShift)) and right > 63:
                raise ValueError('macro shift exceeds 63')
            operations = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right, ast.LShift: lambda: left << right,
                ast.RShift: lambda: left >> right, ast.BitOr: lambda: left | right,
                ast.BitAnd: lambda: left & right}
            value = operations[type(item.op)]()
        else:
            raise ValueError('unsupported macro syntax')
        if not 0 <= value < 1 << 64:
            raise ValueError('macro integer outside unsigned 64 bits')
        return value
    return visit(node)


def hash_modes(source):
    """Parse exactly the selected emulator switch, including fallthrough."""
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    match = re.search(r'static bool sss_hash_mode\([^{}]*\)\s*\{\s*switch\s*\(mode\)\s*\{([^{}]*)\}\s*\}', clean)
    if not match:
        raise ValueError('expected restricted hash-mode switch')
    body = match[1].strip()
    pattern = re.compile(r'((?:case\s+0x[0-9a-f]+:\s*)+)\*md\s*=\s*EVP_(sha1|sha256|sha512)\(\);\s*\*hmac\s*=\s*(true|false);\s*return true;\s*')
    modes = {}
    while not re.fullmatch(r'default:\s*return false;', body):
        entry = pattern.match(body)
        if not entry:
            raise ValueError('unclassified mode-switch statement')
        for literal in re.findall(r'case\s+(0x[0-9a-f]+):', entry[1]):
            key = int(literal, 16)
            if key in modes:
                raise ValueError('duplicate hash mode')
            modes[key] = dict(algorithm=entry[2], hmac=entry[3] == 'true')
        body = body[entry.end():].strip()
    return modes


def compare(sboot, sources):
    texts, identities = {}, {}
    for name, identity in REFERENCES.items():
        texts[name], identities[name] = read_reference(sources[name], identity)
    if 'experimental Exynos 9830 emulator' not in texts['readme'] or 'SM-G986B' not in texts['readme']:
        raise ValueError('reference target statement changed')
    preprocessor = subprocess.run(['cc', '-E', '-dM', '-nostdinc', '-DCONFIG_ACE_USE_SSS_VER_6',
        '-x', 'c', str(Path(sources['ace']).resolve())], capture_output=True, text=True, timeout=10, check=True)
    ace = definitions(preprocessor.stdout)
    public = definitions(texts['public'])
    emulator = definitions(texts['internal']) | public
    base = macro_value(emulator, 'SSS_BASE')
    report = evidence(sboot)
    rows = []
    fields = (
        ('HASH mode', 'ACE_HASH_CONTROL', 'SSS_HASH_MODE', 0x1000),
        ('HASH FIFO/control', 'ACE_HASH_FIFO_MODE', 'SSS_HASH_CONTROL', 0x1008),
        ('HASH status', 'ACE_HASH_STATUS', 'SSS_HASH_STATUS', 0x1010),
        ('HASH size low', 'ACE_HASH_MSGSIZE_LOW', 'SSS_HASH_LEN', 0x1020),
        ('HASH size high', 'ACE_HASH_MSGSIZE_HIGH', 'SSS_HASH_LEN_HI', 0x1024),
        ('HASH previous low', 'ACE_HASH_PRELEN_LOW', 'SSS_HASH_PRE_LEN', 0x1030),
        ('HASH previous high', 'ACE_HASH_PRELEN_HIGH', 'SSS_HASH_PRE_LEN_HI', 0x1034),
        ('HASH material start', 'ACE_HASH_HMAC_KEY_IN1', 'SSS_HASH_KEY', 0x1100),
        ('HASH IV start', 'ACE_HASH_IV1', 'SSS_HASH_IV', 0x1180),
        ('HASH output start', 'ACE_HASH_RESULT1', 'SSS_HASH_DIGEST', 0x11c0),
    )
    observed = {int(item['offset'], 16) for item in report['mmio_inventory']}
    for label, ace_name, emu_name, offset in fields:
        a = macro_value(ace, ace_name)
        e = macro_value(emulator, emu_name) - base
        if a != offset or e != offset or offset not in observed:
            raise ValueError('reference/firmware offset mismatch: ' + label)
        rows.append(dict(field=label, ace_macro=ace_name, emulator_macro=emu_name,
                         matching_offset=hex(offset), HZC2_access_present=True, physical_binding_verified=False))
    dma = {}
    for name, expected in (('SSS_SRC_ADDR_HI', 0x40), ('SSS_SRC_ADDR_LO', 0x44), ('SSS_SRC_LEN', 0x48)):
        actual = macro_value(emulator, name) - base
        if actual != expected:
            raise ValueError('reference DMA dialect changed')
        dma[name] = hex(actual)
    modes = hash_modes(texts['hash'])
    mode = int(report['first_stage']['literal_hash_configuration']['control'], 16)
    legacy = [name for name in ace if name.startswith('ACE_HASH_ENGSEL_') and name != 'ACE_HASH_ENGSEL_MASK'
              and macro_value(ace, name) | macro_value(ace, 'ACE_HASH_STARTBIT_ON') == mode]
    return dict(mode='pinned_source_dialect_comparison', sboot_sha256=report['sboot_sha256'], sources=identities,
        ace_profile='CONFIG_ACE_USE_SSS_VER_6', ace_base=hex(macro_value(ace, 'ACE_SFR_BASE')),
        emulator_target='experimental Exynos9830 / SM-G986B', emulator_base=hex(base), HZC2_code_base='0x18330000',
        matching_hash_fields=rows, reference_dma_words=dma,
        first_stage=dict(mode=hex(mode), emulator_implements_mode=mode in modes,
            emulator_algorithm=modes.get(mode), legacy_reference_names=sorted(legacy),
            candidate_DMA_address=report['first_stage']['candidate_dma_layout']['candidate_address'],
            candidate_DMA_size=report['first_stage']['candidate_dma_layout']['candidate_size'],
            algorithm_identified=False, data_source_identified=False),
        emulator_modes={hex(k): value for k, value in sorted(modes.items())},
        second_stage=dict(mode='0x14', emulator_definition=modes.get(0x14),
            context_word_to_MMIO=report['second_stage']['hash_counter_upload'],
            low_context_offset='0x44', high_context_offset='0x40', HZC2_hardware_semantics_verified=False),
        reference_coverage=dict(ace_explicit_HMAC_words=16, HZC2_uploaded_words=32,
            ace_explicit_result_words=8, HZC2_first_result_words=12,
            complete_first_stage_layout_documented=False),
        conclusions=['Ten HASH offsets and the high/low/size DMA dialect agree across these references',
            'Fireplace explicitly rejects 0x19; its supported SHA512 modes are 0x1a and 0x1b',
            'Legacy ACE names 0x19 as SHA1HMACOUT+START; this cannot be transferred to HZC2',
            'Neither matching offsets nor a 48-byte read identifies the HZC2 first-stage algorithm',
            'The Exynos9830 BootROM is not substituted for an HZC2 data source'],
        source_code_executed=False, ACE_header_preprocessed_only=True, emulator_executed=False,
        firmware_executed=False, MMIO_responses_injected=False, physical_device_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sboot')
    for name in REFERENCES:
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(compare(args.sboot, {name: getattr(args, name) for name in REFERENCES}), indent=2))
    except (OSError, ValueError, SyntaxError, subprocess.SubprocessError) as exc:
        parser.exit(2, 'HASH source comparison failed: ' + str(exc) + '\n')
