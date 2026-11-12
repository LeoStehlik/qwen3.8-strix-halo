#!/usr/bin/env python3
"""Link the operator replay against an already built, recorded Strata worktree."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--sdk', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
a.source, a.sdk, a.out = a.source.resolve(), a.sdk.resolve(), a.out.resolve()
a.out.mkdir(parents=True, exist_ok=False)
probe = Path(__file__).with_name('q8.cpp').resolve()
libs = [a.source / 'build-halo-lab' / n for n in ('libstrata_kernels.a', 'libstrata_core.a')]
cmd = [str(a.sdk / 'lib/llvm/bin/clang++'), '-O3', '-std=c++17', '-DNDEBUG',
       '--rocm-path=' + str(a.sdk), '--offload-arch=gfx1151',
       '-DSTRATA_USE_HIP=1', '-D__HIP_PLATFORM_AMD__=1',
       '-I' + str(a.source / 'include'), '-I' + str(a.source / 'include/strata/hip_compat'),
       '-I' + str(a.sdk / 'include'), '-include', str(a.source / 'include/strata/hip_compat/cuda_runtime.h'),
       str(probe), *map(str, libs), '-L' + str(a.sdk / 'lib'), '-lamdhip64',
       '-Wl,-rpath,' + str(a.sdk / 'lib'), '-o', str(a.out / 'q8')]
meta = {'argv': cmd, 'source_commit': subprocess.check_output(['git', '-C', str(a.source), 'rev-parse', 'HEAD'], text=True).strip(),
        'sha256': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in [probe, *libs]}}
subprocess.run(cmd, check=True)
meta['binary_sha256'] = hashlib.sha256((a.out / 'q8').read_bytes()).hexdigest()
(a.out / 'build.json').write_text(json.dumps(meta, indent=2) + '\n')
