#!/usr/bin/env python3
"""Install the tested persistent service without starting or restarting it.

Run as the serving user, after the pinned bundle/model and an authenticated
optimized profile exist. Existing unit/profile files are backed up privately.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-profile', type=Path, required=True)
    a = ap.parse_args()
    repo = Path(__file__).resolve().parents[1]
    home = Path.home()
    state = home / '.local/share/strata/flash-next'
    bundle = home / '.local/share/strata/terminal/0.1.57'
    engine = home / '.local/share/strata/components/engine/0.1.57-linux-x86_64-hip-halo'
    expected = 'bce2f61ca0f970a1640aafa77925c0908f060243cffcd1ad10e3843b35eed476'
    assert hashlib.sha256((engine / 'strata').read_bytes()).hexdigest() == expected, 'Engine differs from tested build'
    assert (bundle / 'bin/strata').is_file() and (bundle / 'python/bin/python3').is_file()
    cfg = json.loads(a.source_profile.read_text())
    assert cfg.get('api_key') and cfg.get('host') and cfg.get('port')
    assert cfg['model_name'] == 'qwen3.8-flash-next-unsloth-ud-q4_k_xl'
    args = cfg['args']
    for key, value in {'--max-context': '262144', '--kv': 'int8', '--spec': '4',
                       '--prefill': '16384', '--expert-cache': 'auto',
                       '--ple-io': 'mmap', '--kv-resident': '0', '--tail-role-token': '846'}.items():
        assert args[args.index(key) + 1] == value, f'Unexpected {key}'
    assert '--mmap-experts' in args and '--no-prefill-borrow' in args
    cfg['exe'] = str(engine / 'strata')
    cfg['cwd'] = str(bundle)
    cfg['log'] = str(state / 'strata-known-good.log')
    unit = home / '.config/systemd/user/strata-flash-next.service'
    profile = state / 'strata-known-good.json'
    runtime = Path(f'/run/user/{os.getuid()}/systemd/user/strata-flash-next.service.d/90-live-preview.conf')
    backup = state / ('deployment-backup-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(parents=True, mode=0o700)
    for f in [unit, profile, runtime]:
        if f.exists():
            dest = backup / f.name
            shutil.copyfile(f, dest)
            dest.chmod(0o600)
    with tempfile.NamedTemporaryFile(mode='w', dir=state, delete=False) as f:
        temp = Path(f.name)
        f.write(json.dumps(cfg, indent=2) + '\n')
    temp.replace(profile)  # NamedTemporaryFile creates mode 0600, including before rename.
    helper = home / '.local/libexec/strata-ready.py'
    helper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo / 'scripts/strata-ready.py', helper)
    helper.chmod(0o755)
    unit.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(repo / 'systemd/strata-flash-next-known-good.service', unit)
    if runtime.exists():
        runtime.unlink()
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', 'strata-flash-next.service'], check=True)
    print('Persistent service installed and enabled; existing process was not restarted.')
    print('Private rollback backup:', backup)
    print('Ensure loginctl show-user "$USER" reports Linger=yes for startup without login.')


if __name__ == '__main__':
    main()
