#!/usr/bin/env python3
"""Isolated packaged-engine STRATA_PF_PAD off/on/off screen.

Temporarily redirects an existing user service to loopback, preserving all its
other runtime settings. Restores serving in finally. No OpenClaw calls. Keep
the private profile and output directory private; publish only curated evidence.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request


def padding_evidence(log_path, launch_pad):
    """Distinguish an inherited override from defaults added after exec."""
    lines = Path(log_path).read_text().splitlines()
    # Serving logs can be appended across restarts. Never use a default line
    # from before the latest engine start to interpret the current process.
    starts = [i for i, line in enumerate(lines) if line.startswith('[strata]') and ' engine started: ' in line]
    if starts:
        lines = lines[starts[-1] + 1:]
    defaults = next((line for line in reversed(lines)
                     if line.startswith('strata: gfx1151 (Strix Halo):')
                     and 'exact speed switches on by default' in line), '')
    applied = defaults.rsplit(': ', 1)[-1].split() if defaults else []
    if launch_pad != '<unset>':
        if 'PF_PAD' in applied:
            raise RuntimeError('Startup defaults contradict explicit padding override')
        effective = {'value': launch_pad, 'source': 'explicit launch override'}
    elif 'PF_PAD' in applied:
        effective = {'value': '1', 'source': 'gfx1151 startup default'}
    else:
        effective = {'value': 'unknown', 'source': 'insufficient startup evidence'}
    return defaults, effective


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--fixture', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--live-url', required=True)
    ap.add_argument('--unit', default='strata-flash-next.service')
    ap.add_argument('--benchmark-port', type=int, default=8084)
    ap.add_argument('--sizes', type=int, nargs='+', default=[65536])
    ap.add_argument('--repeat', type=int, default=2)
    args = ap.parse_args()
    args.profile = args.profile.resolve()
    args.fixture = args.fixture.resolve()
    args.out = args.out.resolve()
    if args.repeat < 1 or any(n < 1024 for n in args.sizes):
        ap.error('Positive repetitions and prompt sizes of at least 1024 required')
    cfg = json.loads(args.profile.read_text())
    key = cfg['api_key']
    executable = shutil.which('strata')
    if not executable:
        raise RuntimeError('strata CLI is not on PATH')
    args.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    unit_dir = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'systemd/user' / (args.unit + '.d')
    override = unit_dir / '91-padding-screen.conf'
    if override.exists():
        raise RuntimeError('Experiment override already exists; inspect before proceeding')
    originals = {p.name: p.read_bytes() for p in unit_dir.glob('*.conf')}
    if not originals:
        raise RuntimeError('Expected existing runtime settings; refusing an unspecified baseline')
    bench_url = f'http://127.0.0.1:{args.benchmark_port}'
    report = {'protocol': 'strata-padding-v1', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'modes': [0, 1, 0], 'sizes': args.sizes, 'repeat': args.repeat,
              'original_override_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in originals.items()},
              'arms': [], 'completed': False}

    def save(path, value):
        encoded = json.dumps(value, indent=2) + '\n'
        if key in encoded:
            raise RuntimeError('Refusing credential in public metadata')
        path.write_text(encoded)

    def persist():
        save(args.out / 'summary.json', report)

    def api(url, path):
        req = urllib.request.Request(url.rstrip('/') + path, headers={'Authorization': 'Bearer ' + key})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    def service(*command):
        subprocess.run(['systemctl', '--user', *command], check=True)

    def unit_arg(value):
        if '\n' in value or '\r' in value:
            raise ValueError('Newline in service argument')
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'

    def idle(url):
        m = api(url, '/metrics')
        if m['live']['state'] != 'idle' or m['live'].get('queued'):
            raise RuntimeError('Server is busy; refusing to interrupt a request')
        return {k: m.get(k) for k in ('live', 'totals', 'engine')}

    def loaded(url):
        start = time.monotonic()
        last_notice = -30.0
        while True:
            try:
                h = api(url, '/health')
                if h.get('loaded'):
                    return {'health': h, 'load_seconds': time.monotonic() - start}
            except Exception:
                pass
            state = subprocess.check_output(['systemctl', '--user', 'show', args.unit,
                         '-p', 'ActiveState', '--value'], text=True).strip()
            if state in ('failed', 'inactive'):
                raise RuntimeError(f'Service became {state} while waiting for loading')
            elapsed = time.monotonic() - start
            if elapsed - last_notice >= 30:
                print(json.dumps({'event': 'loading', 'elapsed_s': round(elapsed, 1), 'service_state': state}), flush=True)
                last_notice = elapsed
            # Observation time alone is not a reason to restart a live loader.
            time.sleep(2)

    def process_flags(log_path):
        pid = subprocess.check_output(['systemctl', '--user', 'show', args.unit,
                                      '-p', 'MainPID', '--value'], text=True).strip()
        children = {ch for p in Path(f'/proc/{pid}/task').glob('*/children') for ch in p.read_text().split()}
        for child in children:
            if Path(f'/proc/{child}/comm').read_text().strip() != 'strata-host':
                continue
            env = dict(x.split(b'=', 1) for x in Path(f'/proc/{child}/environ').read_bytes().split(b'\0') if b'=' in x)
            names = ['STRATA_PF_PAD', 'STRATA_PF_GEMM', 'STRATA_PF_F16', 'STRATA_CACHE_MESSAGE_BOUNDARY',
                     'STRATA_PREFILL_STREAM_MIN', 'STRATA_PREFILL_TIMING', 'STRATA_TRACE', 'STRATA_PA_NATIVE_I8',
                     'STRATA_GFX1151_DEFAULTS', 'STRATA_DEFAULTS']
            values = {name: env.get(name.encode(), b'<unset>').decode() for name in names}
            # /proc/PID/environ is the launch environment, not a reliable view
            # of defaults added by setenv after exec. Use the startup evidence
            # too; an absent inherited setting does not mean the switch is off.
            defaults, effective_pad = padding_evidence(log_path, values['STRATA_PF_PAD'])
            return {'frontend_pid': int(pid), 'engine_pid': int(child), 'flags': values,
                    'flags_scope': 'inherited environment; excludes later engine setenv defaults',
                    'arch_defaults_startup_line': defaults, 'effective_pad': effective_pad,
                    'short_read_override': b'--short-read' in Path(f'/proc/{child}/cmdline').read_bytes().split(b'\0')}
        raise RuntimeError('Loaded native process was not found')

    def host():
        vm = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines())
        kfd = {}
        for p in Path('/sys/class/kfd/kfd/proc').glob('*/stats_*/evicted_ms'):
            try:
                kfd[p.parent.parent.name + '/' + p.parent.name] = int(p.read_text())
            except OSError:
                pass
        return {'unix_s': time.time(), 'kfd_evicted_ms': kfd,
                'vmstat': {k: int(v) for k, v in vm.items() if k.startswith(('compact_', 'pgmigrate_', 'pgscan_', 'pswp'))},
                'meminfo': {line.split(':')[0]: line.split(':')[1].strip()
                            for line in Path('/proc/meminfo').read_text().splitlines()
                            if line.split(':')[0] in ('MemAvailable', 'MemFree', 'SwapFree', 'Mlocked')},
                'sclk': Path('/sys/class/drm/card0/device/pp_dpm_sclk').read_text().strip(),
                'clock_policy': Path('/sys/class/drm/card0/device/power_dpm_force_performance_level').read_text().strip()}

    report['serving_before'] = idle(args.live_url)
    report['process_before'] = process_flags(cfg['log'])
    assert report['process_before']['flags']['STRATA_CACHE_MESSAGE_BOUNDARY'] == '1'
    assert report['process_before']['flags']['STRATA_PREFILL_STREAM_MIN'] == '128'
    for name, content in originals.items():
        (args.out / ('original-' + name)).write_bytes(content)
    persist()
    touched = False
    try:
        for index, pad in enumerate(report['modes']):
            if index:
                idle(bench_url)
            else:
                idle(args.live_url)
            arm_dir = args.out / f'{index+1:02d}-pad{pad}'
            arm_dir.mkdir(mode=0o700)
            profile = {**cfg, 'host': '127.0.0.1', 'port': args.benchmark_port, 'log': str(arm_dir / 'engine.log')}
            private = arm_dir / 'profile.private.json'
            fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as output:
                json.dump(profile, output, indent=2)
            save(arm_dir / 'profile.json', {k: v for k, v in profile.items() if k != 'api_key'})
            service('stop', args.unit)
            touched = True
            # All measured fast flags and the boundary trial remain inherited
            # from the unchanged 90-live-preview.conf. Only pad differs by arm.
            override.write_text('[Service]\nExecStart=\nExecStart=' + unit_arg(executable) +
                ' serve --profile ' + unit_arg(str(private)) + f' --host 127.0.0.1 --port {args.benchmark_port}\n' +
                f'Environment=STRATA_PF_PAD={pad}\n')
            service('daemon-reload')
            service('start', args.unit)
            print(json.dumps({'event': 'arm_start', 'arm': arm_dir.name}), flush=True)
            record = {'arm': arm_dir.name, 'pad': pad, **loaded(bench_url), 'before': idle(bench_url),
                      'process': process_flags(profile['log']), 'host_before': host()}
            flags = record['process']['flags']
            assert flags['STRATA_PF_PAD'] == str(pad) and flags['STRATA_PF_GEMM'] == '1'
            assert record['process']['effective_pad']['value'] == str(pad)
            assert flags['STRATA_PF_F16'] == '1' and flags['STRATA_CACHE_MESSAGE_BOUNDARY'] == '1'
            assert flags['STRATA_PREFILL_STREAM_MIN'] == '128' and not record['process']['short_read_override']
            assert flags['STRATA_TRACE'] == '<unset>' and flags['STRATA_PREFILL_TIMING'] == '<unset>'
            report['arms'].append(record)
            persist()
            stop = threading.Event()

            def sample():
                with (arm_dir / 'telemetry.jsonl').open('w') as output:
                    while not stop.is_set():
                        row = host()
                        try:
                            m = api(bench_url, '/metrics')
                            row.update(live=m['live'], totals=m['totals'], hardware=m['hardware'])
                        except Exception as exc:
                            row['error'] = type(exc).__name__
                        output.write(json.dumps(row) + '\n')
                        output.flush()
                        stop.wait(1)

            sampler = threading.Thread(target=sample, daemon=True)
            sampler.start()
            command = [sys.executable, str(Path(__file__).with_name('strata-prefill.py')),
                       '--url', bench_url, '--model', cfg['model_name'], '--fixture', str(args.fixture),
                       '--out', str(arm_dir / 'results.json'), '--sizes', *map(str, args.sizes),
                       '--repeat', str(args.repeat), '--max-tokens', '128', '--presence-penalty', '0',
                       '--nonce-seed', 'padding-screen-20261107']
            save(arm_dir / 'command.json', {'argv': command, 'extra_env': {'STRATA_API_KEY': '<from private profile>'}})
            env = os.environ.copy()
            env['STRATA_API_KEY'] = key
            try:
                with (arm_dir / 'probe.stdout').open('w') as out, (arm_dir / 'probe.stderr').open('w') as err:
                    subprocess.run(command, env=env, stdout=out, stderr=err, check=True)
            finally:
                stop.set()
                sampler.join(10)
                record.update(after=api(bench_url, '/metrics')['totals'], host_after=host())
                persist()
            result = json.loads((arm_dir / 'results.json').read_text())
            assert result['completed']
            assert record['after']['requests'] - record['before']['totals']['requests'] == len(result['runs'])
            print(json.dumps({'event': 'arm_complete', 'arm': arm_dir.name,
                             'runs': [r for r in result['runs'] if not r['warmup']]}), flush=True)
        report['completed'] = True
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if touched:
            service('stop', args.unit)
            override.unlink(missing_ok=True)
            service('daemon-reload')
            service('start', args.unit)
            report['restoration'] = {**loaded(args.live_url), 'metrics': idle(args.live_url),
                                     'process': process_flags(cfg['log']), 'host': host(),
                                     'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
            assert originals == {p.name: p.read_bytes() for p in unit_dir.glob('*.conf')}
            report['restoration']['original_overrides_unchanged'] = True
        persist()
        print(json.dumps({'event': 'finished', 'completed': report['completed'], 'restored': bool(report.get('restoration'))}), flush=True)


if __name__ == '__main__':
    main()
