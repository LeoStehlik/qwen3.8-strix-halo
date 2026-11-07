#!/usr/bin/env python3
"""Estimate extra FP16 weight-cache capacity and held-out routed-row coverage.

This is a routing/capacity analysis, not a performance model. It retains the
original quantized weights, and uses only the first full chunk for ranking.
"""
import argparse
import hashlib
import json
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--routing', type=Path, required=True)
ap.add_argument('--out', type=Path, required=True)
ap.add_argument('--budgets-gib', type=int, nargs='+', default=[4, 8, 12, 16])
a = ap.parse_args()
raw = a.routing.read_bytes()
data = json.loads(raw)
layers = {}
for r in data['records']:
    if r['tokens'] == 16384:
        assert len(r['counts']) == 512 and sum(r['counts']) == 16384 * 10
        layers.setdefault(r['layer'], []).append(r)
assert len(layers) == 48 and all(len(rs) == 4 for rs in layers.values())
for rs in layers.values():
    rs.sort(key=lambda r: r['position'])
    assert len({r['position'] for r in rs}) == len(rs)

# Two 640x2560 gate/up matrices and one 2560x640 down matrix per expert.
per_expert = 3 * 2560 * 640 * 2
report = {'routing_sha256': hashlib.sha256(raw).hexdigest(),
          'layers': len(layers), 'experts_per_layer': 512,
          'extra_bytes_per_f16_expert': per_expert,
          'extra_bytes_for_all_experts': per_expert * 512 * len(layers),
          'budgets': [], 'limits': [
              'Original quantized weights remain resident for the existing decode path.',
              'Capacity excludes allocation alignment, metadata and temporary conversion workspace.',
              'Equal slots per layer; unused budget is not reassigned.',
              'Rank only on the first full chunk; evaluate on the next three from the same repeated-source prompt.',
              'Per-chunk oracle ranking is an unattainable same-chunk comparison, not the held-out result.',
              'Routed-row coverage is not measured kernel time saved or a predicted throughput gain.',
              'No prepared-weight kernel has been built, and no memory has been allocated by this script.',
              'A capacity budget is hypothetical, not an assertion that serving can safely consume it at full context.'
          ]}
for gib in a.budgets_gib:
    assert gib > 0
    slots = min(512, gib * 1024**3 // (len(layers) * per_expert))
    total = held = oracle = 0
    per_layer = []
    for layer, rs in sorted(layers.items()):
        selected = set(sorted(range(512), key=lambda e: (-rs[0]['counts'][e], e))[:slots])
        n = sum(sum(r['counts']) for r in rs[1:])
        h = sum(sum(r['counts'][e] for e in selected) for r in rs[1:])
        o = sum(sum(sorted(r['counts'], reverse=True)[:slots]) for r in rs[1:])
        total += n; held += h; oracle += o
        per_layer.append({'layer': layer, 'selected_experts': sorted(selected),
                          'held_out_rows': n, 'covered_rows': h, 'oracle_rows': o})
    report['budgets'].append({'budget_gib': gib, 'slots_per_layer': slots,
        'actual_extra_bytes': slots * len(layers) * per_expert,
        'held_out_routed_rows': total, 'covered_routed_rows': held,
        'coverage_fraction': held / total, 'oracle_coverage_fraction': oracle / total,
        'per_layer': per_layer})
a.out.parent.mkdir(parents=True, exist_ok=True)
a.out.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'full_expansion_extra_gib': report['extra_bytes_for_all_experts'] / 1024**3,
                  'budgets': [{k: v for k, v in b.items() if k != 'per_layer'} for b in report['budgets']]}, indent=2))
