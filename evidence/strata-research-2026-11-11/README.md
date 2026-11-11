# November 11 research evidence

All inference requests here use the public source-text fixture or synthetic
tool/state canaries. No real tool actions run. Private serving profiles and API
credentials are excluded.

- `weight-accounting.json`: GGUF header/payload inventory and independent native
  expert-index cross-check; this is not measured DRAM traffic.
- `summary.json`, `00-control/`, `01-profile/`: first normal control and externally
  traced arm, 49K/197K. The original controller was interrupted during the next
  load. Its incomplete manifest is deliberately preserved.
- `interruption-recovery.json`: original endpoint/profile restoration verified
  after that interruption.
- `return-control/`: completed final control-only run and verified restoration.
- `comparison.json`: the complete first-control / trace / return-control comparison.
- `trace-analysis.json`: all kernel/launch-shape buckets, GPU interval unions,
  queue overlap, and distributions outside coarse eviction intervals.
- `timestamp-calibration.json`: eight SDK timestamps bracketed by the monotonic
  request clock. `raw-trace-manifest.json` identifies the retained 425 MiB CSV;
  the full CSV is not put in Git.
- `q51-check/`, `q51-bench/`: initial isolated correctness and timing screen.
- `q51-bench-qualified/`, `q51-analysis.json`: timing run with per-measurement
  eviction accounting. All 360 samples are retained; three evicted samples are
  separately flagged and excluded from clean paired comparisons.
- `q51-counters/`: L2 outgoing request and wave-count probes. They do not measure
  physical DRAM bandwidth. The counter metadata preserves the earlier binary;
  subsequent eviction instrumentation changes host-side measurement only.
- `q51-integrated-parity/`: existing Strata parity suite with the opt-in engine
  patch active, zero failures. `q51-engine-build.json` identifies that engine.

Recompute the control comparison and operator summary from the published files:

```sh
python3 benchmarks/analyze-strata-decode-profile.py \
  --trial evidence/strata-research-2026-11-11 \
  --return-control evidence/strata-research-2026-11-11/return-control \
  --out /tmp/strata-comparison.json
python3 experiments/strata-decode-q51/analyze.py \
  --run evidence/strata-research-2026-11-11/q51-bench-qualified \
  --counters evidence/strata-research-2026-11-11/q51-counters \
  --out /tmp/q51-analysis.json
```

The source/kernel prototype and full-engine validation status are documented in
the [research program](../../docs/STRATA-RESEARCH-PROGRAM-2026-11-11.md). No speedup
or validation result is inferred from a started but incomplete run.
