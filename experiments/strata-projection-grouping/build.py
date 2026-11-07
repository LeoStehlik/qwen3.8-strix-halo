#!/usr/bin/env python3
"""Build an isolated scheduling probe from the pinned, unmodified kernel."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source',type=Path,required=True)
ap.add_argument('--sdk',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--row-stream',action='store_true',help='Add the isolated fragment-load scheduling candidate')
a=ap.parse_args()
a.source=a.source.resolve();a.sdk=a.sdk.resolve();a.out=a.out.resolve()
a.out.mkdir(parents=True,exist_ok=True)
kernel=a.source/'src/prefill/wmma_gemm.cu'
raw=kernel.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='eca51cd8a3cdd63690fb47bdb267dfaf4f721b3f0e2786b3ffc4f45ae5487860', 'Unexpected source kernel'
text=raw.decode()
marker='__global__ void __launch_bounds__(256) kernel_bk64('
assert text.count(marker)==1
text=text.replace(marker,'template<int GROUP_M>\n'+marker)
start=text.index(marker);body=text.index('    constexpr int BN = 256, WN = 64, BK64 = 64, LDK64 = BK64 + 8;',start)
text=text[:body]+'    constexpr int GM = GROUP_M;\n'+text[body:]
assert text.count('pfg::kernel_bk64<<<')==1
text=text.replace('pfg::kernel_bk64<<<','pfg::kernel_bk64<8><<<')
if a.row_stream:
    original=raw.decode()
    start=original.index(marker);end=original.index('// S23 (STRATA_PF_HCDOWN=1)',start)
    candidate=original[start:end].replace('kernel_bk64(', 'kernel_bk64_rowstream(',1)
    operands='''            const h16 a0 = frag(&sA[ar][ks]), a1 = frag(&sA[ar + 16][ks]), a2 = frag(&sA[ar + 32][ks]),
                      a3 = frag(&sA[ar + 48][ks]);
'''
    assert candidate.count(operands)==1
    candidate=candidate.replace(operands,'')
    calls='            PFG_ROW(0, a0) PFG_ROW(1, a1) PFG_ROW(2, a2) PFG_ROW(3, a3)'
    assert candidate.count(calls)==1
    candidate=candidate.replace(calls,'''            { const h16 a = frag(&sA[ar][ks]); PFG_ROW(0, a) }
            { const h16 a = frag(&sA[ar + 16][ks]); PFG_ROW(1, a) }
            { const h16 a = frag(&sA[ar + 32][ks]); PFG_ROW(2, a) }
            { const h16 a = frag(&sA[ar + 48][ks]); PFG_ROW(3, a) }''')
    insertion=text.index('// S23 (STRATA_PF_HCDOWN=1)')
    text=text[:insertion]+candidate+text[insertion:]
generated=a.out/'wmma_gemm_grouping.generated.cuh';generated.write_text(text)
env=os.environ.copy()
env.update(ROCM_PATH=str(a.sdk),HIP_PATH=str(a.sdk),HIP_PLATFORM='amd',
           LD_LIBRARY_PATH=f'{a.sdk}/lib:{a.sdk}/lib/rocm_sysdeps/lib:{a.sdk}/lib/llvm/lib',
           PATH=f'{a.sdk}/bin:{a.sdk}/lib/llvm/bin:'+env['PATH'])
cmd=[str(a.sdk/'bin/hipcc'),'-O3','-std=c++17','--offload-arch=gfx1151','-DSTRATA_WMMA_GFX11=1','-DSTRATA_USE_HIP=1',
     '-I'+str(a.source/'include'),'-I'+str(a.source/'src/prefill'),'-I'+str(a.out),
     '-x','hip',str(Path(__file__).with_name('grouping.hip').resolve()),'-o',str(a.out/'grouping')]
if a.row_stream:cmd.insert(1,'-DPROJECTION_ROW_STREAM=1')
meta={'argv':cmd,'source_sha256':hashlib.sha256(raw).hexdigest(),
      'generated_sha256':hashlib.sha256(generated.read_bytes()).hexdigest(),
      'probe_sha256':hashlib.sha256(Path(__file__).with_name('grouping.hip').read_bytes()).hexdigest(),
      'change':'Only template the BK64 kernel block-group size; preserve GM=8 for its original wrapper.',
      'row_stream_candidate':a.row_stream}
with (a.out/'build.stdout').open('w') as out,(a.out/'build.stderr').open('w') as err:
    result=subprocess.run(cmd,env=env,stdout=out,stderr=err)
meta['exit_code']=result.returncode
if not result.returncode:meta['binary_sha256']=hashlib.sha256((a.out/'grouping').read_bytes()).hexdigest()
(a.out/'build.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps({'exit_code':result.returncode,'out':str(a.out)}),flush=True)
raise SystemExit(result.returncode)
