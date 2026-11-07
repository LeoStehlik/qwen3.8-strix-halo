# Flash-Next attention: captured selections and instruction trace

2026-11-07, Strix Halo gfx1151 / 128 GB, isolated TheRock 7.14.1 lab SDK.
The updated target remains 1,700–2,000 tok/s prefill, then 50–70 generation.
**No attention kernel change is promoted.** The live packaged baseline is
unchanged. These are operator investigations, not new whole-model speed claims.

## Capture and replay

The existing packaged `STRATA_QSA_DUMP` hook captured two public cold 64K
requests, with `STRATA_QSA_DUMP_LAST=4096` and `STRATA_QSA_DUMP_STEPS=1`.
The hook dumps the entire overlapping chunk: 24 full records covering all
12 QSA layers twice, each 16,384 queries at position 49,152. Warm-up and small
tail records bring the total to 60 complete records / 3,247,427,040 bytes.
Diagnostics synchronize and write data; their request rates are not baselines.

The [parser](../../benchmarks/strata-qsa-profile.py) analyzes the final 4,096
queries per large record. It samples 64 groups for each group size, validates
sampled selections and all step positions/widths, and rejects incomplete or
changing input files. An initial read made before the writer stopped was
discarded and repeated against the completed file; only the completed capture
summary is published. The public fixture and exact prompt hashes are recorded
in `capture-results.json` below. This repeated document is not an agent corpus.

| Adjacent queries per group | Pooled ideal KV-read sharing |
|---|---:|
| 2 | 1.25× |
| 4 | 1.59× |
| 8 | 2.07× |
| 16 | 2.78× |
| 32 | 3.87× |

Four-query sharing ranges 1.37–2.20× across layers/runs. This is a set-overlap
opportunity, not measured speedup. A union has more cells than one selection;
computing every query against the entire union would add substantial work.

The upstream `pa_bench` uses synthetic queries and INT8 KV with recorded
selection IDs. [gated-replay.patch](gated-replay.patch) adds the live kernel's
gated FP16 output and padded leading dimension via `PA_BENCH_GATE=1`, checks
padding and finite outputs, and preserves the ungated inputs. The original
and extended ungated benchmark both produce hash `aedafffba53d24f3` on layer 7.
No production kernel is changed by this patch. Only the HIP build was tested.

Initial gated controls (4,096 queries, 65,536 cells, cap 2,051, median of 21):
layer 0 **22.216 ms**, layer 3 **23.223 ms**, layer 7 **24.046 ms**.
These are isolated synthetic-value replays, not model-layer wall times.

## Profile findings

The gated fast kernel uses **200 VGPRs/thread, 18,432 LDS bytes/block, no
scratch spills**, 128 threads/block. Unlike the earlier expert counter
problem, this single-kernel collection returned nonzero memory and ALU counts.

External L2 read requests total about **5.19 GB** for layer 0 and **7.68 GB**
for layer 7 per replay; profiled durations were 23.55 and 25.05 ms. These are
L2 external requests, **not a direct DRAM-bandwidth measurement**. A separate
layer-7 collection measured **20.25% L2 hits** and zero 96-byte reads. Do not
declare DRAM saturation from these counters.

Advanced Thread Trace worked on gfx1151 with the existing SDK. One dispatch,
one selected WGP/SIMD produced 410 traced waves. Aggregated instruction latency:

- Vector-memory waits: 44.7%.
- Other vector instructions: 32.1%.
- LDS/scalar-memory waits: 9.1%; workgroup barriers: 5.9%.
- LDS instructions: 5.7%; WMMA instructions: 0.64%.

These percentages sum instruction latency across traced waves. They are
**not GPU wall-time fractions or a speedup ceiling**. Several dominant waits
follow V/K scale loads; two others follow the next selected ID and page-table
entry. INT8 conversion instructions also account for many executed operations.
The instruction listing, aggregate counters, commands and caveats are in the
[evidence directory](../../evidence/strata-performance-2026-11-07/attention-replay/).
Raw ATT/wave data remains local (about 1.55 GB); hashes of its raw trace and
code objects are published. The compact decoded `code.json` is included. Compiler diagnostic trailing
whitespace was stripped in the published restored-build log; measurement logs
and counter CSVs were not normalized.

## Independent scheduling screens

All screens used the same three captured records, gate on, fast FP16 attention,
trim 2, read-prefetch on, 31 timed repetitions per process, order off/on/on/off.
Every output hash matched its control; every padded output row stayed intact.

| Candidate | Layer 0 | Layer 3 | Layer 7 | Decision |
|---|---:|---:|---:|---|
| Stage V before K loads | −0.04% | +0.23% | +0.51% | Reject: noise, still 200 VGPRs |
| Delay scale conversion, plain C++ | −0.74% | +1.36% | +0.23% | Reject: compiler undid intended scheduling |
| Delay conversion with empty value barrier | +1.75% | +1.60% | +0.45% | Shelve: too small/inconsistent to promote |

Percentages compare means of process medians, not confidence intervals.
The plain C++ variants have the same wait sequence and differ only in two
register-zeroing instructions. The empty value barrier reduces static vector
wait instructions from 27 to 21, but gives only the small replay gains above.
It leaves values unchanged and emits no instruction itself. No full-model,
state/continuation or broader correctness suite was run for these shelved
production changes. Three same-input replay hashes are narrower evidence.

The three archived patches each apply independently to the pinned source;
do not stack them. All were removed from the working production kernel file.
The restored replay binary matches the saved gated-control SHA-256 exactly.
The cooperative expert epilogue remained off throughout, and was absent from
the packaged capture run. Nothing here changes the live model or its context.

## Reproduce and continue

Use source v0.2.11 `c3b3f5035506f3e966f1b4b7b188aeaabae92f1d` and the
[recorded lab build setup](../strata-expert-profile/README.md). Apply only
`gated-replay.patch` for the control, build `hip_pa_bench`, and unpack a
published `record-*.bin.gz` outside the checkout. With the SDK runtime library
paths set as in the recorded commands:

```sh
STRATA_HIP_WMMA=1 STRATA_PA_FAST=1 STRATA_PF_SWITCH_MIN_T=4096 \
  PA_BENCH_GATE=1 "$BUILD/hip_pa_bench" /tmp/selection.bin 31
```

`STRATA_PA_STAGE_V=1` selects the first archived experiment;
`STRATA_PA_RAW_SCALES=1` selects either raw-scale experiment in its own build.
The selectors require trim ≥2 and read-prefetch on; otherwise they fall back.
The archived patches have been apply-checked against the pinned source.
Build all affected backends before considering any upstream review.

Next candidates should target the demonstrated costs: precompute physical
selected-row addresses to remove repeated dependent ID/page-table lookups;
or reduce repeated INT8-to-half conversion instructions. The former needs
non-identity/nonresident page-table tests and must include preprocessing cost.
The latter needs exhaustive checks of all 256 codes before operator tests.
The physical-row candidate has now been implemented and tested separately;
see [its results and promotion limits](../strata-attention-rows/README.md).
Exact INT8 conversion remains unimplemented. Actual attention is about 10% of
whole prefill, so even a substantial operator gain only addresses part of the
remaining target. Keep these separate from the larger GDN/HC/expert work.
