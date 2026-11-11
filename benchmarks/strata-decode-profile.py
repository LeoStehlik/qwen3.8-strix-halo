#!/usr/bin/env python3
"""Bracket a detailed GPU decode profile with normal packaged-engine runs.

Requires an authorized maintenance window. Uses public prompts on authenticated
loopback and restores the persistent service in finally. The internal profiler
disables normal overlap and some fusion. Optional external attachment traces
the unchanged packaged engine instead. Output limits apply only to probes.
No OpenClaw tools are run.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--terminal', type=Path, required=True)
    ap.add_argument('--fixture', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--sizes', type=int, nargs='+', default=[49152, 196608])
    ap.add_argument('--max-tokens', type=int, default=1024)
    ap.add_argument('--unit', default='strata-flash-next.service')
    ap.add_argument('--port', type=int, default=8084)
    ap.add_argument('--profile-mode', choices=('internal', 'external', 'candidate'), default='internal')
    ap.add_argument('--engine', type=Path, help='Isolated engine executable for candidate/control comparisons')
    ap.add_argument('--candidate-env', action='append', default=[], metavar='STRATA_NAME=VALUE',
                    help='Opt-in kernel switch, set only in the middle candidate arm')
    ap.add_argument('--expected-results', type=Path, help='Require matching public fixture inputs/output hashes')
    ap.add_argument('--checkpoint-checks', action='store_true',
                    help='Run the existing synthetic tool/state continuation checks after each measured arm')
    ap.add_argument('--sdk', type=Path, help='ROCm SDK with rocprofv3; required for external tracing')
    ap.add_argument('--external-sudo', action='store_true', help='Use sudo -n for profiler attachment only')
    ap.add_argument('--arms', nargs='+', choices=('control', 'profile'),
                    default=['control', 'profile', 'control'], help='Use profile alone for a short profiler qualification')
    ap.add_argument('--execute', action='store_true')
    a = ap.parse_args()
    if a.profile_mode == 'external' and (not a.sdk or not (a.sdk / 'bin/rocprofv3').is_file()):
        ap.error('External tracing requires --sdk with bin/rocprofv3')
    if a.profile_mode == 'candidate' and (not a.engine or not a.candidate_env):
        ap.error('Candidate comparison requires --engine and --candidate-env')
    if a.profile_mode != 'candidate' and (a.engine or a.candidate_env):
        ap.error('--engine and --candidate-env are only supported in candidate mode')
    switches = dict(v.split('=', 1) for v in a.candidate_env)
    if any(not n.startswith('STRATA_') or not n.replace('_', '').isalnum() for n in switches):
        ap.error('Candidate switches must be STRATA_* environment names')
    os.umask(0o077)
    a.profile, a.out = a.profile.resolve(), a.out.resolve()
    original = a.profile.read_bytes()
    cfg = json.loads(original)
    baseline_engine_sha256 = hashlib.sha256(Path(cfg['exe']).read_bytes()).hexdigest()
    if a.engine:
        # Keep the original profile bytes intact; only private arm copies change.
        cfg['exe'] = str(a.engine.absolute())
    key = cfg['api_key']
    live = f"http://{cfg['host']}:{cfg['port']}"
    bench = f'http://127.0.0.1:{a.port}'
    cli = a.terminal.resolve() / 'bin/strata'
    ready = Path.home() / '.local/libexec/strata-ready.py'
    assert cli.is_file() and ready.is_file() and a.fixture.is_file()
    assert '--tail-role-token' in cfg['args']
    assert a.max_tokens >= 256 and all(1024 <= n <= 220000 for n in a.sizes)
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    unit_dir = Path(f'/run/user/{os.getuid()}/systemd/user/{a.unit}.d')
    override = unit_dir / '98-decode-profile.conf'
    assert not override.exists()
    overrides = {str(p): p.read_bytes() for p in unit_dir.glob('*.conf')}
    spec = importlib.util.spec_from_file_location('mtp_accounting', Path(__file__).with_name('strata-mtp-window.py'))
    accounting = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(accounting)
    report = {'protocol': 'decode-profile-v2', 'profile_mode': a.profile_mode,
              'requested_arms': a.arms,
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'engine_sha256': hashlib.sha256(Path(cfg['exe']).read_bytes()).hexdigest(),
              'baseline_engine_sha256': baseline_engine_sha256,
              'candidate_switches': switches,
              'profile_sha256': hashlib.sha256(original).hexdigest(), 'arms': [], 'completed': False,
              'limits': ['Public repeated-source fixture, not an agent quality evaluation.',
                         ('Internal profiling disables overlap and some fusion; stage sums are not the normal critical path.'
                          if a.profile_mode == 'internal' else
                          'External tracing preserves application path selection; tracing overhead must be measured against controls.'
                          if a.profile_mode == 'external' else
                          'Candidate mode compares opt-in switches on/off in the same isolated engine; no profiler is attached.'),
                         'DECODE_TIMING is common to all arms; output limit is probe-only.']}

    def save(path, value):
        raw = json.dumps(value, indent=2) + '\n'
        assert key not in raw
        path.write_text(raw)

    def persist():
        save(a.out / 'summary.json', report)

    def api(url, path):
        req = urllib.request.Request(url + path, headers={'Authorization': 'Bearer ' + key})
        return json.load(urllib.request.urlopen(req, timeout=5))

    def idle(url):
        m = api(url, '/metrics')
        assert m['live']['state'] == 'idle' and not m['live'].get('queued'), 'Active/queued inference'
        return {k: m[k] for k in ('live', 'totals', 'engine')}

    def service(*argv):
        subprocess.run(['systemctl', '--user', *argv], check=True)

    def loaded(url):
        start, notice = time.monotonic(), 0
        while True:
            try:
                health = api(url, '/health')
                if health.get('loaded'):
                    return {'load_s': time.monotonic() - start, 'health': health}
            except (OSError, ValueError):
                pass
            state = subprocess.check_output(['systemctl', '--user', 'show', a.unit,
                                             '-p', 'ActiveState', '--value'], text=True).strip()
            if state in ('failed', 'inactive') or time.monotonic() - start > 360:
                raise RuntimeError('Service failed to become ready: ' + state)
            if time.monotonic() - notice > 25:
                print(json.dumps({'event': 'loading', 'seconds': round(time.monotonic() - start)}), flush=True)
                notice = time.monotonic()
            time.sleep(2)

    def quote(value):
        s = str(value)
        assert not any(c in s for c in ('\n', '\r', '$'))
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'

    def process(profiled):
        pid = subprocess.check_output(['systemctl', '--user', 'show', a.unit, '-p', 'MainPID', '--value'], text=True).strip()
        children = {c for t in Path(f'/proc/{pid}/task').glob('*/children') for c in t.read_text().split()}
        native = [c for c in children if Path(f'/proc/{c}/comm').read_text().strip() == 'strata-host']
        assert len(native) == 1
        base = Path('/proc') / native[0]
        env = dict(x.split(b'=', 1) for x in (base / 'environ').read_bytes().split(b'\0') if b'=' in x)
        argv = (base / 'cmdline').read_bytes().split(b'\0')
        assert argv[argv.index(b'--tail-role-token') + 1] == b'846'
        assert env.get(b'STRATA_DECODE_TIMING') == b'1'
        assert (b'STRATA_VERIFY_PROFILE' in env) == (profiled and a.profile_mode == 'internal')
        assert env.get(b'STRATA_PF_F16') == b'1'
        assert env.get(b'STRATA_CACHE_MESSAGE_BOUNDARY') == b'1'
        for name, value in switches.items():
            assert env.get(name.encode()) == (value.encode() if profiled else None)
        names = ('STRATA_DECODE_TIMING', 'STRATA_VERIFY_PROFILE', 'STRATA_SH_STREAM',
                 'STRATA_VERIFY_EARLY_PLE_FLAG', 'ROCP_TOOL_ATTACH', *switches)
        mappings = {line.split()[-1] for line in (base / 'maps').read_text().splitlines()
                    if len(line.split()) >= 6}
        libraries = {}
        for name in ('libamdhip64.so.7', 'libhsa-runtime64.so.1', 'librocprofiler-register.so.0'):
            expected = (Path(cfg['exe']).parent / name).resolve()
            actual = {str(Path(p).resolve()) for p in mappings if Path(p).name.startswith(name)}
            assert str(expected) in actual, f'Packaged runtime library replaced: {name}: {actual}'
            libraries[name] = {'path': str(expected), 'sha256': hashlib.sha256(expected.read_bytes()).hexdigest()}
        if a.profile_mode == 'external':
            assert env.get(b'ROCP_TOOL_ATTACH') == b'1'
            assert any(p.read_text().strip() == 'rocp-bg-attach' for p in (base / 'task').glob('*/comm'))
        return {'native_pid': int(native[0]),
                'inherited_environment': {n: env.get(n.encode(), b'<unset>').decode() for n in names},
                'runtime_libraries': libraries}

    def host():
        vm = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines())
        evictions = {}
        for p in Path('/sys/class/kfd/kfd/proc').glob('*/stats_*/evicted_ms'):
            try:
                evictions[p.parent.parent.name + '/' + p.parent.name] = int(p.read_text())
            except OSError:
                pass
        return {'unix_s': time.time(), 'evicted_ms': evictions,
                'swap': {n: int(vm[n]) for n in ('pswpin', 'pswpout')},
                'clock_policy': Path('/sys/class/drm/card0/device/power_dpm_force_performance_level').read_text().strip()}

    persist()
    if not a.execute:
        print('Prepared metadata only; --execute requires a maintenance window.')
        return
    before = idle(live)
    time.sleep(3)
    assert idle(live)['totals']['requests'] == before['totals']['requests']
    unit_dir.mkdir(parents=True, exist_ok=True)
    touched = False
    trace_process = None
    trace_stdout = trace_stderr = None

    def detach_trace():
        nonlocal trace_process, trace_stdout, trace_stderr
        if trace_process is None:
            return
        try:
            if trace_process.poll() is None:
                # rocprof-attach's supported interactive detach: Enter flushes
                # the trace synchronously without terminating the target.
                trace_process.communicate(input='\n', timeout=150)
            if trace_process.returncode != 0:
                raise RuntimeError(f'External profiler exited {trace_process.returncode}')
        finally:
            if trace_process.poll() is None:
                trace_process.terminate()
                try:
                    trace_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    trace_process.kill()
                    trace_process.wait(timeout=10)
            trace_process = None
            if trace_stdout:
                trace_stdout.close()
            if trace_stderr:
                trace_stderr.close()

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f'signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        for index, arm_name in enumerate(a.arms):
            profiled = arm_name == 'profile'
            idle(bench if touched else live)
            directory = a.out / f'{index:02d}-' / ('profile' if profiled else 'control')
            directory.mkdir(parents=True)
            private = directory / 'profile.private.json'
            cfg_arm = dict(cfg, host='127.0.0.1', port=a.port, log=str(directory / 'engine.private.log'))
            private.write_text(json.dumps(cfg_arm, indent=2) + '\n')
            touched = True
            service('stop', a.unit)
            override.write_text('[Service]\nExecStart=\nExecStart=' + quote(cli) + ' serve --profile ' + quote(private) +
                '\nExecStartPost=\nExecStartPost=/usr/bin/python3 ' + quote(ready) + ' --profile ' + quote(private) +
                ' --timeout 240\nEnvironment=STRATA_DECODE_TIMING=1\n' +
                ('Environment=STRATA_VERIFY_PROFILE=1\n' if profiled and a.profile_mode == 'internal'
                 else 'UnsetEnvironment=STRATA_VERIFY_PROFILE\n') +
                ('Environment=ROCP_TOOL_ATTACH=1\nEnvironment=' + quote('LD_LIBRARY_PATH=' +
                 str(Path(cfg['exe']).parent) + ':' + str(a.sdk.resolve() / 'lib')) + '\n'
                 if a.profile_mode == 'external' else '') +
                ('Environment=' + quote('LD_LIBRARY_PATH=' + str(Path(cfg['exe']).parent)) + '\n'
                 if a.profile_mode == 'candidate' else '') +
                ''.join(('Environment=' + quote(name + '=' + value) if profiled
                         else 'UnsetEnvironment=' + name) + '\n' for name, value in switches.items()))
            service('daemon-reload')
            service('start', '--no-block', a.unit)
            print(json.dumps({'event': 'arm_start', 'index': index, 'profiled': profiled}), flush=True)
            arm = {'index': index, 'profiled': profiled, **loaded(bench), 'before': idle(bench),
                   'process': process(profiled), 'host_before': host()}
            report['arms'].append(arm)
            persist()
            if profiled and a.profile_mode == 'external':
                trace_dir = directory / 'external-trace'
                trace_dir.mkdir()
                command = (['sudo', '-n'] if a.external_sudo else []) + [str(a.sdk.resolve() / 'bin/rocprofv3'),
                           '--attach', str(arm['process']['native_pid']), '--attach-children=false',
                           '--attach-sync-output=true', '--kernel-trace', '--memory-copy-trace',
                           '--output-format', 'csv', '--output-config',
                           '-d', str(trace_dir), '-o', 'execution']
                save(directory / 'trace-command.json', {'argv': command})
                trace_stdout = (directory / 'trace.stdout').open('w')
                trace_stderr = (directory / 'trace.stderr').open('w')
                trace_process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=trace_stdout,
                                                 stderr=trace_stderr, text=True)
                # Wait for the attach tool's ready prompt, never infer readiness
                # merely because a process exists. Retain failures for diagnosis.
                attach_start = time.monotonic()
                while True:
                    trace_text = ((directory / 'trace.stdout').read_text(errors='replace') +
                                  (directory / 'trace.stderr').read_text(errors='replace'))
                    if 'press enter' in trace_text.lower() or 'press ENTER' in trace_text:
                        break
                    if trace_process.poll() is not None or time.monotonic() - attach_start > 30:
                        raise RuntimeError('External profiler did not confirm attachment; inspect trace stdout/stderr')
                    time.sleep(0.25)
                arm['external_trace_attached'] = True
                persist()
            stop = threading.Event()

            def sample():
                with (directory / 'telemetry.jsonl').open('w') as out:
                    while not stop.is_set():
                        row = host()
                        try:
                            m = api(bench, '/metrics')
                            row.update(live=m['live'], totals=m['totals'], hardware=m['hardware'])
                        except Exception as exc:
                            row['error'] = type(exc).__name__
                        out.write(json.dumps(row) + '\n')
                        out.flush()
                        stop.wait(2)
            sampler = threading.Thread(target=sample, daemon=True)
            sampler.start()
            command = [sys.executable, str(Path(__file__).with_name('strata-prefill.py')),
                       '--url', bench, '--model', cfg['model_name'], '--fixture', str(a.fixture.resolve()),
                       '--out', str(directory / 'results.json'), '--sizes', *map(str, a.sizes), '--repeat', '1',
                       '--max-tokens', str(a.max_tokens), '--presence-penalty', '0', '--sampling-preset', 'openclaw',
                       '--nonce-seed', 'decode-profile-20261108']
            save(directory / 'command.json', {'argv': command, 'secret_source': 'private profile, never command line'})
            try:
                with (directory / 'probe.stdout').open('w') as out, (directory / 'probe.stderr').open('w') as err:
                    subprocess.run(command, env=dict(os.environ, STRATA_API_KEY=key), stdout=out, stderr=err, check=True)
            finally:
                stop.set()
                sampler.join(10)
                detach_trace()
            results = json.loads((directory / 'results.json').read_text())
            assert results['completed']
            if a.expected_results:
                expected = json.loads(a.expected_results.read_text())['runs']
                assert len(expected) == len(results['runs'])
                for want, got in zip(expected, results['runs']):
                    for field in ('target_tokens', 'messages_sha256', 'output_sha256'):
                        assert want[field] == got[field], f'Reference mismatch: {field}, target {got["target_tokens"]}'
                arm['reference_outputs_match'] = True
            arm.update(after=idle(bench), host_after=host())
            assert arm['after']['totals']['requests'] - arm['before']['totals']['requests'] == len(results['runs'])
            native = accounting.native_accounting(cfg_arm['log'], results['runs'])
            save(directory / 'native-accounting.json', native)
            stages = [l for l in Path(cfg_arm['log']).read_text().splitlines() if l.startswith('strata decode GPU stages')]
            save(directory / 'gpu-stages.json', {'lines': stages})
            arm['runs'] = [{k: r[k] for k in ('target_tokens', 'usage', 'timings', 'output_sha256', 'elapsed_s')} for r in results['runs']]
            if a.checkpoint_checks:
                command = [sys.executable, str(Path(__file__).with_name('strata-checkpoint-tools.py')),
                           '--profile', str(private), '--out', str(directory / 'checkpoint-tools.json'),
                           '--runtime-padding-rows', '80']
                with (directory / 'checkpoint.stdout').open('w') as out, (directory / 'checkpoint.stderr').open('w') as err:
                    subprocess.run(command, stdout=out, stderr=err, check=True)
                checks = json.loads((directory / 'checkpoint-tools.json').read_text())
                assert checks['passed']
                arm['checkpoint_checks_passed'] = True
                arm['after_checkpoint_checks'] = idle(bench)
            persist()
            print(json.dumps({'event': 'arm_complete', 'index': index,
                'decode_tok_s': [round(sum(s['generated'] for s in group) / sum(s['decode_ms'] for s in group) * 1000, 2)
                                 for group in native['groups'][1:]]}), flush=True)
        report['completed'] = True
    except BaseException as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        try:
            detach_trace()
        except Exception as exc:
            report['trace_cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
        if touched:
            service('stop', a.unit)
            override.unlink(missing_ok=True)
            service('daemon-reload')
            service('start', '--no-block', a.unit)
            report['restoration'] = loaded(live)
            assert a.profile.read_bytes() == original
            assert {str(p): p.read_bytes() for p in unit_dir.glob('*.conf')} == overrides
            report['restoration']['profile_and_overrides_unchanged'] = True
        persist()
        print(json.dumps({'event': 'finished', 'completed': report['completed'], 'restored': bool(report.get('restoration'))}), flush=True)


if __name__ == '__main__':
    main()
