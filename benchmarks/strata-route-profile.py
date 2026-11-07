#!/usr/bin/env python3
"""Summarize Strata STRATA_DBG_FEAT routing dumps from public-input probes.

Upstream format: int32 layer, position, tokens, has_bf16_hidden; then
tokens*10 uint16 expert ids, tokens*10 bf16 routing weights, and optionally
tokens*2560 bf16 hidden values. No activation or weight values are published.
An extracted replay contains little-endian int32 ids for S20_ROUTE_IDS.
"""
import argparse
import array
import collections
import hashlib
import json
from pathlib import Path
import statistics
import struct
import sys

BUCKETS = [(0, 0), (1, 16), (17, 32), (33, 64), (65, 128),
           (129, 256), (257, 512), (513, 1024), (1025, 262144)]


def exact(f, n):
    data = f.read(n)
    if len(data) != n:
        raise ValueError("truncated routing record")
    return data


def summarize(counts):
    total = sum(counts)
    return {
        "zero_experts": counts.count(0), "min_rows": min(counts),
        "median_rows": statistics.median(counts), "max_rows": max(counts),
        "buckets": [{"min": lo, "max": hi,
                     "experts": sum(lo <= n <= hi for n in counts),
                     "rows": sum(n for n in counts if lo <= n <= hi)}
                    for lo, hi in BUCKETS],
        "tile_capacity": {str(bn): sum((n + bn - 1) // bn * bn for n in counts)
                          for bn in [16, 64, 128]},
        "total_rows": total,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dump", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--extract-record", type=int)
    ap.add_argument("--ids-out", type=Path)
    ap.add_argument("--allow-truncated-tail", action="store_true",
                    help="report and omit an incomplete final stdio buffer after engine shutdown")
    args = ap.parse_args()
    if (args.extract_record is None) != (args.ids_out is None):
        ap.error("--extract-record and --ids-out must be used together")
    records, full_counts = [], []
    extracted, truncated_tail = None, None
    file_bytes = args.dump.stat().st_size
    with args.dump.open("rb") as f:
        while header := f.read(16):
            if len(header) != 16:
                raise ValueError("truncated record header")
            layer, position, tokens, hidden = struct.unpack("<4i", header)
            if not (0 <= layer < 64 and position >= 0 and 0 < tokens <= 262144 and hidden in [0, 1]):
                raise ValueError("invalid record header")
            payload_bytes = tokens * (10 * 4 + hidden * 2560 * 2)
            if file_bytes - f.tell() < payload_bytes:
                if not args.allow_truncated_tail:
                    raise ValueError("truncated final payload; use --allow-truncated-tail to report and omit it")
                truncated_tail = {"index": len(records), "layer": layer, "position": position,
                                  "tokens": tokens, "payload_expected": payload_bytes,
                                  "payload_available": file_bytes - f.tell()}
                break
            ids = array.array("H")
            ids.frombytes(exact(f, tokens * 10 * 2))
            if sys.byteorder != "little":
                ids.byteswap()
            if max(ids) >= 512:
                raise ValueError("expert id outside this model's 512 experts")
            exact(f, tokens * 10 * 2)
            if hidden:
                exact(f, tokens * 2560 * 2)
            counter = collections.Counter(ids)
            counts = [counter[i] for i in range(512)]
            if max(counts) > tokens:
                raise ValueError("expert has more rows than tokens")
            record = {"index": len(records), "layer": layer, "position": position,
                      "tokens": tokens, "counts": counts, **summarize(counts)}
            records.append(record)
            if tokens == 16384:
                full_counts.extend(counts)
            if record["index"] == args.extract_record:
                replay = array.array("i", ids)
                if replay.itemsize != 4:
                    raise RuntimeError("int32 replay unsupported on this host")
                if sys.byteorder != "little":
                    replay.byteswap()
                data = replay.tobytes()
                args.ids_out.write_bytes(data)
                extracted = {"record": record["index"], "layer": layer,
                             "position": position, "tokens": tokens,
                             "sha256": hashlib.sha256(data).hexdigest()}
    if args.extract_record is not None and extracted is None:
        raise ValueError("requested record not found")
    with args.dump.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    result = {"format": "strata-debug-features-v0.2.11",
              "source_sha256": digest,
              "full_chunk_records": len(full_counts) // 512,
              "full_chunk_summary": summarize(full_counts) if full_counts else None,
              "extracted": extracted, "truncated_tail": truncated_tail, "records": records}
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
