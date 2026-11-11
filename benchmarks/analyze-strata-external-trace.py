#!/usr/bin/env python3
"""Summarize rocprofv3 traces by observable request phase and dispatch shape.

GPU interval unions account for overlap. Kernel sums do not identify a critical
path. Eviction telemetry marks coarse suspect intervals, not exact pause times.
"""
import argparse
import bisect
import collections
import csv
import hashlib
import json
from pathlib import Path


def merge_intervals(intervals):
    out = []
    for start, end in sorted(intervals):
        if not out or start > out[-1][1]:
            out.append([start, end])
        else:
            out[-1][1] = max(out[-1][1], end)
    return out


def duration(intervals):
    return sum(b - a for a, b in merge_intervals(intervals))


def category(name):
    if 'moe_combine' in name:
        return 'routing_combine_activation_and_quantization'
    if any(s in name for s in ('native_gu_', 'native_down_', 's27_gu_', 's27_down_',
                               's26_gu_', 's26_down_', 'moe_', 'fused_iq_', 'f16kq::')):
        return 'expert_matrices'
    if any(s in name for s in ('gr_', 'hc_', 'hcd_')):
        return 'hyper_connections'
    if 'gdn_' in name:
        return 'gdn'
    if any(s in name for s in ('attn_', 'qsa_', 'topk_', 'kv_', 'indexer_')):
        return 'attention_selection_and_kv'
    if any(s in name for s in ('gemm', 'Gemm', 'mmvq', 'mmvf', 'q8_0_packed', 'q6_k_packed',
                               'pfg::kernel', 'Cijk_')):
        return 'dense_matrix_family_including_head_and_shared'
    if any(s in name for s in ('route_', 'resident_plan', 'combine', 'swiglu_', 'quantize_')):
        return 'routing_combine_activation_and_quantization'
    return 'other'


def stats(values):
    if not values:
        return {'count': 0}
    v = sorted(values)
    return {'count': len(v), 'sum_ms': sum(v) / 1e6,
            'median_us': v[len(v) // 2] / 1e3,
            'p95_us': v[min(len(v) - 1, int(len(v) * .95))] / 1e3,
            'max_us': v[-1] / 1e3}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    runs = json.loads((a.arm / 'results.json').read_text())['runs']
    telemetry = [json.loads(l) for l in (a.arm / 'telemetry.jsonl').read_text().splitlines()]
    phases = []
    for r in runs:
        if r['warmup']:
            continue
        start = r['clock_start']['monotonic_ns']
        first, end = r['first_token_monotonic_ns'], r['end_monotonic_ns']
        offset = r['clock_start']['unix_ns'] - start
        for name, lo, hi in [('through_first_stream_token', start, first),
                             ('after_first_stream_token', first, end)]:
            assert hi > lo
            suspect, evicted, swapped = [], collections.Counter(), 0
            for prev, nxt in zip(telemetry, telemetry[1:]):
                tl = int(prev['unix_s'] * 1e9) - offset
                th = int(nxt['unix_s'] * 1e9) - offset
                if th <= lo or tl >= hi:
                    continue
                delta = {k: v - prev['evicted_ms'][k] for k, v in nxt['evicted_ms'].items()
                         if k in prev['evicted_ms'] and v > prev['evicted_ms'][k]}
                if delta:
                    suspect.append((max(lo, tl), min(hi, th)))
                # Whole sample intervals only: report boundary omissions explicitly.
                if lo <= tl < th <= hi:
                    evicted.update(delta)
                    swapped += nxt['swap']['pswpin'] - prev['swap']['pswpin']
            suspect = merge_intervals(suspect)
            phases.append({'target_tokens': r['target_tokens'], 'phase': name,
                           'start_ns': lo, 'end_ns': hi, 'suspect': suspect,
                           'suspect_ends': [q[1] for q in suspect],
                           'sampled_evicted_ms_by_process': dict(evicted),
                           'sampled_swap_in_pages': swapped,
                           'kernels': collections.defaultdict(lambda: {'all': [], 'clean': []}),
                           'intervals': [], 'copy_intervals': [],
                           'categories': collections.defaultdict(list),
                           'queues': collections.defaultdict(list)})
    kernel_file = a.arm / 'external-trace/execution_kernel_trace.csv'
    shape_fields = ('Workgroup_Size_X', 'Workgroup_Size_Y', 'Workgroup_Size_Z',
                    'Grid_Size_X', 'Grid_Size_Y', 'Grid_Size_Z', 'LDS_Block_Size',
                    'Scratch_Size', 'VGPR_Count', 'SGPR_Count')
    total_rows = 0
    with kernel_file.open() as f:
        for row in csv.DictReader(f):
            total_rows += 1
            start, end = int(row['Start_Timestamp']), int(row['End_Timestamp'])
            assert end >= start
            for phase in phases:
                lo, hi = phase['start_ns'], phase['end_ns']
                if start >= hi or end <= lo:
                    continue
                clipped = (max(start, lo), min(end, hi))
                phase['intervals'].append(clipped)
                phase['queues'][row['Queue_Id']].append(clipped)
                phase['categories'][category(row['Kernel_Name'])].append(clipped)
                # Cross-boundary dispatches affect unions, but not duration samples.
                if not lo <= start <= end <= hi:
                    continue
                key = (row['Kernel_Name'], tuple(int(row[k]) for k in shape_fields))
                entry = phase['kernels'][key]
                entry['all'].append(end - start)
                i = bisect.bisect_right(phase['suspect_ends'], start)
                if i == len(phase['suspect']) or phase['suspect'][i][0] >= end:
                    entry['clean'].append(end - start)
    copy_file = a.arm / 'external-trace/execution_memory_copy_trace.csv'
    if copy_file.is_file():
        with copy_file.open() as f:
            for row in csv.DictReader(f):
                start, end = int(row['Start_Timestamp']), int(row['End_Timestamp'])
                for phase in phases:
                    lo, hi = phase['start_ns'], phase['end_ns']
                    if start < hi and end > lo:
                        phase['copy_intervals'].append((max(lo, start), min(hi, end)))
    with kernel_file.open('rb') as f:
        trace_sha256 = hashlib.file_digest(f, 'sha256').hexdigest()
    report = {'protocol': 'strata-external-timeline-analysis-v1', 'trace_dispatches': total_rows,
              'kernel_csv_sha256': trace_sha256,
              'limits': [
                  'Timeline and request clocks use CLOCK_MONOTONIC; SDK get_timestamp was independently bracket-checked.',
                  'Through-first-token includes first-token generation, initialization and frontend work, not pure prefill.',
                  'After-first-token excludes initial generation and may include checkpoint/copy work.',
                  'Kernel duration sums include queue overlap; interval unions remove double counting.',
                  'Kernel names classify families; a family may serve more than one logical model stage.',
                  'Clean samples exclude all dispatches overlapping coarse telemetry intervals with queue eviction.',
                  'Eviction/swap totals omit phase boundary intervals; no precise per-kernel stall attribution is claimed.',
                  'This trace measures time and geometry, not memory bytes, occupancy or achieved DRAM bandwidth.',
              ], 'phases': []}
    for phase in phases:
        wall = phase['end_ns'] - phase['start_ns']
        union = duration(phase['intervals'])
        total = sum(e - s for s, e in phase['intervals'])
        kernel_rows = [{'name': k[0], 'shape': dict(zip(shape_fields, k[1])),
                        'category': category(k[0]), 'all': stats(v['all']),
                        'outside_eviction_intervals': stats(v['clean'])}
                       for k, v in phase['kernels'].items()]
        kernel_rows.sort(key=lambda r: r['all']['sum_ms'], reverse=True)
        row = {k: phase[k] for k in ('target_tokens', 'phase', 'start_ns', 'end_ns',
                                     'sampled_evicted_ms_by_process', 'sampled_swap_in_pages')}
        row.update(wall_ms=wall / 1e6, kernel_union_ms=union / 1e6,
                   kernel_sum_ms=total / 1e6, overlapping_kernel_ms=(total - union) / 1e6,
                   no_kernel_interval_ms=(wall - union) / 1e6,
                   kernel_and_copy_union_ms=duration(phase['intervals'] + phase['copy_intervals']) / 1e6,
                   suspect_interval_ms=duration(phase['suspect']) / 1e6,
                   queue_union_ms={k: duration(v) / 1e6 for k, v in phase['queues'].items()},
                   categories={k: {'sum_ms': sum(e - s for s, e in v) / 1e6,
                                    'union_ms': duration(v) / 1e6} for k, v in phase['categories'].items()},
                   kernels_by_shape=kernel_rows)
        assert 0 <= union <= wall and total >= union
        report['phases'].append(row)
    a.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps([{k: r[k] for k in ('target_tokens', 'phase', 'wall_ms', 'kernel_union_ms',
                                        'overlapping_kernel_ms', 'suspect_interval_ms')}
                      for r in report['phases']], indent=2))


if __name__ == '__main__':
    main()
