#!/usr/bin/env python3
"""Summarize qualified timings; retain and separately exclude evicted samples."""
import argparse
import collections
import csv
import json
from pathlib import Path
import statistics

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--run', type=Path, required=True)
p.add_argument('--counters', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
meta = json.loads((a.run / 'bench.json').read_text())
assert meta['exit_code'] == 0 and meta['serving_requests_before'] == meta['serving_requests_after']
rows = [json.loads(l) for l in (a.run / 'bench.stdout').read_text().splitlines()]
checks = [r for r in rows if r['kind'] == 'correctness']
assert len(checks) == 31 and all(r['passed'] for r in checks)
timings = [r for r in rows if r['kind'] == 'timing']
assert len(timings) == 360
groups = collections.defaultdict(lambda: collections.defaultdict(list))
for r in timings:
    groups[(r['groups'], r['entries_per_group'], r['banks'])][r['lanes']].append(r)
report = {'protocol': 'q51-subwarp-v1', 'binary_sha256': meta['binary_sha256'],
          'correctness_cases': len(checks), 'max_cpu_reference_relative_l1': max(r['relative_l1'] for r in checks),
          'samples': len(timings), 'evicted_samples': [r for r in timings if r['timed_evicted_ms']],
          'cases': [], 'counters': [], 'limits': [
              'Synthetic weights and group multiplicities, not captured decode routing.',
              'Some dense combinations exceed the ordinary four-token verification window.',
              'No whole-model speedup is established by this operator benchmark.',
              'L2 outgoing reads can hit the LLC; they are not a DRAM-bandwidth measurement.',
              'Counter timings are instrumented and must not replace unprofiled timings.',
              'Counter run uses the earlier binary; later host-only eviction instrumentation leaves kernel source unchanged.',
          ]}
for (ng, ne, banks), variants in groups.items():
    result = {'groups': ng, 'entries_per_group': ne, 'banks': banks, 'layouts': {}}
    control = {r['trial']: r for r in variants[32]}
    for lanes, values in variants.items():
        assert len(values) == 5
        clean = [r for r in values if not r['timed_evicted_ms']]
        assert len(clean) >= 4
        paired = [control[r['trial']]['us'] / r['us'] for r in clean
                  if not control[r['trial']]['timed_evicted_ms']]
        result['layouts'][str(lanes)] = {
            'all_median_us': statistics.median(r['us'] for r in values),
            'clean_samples': len(clean), 'clean_median_us': statistics.median(r['us'] for r in clean),
            'paired_clean_samples': len(paired), 'paired_median_speedup': statistics.median(paired),
            'paired_min_speedup': min(paired), 'paired_max_speedup': max(paired),
        }
    report['cases'].append(result)
for path in sorted(a.counters.glob('*/q51_counter_collection.csv')):
    rows = list(csv.DictReader(path.open()))
    dispatches = collections.defaultdict(dict)
    for r in rows:
        entry = dispatches[r['Dispatch_Id']]
        entry[r['Counter_Name']] = float(r['Counter_Value'])
    assert len(dispatches) == 5
    if 'memory' not in path.parent.name:
        continue
    row = {'mode': path.parent.name, 'samples': len(dispatches),
           'median_waves': statistics.median(v['SQ_WAVES_sum'] for v in dispatches.values()),
           'median_l2_outgoing_read_bytes': statistics.median(
               sum(v[f'GL2C_EA_RDREQ_{n}B_sum'] * n for n in (32, 64, 128)) for v in dispatches.values()),
           'vgpr': int(rows[0]['VGPR_Count']), 'scratch': int(rows[0]['Scratch_Size'])}
    assert 48_000_000 < row['median_l2_outgoing_read_bytes'] < 51_000_000
    report['counters'].append(row)
a.out.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'checks': len(checks), 'timings': len(timings),
                  'excluded_evicted_timings': len(report['evicted_samples']), 'counters': report['counters']}, indent=2))
