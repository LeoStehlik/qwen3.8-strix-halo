# Flash-Next expert profile and routing replay, 2026-11-07

This experiment separates gate/up from down and measures how actual expert
routing changes the operator cost. It introduces **no production kernel change**.
The packaged baseline is restored on private port 8083. The objective remains
1,700–2,000 tok/s prefill first, then 50–70 sustained generation.

Source: Strata v0.2.11, commit
`c3b3f5035506f3e966f1b4b7b188aeaabae92f1d`. HIP gfx1151, TheRock 7.14.1,
128 GB Ryzen AI Max+ 395. The native operator uses synthetic Q4_K gate/up and
Q5_1 down weights and activations, 512 experts and top 10. This is the format
pair used by 43 of this model's 48 expert layers. It is not a whole-model
quality test. The previous persistent-dispatch patch is absent.

Later follow-ups: the cooperative epilogue was tested and retained as a small
undeployed candidate. The [expert ATT/source mapping](../../docs/STRATA-EXPERT-ATT-2026-11-07.md)
then motivated [prepared activations](../../docs/STRATA-EXPERT-PREPARED-2026-11-07.md),
which preserved exact outputs but showed no repeatable gain. The original
"Next experiment" section below records the earlier decision.

## What the timing trace establishes

Unmodified operator, uniform random routing. The table sums kernel durations
over one layer, averaging the final 16 timed iterations after warm-up. Four
128-expert launches form each gate/up or down layer. Profiling overhead is
included; do not compare these absolute times to earlier unprofiled results
as if they were a regression.

| Input chunk | Mean rows/expert | Gate/up ms | Down ms | Activation quantization ms |
|---:|---:|---:|---:|---:|
| 256 | 5 | 4.418 | 3.064 | 0.014 |
| 2,048 | 40 | 6.279 | 4.159 | 0.123 |
| 8,192 | 160 | 19.332 | 11.464 | 0.522 |
| 16,384 | 320 | 35.355 | 20.963 | 1.012 |

At 16K, gate/up accounts for about 61.6% of these kernel durations, down 36.5%,
and activation quantization 1.8%. Group count/scan/place total about 0.036 ms.
The all-dispatch profiler summary, which also includes warm-up/initialization,
reports 61.39% gate/up and 36.39% down. These are different denominators.

The compiled 128-row gate/up kernel uses 176 VGPRs and 22,528 bytes of LDS;
down uses 152 VGPRs and 23,552 bytes. Both report **zero scratch allocation**.
The 64-row versions use 136/112 VGPRs and 13,824/14,848 bytes respectively.
These are resource allocations, not measured occupancy or utilization.

## Actual routing from a public 64K request

The packaged engine's existing `STRATA_DBG_FEAT` hook captured all four full
16,384-token chunks from all 48 layers: **192 complete layer/chunk records**,
98,304 expert observations and 31,457,280 routed rows. Hidden-state dumping
was disabled with `STRATA_DBG_FEAT_LAYERS=`. The prompt was the existing public
source fixture, with nonce seed `expert-routing-profile-v1`; no user messages
were used. Its repeated source text need not represent all OpenClaw tasks.

| Expert row count | Share of expert observations | Share of routed rows |
|---|---:|---:|
| 0 | 2.17% | 0% |
| 1–16 | 12.21% | 0.29% |
| 17–32 | 8.24% | 0.63% |
| 33–64 | 12.47% | 1.85% |
| 65–128 | 15.98% | 4.67% |
| 129–256 | 16.71% | 9.67% |
| 257–512 | 14.79% | 16.86% |
| 513–1,024 | 10.37% | 23.28% |
| Above 1,024 | 7.06% | 42.75% |

The median is 123 rows; the largest expert receives 16,244 of a chunk's
16,384 tokens. Small expert batches are common, but carry little arithmetic
work. This table counts rows; it **does not assign measured time to each row
bucket**. The compiled kernel skips inactive 16-row WMMA tiles, so nominal
128-row capacity waste is not equivalent to wasted matrix work.

The diagnostic request processed 65,551 uncached tokens in 50.3433 seconds
(1,302.1 tok/s). Dumping synchronizes each layer and writes routing records;
this is a diagnostic measurement, not a new baseline comparison. Engine
shutdown left an incomplete final 8-token record at layer 43. The parser
explicitly reports and omits that tail; all 192 full chunks are intact. The
recorded position is the hook's cumulative position, including the short
warm-up, rather than a fresh request-relative offset.

## Replay result

`routing-replay.patch` adds `S20_ROUTE_IDS` to the operator test only. It reads
exactly `T * 10` little-endian int32 expert IDs and rejects wrong lengths,
out-of-range IDs and duplicates within a token. Weights and activations stay
synthetic and identical across runs. The original row ownership and sampled
CPU reference checks remain enabled.

We selected the least, median and most padded 128-row distributions among
the 192 complete records. This selection samples padding, not every possible
source of routing skew. All three use 16K tokens and the Q4_K/Q5_1 operator.

| Routing | Layer / cumulative position | Operator median ms | Gate/up ms | Down ms | Output bit hash |
|---|---|---:|---:|---:|---|
| Uniform, replay disabled | synthetic | 57.949 | 35.660 | 21.118 | `507bd523cd60c84a` |
| Least padding | 0 / 144 | 58.521 | 35.619 | 21.820 | `1d93796a69b50cdd` |
| Median padding | 30 / 144 | 59.337 | 35.911 | 22.278 | `019f42e2855f67cc` |
| Most padding | 15 / 16528 | 59.768 | 36.179 | 22.465 | `2d94e082fc89ce20` |

The operator median and individual-stage means are different summaries, so
they need not sum exactly. Captured routing adds roughly 1.0–3.1% relative to
the same rebuilt uniform control. This weakens the hypothesis that row
imbalance is the dominant remaining cost. It does not prove that every layer
or workload behaves alike. Hashes differ across routing inputs as expected;
the replay-disabled hash matches the original unmodified binary exactly.

All four rebuilt-harness runs passed row ownership and 96 sampled pair
comparisons against the CPU reference. Relative RMS was about 0.00634, worst
row about 0.053, inside the existing operator tolerance. These checks validate
the replay harness, not a new numerical kernel.

## Hardware counter limitation

Three expert-counter passes collected four gate/up and four down dispatches
each. `SQ_WAVES_sum` and `SQ_BUSY_CYCLES_avr` were nonzero. The requested GL2C
traffic, SALU/VALU/LDS instruction, wave-cycle and GRBM counters returned zero.
Those zeros cannot establish bandwidth, arithmetic intensity or occupancy.

A separate 640 MiB vector-copy control returned plausible GL2C counts:
5,242,883 128-byte read requests and 10,471,274 64-byte writes for its sampled
dispatch. Thus counters are **not universally unavailable on this host**;
the cause of the expert-run zeros remains unresolved. Do not publish a
memory-bound/compute-bound conclusion from them. The timing traces and
compiled resource metadata are independently usable.

## Reproduce

Use the pinned source and local SDK/build described in the
[performance record](../../docs/STRATA-PERFORMANCE-2026-11-07.md). Stop an idle
inference backend before isolated GPU measurements. Do not restart OpenClaw.

```sh
# In the pinned Strata source tree, with the documented SDK build environment:
git apply /path/to/this/repo/experiments/strata-expert-profile/routing-replay.patch
cmake --build build-halo-lab --target hip_prefill_fused_iq -j 4

# SDK bin/ and its shared libraries must be in PATH/LD_LIBRARY_PATH.
STRATA_PF_F16=1 S20_NOMMQ=1 rocprofv3 --kernel-trace --stats \
  -d /tmp/expert-uniform -o expert --output-format csv -- \
  ./build-halo-lab/hip_prefill_fused_iq --no-ref \
  '--only=Q4_K / Q5_1' --chunks=16384

gzip -dc /path/to/this/repo/evidence/strata-performance-2026-11-07/expert-profile/real64k/median-padding.ids.i32.gz > /tmp/median.ids.i32
STRATA_PF_F16=1 S20_NOMMQ=1 S20_ROUTE_IDS=/tmp/median.ids.i32 \
  rocprofv3 --kernel-trace --stats -d /tmp/expert-replay -o expert \
  --output-format csv -- ./build-halo-lab/hip_prefill_fused_iq --no-ref \
  '--only=Q4_K / Q5_1' --chunks=16384
```

With `S20_NOMMQ=1`, the harness prints a placeholder MMQ time of 1 ms. Ignore
that time and its ratio. Only the fused durations are measured here.

To collect new routing, use a loopback-only copy of the working configuration
with `STRATA_DBG_FEAT=/path/routes.bin` and `STRATA_DBG_FEAT_LAYERS=`. Send the
public fixture with `benchmarks/strata-prefill.py`; stop the diagnostic engine
before parsing. `benchmarks/strata-route-profile.py` summarizes and optionally
extracts an individual record. The complete original binary dump is retained
locally; its SHA-256, all complete histograms and three compressed replay
inputs are published. Parser validation covered exact extraction, truncated
payload rejection/explicit omission, short headers, invalid layers and IDs.

## Next experiment

Keep routing-list work and the rejected persistent grid off the candidate
list. Gate/up deserves the first focused code experiment. One concrete
candidate from source inspection is its SwiGLU/int8 epilogue: only 32 of 256
threads process a tile, each holding 32 feature values. Test a cooperative
epilogue independently, preserving the existing rounding and output layout.
That is a hypothesis, not a measured win. Inspect compiler resources, require
same-input output checks, then replay captured distributions before any
whole-model run. Resolve counter collection before making a roofline claim.

Using the earlier 24.9% whole-prefill expert share, gate/up is roughly 15% of
total prefill. Even a 2x gate/up improvement would predict only about 8%
overall. Reaching the new target will likely require several contributions.

[Raw evidence](../../evidence/strata-performance-2026-11-07/expert-profile/).
Trailing whitespace was stripped from the available-counter listing only;
measurement CSVs and logs are unchanged.
