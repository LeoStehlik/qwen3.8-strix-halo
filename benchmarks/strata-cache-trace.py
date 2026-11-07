#!/usr/bin/env python3
"""Summarize public off/on/off cache traces, retaining nested-timing caveats."""
import argparse
import json,re
from pathlib import Path
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--root', type=Path, required=True)
ap.add_argument('--out', type=Path)
args=ap.parse_args()
root=args.root
arms={}
for name in ['off1','on1','off2']:
 p=root/name
 if not (p/'engine.log').exists():continue
 groups=[];cur=None
 for line in (p/'engine.log').read_text().splitlines():
  m=re.search(r'strata trace: r0 -1 -1 ([\d.]+) ms',line)
  if m:
   cur={'r0_ms':float(m[1]),'segments':[],'checkpoints':[]};groups.append(cur);continue
  if cur is None:continue
  m=re.search(r'strata trace: request (\d+) \d+ ([\d.]+) ms',line)
  if m:cur.update(prompt_tokens=int(m[1]),preparation_ms=float(m[2])-cur['r0_ms'])
  m=re.search(r'strata trace: read (\d+) tokens \(([^)]+)\) in ([\d.]+) ms',line)
  if m:cur['segments'].append({'tokens':int(m[1]),'path':m[2],'ms':float(m[3])})
  m=re.search(r'strata trace: checkpoint at (\d+): sync ([\d.]+) ms, save ([\d.]+) ms',line)
  if m:cur['checkpoints'].append({'tokens':int(m[1]),'sync_ms':float(m[2]),'save_ms':float(m[3])})
  m=re.search(r'strata trace: checkpoint at (\d+): (\d+) evicted in ([\d.]+) ms',line)
  if m:cur.setdefault('checkpoint_evictions',[]).append({'tokens':int(m[1]),'count':int(m[2]),'ms':float(m[3])})
  m=re.search(r'strata trace: prompt done \(slots refilled\) -1 -1 ([\d.]+) ms',line)
  if m:cur['prompt_total_ms']=float(m[1])-cur['r0_ms']
 groups=[g for g in groups if 'prompt_total_ms' in g]
 result=[]
 for pad in [0,16]:
  f=p/f'tail-{pad}'/'results.json'
  if not f.exists():continue
  j=json.loads(f.read_text())
  for r in j['runs']:
   matches=[g for g in groups if g['prompt_tokens']==r['prompt_tokens_offline']]
   assert len(matches)==1,(name,pad,r['turn'],len(matches))
   g=matches[0];t=r['timings'];assert abs(g['prompt_total_ms']-t['prompt_ms'])<1
   a,b=r['host_before'],r['host_after']
   result.append({'padding_rows':pad,'turn':r['turn'],'wall_s':r['elapsed_s'],
    'prefill_ms':t['prompt_ms'],'read_tokens':t['prompt_n'],'reused_tokens':t['cache_n'],
    'answer_correct':r['answer_correct'],
    'tail_tokens':r['message_boundaries'][-1]-r['message_boundaries'][-2],
    **{k:r[k] for k in ['request_sha256','rendered_sha256','output_sha256']},
    'trace':g,'kfd_evicted_delta_ms':{k:b['kfd_evicted_ms'][k]-v for k,v in a['kfd_evicted_ms'].items() if k in b['kfd_evicted_ms']},
    'vmstat_delta':{k:b['vmstat'][k]-v for k,v in a['vmstat'].items() if b['vmstat'][k]!=v}})
 arms[name]=result
j={'arms':arms,'limits':['Trace preparation and prompt total are elapsed intervals. Read segments can include periodic checkpoint saves; do not add nested timings as disjoint costs.','KFD counters are per process/GPU; vision and main-engine evictions may overlap and must not be summed as wall time.','VM counters are host-wide and cover the whole request, not an individually attributed stage.','Diagnostic trace changes logging overhead; use the earlier untraced comparison for primary warm performance.']}
complete=set(arms)=={'off1','on1','off2'} and all(len(rows)==4 for rows in arms.values())
j['complete_comparison']=complete
j['matching_hashes']={key:all(len({arms[a][i][key] for a in arms})==1 for i in range(4))
    for key in ['request_sha256','rendered_sha256','output_sha256']} if complete else None
j['all_state_canaries_correct']=all(r['answer_correct'] for rows in arms.values() for r in rows) if complete else None
(args.out or root/'trace-summary.json').write_text(json.dumps(j,indent=2)+'\n')
for name,rows in arms.items():
 for r in rows:print(name,r['padding_rows'],r['turn'],round(r['wall_s'],3),'prep_ms',round(r['trace']['preparation_ms'],1),'segments',r['trace']['segments'],'evicted_ms',r['kfd_evicted_delta_ms'])
