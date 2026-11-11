#!/usr/bin/env python3
"""Inventory stored Flash-Next weights without reading tensor payloads.

This is a payload inventory, not measured DRAM traffic. Reuse, MTP candidate
rows, recurrent/KV state, runtime conversions and rereads need separate evidence.
Uses Strata's existing GGUF header reader; records its digest for reproduction.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def group(name):
    if name in ('token_embd.weight', 'per_layer_token_embd.weight'):
        return 'embedding_lookup_tables'
    if '_exps.' in name:
        return 'routed_experts'
    if name == 'output.weight':
        return 'output_head'
    if '_shexp.' in name and 'gate_inp' not in name:
        return 'shared_experts'
    if 'hc_' in name:
        return 'hyper_connections'
    if 'gate_inp' in name:
        return 'routing'
    if any(x in name for x in ('attn_qkv.', 'attn_gate.', 'ssm_out.')):
        return 'gdn_dense_projections'
    if 'ssm_' in name:
        return 'gdn_other'
    if 'attn_' in name or 'indexer.' in name:
        return 'qsa_projections_and_norms'
    if 'ple_' in name:
        return 'ple_dense_and_norms'
    return 'other'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--strata-source', type=Path, required=True)
    p.add_argument('--model-dir', type=Path, required=True)
    p.add_argument('--pack', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    reader = args.strata_source / 'tools/gguf_reader.py'
    sys.path.insert(0, str(reader.parent.resolve()))
    from gguf_reader import GGUFFile
    tensors = []
    shards = []
    metadata = {}
    names = set()
    for path in sorted(args.model_dir.glob('*.gguf')):
        gguf = GGUFFile(path)
        metadata.update({k: v for k, v in gguf.metadata.items() if k.startswith('qwen4exp.')})
        with path.open('rb') as fh:
            header_hash = hashlib.sha256(fh.read(gguf.data_start)).hexdigest()
        shards.append({'name': path.name, 'file_bytes': path.stat().st_size,
                       'header_bytes': gguf.data_start, 'header_sha256': header_hash,
                       'tensor_count': len(gguf.tensors)})
        for t in gguf.tensors:
            assert t.name not in names, f'Duplicate tensor: {t.name}'
            names.add(t.name)
            nbytes = t.expected_bytes()
            assert nbytes is not None, f'Unknown payload geometry: {t.name}: {t.type_name}'
            tensors.append({'name': t.name, 'shape': t.shape, 'type': t.type_name,
                            'elements': t.elements, 'stored_bytes': nbytes, 'group': group(t.name)})
    assert tensors and metadata
    experts = metadata['qwen4exp.expert_count']
    selected = metadata['qwen4exp.expert_used_count']
    layers = metadata['qwen4exp.block_count']
    totals = collections.defaultdict(lambda: {'elements': 0, 'stored_bytes': 0, 'tensors': 0})
    for t in tensors:
        row = totals[t['group']]
        row['elements'] += t['elements']
        row['stored_bytes'] += t['stored_bytes']
        row['tensors'] += 1
    native_path = args.pack / 'native_experts.txt'
    native = [line.split() for line in native_path.read_text().splitlines()
              if line.strip() and not line.startswith('#')]
    assert len(native) == layers
    native_per_expert = sum(int(row[4]) for row in native)
    assert native_per_expert * experts == totals['routed_experts']['stored_bytes']
    dense = sum(t['stored_bytes'] for t in tensors
                if t['group'] not in ('routed_experts', 'embedding_lookup_tables'))
    expert_selected = native_per_expert * selected
    report = {
        'protocol': 'flash-next-stored-weight-inventory-v1',
        'strata_source_commit': subprocess.check_output(
            ['git', '-C', str(args.strata_source), 'rev-parse', 'HEAD'], text=True).strip(),
        'reader_sha256': hashlib.sha256(reader.read_bytes()).hexdigest(),
        'native_experts_sha256': hashlib.sha256(native_path.read_bytes()).hexdigest(),
        'shards': shards, 'layers': layers, 'experts_per_layer': experts,
        'selected_experts_per_token_per_layer': selected, 'groups': dict(totals),
        'selected_routed_expert_payload_bytes': expert_selected,
        'nonexpert_payload_excluding_lookup_tables_bytes': dense,
        'one_selected_set_plus_nonexpert_payload_bytes': dense + expert_selected,
        'interpretation': [
            'Stored tensor payloads include quantization scales and metadata inside blocks.',
            'The selected expert count is for one target evaluation, not one emitted token.',
            'Nonexpert payload is an inventory; runtime pack conversions may change its representation.',
            'Do not multiply these values by emitted tokens/s to claim measured DRAM bandwidth.',
            'Speculative candidate rows can share experts/weights, and rejected rows still cost work.',
            'Embedding tables are lookups, not full tensor reads per evaluation.',
            'Draft-model weights, activations, recurrent state, KV/indexer traffic and rereads are excluded.',
        ],
        'tensors': tensors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in (
        'selected_routed_expert_payload_bytes', 'nonexpert_payload_excluding_lookup_tables_bytes',
        'one_selected_set_plus_nonexpert_payload_bytes')}))


if __name__ == '__main__':
    main()
