#!/usr/bin/env python3
"""Run a fixed standalone measurement plan, restoring the idle service in finally."""
import argparse,hashlib,json,os,signal,subprocess,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for n in ('profile','plan','out'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--unit',default='strata-flash-next.service')
a=p.parse_args();os.umask(0o077);a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
raw=a.profile.read_bytes();cfg=json.loads(raw);plan=json.loads(a.plan.read_text())
url=f"http://{cfg['host']}:{cfg['port']}"
def api(path):
 r=urllib.request.Request(url+path,headers={'Authorization':'Bearer '+cfg['api_key']})
 with urllib.request.urlopen(r,timeout=5) as f:return json.load(f)
def service(action):subprocess.run(['systemctl','--user',action,a.unit],check=True)
def host():
 vm=dict(x.split() for x in Path('/proc/vmstat').read_text().splitlines())
 d={'time':time.time(),'swap':{k:int(vm[k]) for k in ('pswpin','pswpout')},'evicted_ms':{}}
 for q in Path('/sys/class/kfd/kfd/proc').glob('*/stats_*/evicted_ms'):
  try:d['evicted_ms'][str(q.parent.parent.name)+'/'+q.parent.name]=int(q.read_text())
  except FileNotFoundError:pass
 for q in Path('/sys/class/drm/card0/device/hwmon').glob('hwmon*/temp*_input'):
  d[q.name]=int(q.read_text())
 return d
m=api('/metrics');assert m['live']['state']=='idle' and not m['live']['queued']
for step in plan:assert Path(step['argv'][0]).is_file()
meta={'profile_sha256':hashlib.sha256(raw).hexdigest(),'before_requests':m['totals']['requests'],'plan':plan,'completed':False,'steps':[]}
def save():
 s=json.dumps(meta,indent=2)+'\n';assert cfg['api_key'] not in s;(a.out/'summary.json').write_text(s)
save();proc=None
def interrupted(signum,frame):raise KeyboardInterrupt(f'signal {signum}')
signal.signal(signal.SIGTERM,interrupted)
try:
 service('stop');print(json.dumps({'event':'service_stopped'}),flush=True)
 for step in plan:
  directory=a.out/step['name'];directory.mkdir()
  item={'name':step['name'],'before':host(),'argv':step['argv']};meta['steps'].append(item);save()
  print(json.dumps({'event':'start','step':step['name']}),flush=True)
  with (directory/'stdout').open('w') as out,(directory/'stderr').open('w') as err,(directory/'telemetry.jsonl').open('w') as tel:
   proc=subprocess.Popen(step['argv'],env={**os.environ,**step.get('env',{})},cwd=directory,stdout=out,stderr=err)
   start=time.monotonic()
   while proc.poll() is None:
    tel.write(json.dumps(host())+'\n');tel.flush()
    assert time.monotonic()-start<step.get('timeout',600),'Measurement timeout'
    time.sleep(0.5)
   item.update(exit_code=proc.returncode,elapsed_s=time.monotonic()-start,after=host());save()
   assert proc.returncode==0,'Measurement failed; output retained'
  print(json.dumps({'event':'complete','step':step['name']}),flush=True)
 meta['completed']=True
except BaseException as exc:
 meta['error']=type(exc).__name__+': '+str(exc)
 raise
finally:
 if proc and proc.poll() is None:
  proc.terminate()
  try:proc.wait(timeout=20)
  except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=20)
 start=time.monotonic();service('start')
 while time.monotonic()-start<360:
  try:
   h=api('/health')
   if h.get('loaded'):
    meta['restoration']={'load_s':time.monotonic()-start,'health':h,'profile_unchanged':a.profile.read_bytes()==raw};break
  except (OSError,ValueError):pass
  time.sleep(2)
 save();assert meta.get('restoration',{}).get('health',{}).get('loaded'),'Restoration failed'
 assert a.profile.read_bytes()==raw,'Persistent profile changed'
 print(json.dumps({'event':'restored','completed':meta['completed']}),flush=True)
