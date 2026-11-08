#!/usr/bin/env python3
"""Copy an installed Flash-Next profile with the measured Halo memory settings.

Preserves model paths, vision settings and API credentials; starts nothing.
The intended host is a 128 GB Strix Halo with the documented GPU memory budget.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-profile', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--host', help='Optional explicit bind address; otherwise preserve source')
    ap.add_argument('--credentials-profile', type=Path,
                    help='Optional private profile supplying the existing API key')
    a = ap.parse_args()
    assert a.out.resolve() != a.source_profile.resolve(), 'Keep the original profile'
    cfg = json.loads(a.source_profile.read_text())
    if a.credentials_profile:
        cfg['api_key'] = json.loads(a.credentials_profile.read_text())['api_key']
    elif not cfg.get('api_key'):
        cfg['api_key'] = os.environ.get('STRATA_API_KEY')
    assert cfg.get('api_key'), 'Supply an existing credentials profile or STRATA_API_KEY'
    assert cfg['model_name'] == 'qwen3.8-flash-next-unsloth-ud-q4_k_xl'
    # This is the tested Qwen tokenizer and start-position effort template.
    # Never copy the numeric role ID to another model/template without checking.
    assert json.loads((Path(cfg['tokenizer']) / 'vocab.json').read_text())['user'] == 846
    assert cfg.get('effort_position', 'start') == 'start'
    values = {'--expert-cache': 'auto', '--prefill': '16384', '--spec': '4',
              '--spec-min-p': '0.5', '--max-context': '262144', '--kv': 'int8',
              '--ple-io': 'mmap', '--kv-resident': '0', '--vram-reserve-mib': '700',
              '--tail-role-token': '846'}
    old, args, i = cfg['args'], [], 0
    while i < len(old):
        key = old[i]
        if key in values or key == '--resident-budget-gib':
            assert i + 1 < len(old) and not old[i + 1].startswith('--'), f'Missing value for {key}'
            i += 2
        elif key in ('--mmap-experts', '--no-prefill-borrow'):
            i += 1
        else:
            args.append(key)
            i += 1
    for key, value in values.items():
        args += [key, value]
    args += ['--mmap-experts', '--no-prefill-borrow']
    cfg.update(args=args, args_written=list(args), parallel=1)
    if a.host:
        cfg['host'] = a.host
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=a.out.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(json.dumps(cfg, indent=2) + '\n')
    temp.replace(a.out)
    print('Prepared private optimized profile; no service was started or changed.')


if __name__ == '__main__':
    main()
