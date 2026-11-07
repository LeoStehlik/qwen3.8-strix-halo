#!/usr/bin/env python3
"""Summarize Strata QSA_DUMP_STEPS captures and extract pa_bench records.

Format: little-endian int32 {layer, position, queries, cap}, queries*cap
selection IDs, queries*4 step entries (position, n_kv, n_bid, width).
Only sampled selections are validated; all record dimensions and steps are
checked. Sharing is a theoretical read-reuse opportunity, not a speedup.
"""
import argparse
from array import array
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def analyze(path, sample_groups=64, queries=4096, extract_dir=None):
    if sys.byteorder != 'little':
        raise ValueError('memoryview parser requires a little-endian host')
    records = []
    initial_stat = path.stat()
    if extract_dir is not None:
        extract_dir.mkdir(parents=True, exist_ok=True)
    with path.open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        offset = 0
        while offset < len(mm):
            if len(mm) - offset < 16:
                raise ValueError(f'incomplete header at {offset}')
            layer, p0, t, cap = struct.unpack_from('<4i', mm, offset)
            if layer < 0 or p0 < 0 or t < 1 or cap < 1 or cap > 262144 or t > 262144:
                raise ValueError(f'invalid dimensions at {offset}')
            ids_at = offset + 16
            steps_at = ids_at + t * cap * 4
            end = steps_at + t * 16
            if end > len(mm):
                raise ValueError(f'incomplete record at {offset}: needs {end-len(mm)} more bytes')
            steps = array('i', mm[steps_at:end])
            widths = steps[3::4]
            if any(w < 0 or w > cap for w in widths):
                raise ValueError(f'invalid selection width at {offset}')
            if any(steps[4*i] != p0+i or steps[4*i+1] != p0+i+1 for i in range(t)):
                raise ValueError(f'inconsistent step position at {offset}')
            rec = {'index':len(records), 'offset':offset, 'layer':layer, 'position':p0,
                   'queries':t, 'cap':cap, 'selection_width_min':min(widths),
                   'selection_width_max':max(widths), 'selection_width_mean':sum(widths)/t}
            if t >= queries:
                start = t - queries
                cache = {}
                def cells(i):
                    if i not in cache:
                        at = ids_at + i * cap * 4
                        vals = array('i', mm[at:at+widths[i]*4])
                        if vals and (min(vals) < 0 or max(vals) > p0+i or len(set(vals)) != len(vals)):
                            raise ValueError(f'invalid selection: record {len(records)}, row {i}')
                        cache[i] = set(vals)
                    return cache[i]
                reuse = []
                for r in (2,4,8,16,32):
                    count = min(sample_groups, queries//r)
                    starts = [start + (i*(queries//r)//count)*r for i in range(count)]
                    sum_reads = sum_union = sum_pages = sum_intersection = sum_pair_union = 0
                    for first in starts:
                        rows = [cells(i) for i in range(first, first+r)]
                        union = set().union(*rows)
                        sum_reads += sum(map(len, rows))
                        sum_union += len(union)
                        sum_pages += len({c//4 for c in union})
                        sum_intersection += len(rows[0] & rows[1])
                        sum_pair_union += len(rows[0] | rows[1])
                    reuse.append({'queries_per_group':r, 'sampled_groups':count,
                                  'mean_selection':sum_reads/(count*r), 'mean_union_cells':sum_union/count,
                                  'mean_union_pages':sum_pages/count,
                                  'ideal_read_sharing_factor':sum_reads/sum_union if sum_union else 0,
                                  'union_vs_single_selection':sum_union*r/sum_reads if sum_reads else 0,
                                  'adjacent_pair_jaccard':sum_intersection/sum_pair_union if sum_pair_union else 0})
                rec['reuse'] = reuse
                rec['sampled_rows_validated'] = len(cache)
                if extract_dir is not None:
                    out = extract_dir / f'record-{len(records):03d}-layer-{layer:02d}-pos-{p0+start}.bin'
                    with out.open('xb') as g:
                        g.write(struct.pack('<4i', layer, p0+start, queries, cap))
                        g.write(mm[ids_at+start*cap*4:steps_at])
                        g.write(mm[steps_at+start*16:end])
                    rec['replay'] = {'file':out.name, 'queries':queries, 'sha256':sha256(out)}
            records.append(rec)
            offset = end
    digest = sha256(path)
    final_stat = path.stat()
    if (initial_stat.st_size, initial_stat.st_mtime_ns) != (final_stat.st_size, final_stat.st_mtime_ns):
        raise ValueError('capture changed during analysis; wait for the writer to finish')
    return {'format':'STRATA_QSA_DUMP_STEPS int32 little-endian', 'input_bytes':initial_stat.st_size,
            'input_sha256':digest, 'sample_groups':sample_groups, 'tail_queries_analyzed':queries,
            'records':records, 'limitations':['public repeated document, not an agent-prompt corpus',
            'sampled selection overlap; not measured cache hit rate or time saved',
            'shared K/V reads do not permit sharing query-dependent attention arithmetic']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('dump', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--extract-dir', type=Path)
    ap.add_argument('--sample-groups', type=int, default=64)
    ap.add_argument('--queries', type=int, default=4096)
    a = ap.parse_args()
    if a.sample_groups < 1 or a.queries < 32:
        ap.error('sample-groups must be positive; queries must be at least 32')
    result = analyze(a.dump, a.sample_groups, a.queries, a.extract_dir)
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    for rec in result['records']:
        if 'reuse' in rec:
            print(json.dumps({k:rec[k] for k in ('index','layer','position','queries','reuse')}), flush=True)
    print(json.dumps({'records':len(result['records']), 'bytes':result['input_bytes']}))

if __name__ == '__main__':
    main()
