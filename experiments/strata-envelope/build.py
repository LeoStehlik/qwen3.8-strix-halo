#!/usr/bin/env python3
"""Build independent gfx1151 calibration; do not replace the serving engine."""
import argparse, hashlib, json, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--sdk',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args();a.sdk=a.sdk.resolve();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
source=Path(__file__).with_name('calibrate.hip').resolve()
cmd=[str(a.sdk/'lib/llvm/bin/clang++'),'-x','hip','-std=c++20','-O3','--offload-arch=gfx1151',
     '--rocm-path='+str(a.sdk),'--rocm-device-lib-path='+str(a.sdk/'lib/llvm/amdgcn/bitcode'),
     str(source),'-L'+str(a.sdk/'lib'),'-lamdhip64','-Wl,-rpath,'+str(a.sdk/'lib'),'-o',str(a.out/'calibrate')]
meta={'argv':cmd,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
(a.out/'build.json').write_text(json.dumps(meta,indent=2)+'\n')
subprocess.run(cmd,check=True)
meta['binary_sha256']=hashlib.sha256((a.out/'calibrate').read_bytes()).hexdigest()
(a.out/'build.json').write_text(json.dumps(meta,indent=2)+'\n')
