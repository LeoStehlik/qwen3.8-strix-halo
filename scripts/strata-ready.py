#!/usr/bin/env python3
"""Wait for authenticated model readiness without creating an inference request."""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--timeout', type=float, default=240)
    a = ap.parse_args()
    cfg = json.loads(a.profile.read_text())
    assert cfg.get('api_key'), 'An authenticated profile is required'
    args = cfg['args']
    context = int(args[args.index('--max-context') + 1])
    req = urllib.request.Request(
        f"http://{cfg['host']}:{cfg['port']}/health",
        headers={'Authorization': 'Bearer ' + cfg['api_key']})
    deadline = time.monotonic() + a.timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                health = json.load(r)
            if health.get('loaded'):
                assert health.get('model') == cfg['model_name'], 'Wrong model'
                assert health.get('max_context') == context, 'Wrong context capacity'
                assert health.get('api_key') is True, 'Authentication is disabled'
                print('Strata model loaded; model, context and authentication verified.', flush=True)
                return
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
            pass
        time.sleep(2)
    raise SystemExit('Strata did not become ready before the startup deadline')


if __name__ == '__main__':
    main()
