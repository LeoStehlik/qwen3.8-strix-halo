#!/usr/bin/env python3
"""Summarize local envelope measurements without inferring DRAM from GL2 counts."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics as st

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--root', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
r = a.root
def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.startswith('{')]
def stats(v):
    return {'n':len(v), 'min':min(v), 'median':st.median(v), 'max':max(v)}
out = {'protocol':'strata-measured-envelope-v1', 'calibration':{}, 'routes':[], 'operators':{}}
for run in ('calibration-first','calibration-return'):
    raw = lines(r/'calibration-exclusive'/run/'stdout')
    groups = defaultdict(list)
    for row in raw:
        if row['kind'] not in ('memory','compute') or row['trial']==0 or row['evicted_ms']:
            continue
        key = (row['kind'], row.get('op'), row.get('mib_per_buffer'), row['grid'])
        groups[key].append(row)
    data = []
    for key, rows in groups.items():
        metric = 'requested_gb_s' if key[0]=='memory' else 'teraops_s'
        data.append({'kind':key[0], 'op':key[1], 'mib_per_buffer':key[2], 'grid':key[3], 'metric':metric, **stats([x[metric] for x in rows])})
    out['calibration'][run] = data
inv = json.loads((r/'runtime-inventory.json').read_text())
payload = defaultdict(int)
for t in inv['tensors']:
    if t['group']=='routed_experts':payload[int(t['name'].split('.')[1])] += t['runtime_payload_bytes']//512
groups = defaultdict(list)
for row in lines(r/'routes.jsonl'):groups[row['report']].append(row)
for report, rows in groups.items():
    widths={x['T']:x['windows'] for x in rows}
    assert len(rows)==48*len(widths)
    for x in rows:
        assert x['new_per_row'][0]==10*x['windows']
        assert all(0<=v<=10*x['windows'] for v in x['new_per_row'])
    windows=sum(widths.values())
    expert=sum(sum(x['new_per_row'])*payload[x['layer']] for x in rows)/windows
    row={'native_report':report,'windows_by_width':widths,'windows':windows,
         'mean_T':sum(k*v for k,v in widths.items())/windows,
         'mean_distinct_experts_per_layer':sum(sum(x['new_per_row']) for x in rows)/(48*windows),
         'expert_payload_bytes_per_window':expert,
         'dense_plus_distinct_expert_payload_bytes_per_window':expert+inv['nonexpert_runtime_payload_excluding_lookup_bytes']}
    row['single_stream_weight_ms_at_242GBs']=row['dense_plus_distinct_expert_payload_bytes_per_window']/242e6
    row['single_stream_weight_ms_at_256GBs']=row['dense_plus_distinct_expert_payload_bytes_per_window']/256e6
    out['routes'].append(row)
for run in ('q8-first','q8-return'):
    path=r/'q8-final'/run/'stdout'
    if not path.exists():continue
    groups=defaultdict(list);raw=lines(path)
    for x in raw:
        if x['kind']=='timing' and x['trial']>0 and x['self_evicted_ms']==0:
            groups[(x['shape'],x['cols'])].append(x)
    out['operators'][run]=[{'shape':k[0],'cols':k[1], 'packed':v[0]['packed'], 'bank_bytes':v[0]['copies']*v[0]['bytes'],
                           'ms_per_call':stats([x['ms_per_call'] for x in v]),'logical_GB_s':stats([x['logical_GB_s'] for x in v])}
                          for k,v in groups.items()]
for shape in ('qkv','gate','out'):
    path=r/'operators'/('projection-'+shape)/'stdout'
    if not path.exists():continue
    rows=[x for x in lines(path) if x['kind']=='timing' and x['group']==8 and x['round']>0]
    ms=st.median(x['ms'] for x in rows);x=rows[0]
    out['operators']['projection-'+shape]={'ms':stats([x['ms'] for x in rows]),
        'matrix_TFLOP_s':2*x['m']*x['n']*x['k']/ms/1e9,
        'source_group':8, 'm':x['m'],'n':x['n'],'k':x['k']}
out['runtime_inventory_summary']={k:v for k,v in inv.items() if k not in ('tensors','input_sha256')}
out['limits']=['Window counts include native prelude/restore evaluations, not only emitting decode windows.',
               'Logical unique weight inventory is an optimistic single-stream model, not measured DRAM traffic.',
               '242 GB/s is empirical read calibration; 256 GB/s is conditional nominal bandwidth from firmware 8000 MT/s and 256-bit width.',
               'Neither weight-only time nor register-only matrix throughput is an attainable end-to-end bound.',
               'Projection control repeats share buffers. Q8 replays rotate a >=128 MiB weight bank.',
               'Calibration medians exclude warmup and self-evicted samples. Projection timings need separate telemetry review.']
a.out.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'routes':out['routes'],'operator_groups':list(out['operators'])}))
