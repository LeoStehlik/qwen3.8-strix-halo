#!/usr/bin/env python3
"""Measure isolated, approximately 64K/128K cold prefill over Strata's HTTP API.

Use a public text fixture. Exact prompt and uncached counts come from each
response; do not substitute the requested size for the actual token count.
This is a custom performance probe, not Strata's standard benchmark suite.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import uuid


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', default='http://127.0.0.1:8083')
    ap.add_argument('--fixture', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--sizes', type=int, nargs='+', default=[65536, 131072])
    ap.add_argument('--repeat', type=int, default=2)
    ap.add_argument('--max-tokens', type=int, default=128,
                    help='Output allowance for benchmark requests only')
    ap.add_argument('--spec-min-p', type=float,
                    help='Optional Strata draft-confidence override for these requests only')
    ap.add_argument('--presence-penalty', type=float,
                    help='Explicit request penalty; omitted retains the server default (1.5 for non-thinking Flash-Next)')
    ap.add_argument('--sampling-preset', choices=('greedy', 'openclaw'), default='greedy',
                    help='OpenClaw preset uses thinking and the recorded tiercelmoe sampling values')
    ap.add_argument('--nonce-seed',
                    help='Reproducible prompt nonce for comparisons across fresh server starts')
    ap.add_argument('--model', default='qwen3.8-flash-next-unsloth')
    args = ap.parse_args()
    if args.repeat < 1 or args.max_tokens < 1 or any(n < 1024 for n in args.sizes):
        ap.error('Use positive repeats/output allowance and sizes of at least 1024 tokens')
    if args.spec_min_p is not None and not 0 <= args.spec_min_p <= 1:
        ap.error('--spec-min-p must be between zero and one')
    if args.presence_penalty is not None and not 0 <= args.presence_penalty <= 2:
        ap.error('--presence-penalty must be between zero and two')
    raw = args.fixture.read_bytes()
    source = raw.decode('utf-8')
    if not source.strip():
        ap.error('The fixture must contain text')
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('STRATA_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['STRATA_API_KEY']
    sampling = {'temperature': 0, 'enable_thinking': False, 'max_tokens': args.max_tokens}
    if args.sampling_preset == 'openclaw':
        sampling.update(temperature=0.3, enable_thinking=True, top_p=0.95, top_k=20,
                        min_p=0.05, presence_penalty=0, repeat_penalty=1, seed=1)
    report = {'protocol': 'strata-cold-prefill-custom-v3',
              'fixture_sha256': hashlib.sha256(raw).hexdigest(),
              'sampling': sampling, 'sampling_preset': args.sampling_preset,
              'nonce_seed': args.nonce_seed,
              'strata_tune': {} if args.spec_min_p is None else {'spec_min_p': args.spec_min_p},
              'runs': [], 'completed': False}
    if args.presence_penalty is not None:
        report['sampling']['presence_penalty'] = args.presence_penalty
    elif 'presence_penalty' not in sampling:
        report['sampling']['presence_penalty_source'] = 'server default; not overridden'

    def request(path, body, timeout=1800):
        req = urllib.request.Request(args.url.rstrip('/') + path,
                                     json.dumps(body).encode(), headers)
        return urllib.request.urlopen(req, timeout=timeout)

    def persist():
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + '\n')

    def messages(text, nonce):
        return [{'role': 'user', 'content': f'{nonce}\nRead this reference material:\n{text}\n'
                 'List the main technical themes with a brief explanation of each.'}]

    def count(text):
        # This performs no inference. API templates can differ by a few tokens;
        # the completion's actual usage is the measurement, not this estimate.
        with request('/v1/messages/count_tokens', {'model': args.model,
                     'messages': messages(text, '0123456789abcdef' * 2),
                     'thinking': {'type': 'disabled'}, 'max_tokens': 128}) as r:
            return int(json.load(r)['input_tokens'])

    def run(text, target, repetition, warmup=False):
        nonce = '0123456789abcdef' * 2 if warmup else uuid.uuid4().hex
        if not warmup and args.nonce_seed is not None:
            nonce = hashlib.sha256(f'{args.nonce_seed}:{target}:{repetition}'.encode()).hexdigest()[:32]
        msg = messages(text, nonce)
        body = {'model': args.model, 'messages': msg, 'stream': True,
                'stream_options': {'include_usage': True},
                'reasoning_effort': 'medium' if sampling['enable_thinking'] else 'none',
                'chat_template_kwargs': {'enable_thinking': sampling['enable_thinking']},
                'max_tokens': args.max_tokens if not warmup else 16}
        for name in ('temperature', 'top_p', 'top_k', 'min_p', 'presence_penalty', 'repeat_penalty', 'seed'):
            if name in sampling:
                body[name] = sampling[name]
        if report['strata_tune']:
            body['strata_tune'] = report['strata_tune']
        start = time.monotonic()
        clock_start = {'monotonic_ns': time.monotonic_ns(), 'unix_ns': time.time_ns(),
                       'monotonic_raw_ns': time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW),
                       'boottime_ns': time.clock_gettime_ns(time.CLOCK_BOOTTIME)}
        first = None
        first_monotonic_ns = None
        usage = timings = None
        output = []
        finish = None
        saw_done = False
        with request('/v1/chat/completions', body) as response:
            for line in response:
                if not line.startswith(b'data:'):
                    continue
                data = line[5:].strip()
                if data == b'[DONE]':
                    saw_done = True
                    break
                event = json.loads(data)
                if event.get('error'):
                    raise RuntimeError(event['error'])
                usage = event.get('usage') or usage
                timings = event.get('timings') or timings
                for choice in event.get('choices', []):
                    delta = choice.get('delta') or {}
                    piece = (delta.get('reasoning_content') or '') + (delta.get('content') or '')
                    if piece:
                        if first is None:
                            first = time.monotonic() - start
                            first_monotonic_ns = time.monotonic_ns()
                        output.append(piece)
                    finish = choice.get('finish_reason') or finish
        row = {'target_tokens': target, 'repeat': repetition, 'warmup': warmup,
               'nonce': nonce, 'messages_sha256': hashlib.sha256(json.dumps(msg).encode()).hexdigest(),
               'usage': usage, 'timings': timings, 'first_token_s': first,
               'elapsed_s': time.monotonic() - start, 'finish_reason': finish,
               'clock_start': clock_start, 'end_monotonic_ns': time.monotonic_ns(),
               'first_token_monotonic_ns': first_monotonic_ns,
               'complete_stream': saw_done,
               'output_sha256': hashlib.sha256(''.join(output).encode()).hexdigest()}
        report['runs'].append(row)
        persist()
        if first is None or not usage or not timings or not saw_done:
            raise RuntimeError('Incomplete response or missing measurements')
        if not warmup and int(timings.get('cache_n', -1)) not in range(65):
            raise RuntimeError('Cache accounting absent or >64 tokens reused; not a cold result')
        print(json.dumps(row), flush=True)

    try:
        # Stay above the engine's 64-token short-read boundary. A random nonce
        # and a tiny warm-up could select different paths between fresh loads.
        run('Explain what a compiler does. ' * 16, 0, 0, warmup=True)
        for size in args.sizes:
            # Repetition changes expert distributions; record the fixture and
            # construction method, and also judge separate real OpenClaw traffic.
            expanded = (source + '\n') * max(1, (size * 8 // (len(source) + 1)) + 1)
            lo, hi = 1, len(expanded)
            if count(expanded) < size:
                raise RuntimeError('Fixture has too few tokens; provide a denser public text')
            best = expanded
            for _ in range(18):
                mid = (lo + hi) // 2
                best = expanded[:mid]
                n = count(best)
                if abs(n - size) <= 8:
                    break
                if n < size:
                    lo = mid + 1
                else:
                    hi = mid - 1
            for repetition in range(args.repeat):
                run(best, size, repetition)
        report['completed'] = True
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        persist()


if __name__ == '__main__':
    main()
