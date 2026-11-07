# Projection block grouping: no substantial gain

The later resource profile and tile experiments use the same probe. See the
[projection profile](../../docs/STRATA-PROJECTION-PROFILE-2026-11-07.md) and
[final checkpoint](../../docs/STRATA-OPTIMIZATION-CHECKPOINT-2026-11-07.md).
The fragment-load reorder was neutral; narrower K64 and wider K32 tiles were
slower. None is deployed. `build.py --row-stream` and `build.py --tiles` select
these independent experiments; use separate output directories and
`run.py --rounds 61`. `inspect-code.py` archives compiler resource metadata and
checks the unchanged control instruction hash.

Changing the padded FP16 projection kernel's launch grouping from its existing
8 token tiles per group did not uncover a useful large improvement. Best
operator medians improved by **0.2–1.2%**; several settings were substantially
slower. No selector is promoted. These percentages are operator timings,
not model throughput, and do not establish a new prefill baseline.

This follows the [padding default correction](../../docs/STRATA-PROJECTION-PADDING-2026-11-07.md):
padding was already on. The experiment below changes block ordering while
keeping padding on, matrix dimensions and arithmetic unchanged.

## Measured screen

Source `41021fb`, pinned `src/prefill/wmma_gemm.cu` SHA-256
`eca51cd8a3cdd63690fb47bdb267dfaf4f721b3f0e2786b3ffc4f45ae5487860`,
ROCm lab SDK 7.14.1, gfx1151, `-O3`. The standalone probe generates a copy
of the existing BK64 kernel with its group size templated. The original
wrapper still selects group 8. Neither the source worktree nor the packaged
serving binary is changed.

All shapes have 16,384 input rows, FP16 input/weights and FP32 output. Weights
use K+64 stride. The output projection also pads input stride by 64; the
other inputs are contiguous, matching their production producers. Data are
synthetic, at model matrix dimensions, not captured activations. Timings are
31 GPU-event samples per group, rotating and reversing the seven-setting
order each round. Full output checks precede timing. The resident server
remained loaded and idle: request count stayed zero and no restart occurred.

| Output N / input K | Existing group 8 | Best median | Best group | Operator improvement |
|---|---:|---:|---:|---:|
| 10,240 / 2,560 | 19.972 ms | 19.727 ms | 4 | 1.24% |
| 6,144 / 2,560 | 11.962 ms | 11.866 ms | 1 | 0.82% |
| 2,560 / 6,144 | 11.346 ms | 11.321 ms | 4 | 0.22% |

Group 1 was 42.5% slower on the widest shape; group 64 was about 31% slower
on both input projection shapes. There is no general "smaller group wins"
rule. The small positive medians need independent confirmation before any
performance claim; their whole-model contribution would be smaller still.
Set this path aside rather than start a full-model promotion ladder.

Long-tail samples remain in the data (including a 197.6 ms output-projection
sample versus its ~11 ms median). KFD eviction counters also increased.
These events are not independently attributed to a particular kernel, and
their cost must not be subtracted from end-to-end latency claims. The screen
does not classify the kernel as bandwidth- or compute-bound.

## Correctness and limits

**All 49 complete GPU output comparisons were bit-identical** to group 8,
including finite checks. Boundary checks use M/N/K of 129/1031/64 and
2049/1025/64, padded and contiguous input strides, output padding sentinels,
and both beta 0 and 1. These cover partial blocks and partial final groups.
The three large shapes also compare every output element for all seven groups.

The independent CPU double reference covers the four small boundary/accumulation
cases with absolute tolerance 1e-6; maximum observed error was **1.34e-7**.
An initial probe incorrectly required bitwise equality to the double sum and
stopped on the unchanged group-8 GPU control. Its diagnostic showed small
floating-point differences. Those failed runs are retained; they produced no
performance results. The CPU check now records the nonidentical count and
error bound, while candidate-versus-control GPU equality remains strict.
The cause of the control's CPU discrepancy was not traced to individual
instructions. Do not describe these as exact CPU results.

The first standalone compilation also missed `STRATA_USE_HIP`, selecting
header stubs and failing with duplicate definitions. The build driver now
sets both HIP and gfx11 macros; the failed log is retained. No failed build
or failed correctness run contributed to the timing table.

No model-level quality, checkpoint/state continuation, production dispatch
integration or CUDA/gfx12 validation was run. Nothing is deployed.

## Reproduction

```sh
python3 experiments/strata-projection-grouping/build.py \
  --source /path/to/pinned/strata \
  --sdk /path/to/rocm-sdk \
  --out /tmp/projection-grouping
python3 experiments/strata-projection-grouping/run.py \
  --profile /path/to/private/serving-profile.json \
  --sdk /path/to/rocm-sdk \
  --out /tmp/projection-grouping
python3 experiments/strata-projection-grouping/analyze.py /tmp/projection-grouping
```

Use a new output directory. The runner checks that the existing endpoint is
idle and no requests arrived between operators; it does not send an inference
request, execute tools, or restart the service. Operator workloads use the
same GPU, so run during an idle experiment window. The private API key is used
only for read-only metrics, and is excluded from reports.

[Raw measurements and build metadata](../../evidence/strata-performance-2026-11-07/projection-grouping/)
include the full sample distribution, parity records, telemetry and failed
check diagnostics. Generated kernel code and binaries can be reproduced from
the pinned source; they are not distributed as a serving engine.
