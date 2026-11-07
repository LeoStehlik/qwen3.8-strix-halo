#!/usr/bin/env python3
"""Profile group 8 of the existing projection probe; leave serving unchanged."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--binary',type=Path,required=True);ap.add_argument('--sdk',type=Path,required=True)
ap.add_argument('--profile',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--modes',nargs='+',choices=['memory','cache','alu','att'],default=['memory','cache','alu'])
ap.add_argument('--shapes',nargs='+',choices=['qkv','gate','out'],default=['qkv','gate','out'])
a=ap.parse_args();a.out=a.out.resolve();a.sdk=a.sdk.resolve();a.binary=a.binary.resolve()
a.out.mkdir(parents=True,exist_ok=True)
cfg=json.loads(a.profile.read_text());url=f"http://{cfg['host']}:{cfg['port']}"
def idle():
    req=urllib.request.Request(url+'/metrics',headers={'Authorization':'Bearer '+cfg['api_key']})
    with urllib.request.urlopen(req,timeout=5) as r:m=json.load(r)
    assert m['live']['state']=='idle' and not m['live'].get('queued'),'Serving is busy'
    return m['totals']['requests']
requests=idle()
settings={'ROCM_PATH':str(a.sdk),'HIP_PATH':str(a.sdk),'HIP_PLATFORM':'amd',
          'LD_LIBRARY_PATH':f'{a.sdk}/lib:{a.sdk}/lib/rocm_sysdeps/lib:{a.sdk}/lib/llvm/lib'}
env={**os.environ,**settings}
counters={'memory':['GL2C_EA_RDREQ_32B_sum','GL2C_EA_RDREQ_64B_sum','GL2C_EA_RDREQ_128B_sum','GL2C_EA_WRREQ_64B_sum','SQ_WAVES_sum'],
          'cache':['GL2C_HIT_sum','GL2C_MISS_sum','GL2C_EA_RDREQ_96B_sum','SQ_WAVES_sum'],
          'alu':['SQ_INSTS_VALU','SQ_INSTS_LDS','SQ_INSTS_SALU','SQ_BUSY_CYCLES']}
shapes={'qkv':['10240','2560','0'],'gate':['6144','2560','0'],'out':['2560','6144','64']}
for shape in a.shapes:
    for mode in a.modes:
        assert idle()==requests,'Actual requests arrived; stop profiling'
        directory=a.out/(shape+'-'+mode);directory.mkdir(exist_ok=False)
        cmd=[str(a.sdk/'bin/rocprofv3')]
        if mode=='att':
            cmd+=['--att','--att-target-cu','1','--att-simd-select','0','--att-buffer-size','0x10000000',
                  '--kernel-iteration-range','3']
        else:
            cmd+=['--kernel-trace','--pmc',*counters[mode],'--output-format','csv','--kernel-iteration-range','3-7']
        cmd+=['--kernel-include-regex','.*kernel_bk64<8>.*','-d',str(directory),'-o','projection',
              '--',str(a.binary),*shapes[shape],'1' if mode=='att' else '5']
        record={'argv':cmd,'env':settings,'binary_sha256':hashlib.sha256(a.binary.read_bytes()).hexdigest(),
                'cwd':str(directory),
                'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'serving_requests_before':requests}
        def save():
            text=json.dumps(record,indent=2)+'\n';assert cfg['api_key'] not in text
            (directory/'command.json').write_text(text)
        save();print(json.dumps({'event':'start','shape':shape,'mode':mode}),flush=True)
        with (directory/'stdout').open('w') as out,(directory/'stderr').open('w') as err:
            result=subprocess.run(cmd,env=env,cwd=directory,stdout=out,stderr=err)
        record.update(exit_code=result.returncode,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      serving_requests_after=idle());save()
        assert result.returncode==0,'Profiler command failed; inspect evidence'
        assert record['serving_requests_after']==requests,'Timing contaminated by serving traffic'
        print(json.dumps({'event':'complete','shape':shape,'mode':mode}),flush=True)
