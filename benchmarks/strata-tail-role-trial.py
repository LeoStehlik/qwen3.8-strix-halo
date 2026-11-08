#!/usr/bin/env python3
"""Prepare/run an isolated control/candidate/control checkpoint-placement trial.

The packaged engine's --tail-role-token marks the final user-role runtime
carrier as outside the reusable history. No prompt text, sampling, model or
kernel changes. Execute only when live serving is idle. Temporary systemd
overrides use loopback and are removed in finally; the original service and
private profile are restored. No OpenClaw turns or real tools are executed.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--terminal', type=Path, required=True)
    ap.add_argument('--execute', action='store_true', help='Default only prepares private profiles and offline fixtures')
    ap.add_argument('--unit', default='strata-flash-next.service')
    ap.add_argument('--port', type=int, default=8084)
    a = ap.parse_args()
    os.umask(0o077)
    a.profile, a.out, a.terminal = a.profile.resolve(), a.out.resolve(), a.terminal.resolve()
    a.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    baseline_bytes = a.profile.read_bytes()
    cfg = json.loads(baseline_bytes)
    secret = cfg['api_key']
    live_url = f"http://{cfg['host']}:{cfg['port']}"
    bench_url = f'http://127.0.0.1:{a.port}'
    cli = a.terminal / 'bin/strata'
    ready = Path.home() / '.local/libexec/strata-ready.py'
    assert cli.is_file() and ready.is_file()
    assert b'--tail-role-token' in Path(cfg['exe']).read_bytes()
    assert cfg.get('effort_position', 'start') == 'start'
    assert not a.profile.with_suffix('.shared-settings.json').exists()
    sys.path[:0] = [str(a.terminal), str(a.terminal / 'tools')]
    from strata_tokenizer import Tokenizer
    tp = Path(cfg['tokenizer'])
    v = json.loads((tp / 'vocab.json').read_text())
    tokens = [None] * len(v)
    for s, i in v.items():
        tokens[i] = s
    tc = json.loads((tp / 'tokenizer.json').read_text())
    tok = Tokenizer(tokens, (tp / 'merges.txt').read_text().split('\n'),
                    json.loads((tp / 'token_type.json').read_text()), tc.get('pre') or 'qwen35', tc.get('special_ids'))
    role = tok.encode('user', parse_special=True)
    assert len(role) == 1
    profile_hash = hashlib.sha256(baseline_bytes).hexdigest()
    report_path = a.out / 'summary.json'
    if report_path.exists() and json.loads(report_path.read_text()).get('execution_started'):
        raise RuntimeError('This output already contains an executed trial; inspect rather than overwrite')
    report = {'protocol': 'tail-role-checkpoint-v1', 'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'baseline_profile_sha256': profile_hash, 'role_token': role[0],
              'engine_sha256': hashlib.sha256(Path(cfg['exe']).read_bytes()).hexdigest(),
              'arms': [], 'completed': False, 'execution_started': False}

    def save():
        raw = json.dumps(report, indent=2) + '\n'
        assert secret not in raw
        report_path.write_text(raw)

    def api(url, path):
        req = urllib.request.Request(url + path, headers={'Authorization': 'Bearer ' + secret})
        return json.load(urllib.request.urlopen(req, timeout=5))

    def warmup():
        body = {'model': cfg['model_name'], 'messages': [
            {'role': 'system', 'content': 'Public warm-up. ' + 'alpha beta gamma delta. ' * 40},
            {'role': 'user', 'content': 'Reply only READY.'}], 'stream': False,
            'temperature': 0, 'max_tokens': 16,
            'chat_template_kwargs': {'enable_thinking': False}}
        req = urllib.request.Request(bench_url + '/v1/chat/completions', json.dumps(body).encode(),
            {'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
        r = json.load(urllib.request.urlopen(req, timeout=300))
        assert r['usage']['prompt_tokens'] > 64
        return {'usage': r['usage'], 'timings': r.get('timings')}

    def verify_process(variant):
        pid = subprocess.check_output(['systemctl', '--user', 'show', a.unit,
                                      '-p', 'MainPID', '--value'], text=True).strip()
        children = {p for task in Path(f'/proc/{pid}/task').glob('*/children') for p in task.read_text().split()}
        native = [p for p in children if Path(f'/proc/{p}/comm').read_text().strip() == 'strata-host']
        assert len(native) == 1, 'Expected exactly one native child'
        argv = Path(f'/proc/{native[0]}/cmdline').read_bytes().split(b'\0')
        actual_role = argv[argv.index(b'--tail-role-token') + 1].decode() if b'--tail-role-token' in argv else None
        assert actual_role == (str(role[0]) if variant == 'candidate' else None)
        env = dict(x.split(b'=', 1) for x in Path(f'/proc/{native[0]}/environ').read_bytes().split(b'\0') if b'=' in x)
        assert env.get(b'STRATA_CACHE_MESSAGE_BOUNDARY') == b'1'
        assert env.get(b'STRATA_TRACE') == b'1'
        assert env.get(b'STRATA_PF_F16') == b'1'
        return {'frontend_pid': int(pid), 'native_pid': int(native[0]), 'tail_role_token': actual_role}

    def idle(url):
        m = api(url, '/metrics')
        if m['live']['state'] != 'idle' or m['live'].get('queued'):
            raise RuntimeError('Serving has active/queued work; defer trial')
        return m

    def service(*cmd):
        subprocess.run(['systemctl', '--user', *cmd], check=True)

    def ready_at(url):
        start, notice = time.monotonic(), 0
        while True:
            try:
                h = api(url, '/health')
                if h.get('loaded'):
                    return {'load_s': round(time.monotonic() - start, 3), 'health': h}
            except (OSError, ValueError):
                pass
            state = subprocess.check_output(['systemctl', '--user', 'show', a.unit,
                                             '-p', 'ActiveState', '--value'], text=True).strip()
            if state in ('failed', 'inactive'):
                raise RuntimeError('Service terminal during load: ' + state)
            now = time.monotonic()
            if now - notice >= 25:
                print(json.dumps({'event': 'loading', 'service': state, 'seconds': round(now - start, 1)}), flush=True)
                notice = now
            time.sleep(2)

    def unit_arg(s):
        s = str(s)
        if any(x in s for x in ('\n', '\r', '$')):
            raise ValueError('Unsupported systemd argument')
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'

    def probe_command(out, padding, offline=False):
        return [sys.executable, str(Path(__file__).with_name('strata-cache-boundary.py')),
                '--url', bench_url, '--model', cfg['model_name'], '--terminal', str(a.terminal),
                '--tokenizer', str(tp), '--out', str(out), '--modes', 'moving', '--turns', '3',
                '--history-rows', '3300', '--runtime-padding-rows', str(padding),
                '--seed', f'tail-role-20261108-padding-{padding}'] + (['--offline'] if offline else [])

    profiles = []
    for index, variant in enumerate(('control', 'candidate', 'control')):
        directory = a.out / f'{index:02d}-{variant}'
        directory.mkdir(exist_ok=True, mode=0o700)
        profile = dict(cfg, host='127.0.0.1', port=a.port, log=str(directory / 'engine.private.log'))
        for field in ('args', 'args_written'):
            if field in cfg:
                values = list(cfg[field])
                if '--tail-role-token' in values:
                    pos = values.index('--tail-role-token')
                    assert values[pos + 1] == str(role[0])
                    del values[pos:pos + 2]
                profile[field] = values + (['--tail-role-token', str(role[0])] if variant == 'candidate' else [])
        private = directory / 'profile.private.json'
        private.write_text(json.dumps(profile, indent=2) + '\n')
        profiles.append((variant, directory, private))
    for padding in (16, 80):
        out = a.out / f'offline-tail-{padding}.json'
        subprocess.run(probe_command(out, padding, True), stdout=subprocess.DEVNULL, check=True)
        fixture = json.loads(out.read_text())
        report.setdefault('fixtures', []).append({'padding_rows': padding,
            'prompt_tokens': [r['prompt_tokens_offline'] for r in fixture['runs']],
            'tail_tokens': [r['message_boundaries'][-1] - r['message_boundaries'][-2] for r in fixture['runs']]})
    save()
    if not a.execute:
        print(json.dumps({'prepared': True, 'fixtures': report['fixtures'], 'role_token': role[0]}))
        return
    unit_dir = Path(f'/run/user/{os.getuid()}/systemd/user/{a.unit}.d')
    override = unit_dir / '98-tail-role-trial.conf'
    if override.exists():
        raise RuntimeError('Trial override already exists; inspect')
    originals = {str(p): p.read_bytes() for p in unit_dir.glob('*.conf')}
    before = idle(live_url)
    time.sleep(3)
    again = idle(live_url)
    assert before['totals']['requests'] == again['totals']['requests'], 'Traffic arrived during idle check'
    report['execution_started'] = True
    report['before'] = {'live': again['live'], 'totals': again['totals']}
    save()
    unit_dir.mkdir(parents=True, exist_ok=True)
    touched = False
    env = dict(os.environ, STRATA_API_KEY=secret)
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f'signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        for variant, directory, private in profiles:
            idle(live_url if not touched else bench_url)
            touched = True
            service('stop', a.unit)
            override.write_text('[Service]\nExecStart=\nExecStart=' + unit_arg(cli) +
                ' serve --profile ' + unit_arg(private) + '\nExecStartPost=\nExecStartPost=/usr/bin/python3 ' +
                unit_arg(ready) + ' --profile ' + unit_arg(private) + ' --timeout 240\nEnvironment=STRATA_TRACE=1\n')
            service('daemon-reload')
            service('start', '--no-block', a.unit)
            print(json.dumps({'event': 'arm_start', 'arm': directory.name}), flush=True)
            arm = {'name': directory.name, **ready_at(bench_url), 'runs': [],
                   'process': verify_process(variant), 'warmup': warmup()}
            report['arms'].append(arm)
            for padding in (16, 80):
                out = directory / f'tail-{padding}.json'
                pre = idle(bench_url)
                with (directory / f'tail-{padding}.stdout').open('w') as stdout:
                    subprocess.run(probe_command(out, padding), env=env, stdout=stdout, check=True)
                result = json.loads(out.read_text())
                post = idle(bench_url)
                assert post['totals']['requests'] - pre['totals']['requests'] == 3, 'Unexpected requests in isolated trial'
                assert result['completed']
                arm['runs'].append({'padding_rows': padding, 'canaries': result['all_state_canaries_correct'],
                    'requests': [{k: r[k] for k in ('prompt_tokens_offline', 'elapsed_s', 'usage', 'timings',
                                                  'answer_correct', 'output_sha256')} for r in result['runs']]})
                save()
                print(json.dumps({'event': 'case_complete', 'arm': directory.name, 'padding_rows': padding,
                    'canaries': result['all_state_canaries_correct'],
                    'cached': [r['usage']['prompt_tokens_details']['cached_tokens'] for r in result['runs']],
                    'wall_s': [round(r['elapsed_s'], 3) for r in result['runs']]}), flush=True)
            if variant == 'candidate':
                with (directory / 'tools.stdout').open('w') as stdout:
                    subprocess.run([sys.executable, str(Path(__file__).with_name('strata-checkpoint-tools.py')),
                        '--profile', str(private), '--out', str(directory / 'tools.json'),
                        '--runtime-padding-rows', '100'], stdout=stdout, check=True)
                arm['tool_state_checks'] = json.loads((directory / 'tools.json').read_text())['passed']
                save()
        report['completed'] = True
    except BaseException as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        if touched:
            service('stop', a.unit)
            override.unlink(missing_ok=True)
            service('daemon-reload')
            service('start', '--no-block', a.unit)
            report['restoration'] = ready_at(live_url)
            assert a.profile.read_bytes() == baseline_bytes
            assert {str(p): p.read_bytes() for p in unit_dir.glob('*.conf')} == originals
            report['restoration']['profile_and_overrides_unchanged'] = True
        save()
        print(json.dumps({'event': 'finished', 'completed': report['completed'],
                          'restored': bool(report.get('restoration'))}), flush=True)


if __name__ == '__main__':
    main()
