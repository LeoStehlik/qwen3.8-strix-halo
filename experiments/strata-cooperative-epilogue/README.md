# Cooperative expert epilogue: small isolated gain, not deployed

The gate/up epilogue is faster when its SwiGLU/int8 work is shared across all
256 threads instead of 32 threads. On captured 16K routing, the complete
expert operator improved by **2.4–2.5%**, with identical output hashes. This
would imply only about **0.6% whole-prefill improvement** using the earlier
24.9% expert share. That estimate is not a measured model-level speedup.

The patch is retained as an opt-in experiment. It is not deployed, and has
not received a full-model/state/continuation test. The revised goal remains
1,700–2,000 tok/s prefill, then 50–70 sustained generation. This small result
does not satisfy it.

## Implementation and validation

Pinned Strata v0.2.11 source
`c3b3f5035506f3e966f1b4b7b188aeaabae92f1d`, HIP gfx1151, isolated TheRock
7.14.1 SDK on the same 128 GB Ryzen AI Max+ 395. No driver changes.

`cooperative-epilogue.patch` changes only `src/prefill/moe_f16_kq.cu`.
`STRATA_PF_F16_GU_EPI=1` selects the candidate; absent/zero keeps the original
path. Eight lanes share each 32-feature quantization group, each computing
four values. The maximum and integer sum use lane shuffles. The matrix
accumulation, per-value SwiGLU expression, quantization, scale representation
and output layout remain unchanged. The down kernel is unchanged.

`test-harness.patch` includes the earlier routing replay support **and** a
new hash of every intermediate H byte and final output word in token/top-k
order. Apply this patch instead of stacking the earlier routing-only patch.

Twelve reference processes covered Q4_K/Q5_1, Q4_K/Q8_0 and Q5_K/Q8_0,
64/128-row tiles, and candidate off/on. Every paired intermediate-byte and
output hash matched exactly. Existing CPU reference tolerances passed,
including the zero token, unused experts, unrelated expert allocations and
partially filled tiles. Captured-routing runs retained the row ownership and
96-pair CPU checks; all passed. The current rebuilt binary exactly matches
the archived cooperative-only binary. Only HIP was built and tested.

## Timing

These are unprofiled complete-operator medians, including quantization,
grouping, gate/up and down. Each process warms up for one second, then uses
the existing harness's timed repetitions. Weights and activations are
synthetic; captured expert IDs come from the public 64K probe described in
the [routing profile](../strata-expert-profile/README.md).

| Q4_K/Q5_1 input | Original ms | Cooperative ms | Operator speedup |
|---|---:|---:|---:|
| Uniform 256 tokens | 7.508 | 7.500 | within noise |
| Uniform 2K | 10.171 | 10.071 | 1.0% |
| Uniform 8K | 29.518 | 29.128 | 1.3% |
| Uniform 16K, mean of two medians each | 53.895 | 52.894 | 1.9% |
| Captured, least padded | 55.081 | 53.771 | 2.4% |
| Captured, median padding | 55.743 | 54.368 | 2.5% |
| Captured, most padded | 56.017 | 54.684 | 2.4% |

At 16K, Q4_K/Q8_0 improved from 54.451 to 53.392 ms, and Q5_K/Q8_0 from
57.786 to 57.135 ms. All same-input output hashes matched. Original binary
and rebuilt candidate-off 16K controls were 53.737 and 53.729 ms respectively.
The paired 16K screen ran off/on/on/off to expose timing drift.

The cooperative 128-row gate/up kernel still reports 176 VGPRs, 22,528 bytes
of LDS and zero scratch, just like the original. It improves epilogue work
without lowering peak register allocation. No model-level speed or quality
claim follows from these operator measurements.

## Rejected four-stage unroll

An independently switched main-loop experiment exposed four consecutive
64-value stages per 256-value weight block to the compiler, preserving their
execution/accumulation order. The cooperative epilogue was off. Candidate
times were 54.181/54.077 ms versus controls 53.792/53.945 ms; all hashes were
`507bd523cd60c84a`. It was slower, so it was removed from the working source.

`combined-unroll4-rejected.patch` archives that full alternative against the
pinned base. It includes both switches; use `STRATA_PF_F16_GU_UNROLL4=1` and
`STRATA_PF_F16_GU_EPI=0` to reproduce the rejected comparison. Do not stack it
on the retained production-file patch. It did not advance to a full-model test.

## Counter collection follow-up

Collecting memory counters for **only gate/up**, then **only down**, returned
plausible nonzero values repeatedly. A filter including both kernel names
returned zeros for the same memory events, with or without the iteration
range. The underlying SDK/driver cause is unproven; do not describe this as
a repaired profiler. Use separate per-kernel collections for now.

Across the last 64 sampled dispatches, reported L2 external read/write request
rates averaged approximately **114 GB/s gate/up** and **168 GB/s down**.
Those rates omit the 96-byte request event and are not direct DRAM bandwidth
measurements. They do not by themselves establish a compute or bandwidth
ceiling. SALU/VALU/LDS instruction counters worked for down but still returned
zeros for gate/up. Wave counts were nonzero in all these collections.

## Wider hipBLASLt search

`max-algos.patch` adds an optional `--max-algos` argument to the upstream
tuner, defaulting to its original 16. It does not modify the inference engine
or installed tuning table. Asking for 128 candidates returned only seven for
FP16 T=16384/N=10240/K=2560, at both 32 and 256 MiB workspace limits. Existing
solution **2390** remained fastest (30.686 / 30.921 ms). The BF16 HC down
shape T=16384/N=320/K=10240 returned nine candidates; existing **1176** remained
fastest at 6.470 ms. All selected algorithms passed the existing accuracy and
padding checks. The earlier 16-candidate limit had not hidden a better choice
from this heuristic query. This is not an exhaustive enumeration of every
library algorithm.

The tuner output files named `*.json` in this experiment are actually its
plain-text `STRATA_HIPBLASLT_TUNING_V1` format; the command records preserve
the original filenames. None is installed as a runtime table.

## Reproduce

Apply the retained kernel patch and test patch to the pinned clean source.
Use the SDK environment and CMake configuration from the
[performance record](../../docs/STRATA-PERFORMANCE-2026-11-07.md), then build
`hip_prefill_fused_iq`. Keep the inference backend stopped during GPU tests.

```sh
STRATA_PF_F16=1 S20_NOMMQ=1 STRATA_PF_F16_GU_EPI=0 \
  ./build-halo-lab/hip_prefill_fused_iq --no-ref \
  '--only=Q4_K / Q5_1' --chunks=16384
STRATA_PF_F16=1 S20_NOMMQ=1 STRATA_PF_F16_GU_EPI=1 \
  ./build-halo-lab/hip_prefill_fused_iq --no-ref \
  '--only=Q4_K / Q5_1' --chunks=16384
```

Use `--no-timing` instead of `--no-ref` for the full operator reference case,
and `STRATA_PF_F16_BN=64` or `128` to cover both tile sizes. Set
`S20_ROUTE_IDS` to a decompressed replay file from the earlier routing evidence
for a captured distribution. Ignore the disabled-MMQ placeholder time/ratio.

[Operator evidence](../../evidence/strata-performance-2026-11-07/cooperative-epilogue/)
and [expanded tuner evidence](../../evidence/strata-performance-2026-11-07/lt-expanded/).
