# Cost-aware MTP: no demonstrated gain

The packaged `STRATA_SPEC_COST=1` policy did not establish a generation
improvement. It lost at 16K; its 64K result lies between the two controls.
Keep the original policy. No source engine change or model substitution is
involved, and this experiment does not improve raw prefill.

## Comparison

Same packaged Strata 0.2.11 / HIP-Halo 0.1.57, Flash-Next UD-Q4_K_XL,
262,144 context, INT8 KV, all experts resident, measured fast flags and the
existing message-boundary checkpoint trial. `--spec 4` stays fixed, with
effective maximum verification width 6 and MTP width 4 in every arm.
Only `STRATA_SPEC_COST` changes: **0 / 1 / 0**, each in a fresh process.
Launch-environment checks confirm each value. Native decode timing logging
is common; detailed GPU verification profiling stays off.

The public fixture, matched nonces, warm-up and OpenClaw sampling preset are
the same as the [window-size comparison](STRATA-MTP-WINDOW-2026-11-07.md).
Each process receives 16K then 64K, with 1,024 output tokens per benchmark
request. That allowance does not change any provider response limit. The
policy learns during the process, so request order is part of the experiment.

Native decoded tokens divided by native decode time:

| Context | Cost off, first | Cost on | Cost off, return |
|---|---:|---:|---:|
| 16K | 41.42 tok/s | 39.86 | 41.31 |
| 64K | 41.35 tok/s | 40.77 | 38.95 |

The 16K controls are close; enabling the policy is about 3.6% slower than
the return control. The 64K controls drift by about 5.8%, so the enabled
result between them cannot establish an improvement. Do not compare it only
with the slower return control. No additional 10–20 tok/s was observed.

All three 16K output hashes match. At 64K the two controls match each other,
while the enabled policy differs. The difference was not evaluated as a
quality regression or as harmless variation. With no reliable performance
gain, this arm did not advance to tool, continuation or state validation.

## What the policy actually did

Source inspection shows the existing policy estimates accepted tokens per
millisecond using observed round costs and acceptance by draft probability.
It replaces the fixed minimum-probability chain rule, maintains context cost
buckets and limits the influence of unusually slow rounds. Unmeasured widths
start from a prior cost curve; this is not a machine-specific calibrated table.
The serving path learns online. The source's `STRATA_SPEC_COST_TABLE` loader
is in the CLI generation path, not the serving setup used here; no seed table
was supplied or claimed active.

The expectation that it might shorten wasteful windows did not describe this
fixture's result. At 16K it raised average verification width from **3.03 to
3.56**, producing 2.40 tokens/window instead of 2.30. Verification rose from
46.58 to 50.88 ms/window and drafting from 9.05 to 9.40. At 64K width rose
from 3.14 to 3.33, while emitted tokens/window changed only from 2.423 to
2.436. Extra acceptance did not establish higher total throughput.

Probabilistic draft acceptance remains off in this setup; no new sampling
mode was enabled. These are observations about this packaged policy and two
public fixtures, not a proof that every adaptive drafting policy would fail.
The return-control slowdown remains unattributed; this screen does not resolve
the previously observed GPU queue stalls.

## Reproduce and operational state

```sh
python3 benchmarks/strata-mtp-window.py \
  --profile /path/to/private/serving-profile.json \
  --fixture /path/to/pinned/public/prompt.txt --out /tmp/mtp-cost \
  --live-url http://PRIVATE_HOST:8083 \
  --windows 4 4 4 --cost-aware 0 1 0 --sizes 16384 65536 \
  --max-tokens 1024 --sampling-preset openclaw
python3 benchmarks/analyze-strata-mtp.py /tmp/mtp-cost \
  --out /tmp/mtp-cost-analysis.json
```

The runner requires idle serving, temporarily runs the backend on authenticated
loopback 8084, and restores the original runtime override in `finally`.
It never calls or restarts OpenClaw. Credentials and complete engine logs stay
private. Native accounting includes both thinking and answer segments and
reconciles them with API counters. The
[evidence](../evidence/strata-performance-2026-11-07/mtp-cost/)
records process flags, results, timing segments, telemetry and restoration.
The run completed successfully and restored the original override byte for
byte at 21:59:11 UTC. Health reported loaded, metrics idle, and the restored
process had cost-aware mode unset. Boot promotion remains unchanged/pending.
