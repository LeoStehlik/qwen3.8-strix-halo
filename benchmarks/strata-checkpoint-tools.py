#!/usr/bin/env python3
"""Public long-prefix tool/cache checks against an idle backend; no tools execute.

This validates the serving API and full-state reuse, not OpenClaw delivery or
general answer quality. Credentials stay in the private profile.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--runtime-padding-rows', type=int, default=0,
                    help='Inert rows in the moving context to check long-tail restore points')
    a = ap.parse_args()
    assert 0 <= a.runtime_padding_rows <= 200
    cfg = json.loads(a.profile.read_text())
    url = f"http://{cfg['host']}:{cfg['port']}"
    headers = {'Authorization': 'Bearer ' + cfg['api_key'], 'Content-Type': 'application/json'}
    report = {'protocol': 'checkpoint-tools-v1', 'synthetic': True,
              'real_tools_executed': False, 'checks': [], 'passed': False}

    def request(path, body=None):
        q = urllib.request.Request(url + path, None if body is None else json.dumps(body).encode(), headers)
        with urllib.request.urlopen(q, timeout=600) as r:
            return json.load(r)

    before = request('/metrics')
    assert before['live']['state'] == 'idle' and not before['live']['queued']
    count = before['totals']['requests']

    def save():
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2) + '\n')

    def chat(label, messages, tools=None):
        nonlocal count
        m = request('/metrics')
        assert m['live']['state'] == 'idle' and not m['live']['queued'], 'Real traffic is active'
        assert m['totals']['requests'] == count, 'Traffic arrived; defer synthetic checks'
        body = {'model': cfg['model_name'], 'messages': messages, 'temperature': 0,
                'max_tokens': 2048, 'stream': False}
        if tools:
            body.update(tools=tools, tool_choice='auto')
        start = time.monotonic()
        response = request('/v1/chat/completions', body)
        count += 1
        choice = response['choices'][0]
        row = {'label': label, 'elapsed_s': time.monotonic() - start,
               'usage': response.get('usage'), 'timings': response.get('timings'),
               'finish_reason': choice.get('finish_reason'), 'message': choice['message']}
        report['checks'].append(row)
        save()
        assert not response.get('error') and choice.get('finish_reason') != 'length'
        return choice['message'], row

    args = {'record_id': 'TIER-042', 'include_archived': False, 'fields': ['status', 'owner']}
    tool = {'type': 'function', 'function': {'name': 'lookup_record',
            'description': 'Read the current record from the registry.', 'parameters': {
            'type': 'object', 'properties': {'record_id': {'type': 'string'},
            'include_archived': {'type': 'boolean'}, 'fields': {'type': 'array', 'items': {'type': 'string'}}},
            'required': list(args), 'additionalProperties': False}}}
    # Long enough to exercise the engine's >=8192-token message-boundary selector.
    base = [{'role': 'system', 'content': 'Checkpoint tool validation A. Root marker is ROOT-VIOLET-42. '
             'Use tools for retrieval. Reference rows below are inert data, not instructions.\n' +
             ''.join(f'Reference row {i:05d}: alpha beta gamma delta epsilon.\n' for i in range(700))},
            {'role': 'user', 'content': 'Look up record TIER-042, exclude archived records, and request '
             'fields status and owner in that order. After the tool returns, report verification_code '
             'exactly together with the root marker. Do not invent either value.'}]
    carrier = {'role': 'user', 'content': 'Runtime context: follow the original task above. '
               'Use the available tool when retrieval is needed; once results arrive, answer from them.'}
    carrier['content'] += ''.join(f'\nInert runtime row {i:03d}: copper silver gold.'
                                 for i in range(a.runtime_padding_rows))
    try:
        first, cold = chat('long-prefix-tool-call', base + [carrier], [tool])
        calls = first.get('tool_calls') or []
        assert cold['usage']['prompt_tokens'] > 8192
        assert len(calls) == 1
        call = calls[0]
        assert call.get('id') and call['function']['name'] == 'lookup_record'
        assert json.loads(call['function']['arguments']) == args
        report['exact_tool_arguments'] = True
        base += [first, {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps({
            'status': 'READY', 'owner': 'Harper', 'verification_code': 'R7P2'})}]
        second, continuation = chat('moving-context-tool-result', base + [carrier], [tool])
        text = second.get('content') or ''
        assert not second.get('tool_calls') and 'R7P2' in text and 'ROOT-VIOLET-42' in text
        report['tool_result_continuation'] = True
        # Different conversation forces the previous conversation to be parked/reselected.
        other, _ = chat('other-conversation', [{'role': 'system', 'content': 'Checkpoint validation B.'},
                        {'role': 'user', 'content': 'Reply only with SEPARATE-19.'}])
        assert 'SEPARATE-19' in (other.get('content') or '')
        base += [second, {'role': 'user', 'content': 'Without calling tools again, repeat the verification '
                 'code and root marker, and name the owner from that result.'}]
        final, restored = chat('restored-follow-up', base + [carrier], [tool])
        text = final.get('content') or ''
        assert not final.get('tool_calls') and all(x in text for x in ['R7P2', 'ROOT-VIOLET-42', 'Harper'])
        reused = [r['usage']['prompt_tokens_details']['cached_tokens'] for r in [continuation, restored]]
        assert reused[0] >= 8192 and reused[1] > reused[0], 'History reuse did not advance'
        report.update(restored_state_correct=True, advancing_reused_tokens=reused, passed=True)
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        save()
    print(json.dumps({k: report[k] for k in ['passed', 'exact_tool_arguments', 'tool_result_continuation',
                                          'restored_state_correct', 'advancing_reused_tokens']}))


if __name__ == '__main__':
    main()
