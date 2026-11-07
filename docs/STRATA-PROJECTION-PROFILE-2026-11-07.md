# Projection profile: shared-memory residency and synchronization matter

The existing padded FP16 projection kernel runs with **248 VGPRs, 54 KiB LDS
per block and no spills**. Two instruction traces observed a maximum of
**four resident waves on the selected SIMD**, almost continuously. Shared-memory
waits, matrix instructions and barriers dominate the summed instruction latency.
This supports testing the tile's shared-memory footprint and data reuse next;
it does not establish a simple DRAM-bandwidth bottleneck or predict a speedup.

A first fragment-load scheduling change preserved all tested GPU outputs but
was neutral (**−0.05%, +0.20%, +0.21%** across three shapes). Its resources stayed
unchanged. It is rejected. No production change or new prefill baseline.

## Scope and control

This profiles the standalone [projection probe](../experiments/strata-projection-grouping/README.md),
using the unchanged group-8 BK64 kernel at three real matrix dimensions with
synthetic FP16 data. Source `41021fb`, gfx1151, ROCm lab SDK 7.14.1, `-O3`.
Input rows are 16,384; weights use K+64 stride, with activation padding for
the K=6144 output projection. It is not a full-model profile or captured-data
quality test. Earlier full-model phase measurements remain the scope estimate.

Three independent counter passes per shape collect memory traffic, L2 hits
and instruction activity. Each selects five group-8 dispatches after setup.
Counters matched launch geometry in 29 of 30 wave-count records; one QKV
memory record returned all zeros and is explicitly marked unusable. Its
other four dispatches remain reported. The repeat QKV memory pass returned
five valid records. Instruction-only passes returned nonzero data. Thus the
initial 45 records contain 44 usable samples, plus five in the repeated pass.
No invalid zero sample is included in the derived medians.

ATT captured the third group-8 dispatch of the QKV and output shapes on
WGP 1 / SIMD 0 / shader engine 0, decoding 512 and 128 waves. The original
serving process remained loaded and idle; its request count stayed zero.
No endpoint restart, OpenClaw turn or configuration change occurred.

## Resource and residency evidence

| Resource | Observation |
|---|---:|
| Workgroup | 256 threads / 8 wave32 waves |
| Shared memory (LDS) | 55,296 bytes |
| VGPRs | 248 |
| Compiler SGPRs | 24; trace allocation field reports 128 |
| Scratch / register spills | 0 |
| Compiler WGP mode | Enabled |
| Selected-SIMD peak resident waves | 4 in both traces |
| Selected-SIMD time-weighted waves | 3.984 QKV / 3.998 output |

With 128 KiB LDS per workgroup processor, only two 54 KiB blocks fit. Two
eight-wave groups spread across four SIMDs give four waves per SIMD, matching
the sampled residency. This is consistent with an LDS residency limit; it
does not prove every WGP behaved identically or that higher occupancy alone
would improve speed. AMD documents the gfx1151 hardware resources and the
workgroup-level relationship between LDS and occupancy. [Hardware table](https://rocm.docs.amd.com/en/docs-7.1.1/reference/gpu-arch-specs.html),
[occupancy explanation](https://gpuopen.com/learn/occupancy-explained/).

## Traffic and instruction evidence

| N / K | External L2 reads, GB | External L2 writes, GB | External L2 rate, GB/s | L2 hit rate |
|---|---:|---:|---:|---:|
| 10,240 / 2,560 | 4.095 | 0.670 | 221.6 | 42.0% |
| 6,144 / 2,560 | 2.050 | 0.401 | 191.6 | 36.9% |
| 2,560 / 6,144 | 2.232 | 0.167 | 196.2 | 47.3% |

These are medians of valid instrumented dispatches. The repeated QKV pass
measured 3.388 GB reads, 0.670 GB writes and 188.7 GB/s, while duration was
similar: 21.563 ms versus 21.506 ms initially. The traffic difference remains
unexplained; it is not evidence that removing a particular fraction of reads
will remove that fraction of wall time. gfx1151 has a 32 MiB last-level cache
beyond its 2 MiB L2, so external L2 requests must not be labelled direct DRAM
traffic. [AMD hardware specification](https://rocm.docs.amd.com/en/docs-7.1.1/reference/gpu-arch-specs.html).

The following are **shares of summed per-instruction latency on the traced
SIMD**, with overlap between waves. They are not wall-time bottleneck shares:

| Instruction category | QKV trace | Output trace |
|---|---:|---:|
| LDS/scalar-memory waits (`lgkmcnt`) | 32.3% | 35.3% |
| WMMA matrix instructions | 25.0% | 28.8% |
| Workgroup barriers | 16.6% | 16.4% |
| LDS instructions | 10.5% | 11.1% |
| Vector-memory waits (`vmcnt`) | 8.0% | 2.5% |

`lgkmcnt` includes scalar-memory dependencies too; the name alone does not
prove all of that time is LDS. The source and disassembly show repeated
fragment loads followed by matrix operations and two barriers per K tile.
No barrier was removed without proving the shared-memory dependencies.

## Fragment-load scheduling screen: rejected

The isolated `--row-stream` candidate places each activation fragment load
beside the four matrix operations that consume it, keeping weight fragments,
tile size, block grouping and each output's K accumulation order fixed.
Variant ID **99** means this candidate; it is still group 8, not group 99.

61 untraced samples per variant alternate control/candidate order:

| N / K | Control median | Candidate median | Operator improvement |
|---|---:|---:|---:|
| 10,240 / 2,560 | 20.025 ms | 20.034 ms | −0.05% |
| 6,144 / 2,560 | 12.585 ms | 12.561 ms | +0.20% |
| 2,560 / 6,144 | 11.287 ms | 11.263 ms | +0.21% |

All 14 complete GPU comparisons matched bit for bit, including partial
blocks/groups, output padding, beta 0/1 and the three large shapes. The four
smaller independent CPU cases passed the same 1e-6 tolerance as the earlier
screen. The original control's instruction hash is unchanged from the
previous grouping build. Candidate instruction scheduling differs, but both
have 3,119 instructions, 248 VGPRs, 54 KiB LDS and no scratch/spills. The
intended reduction in register allocation did not materialize. Do not promote
this neutral result or spend a full-model/state ladder on it.

## Next constrained experiments

Keep padding and group 8 on. Test tile changes independently against this
control, with complete output comparisons, untraced timing and resource
inspection before full-model work:

1. A narrower 128×128 output tile with K64 and 256 threads: potentially
   36 KiB LDS and more resident blocks, at the cost of repeated activation
   reads. Measure the tradeoff; higher occupancy is not the success criterion.
2. A wider 128×512 output tile with K32 and 512 threads: more output columns
   share activation loads, but the smaller K tile increases synchronization
   frequency. Check register allocation, memory traffic and actual time.

These are proposed geometries, not implemented or measured wins. No projection
change is serving. The 1,700–2,000 tok/s prefill and 50–70 generation targets
remain unmet.

## Reproduction and evidence

Build the ordinary grouping probe using its README. Then:

```sh
python3 experiments/strata-projection-grouping/profile.py \
  --binary /tmp/projection-grouping/grouping --sdk /path/to/rocm-sdk \
  --profile /path/to/private/serving-profile.json --out /tmp/projection-profile
python3 experiments/strata-projection-grouping/profile.py \
  --binary /tmp/projection-grouping/grouping --sdk /path/to/rocm-sdk \
  --profile /path/to/private/serving-profile.json --out /tmp/projection-profile \
  --modes att --shapes qkv out
python3 experiments/strata-projection-grouping/analyze-profile.py /tmp/projection-profile
```

For the rejected scheduling candidate, build in a new directory with
`build.py --row-stream`, run `run.py --rounds 61`, and use `analyze.py`.
No production executable is rebuilt. Exact commands and binary hashes are
stored with each measurement; the private serving profile is not published.

[Profile evidence](../evidence/strata-performance-2026-11-07/projection-profile/)
contains counter CSVs, decoded instruction statistics, extracted wave
intervals, commands and the failed-counter record. Raw ATT binaries remain
local with hashes/byte counts recorded; decoded CSVs and compressed code
objects are published. [Scheduling evidence](../evidence/strata-performance-2026-11-07/projection-rowstream/)
contains all samples, parity checks, ISA comparison, metadata and telemetry.
