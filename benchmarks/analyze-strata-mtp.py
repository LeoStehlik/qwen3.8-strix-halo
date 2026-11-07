#!/usr/bin/env python3
"""Reconcile API throughput and native MTP windows across completed arms."""
import argparse
import json
from pathlib import Path
import re

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('directories', type=Path, nargs='+')
ap.add_argument('--out', type=Path, required=True)
a = ap.parse_args()
report = {'arms': [], 'limits': [
    'Public repeated-source fixture, not an actual OpenClaw turn or a quality evaluation.',
    'OpenClaw sampling is held fixed; different window sizes may still produce different text.',
    '--spec changes the MTP cap and the default suffix-lookup cap; this is a packaged-setting comparison.',
    'Native timings are rounded. API completion counts can include injected thinking-transition tokens.',
    'Decode timing logging is common to all arms; detailed GPU verification profiling is off.']}
timing = re.compile(r'(\d+) windows, avg T ([\d.]+), ([\d.]+) tokens/window, ([\d.]+) ms/window = .*?verify ([\d.]+).*?draft ([\d.]+)')
for directory in a.directories:
    summary = json.loads((directory / 'summary.json').read_text())
    for arm in summary['arms']:
        d = directory / arm['arm']
        data = json.loads((d / 'results.json').read_text())
        assert data['completed']
        native = json.loads((d / 'native-accounting.json').read_text())['groups']
        assert len(native) == len(data['runs'])
        row = {'directory': str(d), 'window': arm['spec_window'], 'sampling': data['sampling'],
               'engine': arm['before']['engine'], 'runs': [],
               'runner_completed': summary['completed'], 'runner_error': summary.get('error')}
        for run, segments in zip(data['runs'], native):
            if run['warmup']:
                continue
            windows = avg_T_sum = verify_ms = draft_ms = 0
            for segment in segments:
                m = timing.search(segment['timing_line'])
                assert m, segment['timing_line']
                w, t, _, _, verify, draft = map(float, m.groups())
                windows += int(w)
                avg_T_sum += w * t
                verify_ms += w * verify
                draft_ms += w * draft
            tokens = sum(s['generated'] for s in segments)
            decode_ms = sum(s['decode_ms'] for s in segments)
            accepted = sum(s['accepted'] for s in segments)
            offered = sum(s['offered'] for s in segments)
            row['runs'].append({
                'target_context': run['target_tokens'], 'messages_sha256': run['messages_sha256'],
                'output_sha256': run['output_sha256'], 'api_completion_tokens': run['usage']['completion_tokens'],
                'api_generation_tok_s': run['timings']['predicted_per_second'],
                'native_generation_tokens': tokens, 'native_decode_ms': decode_ms,
                'native_generation_tok_s': tokens * 1000 / decode_ms,
                'initial_cold_tokens': segments[0]['read'],
                'initial_cold_ms': segments[0]['prefill_ms'],
                'initial_cold_tok_s': segments[0]['read'] * 1000 / segments[0]['prefill_ms'],
                'continuation_read_tokens': sum(s['read'] for s in segments[1:]),
                'native_segments': len(segments), 'windows': windows,
                'mean_verify_rows': avg_T_sum / windows, 'tokens_per_window': tokens / windows,
                'verify_ms_per_window': verify_ms / windows, 'draft_ms_per_window': draft_ms / windows,
                'verify_ms_per_token': verify_ms / tokens, 'draft_ms_per_token': draft_ms / tokens,
                'drafts_offered': offered, 'drafts_accepted': accepted,
                'draft_acceptance_fraction': accepted / offered if offered else None})
        report['arms'].append(row)
assert report['arms']
contexts = sorted({r['target_context'] for arm in report['arms'] for r in arm['runs']})
report['context_comparisons'] = {}
for context in contexts:
    rows = [(arm['window'], r) for arm in report['arms'] for r in arm['runs'] if r['target_context'] == context]
    assert len({r['messages_sha256'] for _, r in rows}) == 1, 'Prompts differ between arms'
    report['context_comparisons'][str(context)] = {
        'identical_output_hashes': len({r['output_sha256'] for _, r in rows}) == 1,
        'ordered_results': [{'window': w, 'tok_s': r['native_generation_tok_s'],
                             'tokens_per_window': r['tokens_per_window'],
                             'verify_ms_per_window': r['verify_ms_per_window'],
                             'draft_ms_per_window': r['draft_ms_per_window']} for w, r in rows]}
a.out.parent.mkdir(parents=True, exist_ok=True)
a.out.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report['context_comparisons'], indent=2))
