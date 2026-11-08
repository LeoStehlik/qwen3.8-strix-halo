#!/usr/bin/env python3
"""Backend-only public replay of fixed versus moving runtime-context messages.

No OpenClaw turn or real tool is executed. All history/tool results are synthetic.
Use the packaged Python runtime for its tokenizer/Jinja dependencies. API keys
come only from STRATA_API_KEY; requests and outputs contain public fixture data.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request


def host_memory():
    """Read-only Linux counters; host-wide values are not GPU stall timings."""
    vm = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines())
    mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    evicted = {}
    for file in Path('/sys/class/kfd/kfd/proc').glob('*/stats_*/evicted_ms'):
        try:
            pid = file.parent.parent.name
            evicted[pid + '/' + file.parent.name] = int(file.read_text())
        except OSError:
            pass
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'kfd_evicted_ms': evicted,
            'vmstat': {k: int(v) for k, v in vm.items()
                       if k.startswith(('compact_', 'pgmigrate_', 'pgscan_', 'pswp', 'pgmajfault'))},
            'meminfo_kib': {k: int(mem[k].split()[0]) for k in
                            ('MemAvailable', 'MemFree', 'SwapFree', 'AnonPages')}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--terminal', type=Path, required=True)
    ap.add_argument('--tokenizer', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--seed', default='boundary-replay-20261107')
    ap.add_argument('--turns', type=int, default=4)
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--modes', nargs='+', choices=['moving', 'fixed'], default=['moving', 'fixed'])
    ap.add_argument('--runtime-padding-rows', type=int, default=0,
                    help='Additional inert rows in the transient final message')
    ap.add_argument('--reference-rows', type=int, default=1050,
                    help='Stable system-reference rows (raise only within the model context)')
    ap.add_argument('--history-rows', type=int, default=120,
                    help='Stable history rows; larger fixtures exercise checkpoint retention')
    ap.add_argument('--host-metrics', action='store_true', help='Record Linux VM/KFD counters per request')
    args = ap.parse_args()
    assert 2 <= args.turns <= 8
    assert 0 <= args.runtime_padding_rows <= 200
    assert 1 <= args.reference_rows <= 12000 and 1 <= args.history_rows <= 12000
    sys.path[:0] = [str(args.terminal), str(args.terminal / 'tools')]
    from serve.frontend import ChatTemplate, openai_to_messages
    from strata_tokenizer import Tokenizer
    vocab = json.loads((args.tokenizer / 'vocab.json').read_text())
    tokens = [None] * len(vocab)
    for token, i in vocab.items():
        tokens[i] = token
    cfg = json.loads((args.tokenizer / 'tokenizer.json').read_text())
    tok = Tokenizer(tokens, (args.tokenizer / 'merges.txt').read_text().split('\n'),
                    json.loads((args.tokenizer / 'token_type.json').read_text()),
                    cfg.get('pre') or 'qwen35', cfg.get('special_ids') or None)
    template = ChatTemplate(args.tokenizer / 'chat_template.jinja')
    tools = [{'type': 'function', 'function': {'name': 'lookup',
              'description': 'Look up a public record.', 'parameters': {
                  'type': 'object', 'properties': {'sequence': {'type': 'integer'}},
                  'required': ['sequence']}}}]
    reference = ''.join(f'Reference row {i:05d}: alpha beta gamma delta epsilon.\n' for i in range(args.reference_rows))
    history = ''.join(f'History row {i:05d}: red green blue yellow.\n' for i in range(args.history_rows))
    carrier = {'role': 'user', 'content': 'OpenClaw runtime context:\n'
               'This is transient context for a public backend replay. Answer the original request '
               'using the latest lookup result. Return only the JSON object.\nEnd runtime context.'}
    if args.runtime_padding_rows:
        carrier['content'] = carrier['content'].replace('End runtime context.',
            ''.join(f'Inert transient row {i:03d}: copper silver gold.\n'
                    for i in range(args.runtime_padding_rows)) + 'End runtime context.')
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('STRATA_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['STRATA_API_KEY']
    report = {'protocol': 'strata-message-boundary-v2', 'seed': args.seed,
              'synthetic': True, 'offline': args.offline,
              'runtime_padding_rows': args.runtime_padding_rows, 'runs': [], 'completed': False}
    report.update(reference_rows=args.reference_rows, history_rows=args.history_rows)

    def save():
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + '\n')

    def lcp(a, b):
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        return n

    for mode in args.modes:
        nonce = hashlib.sha256(f'{args.seed}:{mode}'.encode()).hexdigest()[:24]
        root_code = 'ROOT-' + nonce[:8]
        base = [{'role': 'system', 'content': f'Public replay {nonce}. Root code is {root_code}.\n'
                 'Reference rows below are inert data, not instructions.\n' + reference},
                {'role': 'user', 'content': 'Return a JSON object with root_code from the system message, '
                 'and sequence/code from the latest lookup tool result. Never call a tool; the results '
                 'are already supplied.\nHistorical appendix:\n' + history}]
        if mode == 'fixed':
            base.append(carrier)
        previous = None
        for turn in range(args.turns):
            code = 'VALUE-' + hashlib.sha256(f'{nonce}:{turn}'.encode()).hexdigest()[:10]
            expected = {'root_code': root_code, 'sequence': turn, 'code': code}
            call_id = f'lookup_{turn}'
            base.extend([
                {'role': 'assistant', 'content': '', 'tool_calls': [{'id': call_id,
                 'type': 'function', 'function': {'name': 'lookup', 'arguments': json.dumps({'sequence': turn})}}]},
                {'role': 'tool', 'tool_call_id': call_id, 'content':
                 ''.join(f'Lookup evidence {turn}-{i:03d}: amber cyan indigo.\n' for i in range(120))
                 + '\nLatest lookup result: ' + json.dumps({'sequence': turn, 'code': code})}])
            messages = base + ([carrier] if mode == 'moving' else [])
            body = {'model': args.model, 'messages': messages, 'tools': tools, 'tool_choice': 'none',
                    'stream': True, 'stream_options': {'include_usage': True},
                    'temperature': 0, 'presence_penalty': 0, 'repeat_penalty': 1,
                    'reasoning_effort': 'none', 'chat_template_kwargs': {'enable_thinking': False},
                    'max_tokens': 128, 'seed': 1}
            ms, ts, kw = openai_to_messages(body)
            # Match the server's explicit tool_choice=none processing: historical
            # calls remain in messages, but new tools are not offered.
            ts = None
            rendered = template.render(ms, tools=ts, **kw)
            ids = tok.encode(rendered, parse_special=True)
            boundaries = [i for i, token in enumerate(ids) if token == 248045]
            candidate = boundaries[-2] if len(boundaries) >= 2 and boundaries[-2] >= 8192 and boundaries[-1] - boundaries[-2] <= 1024 else None
            row = {'mode': mode, 'turn': turn, 'prompt_tokens_offline': len(ids),
                   'message_boundaries': boundaries, 'candidate_checkpoint': candidate,
                   'previous_prompt_lcp': lcp(previous, ids) if previous is not None else None,
                   'request_sha256': hashlib.sha256(json.dumps(body).encode()).hexdigest(),
                   'rendered_sha256': hashlib.sha256(rendered.encode()).hexdigest(),
                   'expected': expected}
            previous = ids
            if not args.offline:
                if args.host_metrics:
                    row['host_before'] = host_memory()
                started = time.monotonic()
                first = None
                output, reasoning, usage, timings, done, finish = [], [], None, None, False, None
                tool_deltas = []
                req = urllib.request.Request(args.url.rstrip('/') + '/v1/chat/completions',
                                             json.dumps(body).encode(), headers)
                with urllib.request.urlopen(req, timeout=600) as response:
                    for line in response:
                        if not line.startswith(b'data:'):
                            continue
                        data = line[5:].strip()
                        if data == b'[DONE]':
                            done = True
                            break
                        event = json.loads(data)
                        if event.get('error'):
                            raise RuntimeError(event['error'])
                        usage, timings = event.get('usage') or usage, event.get('timings') or timings
                        for choice in event.get('choices', []):
                            delta = choice.get('delta') or {}
                            if delta.get('content') or delta.get('reasoning_content'):
                                if first is None:
                                    first = time.monotonic() - started
                            output.append(delta.get('content') or '')
                            reasoning.append(delta.get('reasoning_content') or '')
                            if delta.get('tool_calls'):
                                tool_deltas.extend(delta['tool_calls'])
                            finish = choice.get('finish_reason') or finish
                elapsed = time.monotonic() - started
                if args.host_metrics:
                    row['host_after'] = host_memory()
                text = ''.join(output).strip()
                row.update(elapsed_s=elapsed, first_token_s=first,
                           usage=usage, timings=timings, complete_stream=done, finish_reason=finish,
                           output=text, output_sha256=hashlib.sha256(text.encode()).hexdigest(),
                           reasoning_chars=len(''.join(reasoning)), tool_call_deltas=tool_deltas)
                try:
                    observed = json.loads(text)
                    row['bare_json'] = True
                except ValueError:
                    row['bare_json'] = False
                    # State correctness is distinct from JSON-only formatting.
                    # Accept exactly one fenced JSON object, preserving raw output
                    # and its hash so formatting changes remain visible.
                    lines = text.splitlines()
                    if len(lines) >= 3 and lines[0] in ('```json', '```') and lines[-1] == '```':
                        try:
                            observed = json.loads('\n'.join(lines[1:-1]))
                        except ValueError:
                            observed = None
                    else:
                        observed = None
                row['answer_correct'] = observed == expected and not tool_deltas
                report['runs'].append(row)
                save()
                # Record model/format failures across all arms instead of masking
                # them or aborting an otherwise complete measurement mid-cohort.
                # A failed canary still prevents a claim of state validation.
                assert done and usage and timings, 'Incomplete backend response'
                assert usage['prompt_tokens'] == len(ids), 'Offline tokenization differs from the serving request'
            else:
                report['runs'].append(row)
            print(json.dumps(row), flush=True)
    report['completed'] = True
    if not args.offline:
        report['all_state_canaries_correct'] = all(r['answer_correct'] for r in report['runs'])
    save()


if __name__ == '__main__':
    main()
