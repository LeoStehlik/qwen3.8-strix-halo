#!/usr/bin/env python3
"""Summarize the scheduling screen without converting operator gains to tok/s."""
import argparse
import json
from pathlib import Path
import statistics

ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('directory',type=Path);a=ap.parse_args()
run=json.loads((a.directory/'run.json').read_text());assert run['completed']
assert run['service_requests_before']==run['service_requests_after']
build=json.loads((a.directory/'build.json').read_text())
row_stream=build.get('row_stream_candidate',False)
tiles=build.get('tile_candidates',False)
report={'shapes':{},'cpu_reference_checks':[],'gpu_parity_checks':0,'gpu_elements_compared':0,
        'comparison_kind':'tile_shapes' if tiles else 'fragment_load_order' if row_stream else 'block_grouping',
        'variant_labels':{'8':'128x256 K64, 256 threads, control','128':'128x128 K64, 256 threads','512':'128x512 K32, 512 threads'} if tiles else
                         {'8':'existing group 8 control','99':'row-stream fragments, still group 8'} if row_stream else {},
        'decision':'Tile screen only; inspect resources and repeat any winner before integration.' if tiles else
                   'Fragment-load scheduling rejected as neutral; resources unchanged.' if row_stream else
                   'No scheduling selector promoted; best operator median gains are small and have no full-model confirmation.'}
for name in ['correctness','gdn-qkv','gdn-gate','out-projection']:
    rows=[json.loads(s) for s in (a.directory/(name+'.jsonl')).read_text().splitlines()]
    for r in rows:
        if r['kind']=='cpu_reference':
            assert r['failures']==0;report['cpu_reference_checks'].append(r)
        elif r['kind']=='parity':
            assert r['mismatches']==0;report['gpu_parity_checks']+=1;report['gpu_elements_compared']+=r['elements']
    samples=[r for r in rows if r['kind']=='timing']
    if not samples:continue
    data={g:[r['ms'] for r in samples if r['group']==g] for g in sorted({r['group'] for r in samples})}
    control=statistics.median(data[8]);summary={}
    for group,values in data.items():
        med=statistics.median(values)
        summary[str(group)]={'samples':len(values),'median_ms':med,'min_ms':min(values),'max_ms':max(values),
                             'operator_speedup_pct':100*(control/med-1)}
    report['shapes'][name]={'m':samples[0]['m'],'n':samples[0]['n'],'k':samples[0]['k'],
                          'x_padding':samples[0]['xpad'],'weight_padding':64,'groups':summary}
report['limits']=['Synthetic values at real matrix dimensions, not captured model activations.',
                  'Same-source operator control; not an installed-package throughput comparison.',
                  'GPU event samples include scheduling stalls; medians do not remove their end-to-end cost.',
                  'Full output comparison is to GPU group 8; independent CPU tolerance is tested only at two smaller boundary shapes.',
                  'No full model, checkpoint, tool continuation or cross-backend validation; no serving change.']
(a.directory/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'gpu_parity_checks':report['gpu_parity_checks'],'gpu_elements_compared':report['gpu_elements_compared'],
                  'best_operator_speedup_pct':{name:max(g['operator_speedup_pct'] for g in row['groups'].values()) for name,row in report['shapes'].items()}}))
