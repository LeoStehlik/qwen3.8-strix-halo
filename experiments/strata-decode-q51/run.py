#!/usr/bin/env python3
"""Run an isolated operator probe only while the persistent endpoint is idle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

p = argparse.ArgumentParser(description=__doc__)
for name in ('binary', 'profile', 'out'):
    p.add_argument('--' + name, type=Path, required=True)
p.add_argument('--sdk', type=Path)
p.add_argument('--mode', choices=('check', 'bench', 'counters'), default='check')
a = p.parse_args()
a.binary, a.out = a.binary.resolve(), a.out.resolve()
cfg = json.loads(a.profile.read_text())
url = f"http://{cfg['host']}:{cfg['port']}"
a.out.mkdir(parents=True, exist_ok=False)


def idle():
    req = urllib.request.Request(url + '/metrics', headers={'Authorization': 'Bearer ' + cfg['api_key']})
    with urllib.request.urlopen(req, timeout=5) as r:
        m = json.load(r)
    assert m['live']['state'] == 'idle' and not m['live'].get('queued'), 'Serving is busy'
    return m['totals']['requests']


def host():
    evictions = {}
    for f in Path('/sys/class/kfd/kfd/proc').glob('*/stats_*/evicted_ms'):
        try:
            evictions[f.parent.parent.name + '/' + f.parent.name] = int(f.read_text())
        except OSError:
            pass
    return {'monotonic_ns': time.monotonic_ns(), 'evicted_ms': evictions}


requests = idle()
commands = [(a.mode, [str(a.binary)] + (['--bench'] if a.mode == 'bench' else []))]
env = os.environ.copy()
if a.mode == 'counters':
    assert a.sdk and (a.sdk / 'bin/rocprofv3').is_file()
    env.update(ROCM_PATH=str(a.sdk), HIP_PATH=str(a.sdk), HIP_PLATFORM='amd',
               LD_LIBRARY_PATH=f'{a.sdk}/lib:{a.sdk}/lib/rocm_sysdeps/lib:{a.sdk}/lib/llvm/lib')
    commands = []
    # Separate counter groups avoid silent unsupported joint collection.
    counter_sets = {
        'memory': ['GL2C_EA_RDREQ_32B_sum', 'GL2C_EA_RDREQ_64B_sum', 'GL2C_EA_RDREQ_128B_sum',
                   'GL2C_EA_WRREQ_64B_sum', 'SQ_WAVES_sum'],
        'cache': ['GL2C_HIT_sum', 'GL2C_MISS_sum', 'GL2C_EA_RDREQ_96B_sum', 'SQ_WAVES_sum'],
    }
    for lanes in (32, 16, 8):
        for name, counters in counter_sets.items():
            label = f'lanes{lanes}-{name}'
            directory = a.out / label
            directory.mkdir()
            pattern = '.*native_down_kernel<7>.*' if lanes == 32 else f'.*q51_subwarp<{lanes}>.*'
            cmd = [str(a.sdk / 'bin/rocprofv3'), '--kernel-trace', '--pmc', *counters,
                   '--output-format', 'csv', '--kernel-iteration-range', '3-7',
                   '--kernel-include-regex', pattern, '-d', str(directory), '-o', 'q51', '--',
                   str(a.binary), '--counter', str(lanes), '40', '1', '4']
            commands.append((label, cmd))
for label, cmd in commands:
    assert idle() == requests, 'Inference traffic arrived'
    meta = {'argv': cmd, 'serving_requests_before': requests, 'host_before': host(),
            'binary_sha256': hashlib.sha256(a.binary.read_bytes()).hexdigest(), 'cwd': str(a.out)}
    path = a.out / (label + '.json')

    def save():
        raw = json.dumps(meta, indent=2) + '\n'
        assert cfg['api_key'] not in raw
        path.write_text(raw)

    save()
    with (a.out / (label + '.stdout')).open('w') as out, (a.out / (label + '.stderr')).open('w') as err:
        result = subprocess.run(cmd, stdout=out, stderr=err, env=env, cwd=a.out)
    meta.update(exit_code=result.returncode, host_after=host(), serving_requests_after=idle())
    save()
    assert result.returncode == 0, f'{label} failed; retained stdout/stderr'
    assert meta['serving_requests_after'] == requests, 'Inference traffic contaminated run'
    print(json.dumps({'completed': label, 'exit_code': result.returncode}), flush=True)
