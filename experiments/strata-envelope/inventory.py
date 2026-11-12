#!/usr/bin/env python3
"""Account runtime payload and matrix work using GGUF inventory and deployed pack.

This is a source-audited logical payload model, not a physical traffic counter.
gfx1151 HC_Q8 defaults and the deployed native dense loader are assumed.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--weights', type=Path, required=True)
p.add_argument('--index', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
weights = json.loads(a.weights.read_text())
index = {s[0]: list(map(int, s[1:])) for line in a.index.read_text().splitlines()
         if line and not line.startswith('#') for s in [line.split()]}
groups = defaultdict(lambda: defaultdict(int))
tensors = []
for t in weights['tensors']:
    name, group, elems = t['name'], t['group'], t['elements']
    row = dict(t)
    # Source native_dense.cpp: HC down/up/inject use Q8_0 on gfx1151,
    # including F32 inject quantization at load. Norm vectors remain F32.
    hc = (group == 'hyper_connections' and len(t['shape']) == 2)
    if group in ('routed_experts', 'embedding_lookup_tables'):
        payload, fmt = t['stored_bytes'], t['type']
    elif hc:
        payload, fmt = elems // 32 * 34, 'Q8_0'
    else:
        r = index[name]
        kind, dstbytes = r[1], r[5]
        if kind == 4:
            payload, fmt = elems * 2, 'BF16'
        elif kind == 5:
            payload, fmt = elems * 2, 'F16'
        elif kind == 2:
            payload, fmt = elems * 4, 'F32'
        else:
            payload, fmt = t['stored_bytes'], t['type']
    row.update(runtime_payload_bytes=payload, runtime_format=fmt)
    # Matrix MAC operations for every prompt row. The vocabulary head and
    # final HC are evaluated only for selected output positions, not every
    # prompt token. Sparse embedding tables are gathers, not dense GEMMs.
    prompt_flops = 0
    if group == 'routed_experts':
        prompt_flops = 2 * elems // weights['experts_per_layer'] * weights['selected_experts_per_token_per_layer']
    elif name.startswith('blk.') and len(t['shape']) == 2 and group != 'embedding_lookup_tables':
        # Conv1d is listed separately from matrix work.
        if not name.endswith('ssm_conv1d.weight'):
            prompt_flops = 2 * elems
    row['prompt_matrix_flops_per_row'] = prompt_flops
    tensors.append(row)
    groups[group]['runtime_payload_bytes'] += payload
    groups[group]['prompt_matrix_flops_per_row'] += prompt_flops
    groups[group]['stored_bytes'] += t['stored_bytes']
out = {'protocol': 'flash-next-runtime-inventory-v1',
       'input_sha256': {str(x): hashlib.sha256(x.read_bytes()).hexdigest() for x in (a.weights, a.index)},
       'assumptions': ['gfx1151 HC_Q8 default enabled, native dense loaded from original GGUF.',
                       'Packed Q8 copies are a layout change, not extra payload per invocation.',
                       'Prefill expands native weights into FP16/BF16 scratch; conversion is extra work.',
                       'Matrix FLOPs exclude attention, GDN recurrence, nonlinear ops, gathers, norms and launch costs.',
                       'Inventory is not physical DRAM bytes or bytes per emitted token.'],
       'groups': dict(groups),
       'nonexpert_runtime_payload_excluding_lookup_bytes': sum(v['runtime_payload_bytes'] for k,v in groups.items() if k not in ('routed_experts', 'embedding_lookup_tables')),
       'prompt_matrix_flops_per_row': sum(v['prompt_matrix_flops_per_row'] for v in groups.values()),
       'tensors': tensors}
a.out.write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('tensors', 'input_sha256')}))
