#!/usr/bin/env python3
"""Repeat the pinned no-change Magisk repack and locate changed hash inputs."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from capture_a0_formats import digest, layout, require
from check_capture_a0 import PINS, run_tool, verify_file

MTIMES = (1, 1700000000, 1790000000)


def intersection(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def changed_regions(before, after):
    """Coordinates are those of the original, valid stock descriptor."""
    require(len(before) == len(after), 'partition length changed')
    old, new = layout(before), layout(after)
    av, bv = old['avb'], new['avb']
    require(av and av['all_hashes_match'] and bv, 'requires valid original AVB and parseable output')
    require(len(av['hash_descriptors']) == len(bv['hash_descriptors']) == 1, 'requires one hash descriptor')
    end = av['hash_descriptors'][0]['image_size']
    require(old['body_end'] <= end <= av['offset'], 'original hash extent inconsistent with payload')
    bounds = [0, old['body_end'], end, av['offset'], av['offset']+av['bytes'], len(before)-64, len(before)]
    names = ['android_body', 'signed_extension', 'gap_before_original_vbmeta',
             'original_vbmeta', 'tail_padding', 'avb_footer']
    rows = []
    for name, start, stop in zip(names, bounds, bounds[1:]):
        changed = sum(a != b for a, b in zip(memoryview(before)[start:stop], memoryview(after)[start:stop]))
        rows.append(dict(name=name, start=start, end=stop, changed_bytes=changed))
    semantic = lambda inv: {p['name']:(p['bytes'], p['sha256']) for p in inv['parts']
                            if p['kind'] in ('header', 'payload')}
    extension = before[old['body_end']:end]
    prefix = 16 if extension.startswith(b'SEANDROIDENFORCE') else 0
    remainder_start = old['body_end']+prefix
    inside = sum(row['changed_bytes'] for row in rows[:2])
    outside = sum(row['changed_bytes'] for row in rows[2:])
    return dict(original_sha256=old['sha256'], repacked_sha256=new['sha256'],
        original_hash_extent=[0, end], original_footer_extent=[len(before)-64, len(before)],
        footer_inside_original_hash=intersection([0, end], [len(before)-64, len(before)]) != 0,
        changed_inside_original_hash=inside, changed_outside_original_hash=outside,
        changed_bytes=inside+outside, regions_in_original_coordinates=rows,
        header_and_payloads_identical=semantic(old) == semantic(new),
        vbmeta_blob_identical=av['vbmeta_sha256'] == bv['vbmeta_sha256'],
        original_vbmeta_extent=[av['offset'], av['offset']+av['bytes']],
        repacked_vbmeta_extent=[bv['offset'], bv['offset']+bv['bytes']],
        repacked_vbmeta_overlap_original_hash=intersection([0, end], [bv['offset'], bv['offset']+bv['bytes']]),
        original_extension=dict(bytes=len(extension), original_seandroid_prefix_bytes=prefix,
            seandroid_prefix_unchanged=before[old['body_end']:remainder_start] == after[old['body_end']:remainder_start],
            remainder_bytes=end-remainder_start, remainder_sha256=digest(before[remainder_start:end]),
            remainder_starts_signerver03=before[remainder_start:remainder_start+11] == b'SignerVer03',
            remainder_replaced_entirely_by_zero=not any(after[remainder_start:end])),
        original_avb=av, repacked_avb=bv,
        no_change_gate_passed=before == after and bv['all_hashes_match'],
        signature_verified=False, physical_acceptance_established=False)


def inspect(stock_dir, tool_path, output):
    pins = json.loads(PINS.read_text())
    verify_file(tool_path, pins['magisk']['host_binary'])
    paths = {name: stock_dir/(name+'.lz4') for name in ('boot.img', 'vendor_boot.img')}
    for name, path in paths.items(): verify_file(path, pins['stock_lz4'][name+'.lz4'])
    output = output.resolve(); output.mkdir(parents=True, exist_ok=False)
    tool = output/'magiskboot'; tool.write_bytes(tool_path.read_bytes()); tool.chmod(0o700)
    report = dict(schema='S21-CAPTURE-A0-REPACK-v1', magisk=pins['magisk'],
        trial_mtimes=list(MTIMES), unpack_options=['-n', '-h'], repack_options=['-n'],
        native_environment_keys=['PATH', 'LC_ALL'], images={}, a0_complete=False,
        modified_payload_packer_implemented=False, physical_action=False)
    for name, path in paths.items():
        original = output/name
        run_tool(tool, ['decompress', path.resolve(), original], output)
        verify_file(original, pins['stock_raw'][name])
        before = original.read_bytes(); first = None; trials = []
        for index, epoch in enumerate(MTIMES):
            work = output/(name+'-trial-'+str(index)); work.mkdir()
            run_tool(tool, ['unpack', '-n', '-h', original], work, (0,) if name == 'boot.img' else (3,))
            for file in work.iterdir():
                if file.is_file(): os.utime(file, (epoch, epoch))
            repacked = work/'repacked.img'
            run_tool(tool, ['repack', '-n', original, repacked], work)
            after = repacked.read_bytes()
            if first is None:
                first = after
                analysis = changed_regions(before, after)
            trials.append(dict(input_file_mtime=epoch, output_sha256=digest(after),
                               byte_identical_to_first=after == first))
        report['images'][name] = dict(trials=trials,
            all_trials_byte_identical=all(t['byte_identical_to_first'] for t in trials),
            first_trial_analysis=analysis)
    report['all_no_change_gates_passed'] = all(i['first_trial_analysis']['no_change_gate_passed']
        and i['all_trials_byte_identical'] for i in report['images'].values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock-dir', type=Path, required=True)
    parser.add_argument('--magiskboot', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = inspect(args.stock_dir, args.magiskboot, args.output_dir)
        (args.output_dir/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, 'REPACK ANALYSIS REFUSED: '+str(exc)+'\n')
    print('Repack analysis completed; no-change gate:',
          'PASS' if report['all_no_change_gates_passed'] else 'FAIL; A0 remains open')
    return 0 if report['all_no_change_gates_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
