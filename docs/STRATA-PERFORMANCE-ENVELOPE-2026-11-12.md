# Flash-Next performance envelope — 12 November 2026

Status: measurement and feasibility analysis completed; no kernel or deployment
change promoted. The packaged 0.1.57 engine, model, quantization, 262K capacity
and cache configuration remain the baseline. OpenClaw routing was not changed.

**The hardware has remaining opportunities, but the earlier “one third of the
memory wall” argument substantially overstated decode headroom.** The large
native Q8 projections already approach calibrated read bandwidth. Prefill is
more mixed: representative dense projections achieve 40–43 TFLOP/s, while
quantized expert operations have lower effective matrix throughput and other
stages consume substantial time.

1,700–2,000 tok/s prefill is not ruled out by arithmetic capacity; there is no
demonstrated implementation reaching it. It requires improvements across several
stages. Sustained 60–70 tok/s generation is a substantially harder target under
the current weight format, draft acceptance and serial execution schedule.
The evidence supports targeted research, not a promised remaining percentage.

[Reproduction](../experiments/strata-envelope/README.md) ·
[Raw evidence and generated analysis](../evidence/strata-envelope-2026-11-12/) ·
[Previous complete-model profile](STRATA-RESEARCH-PROGRAM-2026-11-11.md)

## What was measured

Same 128 GB Ryzen AI Max+ 395 / gfx1151 host, kernel `7.0.0-43-generic`,
TheRock 7.14.1 laboratory SDK. Read-only and mixed bandwidth, FP32 FMA, signed
integer dot products and FP16 WMMA were calibrated independently. Standalone
tests ran with serving stopped, then automatically restored the normal service.
Every timed sample in both isolated calibration passes recorded zero self
queue-eviction delta. Some processes accumulated 2–3 ms during startup/allocation,
outside the timed samples; the absolute counters remain in host telemetry.

| Calibration, repeated medians | First | Return |
|---|---:|---:|
| 2 GiB linear reads, GB/s | 242.18 | 242.16 |
| 2 GiB reads in permuted 16 KiB tiles, GB/s | 236.79 | 237.53 |
| Copy, read + write GB/s | 211.34 | 211.37 |
| Two reads + one write, GB/s | 209.03 | 208.46 |
| Register-only FP32 FMA, TFLOP/s | 11.49 | 11.48 |
| Register-only signed dot4, scalar TOP/s | 29.22 | 29.34 |
| Register-only FP16 WMMA, TFLOP/s | 57.14 | 57.13 |

Memory figures use the 320-block dispatch; arithmetic figures use 1,280 blocks.
The artifact includes all three dispatch sizes, all trials and numerical checks.
Trial zero is warmup. Memory data and arithmetic outputs passed checks; the
disassembly contains the expected eight FMA, eight dot4 and two WMMA operations
in their respective loops. These are empirical calibrations, not an inference
speed prediction. Register-only arithmetic excludes loads, dequantization,
synchronization and the resource pressure of real kernels.

SMBIOS reports eight 32-bit memory devices configured at 8,000 MT/s. If that
firmware value describes the actual memory clock, aggregate nominal bandwidth
is 256 GB/s. This is a conditional specification calculation, not independent
DRAM clock verification. The SDK reports 20 HIP multiprocessors on this WGP
architecture; that field must not be mistaken for the marketing CU count.

An initial model-loaded calibration also passed numerical checks, but some
samples had queue evictions. The unloaded repeat is the hardware reference.
Projection tests reached sampled temperatures of 72–77°C; these observations
do not establish thermal throttling. No clock or power configuration changed.

## Counter boundary: outgoing GL2 traffic is not physical DRAM traffic

Separate outgoing-request and DRAM-tag counter passes returned nonzero,
consistent counts. A 512 MiB read produced 4,194,306 128-byte outgoing read
requests and 4,194,307 DRAM-tagged read requests. The 2 MiB case also emitted
approximately its full payload beyond GL2. The latter is not proof that the
small buffer physically missed every system cache.

AMD's [gfx115x GL2 documentation](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/develop/conceptual/rdna/gl2-cache.html)
explicitly says requests labelled DRAM may be serviced by system-level caches
after GL2. Therefore these counters qualify an outgoing-cache boundary, not
memory-controller bytes. We do not publish a whole-model “DRAM utilisation”
percentage from them. The documentation is a development-version source;
raw counter values and separate counter passes remain in the evidence.

## Runtime weight and work accounting

The prior inventory counted 4.830 GB of non-expert GGUF payload plus 1.504 GB
for one ten-expert selection across 48 layers. Source and deployed-pack auditing
refine the non-expert runtime payload to **4.681 GB**, excluding lookup tables:

| Runtime group | GB |
|---|---:|
| GDN dense projections | 2.206 |
| Hyper-connections | 0.684 |
| Output vocabulary head | 0.675 |
| QSA projections and norms | 0.674 |
| Shared experts | 0.251 |
| Router matrices and vectors | 0.126 |
| Other GDN and PLE matrices/vectors | 0.065 |

This is an inventory, not an exact transaction ledger. The important format
details are:

- The pack stores several tensors as BF16, including router matrices.
- `NativeDense` defaults hyper-connection down/up/inject reads to Q8 on gfx1151,
  including load-time conversion of the injection rows. Looking only at the
  pack would incorrectly charge BF16 for these decode reads.
- Eligible native Q8 projections are losslessly repacked into integer and scale
  planes. A second resident layout does not mean both copies are read per call.
- The vocabulary head is loaded separately. On this platform it retains the
  original Q8 block layout; eligibility alone does not mean it is registered
  for the packed path.
- Prefill expands native weights into FP16/BF16 scratch for its matrix kernels.
  Conversion, scratch traffic and reuse need separate accounting.
- Embedding tables are sparse gathers. Their full resident size is not traffic
  per token. Norm vectors are included in inventory but not counted as GEMMs.

Matrix operations on each prompt row total **12.053 GFLOP**, using two scalar
operations per multiply-add. This includes routed experts at top-10, dense
projections, shared experts, router matrices and hyper-connection projections.
It excludes attention, GDN recurrence, nonlinear functions, norms, conversions
and gathers. The final vocabulary head is not charged to every prompt row.
At 1,300 tok/s, those matrices alone imply 15.67 TFLOP/s, about 27% of the
57.13 TFLOP/s calibration. This does not imply the remaining 73% is recoverable.

The recurrent state also matters: 36 layers × 48 value heads × 128 × 128 FP32
elements, plus convolution history, occupy about **117.67 MB**. One read and
write of that state is already about 235 MB; verification, retained histories
and commit replay can require more. Attention/indexer pools, selected KV
blocks, activations, gathers and MTP weights add other traffic. Their exact
physical transaction totals were not established here and are not silently
treated as zero in a practical performance prediction.

## Actual speculative expert reuse

The reporting patch enables Strata's existing route counter, exports exact
per-layer counts and reports dispatch selections at native request boundaries.
It adds diagnostic kernels/readbacks but does not change weight arithmetic or
normal fusion choices. **All public probe input/output hashes match the prior
control**, including 49K and 197K. Timing from this diagnostic run is not a new
performance baseline.

| Native request | Counted windows | Mean rows/window | Distinct experts/layer/window | Distinct expert payload/window | Dense + expert payload/window |
|---|---:|---:|---:|---:|---:|
| 49K, first segment | 204 | 3.162 | 22.172 | 3.338 GB | 8.019 GB |
| 49K, continuation | 221 | 3.158 | 22.649 | 3.410 GB | 8.091 GB |
| 197K | 428 | 3.061 | 21.983 | 3.309 GB | 7.990 GB |

Counts include native prelude/restore evaluations. The 197K emitting decode
contains 427 windows; the additional evaluation is the one-row prelude. The
49K continuation includes three six-row restore evaluations. These are recorded
instead of silently being equated with emitting windows. Weight estimates are
weighted by each layer's actual expert format, not one average bit width.

At 197K, the approximately 30.6 routed entries per layer/window collapse to
22 distinct expert IDs. This is useful reuse, but not a single ten-expert pass
for all output tokens. The prior uninstrumented control emitted 1,024 native
tokens in 427 windows: **2.398 accepted output tokens/window**, 597 accepted
drafts from 879 offered. A flat context/speed curve does not by itself prove
that KV work is negligible.

## Representative operators

The Q8 replay uses the same native entry point, registered layouts and TSUM
setting as the deployment. Its weight bank is at least 128 MiB and rotates
between matrices. Activations are quantized through the native function.
An independent CPU calculation checks sampled first/middle/final outputs in
every column against those quantized inputs; packed matrices also match the
original-layout GPU output bit for bit across every output. All checks pass,
and timed samples show zero self queue eviction.

| Q8 shape, four columns | Logical payload GB/s, first / return |
|---|---:|
| 2,560 → 10,240, packed | about 236–238 |
| 2,560 → 6,144, packed | about 235 |
| 2,560 → 12,288, packed | about 238 |
| 6,144 → 2,560, original layout | about 224 |
| 2,560 → 248,320 head, original layout | about 234 |
| 2,560 → 512 | about 153 |
| 640 → 2,560 | about 127 |

These rates are one logical weight payload divided by measured call time,
not hardware DRAM counters. Some single-column rates reach 248 GB/s; this
underscores that the 242 GB/s reduction probe is not a universal hard cap.
Large projections are already efficient. Small matrices have greater scheduling
headroom, but their smaller time budgets limit whole-model gains. The replay
does not replace fused shared-expert or HC operations with standalone GEMVs.
An initial qualification incorrectly registered the head for packing; that
result was excluded and both Q8 passes repeated with the deployed head layout.

Prefill replays use the unchanged `kernel_bk64<8>` control, T=16,384 and the
real projection shapes/strides. They reached **40.26, 40.31 and 42.82 TFLOP/s**
for QKV, gate and output respectively—70–75% of register-only WMMA throughput.
They passed the existing CPU-reference and full-output scheduling-parity checks.
Those figures exclude weight conversion and complete-model dependencies.

The existing [actual-routing expert replay](../experiments/strata-expert-profile/README.md)
already supplies complementary data: 58.52–59.77 ms for a full 16K Q4_K/Q5_1
layer over least/median/most padded distributions. Its approximately 1.611 TFLOP
of matrix work corresponds to about 27 TFLOP/s, including operator overhead.
This is reused November 7 evidence, not a newly measured November 12 gain.
The validated Q5_1 decode prototype's complete-model gain remains only 1.7–2.0%.

## Dependency-aware budget and target feasibility

The November 11 external trace preserves normal overlap. Prefill is effectively
serial on that trace (about 5 ms of overlap in 154 seconds). Generation has
overlap, so summed kernel durations cannot be subtracted as if all were serial.
The reliable overall generation budget comes from unprofiled window timing.

At 197K, baseline verification costs about **49.1 ms/window** and drafting
**9.9 ms/window**, producing about 40.7 tok/s. The diagnostic weight model gives:

| Assumed weight streaming rate | Optimistic weight-only time/window | With unchanged 9.9 ms drafting: implied output rate |
|---|---:|---:|
| 242 GB/s measured calibration | 33.0 ms | about 56 tok/s |
| 248 GB/s observed on selected Q8 replays | 32.2 ms | about 57 tok/s |
| 256 GB/s conditional nominal rate | 31.2 ms | about 58 tok/s |

**These are optimistic conditional scenarios, not achievable whole-engine
ceilings.** They assume every logical weight byte streams once, perfect useful
reuse, the observed acceptance rate, no inter-window weight-cache benefit,
and omit state/activation traffic and non-overlapped compute. They do not
measure physical DRAM. Real execution has extra costs; a different work/reuse
schedule can change the premises.

With the same 2.398 accepted tokens/window:

| Target | Allowed total ms/window | Allowed verify ms with current drafting | Verify reduction from 49.1 ms |
|---|---:|---:|---:|
| 50 tok/s | 47.96 | 38.06 | 22.5% |
| 60 tok/s | 39.97 | 30.07 | 38.8% |
| 70 tok/s | 34.26 | 24.36 | 50.4% |

Simply making all large GEMVs stream faster cannot supply those reductions.
Even deleting drafting entirely gives only about 49 tok/s with the present
verify pass. Conversely, holding drafting unchanged makes 60–70 difficult
even in the optimistic weight-only scenario. Higher acceptance, more useful
rows per weight read, less draft work or a different scheduling architecture
must enter a serious proposal for that range. This is not proof of a universal
hardware impossibility.

At 49K, the clean return control has 421 emitting windows, 1,006 native output
tokens and 18 frontend-injected tokens. Native generation is 41.85 tok/s;
verification averages 47.21 ms/window and drafting 9.88 ms/window. The same
weight-only calculation gives approximately 55–58 tok/s depending on assumed
streaming rate. The conclusion is therefore not specific to the 197K sample.
[Machine-readable budgets](../evidence/strata-envelope-2026-11-12/budget.json)
preserve both contexts and their exact denominators.

For cold prefill, the clean return control's first uncached segments give
1,379 tok/s at 49K and 1,284 at 197K. The earlier approximately 1,371 figure at
49K aggregated the cold segment and a small cached continuation. Target budgets
below use actual uncached token counts, 49,164 and 196,607:

| Context | Baseline prompt time, approximate | 1,700 tok/s | 2,000 tok/s |
|---|---:|---:|---:|
| 49K | 35.64 s | 28.92 s: save 6.72 s | 24.58 s: save 11.06 s |
| 197K | 153.16 s | 115.65 s: save 37.51 s | 98.30 s: save 54.86 s |

These are rounded planning figures. The 197K trace assigns 33.4 s to
expert matrices, 35.2 s to dense matrix families, 27.2 s to HC, 21.1 s to
attention/KV, 12.9 s to GDN and about 23 s to remaining work. Categories are
kernel-family classifications, not mutually exclusive architectural labels.

An illustrative optimistic experiment replaces the approximately 27 TFLOP/s
expert rate and 40–43 TFLOP/s projection rates with the 57 TFLOP/s register-only
rate, keeping other work fixed. It saves roughly **26–28 seconds**, still less
than the 37-second requirement for 1,700 at 197K. It is not a forecast: the
replays and family totals are not perfectly interchangeable, and real kernels
cannot spend all their time on register-only arithmetic. Its purpose is to
show why one kernel family is unlikely to close the target gap.

The older HC residual-write probe already achieved about 191 GB/s on estimated
mixed traffic. Against today's 209–211 GB/s mixed calibration, its remaining
streaming gap is modest. Existing HC config switches and projection retile
screens were already tested; this study does not reopen them as unexplored wins.

## Next designs, with explicit stopping rules

1. **Prefill: expert gate/up tile reuse and instruction scheduling.** The major
   Q4_K gate/up shape accounts for 20.3 seconds at 197K. Investigate reducing
   repeated quant-block decoding and operand movement across useful row tiles,
   with occupancy/LDS/register cost included. Reuse actual routing distributions
   and per-row buckets. This is a kernel redesign, distinct from the already
   unsuccessful prepared-activation and compact-weight-layout experiments.
   A 20% operator time reduction saves about four seconds, only around 3% overall;
   a proposed 10% overall gain needs a correspondingly larger combined budget.
2. **Decode: plan around accepted tokens per weight stream.** Build a costed
   proposal for draft/verify overlap or more useful speculative rows, including
   shared-memory contention, rollback/commit state and acceptance. Unchanged
   serial drafting alone accounts for only about 17% of window time. Do not
   claim that overlapping it is free, or assume different draft widths improve
   acceptance; earlier configuration screens remain evidence.
3. **Retain small exact improvements as composable research.** The Q5_1 patch
   and small-matrix scheduling opportunities can contribute a few percent.
   Require a repeatable complete-model gain and tool/state checks before
   promotion. They do not establish a route to another 20 tok/s by themselves.

This measurement pass concludes with design briefs. The next implementation
should have one explicit mechanism, an operator
ceiling large enough to matter, a bounded test and numerical/state acceptance
criteria. The baseline remains usable and reproducible while that work is
considered separately.
