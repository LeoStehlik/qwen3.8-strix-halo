#!/usr/bin/env python3
"""Cold-prefill clock-policy comparison on an already loaded, idle AMD server.

Uses only documented factory modes; requires noninteractive sudo for the single
sysfs control. Restores its original value even on ordinary exceptions. Does not
restart services. Credentials stay in process memory/environment, never reports.
Do not run alongside other inference clients. Unexpected request counts stop the
ladder after the current arm and mark that arm contaminated.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--fixture', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--url', required=True)
    ap.add_argument('--sizes', type=int, nargs='+', default=[65536])
    ap.add_argument('--modes', nargs='+', choices=['auto', 'high', 'profile_peak'],
                    default=['auto', 'high', 'auto'])
    ap.add_argument('--device', type=Path, default=Path('/sys/class/drm/card0/device'))
    args = ap.parse_args()
    args.out.mkdir(exist_ok=False, parents=True)
    cfg = json.loads(args.profile.read_text())
    control = args.device / 'power_dpm_force_performance_level'
    original = control.read_text().strip()
    hwmon = next((args.device / 'hwmon').glob('hwmon*'))
    report = {'protocol': 'strata-clock-policy-v1', 'original': original,
              'modes': args.modes, 'sizes': args.sizes, 'arms': [], 'completed': False,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}

    def persist():
        (args.out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')

    def metrics():
        req = urllib.request.Request(args.url.rstrip('/') + '/metrics',
                headers={'Authorization': 'Bearer ' + cfg['api_key']})
        with urllib.request.urlopen(req, timeout=5) as r:
            value = json.load(r)
        return {k: value.get(k) for k in ('live', 'totals', 'hardware', 'engine')}

    def read(path):
        try:
            return path.read_text().strip()
        except OSError:
            return None

    def host():
        vm = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines())
        evicted = {}
        for file in Path('/sys/class/kfd/kfd/proc').glob('*/stats_*/evicted_ms'):
            value = read(file)
            if value is not None:
                evicted[file.parent.parent.name + '/' + file.parent.name] = int(value)
        return {'unix_s': time.time(),
                'clock_mode': read(control),
                'sclk': read(args.device / 'pp_dpm_sclk'),
                'mclk': read(args.device / 'pp_dpm_mclk'),
                'busy_percent': read(args.device / 'gpu_busy_percent'),
                'sensors': {name: read(hwmon / name) for name in
                            ('freq1_input', 'temp1_input', 'power1_average', 'power1_input')},
                'kfd_evicted_ms': evicted,
                'vmstat': {k: int(v) for k, v in vm.items()
                           if k.startswith(('compact_', 'pgmigrate_', 'pgscan_', 'pswp'))},
                'meminfo': {line.split(':')[0]: line.split(':')[1].strip()
                            for line in Path('/proc/meminfo').read_text().splitlines()
                            if line.split(':')[0] in ('MemAvailable', 'MemFree', 'SwapFree', 'Mlocked')}}

    def set_mode(mode):
        result = subprocess.run(['sudo', '-n', 'tee', str(control)], input=mode+'\n',
                                text=True, capture_output=True)
        if result.returncode or read(control) != mode:
            raise RuntimeError(f'Clock mode {mode} rejected: {result.stderr.strip()}')

    try:
        for index, mode in enumerate(args.modes):
            before = metrics()
            if before['live']['state'] != 'idle' or before['live'].get('queued'):
                raise RuntimeError('Server is busy; stopping before changing clock mode')
            arm = args.out / f'{index+1:02d}-{mode}'
            arm.mkdir()
            set_mode(mode)
            record = {'mode': mode, 'path': arm.name, 'before': before,
                      'host_before': host(), 'started_unix_s': time.time()}
            report['arms'].append(record)
            persist()
            stop = threading.Event()

            def sample():
                with (arm / 'telemetry.jsonl').open('w') as output:
                    while not stop.is_set():
                        row = host()
                        try:
                            m = metrics()
                            row['live'] = m['live']
                            row['totals'] = m['totals']
                        except Exception as exc:
                            row['metrics_error'] = type(exc).__name__
                        output.write(json.dumps(row) + '\n')
                        output.flush()
                        stop.wait(0.5)

            sampler = threading.Thread(target=sample, daemon=True)
            sampler.start()
            env = os.environ.copy()
            env['STRATA_API_KEY'] = cfg['api_key']
            command = [sys.executable, str(Path(__file__).with_name('strata-prefill.py')),
                       '--url', args.url, '--model', cfg['model_name'],
                       '--fixture', str(args.fixture), '--out', str(arm / 'results.json'),
                       '--sizes', *map(str, args.sizes), '--repeat', '1', '--max-tokens', '128',
                       '--presence-penalty', '0', '--nonce-seed', str(args.out.name)+':'+str(index)]
            print(json.dumps({'arm': arm.name, 'event': 'start'}), flush=True)
            try:
                with (arm / 'probe.stdout').open('w') as out, (arm / 'probe.stderr').open('w') as err:
                    subprocess.run(command, env=env, stdout=out, stderr=err, check=True)
            finally:
                stop.set()
                sampler.join(10)
                record.update(after=metrics(), host_after=host(), ended_unix_s=time.time())
                persist()
            result = json.loads((arm / 'results.json').read_text())
            expected = len(result['runs'])
            observed = record['after']['totals']['requests'] - before['totals']['requests']
            record['expected_requests'] = expected
            record['observed_requests'] = observed
            record['contaminated'] = observed != expected
            persist()
            print(json.dumps({'arm': arm.name, 'event': 'complete', 'contaminated': record['contaminated'],
                              'runs': [r for r in result['runs'] if not r['warmup']]}), flush=True)
            if record['contaminated']:
                raise RuntimeError('Unexpected request count; stopping further benchmark arms')
        report['completed'] = True
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        try:
            set_mode(original)
            report['restored_mode'] = read(control)
        finally:
            persist()


if __name__ == '__main__':
    main()
