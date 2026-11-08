#!/usr/bin/env python3
"""Summarize native decode segments and the bracketing profiler experiment."""
import argparse
import json
from pathlib import Path
import re


def timing(line):
    m = re.search(r'(\d+) windows, avg T ([\d.]+), ([\d.]+) tokens/window, ([\d.]+) ms/window', line)
    assert m, line
    result = dict(zip(('windows', 'avg_T', 'tokens_per_window', 'ms_per_window'), map(float, m.groups())))
    for name in ('verify', 'draft', 'commit/emit', 'other'):
        match = re.search(r'\b' + re.escape(name) + r' ([\d.]+)', line)
        result[name] = float(match.group(1)) if match else 0
    return result


def stages(line):
    total = re.search(r'\| total ([\d.]+) ms/window over (\d+) windows', line)
    assert total
    parts = line.split('GDN layers: ', 1)[1].split(' | QSA layers: ', 1)
    values = {}
    for namespace, part in zip(('GDN', 'QSA'), parts):
        for key, value in re.findall(r'(.+?)\s+(\d+\.\d+)(?=\s|$)', part.split(' | total')[0]):
            key = namespace + '/' + key.strip()
            assert key not in values
            values[key] = float(value)
    return {'total': float(total.group(1)), 'windows': int(total.group(2)), 'stages': values}


def generation_telemetry(path):
    """Only differences wholly inside a sampled generation interval.

    Two-second samples omit boundary intervals; these are observed lower bounds,
    not exact attribution of every stall to an individual native segment.
    """
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    result = {}
    for before, after in zip(rows, rows[1:]):
        b, e = before['live'], after['live']
        if b['state'] != 'generating' or e['state'] != 'generating' or b['prompt_tokens'] != e['prompt_tokens']:
            continue
        key = str(e['prompt_tokens'])
        out = result.setdefault(key, {'sampled_seconds': 0, 'evicted_ms': {}, 'swap_in_pages': 0})
        out['sampled_seconds'] += after['unix_s'] - before['unix_s']
        for pid, value in after['evicted_ms'].items():
            if pid in before['evicted_ms']:
                out['evicted_ms'][pid] = out['evicted_ms'].get(pid, 0) + value - before['evicted_ms'][pid]
        out['swap_in_pages'] += after['swap']['pswpin'] - before['swap']['pswpin']
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    manifest = json.loads((a.trial / 'summary.json').read_text())
    assert manifest['completed'] and manifest['restoration']['profile_and_overrides_unchanged']
    result = {'protocol': 'decode-profile-analysis-v1', 'arms': [], 'comparisons': [],
              'limits': manifest['limits'] + ['Timing-line values round to 0.01 ms; native durations round to milliseconds.',
                'GPU stage counts can include initialization windows; they are retained explicitly.',
                'Hypothetical speedups assume identical accepted tokens and no replacement costs; they are not measurements.',
                'Eviction/swap counts cover only intervals fully inside sampled generation, excluding boundary intervals.',
                'Auto conversation-cache budgets can differ between launches; see arm metadata.']}
    for arm in manifest['arms']:
        directory = a.trial / f"{arm['index']:02d}-" / ('profile' if arm['profiled'] else 'control')
        if not directory.is_dir():
            # Published evidence flattens the private run's nested arm folders.
            directory = a.trial / (f"{arm['index']:02d}-" + ('profile' if arm['profiled'] else 'control'))
        native = json.loads((directory / 'native-accounting.json').read_text())['groups']
        api = json.loads((directory / 'results.json').read_text())['runs']
        gpu = [stages(l) for l in json.loads((directory / 'gpu-stages.json').read_text())['lines']]
        assert not gpu or len(gpu) == sum(map(len, native))
        offset = 0
        rows = []
        for group, request in zip(native, api):
            section = gpu[offset:offset + len(group)] if gpu else []
            offset += len(group)
            if request['warmup']:
                continue
            ts = [timing(r['timing_line']) for r in group]
            windows = sum(t['windows'] for t in ts)
            generated = sum(r['generated'] for r in group)
            decode_ms = sum(r['decode_ms'] for r in group)
            verify_ms = sum(t['windows'] * t['verify'] for t in ts)
            draft_ms = sum(t['windows'] * t['draft'] for t in ts)
            offered = sum(r['offered'] for r in group)
            row = {'target_tokens': request['target_tokens'], 'prompt_tokens': request['usage']['prompt_tokens'],
                   'output_sha256': request['output_sha256'], 'messages_sha256': request['messages_sha256'],
                   'generated_native': generated, 'decode_ms': decode_ms, 'decode_tok_s': generated * 1000 / decode_ms,
                   'native_segments': len(group), 'windows': windows, 'tokens_per_window': generated / windows,
                   'avg_T': sum(t['windows'] * t['avg_T'] for t in ts) / windows,
                   'verify_ms_per_window': verify_ms / windows, 'draft_ms_per_window': draft_ms / windows,
                   'verify_share': verify_ms / decode_ms, 'draft_share': draft_ms / decode_ms,
                   'accepted_fraction': sum(r['accepted'] for r in group) / offered,
                   'zero_draft_hypothetical_tok_s': generated * 1000 / (decode_ms - draft_ms),
                   'required_time_reduction': {str(target): 1 - generated * 1000 / target / decode_ms for target in (60, 70)}}
            if section:
                gw = sum(s['windows'] for s in section)
                means = {k: sum(s['stages'].get(k, 0) * s['windows'] for s in section) / gw for k in section[0]['stages']}
                total = sum(s['total'] * s['windows'] for s in section) / gw
                categories = {
                    'experts': sum(v for k, v in means.items() if k.endswith('/VRAM hits')),
                    'shared_experts': sum(v for k, v in means.items() if k.endswith('/shared+quant')),
                    'hyperconnections': sum(v for k, v in means.items() if '/hc' in k),
                    'head': means['GDN/head'],
                    'qsa_selection_and_attention': sum(means['QSA/' + k] for k in ('scores+topk', 'kv-resolve', 'attention'))}
                row['gpu_profile'] = {'windows': gw, 'total_ms_per_window': total,
                                      'stages': means, 'categories_ms_per_window': categories}
            rows.append(row)
        result['arms'].append({'index': arm['index'], 'profiled': arm['profiled'], 'runs': rows,
            'generation_telemetry': generation_telemetry(directory / 'telemetry.jsonl'),
            'conversation_cache_mib': arm['before']['engine']['conversation_cache_mib']})
    controls = [result['arms'][i]['runs'] for i in (0, 2)]
    profile = result['arms'][1]['runs']
    for first, second, prof in zip(*controls, profile):
        assert first['messages_sha256'] == second['messages_sha256'] == prof['messages_sha256']
        mean = (first['decode_tok_s'] + second['decode_tok_s']) / 2
        result['comparisons'].append({'target_tokens': first['target_tokens'],
            'control_tok_s': [first['decode_tok_s'], second['decode_tok_s']],
            'control_mean_tok_s': mean, 'profile_tok_s': prof['decode_tok_s'],
            'profile_throughput_change_percent': 100 * (prof['decode_tok_s'] / mean - 1),
            'control_output_hashes_match': first['output_sha256'] == second['output_sha256'],
            'profile_output_hash_matches_control': first['output_sha256'] == prof['output_sha256'],
            'time_reduction_needed_for_60': 1 - mean / 60,
            'time_reduction_needed_for_70': 1 - mean / 70})
    a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['comparisons'], indent=2))


if __name__ == '__main__':
    main()
