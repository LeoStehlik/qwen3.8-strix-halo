#!/usr/bin/env python3
"""Isolated prepared-activation correctness and complete-operator screen."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

ap = argparse.ArgumentParser(description=__doc__)
for name in ('binary', 'control', 'sdk', 'profile', 'out'):
    ap.add_argument('--' + name, type=Path, required=True)
ap.add_argument('--phase', choices=['reference', 'screen'], required=True)
ap.add_argument('--routes', type=Path)
ap.add_argument('--modes', nargs='+', choices=['control', 'x', 'h', 'both'], default=['control', 'x', 'h', 'control'])
ap.add_argument('--chunks', type=int, default=16384)
a = ap.parse_args()
for name in ('binary', 'control', 'sdk', 'profile', 'out'):
    setattr(a, name, getattr(a, name).resolve())
a.out.mkdir(parents=True, exist_ok=False)
cfg = json.loads(a.profile.read_text())

def idle():
    req = urllib.request.Request(f"http://{cfg['host']}:{cfg['port']}/metrics", headers={'Authorization': 'Bearer ' + cfg['api_key']})
    with urllib.request.urlopen(req, timeout=5) as r:
        m = json.load(r)
    assert m['live']['state'] == 'idle' and not m['live'].get('queued'), 'Serving is busy'
    return m['totals']['requests']

requests = idle()
settings = {'ROCM_PATH': str(a.sdk), 'HIP_PATH': str(a.sdk), 'HIP_PLATFORM': 'amd',
            'LD_LIBRARY_PATH': f'{a.sdk}/lib:{a.sdk}/lib/rocm_sysdeps/lib:{a.sdk}/lib/llvm/lib',
            'STRATA_PF_F16': '1', 'STRATA_PF_F16_GU_EPI': '0', 'S20_NOMMQ': '1'}
plan = ([(bn, mode) for bn in (64, 128) for mode in ('original', 'control', 'x', 'h', 'both')]
        if a.phase == 'reference' else [(None, mode) for mode in a.modes])
report = {'phase': a.phase, 'runs': [], 'completed': False, 'serving_requests_before': requests}
reference = {}
for index, (bn, mode) in enumerate(plan):
    assert idle() == requests, 'Actual traffic arrived'
    binary = a.control if mode == 'original' else a.binary
    extra = {**settings, 'S20_PREPARED_X': '1' if mode in ('x', 'both') else '0',
             'S20_PREPARED_H': '1' if mode in ('h', 'both') else '0'}
    if bn:
        extra['STRATA_PF_F16_BN'] = str(bn)
    if a.routes and a.phase == 'screen':
        extra['S20_ROUTE_IDS'] = str(a.routes.resolve())
    env = {**os.environ, **extra}
    for key in ('STRATA_PF_F16_BN', 'S20_ROUTE_IDS'):
        if key not in extra:
            env.pop(key, None)
    cmd = [str(binary), '--only=Q4_K / Q5_1'] + (['--no-timing'] if a.phase == 'reference' else ['--no-ref', '--chunks=' + str(a.chunks)])
    name = f'{index:02d}-{mode}' + (f'-bn{bn}' if bn else '')
    row = {'name': name, 'mode': mode, 'tile_rows': bn, 'argv': cmd, 'env': extra,
           'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    with (a.out / (name + '.stdout')).open('w') as out, (a.out / (name + '.stderr')).open('w') as err:
        result = subprocess.run(cmd, env=env, stdout=out, stderr=err)
    text = (a.out / (name + '.stdout')).read_text()
    row.update(exit_code=result.returncode, serving_requests_after=idle(),
               parity_passed='prefill fused MoE (native formats) parity passed' in text,
               reference_hashes=re.findall(r'reference H bytes hash ([0-9a-f]+) output bits hash ([0-9a-f]+)', text),
               output_hashes=re.findall(r'fused output bits hash ([0-9a-f]+)', text),
               median_ms=[float(x) for x in re.findall(r'fused back to back: median ([\d.]+)', text)])
    report['runs'].append(row)
    encoded = json.dumps(report, indent=2) + '\n'
    assert cfg['api_key'] not in encoded
    (a.out / 'results.json').write_text(encoded)
    assert result.returncode == 0 and row['parity_passed'], 'Operator check failed'
    assert row['serving_requests_after'] == requests
    if a.phase == 'reference':
        assert row['reference_hashes'], 'Missing intermediate/output reference hashes'
        if mode == 'original':
            reference[bn] = row['reference_hashes']
        assert row['reference_hashes'] == reference[bn], 'Reference hashes differ from original'
    else:
        assert len(row['output_hashes']) == len(row['median_ms']) == 1
        if index == 0:
            reference[None] = row['output_hashes']
        assert row['output_hashes'] == reference[None], 'Full output hash differs'
    print(json.dumps({k: row[k] for k in ('name', 'parity_passed', 'reference_hashes', 'output_hashes', 'median_ms')}), flush=True)
report['completed'] = True
(a.out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
