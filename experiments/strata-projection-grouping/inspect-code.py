#!/usr/bin/env python3
"""Extract compiled projection kernel instructions and allocation metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--binary',type=Path,required=True);ap.add_argument('--sdk',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True);ap.add_argument('--expected-control-sha256')
a=ap.parse_args();a.binary=a.binary.resolve();a.sdk=a.sdk.resolve();a.out=a.out.resolve()
a.out.mkdir(parents=True,exist_ok=True);llvm=a.sdk/'lib/llvm/bin';commands=[]
def run(argv,path=None):
    commands.append(list(map(str,argv)))
    if path:
        with path.open('w') as f:subprocess.run(argv,stdout=f,check=True)
    else:subprocess.run(argv,check=True)
run([llvm/'llvm-objcopy','--dump-section',f'.hip_fatbin={a.out}/device.fatbin',a.binary])
run([llvm/'clang-offload-bundler','--type=o','--unbundle',f'--input={a.out}/device.fatbin',
     '--targets=hipv4-amdgcn-amd-amdhsa--gfx1151',f'--output={a.out}/device.co'])
run([llvm/'llvm-objdump','-d',a.out/'device.co'],a.out/'device.isa')
run([llvm/'llvm-readelf','--notes',a.out/'device.co'],a.out/'device.metadata')
isa=(a.out/'device.isa').read_text();metadata=(a.out/'device.metadata').read_text()
sections=re.split(r'^([0-9a-f]+ <[^>]+>:)\s*$',isa,flags=re.M);kernels={}
for label,fragment in [('control','kernel_bk64ILi8'),('narrow','kernel_tileILb0'),('wide','kernel_tileILb1'),('rowstream','kernel_bk64_rowstream')]:
    for i in range(1,len(sections),2):
        if fragment not in sections[i]:continue
        instructions=[l.split('//',1)[0].strip() for l in sections[i+1].splitlines() if re.search(r'// [0-9A-Fa-f]+:',l)]
        kernels[label]={'symbol':sections[i],'instruction_count':len(instructions),
                        'instruction_sha256':hashlib.sha256('\n'.join(instructions).encode()).hexdigest()}
        (a.out/(label+'.isa')).write_text('\n'.join(instructions)+'\n')
    if label not in kernels:continue
    for block in metadata.split('  - .args:'):
        if re.search(r'\.name:.*'+fragment,block):
            kernels[label]['resources']={m.group(1):int(m.group(2)) for m in re.finditer(
                r'^    \.(group_segment_fixed_size|private_segment_fixed_size|vgpr_count|sgpr_count|vgpr_spill_count|sgpr_spill_count|workgroup_processor_mode|wavefront_size|max_flat_workgroup_size):\s*(\d+)$',block,re.M)}
result={'commands':commands,'binary_sha256':hashlib.sha256(a.binary.read_bytes()).hexdigest(),'kernels':kernels}
if a.expected_control_sha256:
    result['expected_control_sha256']=a.expected_control_sha256
    result['control_unchanged']=kernels['control']['instruction_sha256']==a.expected_control_sha256
(a.out/'code-inspection.json').write_text(json.dumps(result,indent=2)+'\n')
if a.expected_control_sha256:assert result['control_unchanged'],'Control instructions changed'
print(json.dumps({k:v['resources'] for k,v in kernels.items()}))
