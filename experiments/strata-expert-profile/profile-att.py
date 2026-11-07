#!/usr/bin/env python3
"""Trace the unchanged expert kernels with captured routing and idle serving."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ap = argparse.ArgumentParser(description=__doc__)
for name in ('binary', 'sdk', 'profile', 'routes', 'out'):
    ap.add_argument('--' + name, type=Path, required=True)
ap.add_argument('--iterations', type=int, nargs='+', default=[5, 8])
ap.add_argument('--kernels', nargs='+', choices=['gate', 'down'], default=['gate', 'down'])
ap.add_argument('--expected-output-hash', default='019f42e2855f67cc',
                help='Median-padding replay control hash; change for another routing fixture')
a = ap.parse_args()
for name in ('binary', 'sdk', 'profile', 'routes', 'out'):
    setattr(a, name, getattr(a, name).resolve())
assert all(i > 0 for i in a.iterations)
cfg = json.loads(a.profile.read_text())
url = f"http://{cfg['host']}:{cfg['port']}"

def idle():
    req = urllib.request.Request(url + '/metrics', headers={'Authorization': 'Bearer ' + cfg['api_key']})
    with urllib.request.urlopen(req, timeout=5) as r:
        m = json.load(r)
    assert m['live']['state'] == 'idle' and not m['live'].get('queued'), 'Serving is busy'
    return m['totals']['requests']

requests = idle()
settings = {'ROCM_PATH': str(a.sdk), 'HIP_PATH': str(a.sdk), 'HIP_PLATFORM': 'amd',
            'LD_LIBRARY_PATH': f'{a.sdk}/lib:{a.sdk}/lib/rocm_sysdeps/lib:{a.sdk}/lib/llvm/lib',
            'STRATA_PF_F16': '1', 'STRATA_PF_F16_GU_EPI': '0', 'S20_NOMMQ': '1',
            'S20_ROUTE_IDS': str(a.routes)}
env = {**os.environ, **settings}
patterns = {'gate': r'.*gate_up_kernel<12, 128(, false)?>.*', 'down': r'.*down_kernel<128>.*'}
a.out.mkdir(parents=True, exist_ok=True)
for kernel in a.kernels:
    for iteration in a.iterations:
        assert idle() == requests, 'Actual traffic arrived; stop profiling'
        directory = a.out / f'{kernel}-i{iteration}'
        directory.mkdir(exist_ok=False)
        cmd = [str(a.sdk / 'bin/rocprofv3'), '--att', '--att-target-cu', '1', '--att-simd-select', '0',
               '--att-buffer-size', '0x10000000', '--kernel-iteration-range', str(iteration),
               '--kernel-include-regex', patterns[kernel], '-d', str(directory), '-o', 'expert', '--',
               str(a.binary), '--no-ref', '--only=Q4_K / Q5_1', '--chunks=16384']
        record = {'argv': cmd, 'env': settings, 'cwd': str(directory),
                  'binary_sha256': hashlib.sha256(a.binary.read_bytes()).hexdigest(),
                  'routes_sha256': hashlib.sha256(a.routes.read_bytes()).hexdigest(),
                  'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'serving_requests_before': requests}

        def save():
            encoded = json.dumps(record, indent=2) + '\n'
            assert cfg['api_key'] not in encoded
            (directory / 'command.json').write_text(encoded)

        save()
        print(json.dumps({'event': 'start', 'kernel': kernel, 'iteration': iteration}), flush=True)
        with (directory / 'stdout').open('w') as out, (directory / 'stderr').open('w') as err:
            result = subprocess.run(cmd, env=env, cwd=directory, stdout=out, stderr=err)
        record.update(exit_code=result.returncode, finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      serving_requests_after=idle(), decoded_stats=len(list(directory.glob('stats_*.csv'))))
        record['output_hash_passed'] = ('fused output bits hash ' + a.expected_output_hash) in (directory / 'stdout').read_text()
        save()
        assert result.returncode == 0, 'Profiler failed; inspect retained evidence'
        assert record['decoded_stats'] == 1, 'Missing or ambiguous decoded ATT data'
        assert record['output_hash_passed'], 'Replay output differs from the recorded control'
        assert record['serving_requests_after'] == requests, 'Serving traffic contaminated the trace'
        print(json.dumps({'event': 'complete', 'kernel': kernel, 'iteration': iteration}), flush=True)
