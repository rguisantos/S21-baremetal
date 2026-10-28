#!/usr/bin/env python3
"""Compare observations at the same bounded NEWTIME gate, without executing code."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from inspect_el2_hzc2 import IMAGES
from trace_newtime_columns_qemu import OBSERVATIONS


def read_report(path):
    with Path(path).open('rb') as stream:
        data = stream.read((4 << 20)+1)
    if len(data) > 4 << 20:
        raise ValueError('observation JSON exceeds host bound')
    return json.loads(data), hashlib.sha256(data).hexdigest()


def compare(left, right):
    for report,row in ((left,10),(right,15)):
        if report.get('sboot_sha256') != IMAGES['sboot'][1]:
            raise ValueError('observation firmware identity differs')
        if (report.get('instruction_budget_per_case') != 20000 or report.get('case_count') != 2
                or len(report.get('cases',[])) != 2 or report.get('mmio_or_smc_executed') is not False
                or report.get('phone_execution') is not False):
            raise ValueError('unexpected observation scope')
        if any(c.get('row') != row for c in report['cases']):
            raise ValueError('unexpected row identity')
    for key in ('prefix_instruction_index_sha256','suffix_instruction_index_sha256','gate_observation'):
        if key not in left or left[key] != right.get(key):
            raise ValueError('incompatible preparation or tool provenance')
    indexed = [{c['laboratory_delta']:c for c in r['cases']} for r in (left,right)]
    bases = {'0x40000000','0x40200000'}
    if any(set(cases) != bases for cases in indexed):
        raise ValueError('missing or duplicate laboratory placement')
    rows = []
    for base in sorted(bases):
        cases = [cases[base] for cases in indexed]
        observations = [c['observation'] for c in cases]
        gate = all(o['reason']=='bp:gate_0x19774' and o['pc']==hex(int(base,0)+0x19774)
                   and o['pc_file_offset']=='0x19774' and o['registers']['x0']=='0x158609bc'
                   for o in observations)
        same_return = all(o['image_base']==base and o['callback_return']==o['entry_lr']==
                          hex(int(base,0)+0x15000) for o in observations)
        if not gate or not same_return:
            rows.append(dict(image_base=base,comparable=False,
                reason='different_stop_or_callback_return',field_comparison_performed=False))
            continue
        values, initial = [], []
        for case,observation in zip(cases,observations):
            entry = case['initial_observation']
            if entry['reason'] != 'prepared_entry' or entry['pc'] != hex(int(base,0)+0x193fc):
                raise ValueError('incorrect entry snapshot')
            pair = []
            for snapshot in (entry,observation):
                if snapshot['firmware_instruction_executed_by_snapshot'] is not False:
                    raise ValueError('unexpected snapshot execution')
                fields = {}
                for name,offset,size,relative in OBSERVATIONS:
                    item = snapshot['fields'][name]
                    address = int(base,0)+offset if relative else offset
                    if item['address'] != hex(address) or item['size'] != size:
                        raise ValueError('incorrect snapshot address or width')
                    if not relative and (item.get('error') != 'not_in_lab_regions' or 'hex' in item):
                        raise ValueError('AP literal must remain outside laboratory regions')
                    if 'hex' in item:
                        if not re.fullmatch('[0-9a-f]{'+str(2*size)+'}',item['hex']):
                            raise ValueError('invalid snapshot bytes')
                        fields[name] = item['hex']
                pair.append(fields)
            if not all(name in fields for fields in pair for name in ('ptr_31c30','scratch_31f30')):
                raise ValueError('primary observation is unavailable')
            initial.append(pair[0]);values.append(pair[1])
        primary = ('ptr_31c30','scratch_31f30')
        rows.append(dict(image_base=base, comparable=True,
            field_comparison_performed=True, callback_return=observations[0]['callback_return'],
            primary_fields_identical_between_rows=all(values[0][k]==values[1][k] for k in primary),
            primary_fields_unchanged_from_entry=all(v[k]==i[k] for v,i in zip(values,initial) for k in primary),
            primary_write_events_by_row={str(c['row']):{k:c['observed_field_write_counts'][k] for k in primary} for c in cases},
            predictions=dict(pointer_ff=all(v['ptr_31c30']=='ff'*8 for v in values),
                             scratch_zero=all(v['scratch_31f30']=='00'*108 for v in values)),
            observed_scratch_hex=values[0]['scratch_31f30'],
            informational_compared_fields=sorted((set(values[0]) & set(values[1]))-set(primary)),
            informational_equal=all(values[0][k]==values[1][k] for k in set(values[0]) & set(values[1]) if k not in primary),
            unavailable_field='result_col1_0207365c: not_in_lab_regions'))
    return dict(mode='newtime_gate_comparison',placements=rows,
        artifacts_authenticated=False,physical_execution_inferred=False,
        limits=['Compares declared observations; does not authenticate their producer',
                'Nonzero scratch alone does not demonstrate a write or a particular producer',
                'Trace hashes and instruction counts need not match across different input rows',
                'No execution after the gate is authorized by this result'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args=parser.parse_args()
    try:
        reports = [read_report(Path(args.directory)/f'line{row}__none.json') for row in (10,15)]
        result = compare(*(r[0] for r in reports))
        result['input_sha256'] = {f'line{row}__none.json':r[1] for row,r in zip((10,15),reports)}
        print(json.dumps(result,indent=2))
    except (OSError,ValueError,KeyError,TypeError) as error:
        parser.exit(2,f'compare_newtime_gate: {error}\n')
