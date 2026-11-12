#!/usr/bin/env python3
"""Guard standalone calibration with serving-idle and host telemetry checks."""
import argparse, hashlib, json, os, subprocess, time, urllib.request
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for x in ('binary','profile','out'):p.add_argument('--'+x,type=Path,required=True)
p.add_argument('--mode',choices=('all','memory','compute'),default='all')
a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
cfg=json.loads(a.profile.read_text());url=f"http://{cfg['host']}:{cfg['port']}"
def state():
    r=urllib.request.Request(url+'/metrics',headers={'Authorization':'Bearer '+cfg['api_key']})
    with urllib.request.urlopen(r,timeout=5) as f:m=json.load(f)
    return {'requests':m['totals']['requests'],'live':m['live'],'hardware':m['hardware']}
def host():
    values={'unix_s':time.time(),'monotonic_ns':time.monotonic_ns(),'serving':state()}
    for name in ('meminfo','vmstat'):values[name]=dict(x.split()[:2] for x in Path('/proc',name).read_text().splitlines())
    values['evicted_ms']={str(p.parent.parent.name)+'/'+p.parent.name:int(p.read_text()) for p in Path('/sys/class/kfd/kfd/proc').glob('*/stats_*/evicted_ms')}
    return values
before=host();assert before['serving']['live']['state']=='idle' and not before['serving']['live']['queued']
cmd=[str(a.binary.resolve()),a.mode]
meta={'argv':cmd,'binary_sha256':hashlib.sha256(a.binary.read_bytes()).hexdigest(),'before':before,
      'limits':['Requested memory bytes are not measured DRAM traffic.','Register compute probes omit real kernel loads and unpacking.']}
def save():
    raw=json.dumps(meta,indent=2)+'\n';assert cfg['api_key'] not in raw;(a.out/'run.json').write_text(raw)
save();proc=None
try:
    with (a.out/'samples.jsonl').open('w') as out,(a.out/'stderr').open('w') as err,(a.out/'telemetry.jsonl').open('w') as tel:
        proc=subprocess.Popen(cmd,stdout=out,stderr=err,cwd=a.out)
        while proc.poll() is None:
            h=host();tel.write(json.dumps(h)+'\n');tel.flush()
            assert h['serving']['requests']==before['serving']['requests'] and h['serving']['live']['state']=='idle','Serving traffic arrived'
            time.sleep(0.5)
        meta['exit_code']=proc.returncode
        assert proc.returncode==0,'Calibration failed; raw output retained'
    meta['after']=host()
    assert meta['after']['serving']['requests']==before['serving']['requests']
    meta['completed']=True
finally:
    if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=20)
    save()
print(json.dumps({'completed':True,'out':str(a.out)}))
