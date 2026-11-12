#!/usr/bin/env python3
"""Build conditional planning budgets from published control window accounting."""
import argparse
import json
from pathlib import Path
import re

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--control',type=Path,required=True)
p.add_argument('--analysis',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args();control=json.loads(a.control.read_text());analysis=json.loads(a.analysis.read_text())
result={'protocol':'strata-conditional-time-budget-v1','contexts':[],
        'limits':['Weight-only scenarios omit state/activation/compute costs and assume one stream of each logical weight payload.',
                  'They preserve observed acceptance and serial draft timing, and are not physical ceilings.',
                  'The 49K control has two native output segments and 18 frontend-injected tokens excluded from native throughput.',
                  'Cold prefill uses only the first uncached segment, not the cached continuation.']}
for target,group,reports in zip((49152,196608),control['groups'][1:],((2,3),(4,))):
    details=[]
    for s in group:
        line=s['timing_line'];n=int(re.search(r': (\d+) windows',line)[1]);v=float(re.search(r'\+ verify ([\d.]+)',line)[1]);d=float(re.search(r'\+ draft ([\d.]+)',line)[1])
        details.append((n,v,d))
    windows=sum(x[0] for x in details);emitted=sum(x['generated'] for x in group);perwindow=emitted/windows
    verify=sum(n*v for n,v,d in details)/windows;draft=sum(n*d for n,v,d in details)/windows
    route=[x for x in analysis['routes'] if x['native_report'] in reports]
    payload=sum(x['windows']*x['dense_plus_distinct_expert_payload_bytes_per_window'] for x in route)/sum(x['windows'] for x in route)
    cold=group[0];entry={'nominal_context':target,'windows':windows,'native_emitted_tokens':emitted,'outputs_per_window':perwindow,
        'verify_ms':verify,'draft_ms':draft,'native_decode_tok_s':emitted/sum(x['decode_ms'] for x in group)*1000,
        'weight_payload_bytes_per_window':payload,'decode_targets':[],'weight_only_scenarios':[],
        'cold_prefill':{'tokens':cold['read'],'ms':cold['prefill_ms'],'tok_s':cold['read']/cold['prefill_ms']*1000,'targets':[]}}
    for rate in (50,60,70):
        total=1000*perwindow/rate;allowed=total-draft
        entry['decode_targets'].append({'tok_s':rate,'total_ms':total,'verify_ms_with_current_draft':allowed,'verify_time_reduction_fraction':1-allowed/verify})
    for bw in (242,248,256):
        weight_ms=payload/(bw*1e6)
        entry['weight_only_scenarios'].append({'logical_GB_s':bw,'weight_ms':weight_ms,'with_current_draft_tok_s':1000*perwindow/(weight_ms+draft)})
    for rate in (1700,2000):
        ms=cold['read']/rate*1000
        entry['cold_prefill']['targets'].append({'tok_s':rate,'ms':ms,'save_ms':cold['prefill_ms']-ms})
    result['contexts'].append(entry)
a.out.write_text(json.dumps(result,indent=2)+'\n')
