# November 12 measured performance envelope

See [findings](../../docs/STRATA-PERFORMANCE-ENVELOPE-2026-11-12.md) and
[reproduction](../../experiments/strata-envelope/README.md). These are research
measurements; no faster engine was promoted.

- `analysis.json`: generated medians, routing reuse and runtime inventory summary.
- `budget.json`: conditional 49K/197K planning budgets from the prior normal
  control, with native output/window counts and actual uncached prompt counts.
- `calibration-exclusive/`: repeated hardware probes and separate outgoing-GL2 /
  DRAM-tag counter qualifications, including raw samples and host telemetry.
- `q8-final/`: corrected native-layout replay, CPU samples, packed-output parity,
  timings and eviction deltas. The head uses original Q8 blocks.
- `operators/`: projection control/reference results. Its summary also records
  the preliminary Q8 run whose head registration was not representative; those
  preliminary Q8 timings are excluded from analysis and their raw files omitted.
- `routes.jsonl`: exact per-layer counts of newly encountered expert IDs at each
  speculative row. Native reports include prelude/restore work, explained in the
  findings. No private prompts or Discord messages were used.
- `dispatch.json`: concatenated cumulative JSON snapshots at native request
  completion. Scope selection counts must be combined with graph-launch counts.
  Only trailing blank lines were normalized; `dispatch.original.sha256` records
  the original file's hash.
- `routing-run/`: public-probe hashes, native accounting, command and curated
  restoration/parity metadata. Diagnostic throughput is not a new baseline.
- `runtime-inventory.json`: source-audited formats and logical payload, not
  measured memory transactions. `hardware.json` contains filtered memory
  configuration without serial numbers.
- Build manifests and ISA verification record source/binary hashes.
- `final-restoration.json`: independent confirmation of the original packaged
  executable, loaded/idle endpoint, unchanged profile and absent experiment flags.

Regenerate the aggregates from this directory:

```sh
python3 experiments/strata-envelope/analyze.py \
  --root evidence/strata-envelope-2026-11-12 --out /tmp/envelope-analysis.json
python3 experiments/strata-envelope/budget.py \
  --control evidence/strata-research-2026-11-11/q51-engine-trial/02-control/native-accounting.json \
  --analysis /tmp/envelope-analysis.json --out /tmp/envelope-budget.json
```

The aggregate analysis was regenerated from the published artifacts and matched
exactly before publication. `SHA256SUMS.json` covers measurement artifacts,
including the independently recorded final restoration and planning budget.
Native logs, credentials, model weights and private profile contents are excluded.
