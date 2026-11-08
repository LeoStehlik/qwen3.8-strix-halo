#!/usr/bin/env python3
"""Replay captured text requests to the same local backend to verify cache reuse.

No OpenClaw session is run and no returned tool call is executed. Only these
probe requests have an eight-token output allowance. This checks prompt/state
reuse, not answer quality or generation speed. Input files remain private;
the result contains hashes and counts only, never prompt/response text.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--audit-dir', type=Path, required=True)
    ap.add_argument('--indices', type=int, nargs='+', required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    cfg = json.loads(a.profile.read_text())
    audit = json.loads((a.audit_dir / 'prefix-summary.json').read_text())
    headers = {'Authorization': 'Bearer ' + cfg['api_key'], 'Content-Type': 'application/json'}
    url = f"http://{cfg['host']}:{cfg['port']}"

    def api(path, body=None):
        req = urllib.request.Request(url + path, json.dumps(body).encode() if body is not None else None, headers)
        return json.load(urllib.request.urlopen(req, timeout=600))

    m = api('/metrics')
    assert m['live']['state'] == 'idle' and not m['live'].get('queued')
    count = m['totals']['requests']
    assert m['engine']['tail_role_token'] == 846
    report = {'protocol': 'captured-wire-cache-replay-v1', 'real_tools_executed': False,
              'output_limit_probe_only': 8, 'quality_claim': False, 'rows': [], 'passed': False}
    previous, previous_ids = None, None
    try:
        for index in a.indices:
            r = audit['requests'][index]
            p = a.audit_dir / 'requests' / (r['key'] + '.request.json')
            original = p.read_bytes()
            body = json.loads(original)
            assert body['model'] == cfg['model_name']
            body.pop('max_tokens', None)
            body['max_completion_tokens'] = 8
            body['stream'] = False
            body.pop('stream_options', None)
            ids = json.loads((a.audit_dir / 'requests' / (r['key'] + '.tokens.json')).read_text())
            if previous_ids is not None:
                common = 0
                for x, y in zip(previous_ids, ids):
                    if x != y:
                        break
                    common += 1
                expected = previous['message_boundaries'][-2]
                assert common >= expected, 'Chosen replays change earlier history; choose comparable requests'
            else:
                common = expected = None
            m = api('/metrics')
            assert m['live']['state'] == 'idle' and not m['live'].get('queued')
            assert m['totals']['requests'] == count, 'Concurrent request: defer replay'
            start = time.monotonic()
            response = api('/v1/chat/completions', body)
            count += 1
            usage = response['usage']
            assert usage['prompt_tokens'] == r['prompt_tokens_offline']
            reused = usage['prompt_tokens_details']['cached_tokens']
            row = {'capture_index': index, 'original_file_sha256': hashlib.sha256(original).hexdigest(),
                   'prompt_tokens': usage['prompt_tokens'], 'reused': reused,
                   'fresh': usage['prompt_tokens'] - reused,
                   'common_prefix_with_prior_replay': common, 'expected_reusable_boundary': expected,
                   'elapsed_s': time.monotonic() - start, 'timings': response.get('timings'),
                   'finish_reason': response['choices'][0]['finish_reason']}
            report['rows'].append(row)
            print(json.dumps(row), flush=True)
            if expected is not None:
                assert reused >= expected and reused <= common, 'Expected matching boundary was not reused'
            previous, previous_ids = r, ids
        report['passed'] = True
    finally:
        a.out.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
