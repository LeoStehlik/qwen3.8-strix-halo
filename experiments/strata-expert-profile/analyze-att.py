#!/usr/bin/env python3
"""Summarize expert ATT instruction latencies; these are not wall-time shares."""
import argparse
import collections
import csv
import gzip
import json
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('directory', type=Path)
a = ap.parse_args()
report = {'traces': {}, 'limits': [
    'Each trace samples one dispatch on one WGP and selected SIMD, not whole-GPU occupancy.',
    'Summed instruction latencies overlap across waves; shares are not wall time or additive speedup estimates.',
    'VALU categories include indexing and activation work as well as weight decoding.',
    'ATT waves do not identify logical expert IDs; no row-count timing bucket is inferred.']}
for d in sorted(a.directory.glob('*-i*')):
    cmd = json.loads((d / 'command.json').read_text())
    assert cmd['exit_code'] == 0 and cmd['output_hash_passed']
    assert cmd['serving_requests_before'] == cmd['serving_requests_after']
    stats = sorted(d.glob('stats_*.csv*'))
    assert len(stats) == 1
    with (gzip.open(stats[0], 'rt') if stats[0].suffix == '.gz' else stats[0].open()) as handle:
        rows = list(csv.DictReader(handle, skipinitialspace=True))
    categories = collections.defaultdict(collections.Counter)
    for r in rows:
        inst = r['Instruction']
        op = inst.split()[0] if inst else ''
        cat = ('matrix' if 'wmma' in op else
               'vector_memory_wait' if op == 's_waitcnt' and 'vmcnt' in inst else
               'lds_or_scalar_memory_wait' if op == 's_waitcnt' and 'lgkmcnt' in inst else
               'barrier' if op == 's_barrier' else
               'lds' if op.startswith('ds_') else
               'global_memory' if op.startswith(('global_', 'buffer_', 'flat_')) else
               'vector_conversion' if op.startswith('v_cvt') else
               'vector_bit_or_select' if op.startswith(('v_and', 'v_or', 'v_xor', 'v_lsh', 'v_bfe', 'v_bfi', 'v_perm', 'v_cndmask', 'v_align')) else
               'vector_fp16' if op.startswith('v_') and 'f16' in op else
               'vector_other' if op.startswith('v_') else
               'scalar_other' if op.startswith('s_') else 'other')
        for col in ('Hitcount', 'Latency', 'Stall', 'Idle'):
            categories[cat][col] += int(r[col])
    total = sum(x['Latency'] for x in categories.values())
    assert total > 0
    for x in categories.values():
        x['fraction_of_summed_latency'] = x['Latency'] / total
    waves = []
    events = []
    if (d / 'wave-intervals.json').exists():
        waves = json.loads((d / 'wave-intervals.json').read_text())
    else:
        for path in d.glob('ui*/se0_sm0_sl*_wv*.json'):
            w = json.loads(path.read_text())['wave']
            waves.append({k: w[k] for k in ('begin', 'end', 'cu', 'simd', 'id')})
    for w in waves:
        events.extend(((w['begin'], 1), (w['end'], -1)))
    assert waves
    events.sort()
    pop, last = 0, events[0][0]
    durations = collections.Counter()
    for t, change in events:
        durations[pop] += t - last
        last, pop = t, pop + change
    span = events[-1][0] - events[0][0]
    report['traces'][d.name] = {
        'categories': categories, 'summed_instruction_latency': total, 'wave_count': len(waves),
        'selected_simd_peak_waves': max(k for k, v in durations.items() if v),
        'selected_simd_time_weighted_waves': sum(k * v for k, v in durations.items()) / span,
        'residency_cycles_by_wave_count': durations, 'wave_intervals': waves,
        'top_latency_instructions': sorted(rows, key=lambda r: int(r['Latency']), reverse=True)[:30]}
assert report['traces']
(a.directory / 'analysis.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: {'waves': v['wave_count'], 'resident_mean': v['selected_simd_time_weighted_waves'],
                     'latency_fractions': {c: round(x['fraction_of_summed_latency'], 4) for c, x in v['categories'].items()}}
                  for k, v in report['traces'].items()}))
