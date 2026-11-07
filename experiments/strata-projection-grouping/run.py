#!/usr/bin/env python3
"""Run an isolated operator probe while the unchanged server is idle."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--profile',type=Path,required=True)
ap.add_argument('--sdk',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--rounds',type=int,default=31)
a=ap.parse_args();a.out=a.out.resolve();a.sdk=a.sdk.resolve()
assert a.rounds>0
cfg=json.loads(a.profile.read_text())
url=f"http://{cfg['host']}:{cfg['port']}"
def metrics():
    req=urllib.request.Request(url+'/metrics',headers={'Authorization':'Bearer '+cfg['api_key']})
    with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
def host():
    counters={}
    for p in Path('/sys/class/kfd/kfd/proc').glob('*/stats_*/evicted_ms'):
        try:counters[p.parent.parent.name+'/'+p.parent.name]=int(p.read_text())
        except OSError:pass
    return {'unix_s':time.time(),'kfd_evicted_ms':counters,
            'sclk':Path('/sys/class/drm/card0/device/pp_dpm_sclk').read_text().strip(),
            'clock_policy':Path('/sys/class/drm/card0/device/power_dpm_force_performance_level').read_text().strip()}
before=metrics();assert before['live']['state']=='idle' and not before['live'].get('queued')
base_requests=before['totals']['requests']
report={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'completed':False,
        'service_requests_before':base_requests,'host_before':host(),'arms':[]}
def save():
    text=json.dumps(report,indent=2)+'\n';assert cfg['api_key'] not in text
    (a.out/'run.json').write_text(text)
assert not (a.out/'run.json').exists(),'Use a new directory/run; do not overwrite evidence'
save()
env=os.environ.copy();env['LD_LIBRARY_PATH']=f'{a.sdk}/lib:{a.sdk}/lib/rocm_sysdeps/lib:{a.sdk}/lib/llvm/lib'
stop=threading.Event()
def sample():
    with (a.out/'telemetry.jsonl').open('w') as output:
        while not stop.is_set():
            row=host()
            try:
                m=metrics();row.update(live=m['live'],requests=m['totals']['requests'],hardware=m['hardware'])
            except Exception as e:row['error']=type(e).__name__
            output.write(json.dumps(row)+'\n');output.flush();stop.wait(1)
sampler=threading.Thread(target=sample,daemon=True);sampler.start()
try:
    for label,args in [('correctness',['--check']),('gdn-qkv',['10240','2560','0',str(a.rounds)]),
                       ('gdn-gate',['6144','2560','0',str(a.rounds)]),('out-projection',['2560','6144','64',str(a.rounds)])]:
        m=metrics()
        assert m['live']['state']=='idle' and not m['live'].get('queued') and m['totals']['requests']==base_requests,'Actual traffic arrived; no further operator runs'
        cmd=[str(a.out/'grouping'),*args]
        row={'label':label,'argv':cmd,'start':host()};report['arms'].append(row);save()
        print(json.dumps({'event':'start','label':label}),flush=True)
        with (a.out/(label+'.jsonl')).open('w') as out,(a.out/(label+'.stderr')).open('w') as err:
            p=subprocess.Popen(cmd,env=env,stdout=out,stderr=err);row['pid']=p.pid;save();code=p.wait()
        row.update(exit_code=code,end=host());save();assert code==0,f'{label} exited {code}'
        print(json.dumps({'event':'complete','label':label}),flush=True)
    after=metrics();report['service_requests_after']=after['totals']['requests'];report['serving_state_after']=after['live']['state']
    assert after['totals']['requests']==base_requests and after['live']['state']=='idle','Timing contaminated by serving traffic'
    report['completed']=True
except BaseException as e:
    report['error']=f'{type(e).__name__}: {e}';raise
finally:
    stop.set();sampler.join(10);report['host_after']=host();save()
