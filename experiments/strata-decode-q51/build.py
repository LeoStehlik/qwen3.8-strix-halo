#!/usr/bin/env python3
"""Build an isolated Q5_1 scheduling probe from pinned Strata reference code."""
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
source_file = a.source / 'src/kernels/cuda/iq_kernels.cu'
source = source_file.read_text()


def between(start, end):
    assert source.count(start) == 1, start
    lo = source.index(start)
    return source[lo:source.index(end, lo)]


def function(start):
    # The selected function has no brace-bearing strings/comments. Stop at its
    # closing brace, even if an experimental kernel follows it in a worktree.
    assert source.count(start) == 1
    lo = source.index(start)
    body = source.index('{', lo)
    depth = 0
    for i in range(body, len(source)):
        depth += (source[i] == '{') - (source[i] == '}')
        if depth == 0:
            return source[lo:i + 1] + '\n'
    raise ValueError('Unterminated reference function')


parts = [
    '#include "strata/kernels/iq_kernels.hpp"\n'
    '#include "strata/kernels/dp4a.hpp"\n'
    '#include <cuda_fp16.h>\n#include <cuda_runtime.h>\n'
    '#define GGML_COMMON_DECL_CUDA\n#include "ggml-common.h"\n'
    'using strata::kernels::NativeExpertLayout;\n'
    '#define ggml_cuda_dp4a(a,b,c) STRATA_DP4A((a),(b),(c))\n'
    'constexpr int VDR_Q5_1 = 2;\n',
    between('__device__ __forceinline__ int get_int_b4(', '__device__ __forceinline__ uint32_t unpack_ksigns'),
    between('__device__ __forceinline__ float vec_dot_q5_1_q8_1(', '// Q6_K:'),
    'template<int TY> struct Fmt;\n',
    between('template<> struct Fmt<7>', 'template<> struct Fmt<2>'),
    between('__device__ __forceinline__ float warp_sum(', 'template<int TY>\n__global__ void __launch_bounds__(128) mmvq_kernel'),
    function('template<int TD>\n__global__ void __launch_bounds__(256) native_down_kernel('),
]
reference = '\n'.join(parts)
(a.out / 'reference.hpp').write_text(reference)
probe = Path(__file__).with_name('probe.hip').resolve()
cmd = [str(a.sdk / 'lib/llvm/bin/clang++'), '-x', 'hip', '-std=c++20', '-O3', '-DNDEBUG',
       '--offload-arch=gfx1151', '--rocm-path=' + str(a.sdk),
       '--rocm-device-lib-path=' + str(a.sdk / 'lib/llvm/amdgcn/bitcode'),
       '-DSTRATA_USE_HIP=1', '-D__HIP_PLATFORM_AMD__=1',
       '-I' + str(a.source / 'include'), '-I' + str(a.source / 'include/strata/hip_compat'),
       '-I' + str(a.source / 'third_party/ggml'), '-I' + str(a.out),
       '-include', str(a.source / 'include/strata/hip_compat/cuda_runtime.h'),
       str(probe), '-L' + str(a.sdk / 'lib'), '-lamdhip64',
       '-Wl,-rpath,' + str(a.sdk / 'lib'), '-o', str(a.out / 'q51-probe')]
meta = {'source_commit': subprocess.check_output(['git', '-C', str(a.source), 'rev-parse', 'HEAD'], text=True).strip(),
        'source_file_sha256': hashlib.sha256(source_file.read_bytes()).hexdigest(),
        'reference_sha256': hashlib.sha256(reference.encode()).hexdigest(),
        'probe_sha256': hashlib.sha256(probe.read_bytes()).hexdigest(), 'argv': cmd,
        'limits': ['Standalone operator probe; not a packaged-engine replacement.',
                   'Reference expressions and kernel extracted from the recorded Strata source.']}
(a.out / 'build.json').write_text(json.dumps(meta, indent=2) + '\n')
subprocess.run(cmd, check=True)
meta['binary_sha256'] = hashlib.sha256((a.out / 'q51-probe').read_bytes()).hexdigest()
(a.out / 'build.json').write_text(json.dumps(meta, indent=2) + '\n')
print(str(a.out / 'q51-probe'))
