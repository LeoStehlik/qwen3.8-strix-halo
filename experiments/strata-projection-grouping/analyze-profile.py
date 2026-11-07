#!/usr/bin/env python3
"""Aggregate projection counters and selected-SIMD ATT without wall-time claims."""
import argparse
import collections
import csv
import json
from pathlib import Path
import statistics

ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('directory',type=Path);a=ap.parse_args()
report={'counter_shapes':{},'att':{},'limits':[
    'L2 external request bytes are not direct DRAM traffic; gfx1151 also has an L3 cache.',
    'Counter passes serialize/instrument dispatches; use the untraced screen for operator timings.',
    'ATT covers one dispatch, one WGP and one selected SIMD per shape, not whole-GPU occupancy.',
    'Summed instruction latencies overlap across waves and are not wall-time percentages or additive speedup predictions.']}
for shape,expected_waves in [('qkv',40960),('gate',24576),('out',10240)]:
    entry={'passes':{}}
    for mode in ['memory','cache','alu']:
        d=a.directory/(shape+'-'+mode)
        cmd=json.loads((d/'command.json').read_text());assert cmd['exit_code']==0 and cmd['serving_requests_before']==cmd['serving_requests_after']
        rows=list(csv.DictReader((d/'projection_counter_collection.csv').open()));groups={}
        for r in rows:
            assert 'kernel_bk64<8>' in r['Kernel_Name']
            g=groups.setdefault(r['Dispatch_Id'],{'duration_ms':(int(r['End_Timestamp'])-int(r['Start_Timestamp']))/1e6})
            g[r['Counter_Name']]=float(r['Counter_Value'])
        assert len(groups)==5
        invalid=[]
        for dispatch,g in groups.items():
            if mode in ('memory','cache') and g['SQ_WAVES_sum']!=expected_waves:
                invalid.append(dispatch)
                g['invalid_reason']='Wave count does not match launch geometry; counters unusable'
                continue
            if mode=='alu' and g['SQ_BUSY_CYCLES']==0:
                invalid.append(dispatch)
                g['invalid_reason']='Zero busy cycles; counters unusable'
                continue
            if mode=='memory':
                g['l2_external_read_bytes']=sum(g.get(f'GL2C_EA_RDREQ_{n}B_sum',0)*n for n in [32,64,128])
                g['l2_external_write_bytes']=g['GL2C_EA_WRREQ_64B_sum']*64
                g['l2_external_GB_s']=(g['l2_external_read_bytes']+g['l2_external_write_bytes'])/g['duration_ms']/1e6
            if mode=='cache':
                assert g['GL2C_EA_RDREQ_96B_sum']==0
                g['l2_hit_pct']=100*g['GL2C_HIT_sum']/(g['GL2C_HIT_sum']+g['GL2C_MISS_sum'])
        valid=[g for dispatch,g in groups.items() if dispatch not in invalid];assert len(valid)>=3
        entry['passes'][mode]={'dispatches':groups,'invalid_dispatch_ids':invalid,'valid_dispatches':len(valid),
                              'medians':{k:statistics.median(g[k] for g in valid) for k in valid[0]}}
        entry['resources']={k:int(rows[0][k]) for k in ['LDS_Block_Size','Scratch_Size','VGPR_Count','SGPR_Count','Workgroup_Size']}
    report['counter_shapes'][shape]=entry
for shape in ['qkv','out']:
    d=a.directory/(shape+'-att');rows=list(csv.DictReader(next(d.glob('stats_*.csv')).open(),skipinitialspace=True))
    groups=collections.defaultdict(collections.Counter)
    for r in rows:
        inst=r['Instruction'];op=inst.split()[0] if inst else ''
        category=('wmma' if 'wmma' in op else 'vector_memory_wait' if op=='s_waitcnt' and 'vmcnt' in inst else
                  'lds_wait' if op=='s_waitcnt' and 'lgkmcnt' in inst else 'barrier' if op=='s_barrier' else
                  'lds' if op.startswith('ds_') else 'global_memory' if op.startswith(('global_','buffer_','flat_')) else
                  'vector_alu' if op.startswith('v_') else 'scalar_other' if op.startswith('s_') else 'other')
        for col in ['Hitcount','Latency','Stall','Idle']:groups[category][col]+=int(r[col])
    total=sum(g['Latency'] for g in groups.values())
    for g in groups.values():g['fraction_of_summed_latency']=g['Latency']/total
    events=[];waves=[]
    for p in d.glob('ui*/se0_sm0_sl*_wv*.json'):
        w=json.loads(p.read_text())['wave'];waves.append({'begin':w['begin'],'end':w['end'],'cu':w['cu'],'id':w['id']})
        events.extend([(w['begin'],1),(w['end'],-1)])
    events.sort();pop=0;last=events[0][0];duration=collections.Counter()
    for t,change in events:duration[pop]+=t-last;last=t;pop+=change
    span=events[-1][0]-events[0][0]
    report['att'][shape]={'groups':groups,'summed_instruction_latency':total,'wave_count':len(waves),
                         'selected_simd_peak_waves':max(duration),'selected_simd_time_weighted_waves':sum(k*v for k,v in duration.items())/span,
                         'residency_cycles_by_wave_count':duration,'wave_intervals':waves,
                         'top_latency_instructions':sorted(rows,key=lambda x:int(x['Latency']),reverse=True)[:12]}
report['counter_samples']=sum(len(p['dispatches']) for s in report['counter_shapes'].values() for p in s['passes'].values())
report['valid_counter_samples']=sum(p['valid_dispatches'] for s in report['counter_shapes'].values() for p in s['passes'].values())
(a.directory/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'counter_dispatches':report['counter_samples'],'valid_counter_samples':report['valid_counter_samples'],
                  'att_waves':{k:v['wave_count'] for k,v in report['att'].items()},
                  'selected_simd_peak_waves':{k:v['selected_simd_peak_waves'] for k,v in report['att'].items()}}))
