#!/usr/bin/env python3
"""Compare completed checkpoint arms without mistaking cache reuse for raw speed."""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('trial', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    manifest = json.loads((a.trial / 'summary.json').read_text())
    assert manifest['completed'] and manifest['restoration']['profile_and_overrides_unchanged']
    report = {'protocol': 'tail-role-analysis-v1', 'cases': [],
              'all_canaries_pass': True, 'all_output_hashes_match': True,
              'exact_request_and_render_parity': True, 'candidate_reuse_reaches_boundary': True,
              'candidate_tool_state_checks': manifest['arms'][1].get('tool_state_checks', False),
              'limits': ['Three requests per case and one control/candidate/control sequence.',
                         'Checkpoint placement changes prefill segmentation; cold time includes that cost.',
                         'Generated answers are short canaries, not representative decode benchmarks.',
                         'Performance improvement is avoided rereading, not increased raw prefill throughput.']}
    for padding in (16, 80):
        runs = [json.loads((a.trial / arm / f'tail-{padding}.json').read_text())['runs']
                for arm in ('00-control', '01-candidate', '02-control')]
        assert all(len(rows) == 3 for rows in runs)
        for triplet in zip(*runs):
            for k in ('request_sha256', 'rendered_sha256', 'prompt_tokens_offline'):
                assert len({r[k] for r in triplet}) == 1, f'Mismatched {k}'
            report['all_output_hashes_match'] &= len({r['output_sha256'] for r in triplet}) == 1
            report['all_canaries_pass'] &= all(r['answer_correct'] for r in triplet)
        candidate = runs[1]
        for previous, row in zip(candidate, candidate[1:]):
            expected = previous['message_boundaries'][-2]
            assert expected <= row['previous_prompt_lcp']
            report['candidate_reuse_reaches_boundary'] &= row['usage']['prompt_tokens_details']['cached_tokens'] >= expected
        arms = []
        for rows in runs:
            arms.append({'cached_tokens': [r['usage']['prompt_tokens_details']['cached_tokens'] for r in rows],
                         'cold_s': rows[0]['elapsed_s'],
                         'continuation_s': sum(r['elapsed_s'] for r in rows[1:]),
                         'continuation_prefill_ms': sum(r['timings']['prompt_ms'] for r in rows[1:]),
                         'fresh_continuation_tokens': sum(r['usage']['prompt_tokens'] -
                             r['usage']['prompt_tokens_details']['cached_tokens'] for r in rows[1:]),
                         'whole_case_s': sum(r['elapsed_s'] for r in rows)})
        control = (arms[0]['continuation_s'] + arms[2]['continuation_s']) / 2
        case = {'padding_rows': padding, 'arms': arms,
                'continuation_seconds_saved_vs_control_mean': control - arms[1]['continuation_s'],
                'continuation_time_reduction_percent': 100 * (1 - arms[1]['continuation_s'] / control)}
        report['cases'].append(case)
    report['validation_passed'] = all(report[k] for k in (
        'all_canaries_pass', 'exact_request_and_render_parity',
        'candidate_reuse_reaches_boundary', 'candidate_tool_state_checks'))
    report['output_difference_review_required'] = not report['all_output_hashes_match']
    a.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
