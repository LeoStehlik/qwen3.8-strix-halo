# Expert instruction trace and source mapping

The bounded expert follow-up found repeated activation conversion worth testing,
but it did not establish a memory-bandwidth ceiling or an expected speedup.
The resulting [prepared-activation experiment](STRATA-EXPERT-PREPARED-2026-11-07.md)
preserved outputs and failed to produce a repeatable performance gain.

## Conditions

Ryzen AI Max+ 395, gfx1151, 128 GB, TheRock 7.14.1. The standalone operator
uses Q4_K gate/up and Q5_1 down, synthetic weights/activations, and the captured
median-padding 16K routing distribution from the public 64K fixture. This
format pair covers 43 of Flash-Next's 48 expert layers. It is not an actual
OpenClaw request or a whole-model benchmark.

Four Advanced Thread Traces sampled gate/up and down dispatch occurrences 5
and 8, selecting CU 1 / SIMD 0, with a 256 MiB trace buffer. The cooperative
epilogue was explicitly off. The original operator binary SHA-256 was
`23f32e84c35b76faa11dea074a399d04a1b68687bdf58d3cab0ef127e4be4862`.
All traces completed, decoded, and preserved output hash `019f42e2855f67cc`.
Serving remained loaded and idle; its request count stayed zero throughout.

## What the trace says

These percentages divide **summed instruction latency across sampled waves**.
Waves overlap. These are not wall-time shares, bandwidth utilization, or
additive speedup ceilings. Each range covers the two sampled dispatches.

| Instruction category | Gate/up | Down |
|---|---:|---:|
| Matrix instructions | 8.8–9.0% | 4.8–4.9% |
| LDS/scalar-memory waits | 15.9–16.4% | 22.5–23.6% |
| Barriers | 19.7–20.2% | 18.1–18.2% |
| Vector-memory waits | 6.1–6.3% | 11.6–12.0% |
| Vector bit operations / selection | 16.7–16.9% | 13.1–13.2% |
| FP16 vector arithmetic | 14.4–14.5% | 8.4–8.5% |
| Vector conversions | about 5.0% | about 3.0% |

Time-weighted residency on the selected SIMD was 7.63–7.80 waves for gate/up
and 7.90–7.93 for down; peaks were 8 and 10. This includes short inactive
work items and does not mean every resident wave performs matrix work.
It cannot be generalized to whole-GPU occupancy. The decoded wave records
do not identify logical expert IDs, so no row-count timing buckets are inferred.
The earlier routing histogram remains the evidence for row-count distribution.

## Mapping to source without changing the sampled instructions

`source-map.py` compiled a separate object with `-gline-tables-only`; it did
not replace the measured build. Both relevant instruction sequences matched
the traced code object exactly: 7,795 gate/up instructions and 1,705 down
instructions. All nonzero-latency instructions mapped to source. The same
code-object hash appeared in all four traces.

The original INT8 activation unpack/conversion line accounted for about 9.6%
of summed latency in gate/up and 8.7–8.8% in down. A shared FP16 conversion
header contributed further latency, but its inlined callers cannot all be
distinguished from line attribution alone. Weight decoding, LDS waits and
barriers are also substantial. The existing kernel already prefetches the
next stage; simply adding a prefetch is not a new optimization.

This justified one narrow hypothesis: convert the already-quantized activations
once and reuse those FP16 values across expert tiles. It did not predict that
the saved conversions would outweigh the added memory traffic. Compiler line
attribution can also place a wait on an adjacent operation; do not interpret
line totals as isolated operation cost.

## Reproduce and evidence

Build the pinned Strata source and standalone operator using the
[cooperative-epilogue reproduction](../experiments/strata-cooperative-epilogue/README.md#reproduce),
with its cooperative switch off. Extract the published median routing fixture.
The SDK must provide rocprofv3's ATT decoder. Then run:

```sh
python3 experiments/strata-expert-profile/profile-att.py \
  --binary /path/to/build-halo-lab/hip_prefill_fused_iq \
  --sdk /path/to/rocm-sdk --profile /path/to/private/serving-profile.json \
  --routes /tmp/median.ids.i32 --out /tmp/expert-att
python3 experiments/strata-expert-profile/analyze-att.py /tmp/expert-att
python3 experiments/strata-expert-profile/source-map.py \
  --source /path/to/strata --sdk /path/to/rocm-sdk \
  --traces /tmp/expert-att --out /tmp/expert-source-map
```

The profile runner requires idle serving and checks that no actual requests
arrived between subprocess boundaries. It does not stop or restart the server.
Run the source mapping before applying the prepared-activation patch.

[Published evidence](../evidence/strata-performance-2026-11-07/expert-att/)
contains commands, logs, compressed instruction statistics, extracted wave
intervals, source mappings and hashes. `analyze-att.py` also accepts those
published compressed statistics/intervals and reproduces the summary. Large
raw ATT files and code objects remain local with a published SHA-256 manifest.
