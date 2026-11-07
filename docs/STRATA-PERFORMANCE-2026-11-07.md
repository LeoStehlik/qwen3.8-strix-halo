# Flash-Next performance investigation — November 7, 2026

**Resumed with higher objectives after a successful real OpenClaw test.** The
user now targets **1,700–2,000 tok/s prefill**, then **50–70 tok/s generation**.
The selected packaged baseline is serving the authenticated Tiercel endpoint.
The initial 13 live calls averaged 1,327 prefill / 47.2 generation; the user
reviewed the beta-release/PR research result and was pleased. No losing source
experiment or partial tuning table is deployed.

[Updated objective and next experiment order](STRATA-NEXT-TARGETS-2026-11-07.md).
Keep the existing UD-Q4_K_XL model, full context capacity and useful agent
behaviour. The earlier 1,100 / 50–60 target below is historical. Tool-call
changes remain out of scope unless validation exposes a relevant regression.

The subsequent [expert profile and actual-routing replay](../experiments/strata-expert-profile/README.md)
split the dominant native operator into about 62% gate/up and 37% down.
All 192 full layer/chunk routing records were captured from a public 64K probe;
three selected distributions added only 1–3% over a uniform operator control.
No production kernel change resulted. Hardware counter zeros in the expert
run remain unexplained; a copy control returned plausible traffic counters.
The optimized endpoint was restored at 16:35:56 UTC, with the Mac untouched.

## Subsequent expert and HC screens

The [cooperative epilogue experiment](../experiments/strata-cooperative-epilogue/README.md)
improved the complete expert operator by 2.4–2.5% on three captured 16K
routing distributions, with identical output hashes. Twelve reference
processes also matched all intermediate int8 bytes for the three model weight
format pairs and both tile sizes. Its estimated whole-prefill contribution
is only about 0.6%; a model-level gain has not been measured. It remains an
undeployed, opt-in source experiment. Four-stage gate/up loop unrolling was
slower and was removed. Increasing the hipBLASLt heuristic request to 128 and
testing 256 MiB workspace retained the existing solutions; no table changed.

Memory-counter collection works when gate/up and down are collected
separately; a filter including both reproduces the earlier zeros. The
underlying profiler cause remains unresolved. Gate/up instruction counters
still returned zero. Do not infer a hardware roofline from those results.

Two existing packaged HC options were then compared with a fresh control.
All used the same 65,551-token public prompt, nonce seed `hc-down-compare-v1`,
zero reused tokens, greedy/non-thinking sampling, 16 output tokens and
`STRATA_PREFILL_TIMING=1`. Our source epilogue was not involved.

| Configuration | Prompt ms | Prefill tok/s | GPU timeline ms | HC down+silu ms | HC inject ms | Prior conversation park ms |
|---|---:|---:|---:|---:|---:|---:|
| Packaged control | 47,191.0 | 1,389.1 | 47,029 | 1,897 | 694 | 45.6 |
| `STRATA_HCD_EXACT=1` | 53,853.6 | 1,217.2 | 47,904 | 2,042 | 708 | 5,829.9 |
| `STRATA_PF_HCDOWN=1` | 47,406.1 | 1,382.8 | 47,250 | 2,415 | 8 | 40.2 |

All three produced the same 16-token output hash. That limited observation
does not establish broad model-quality equivalence. The exact variant's
request-time regression includes a separate cache-parking stall; even its
GPU and HC-stage times showed no improvement. Kernel eviction/migration
counters remain in the telemetry, so causal attribution of the entire
regression to the option would be unjustified. The fused variant saved
168 ms across down/inject but showed no whole-request gain. Neither option
was promoted. No driver or host memory policy was changed.

[Comparison data](../evidence/strata-performance-2026-11-07/hcd-comparison.json)
and per-arm logs/telemetry are retained. The larger 1,700–2,000 prefill and
50–70 generation objectives remain unmet. Next: capture actual attention
selections and test KV reuse/scheduling opportunities on the existing kernel;
its trimming and read-prefetch defaults are already enabled.

## Initial deployment missed the target

The first real OpenClaw request supplied 187,737 input tokens. It was cancelled
after the engine processed 80,551 uncached tokens in 154.462 seconds: 521.5
tokens/s. This was a partial prompt, not a completed 187K benchmark.

After the user reset the session, a 15,388-token request reused 15,015 tokens;
only 373 were newly processed. Its 36.8 tokens/s generation and short prompt
delay must not be presented as cold 15K performance. Later live generation
ranged roughly 25.5–42 tokens/s.

At 13:59 UTC a native verification watchdog timed out at layer 45 during
generation. The engine exited with SIGTERM and the control server loaded it
again for the retry. No assistant restart caused this incident. Kernel logs
reported long-running `amdgpu_amdkfd_restore_userptr_worker` work, but no GPU
reset or OOM was observed. Causation is unproven. An engine that recovers on
retry has not thereby passed stability validation.

## Controlled comparison

Strata release v0.2.11, engine/control 0.1.57, build `0bdcef4682c5+rocm`,
HIP gfx1151 on the 128 GB Ryzen AI Max+ 395. Same model revision and quant,
262,144 context capacity, INT8 KV, MTP, vision and route-tail skipping disabled.
The bundled 90-row hipBLASLt table is active.

`benchmarks/strata-prefill.py` sends public source text at approximately the
specified sizes. It places a fresh nonce at the start, records actual token
counts and cache reuse, and requests 512 output tokens at temperature zero,
thinking disabled. This is an inference benchmark, not an OpenClaw task or a
claim about tool quality. The output allowance applies only to these requests.
Cold means no reused prompt state; it does not mean cleared OS file caches.

Fixture SHA-256:
`6efd5cb8693d5c7fc9fa826da0e454895172071c7d30283f6eb6c04978875346`.
The fixture contains repeated source material; its expert distribution and
draft acceptance need not match a real conversation. Each arm receives a short
warm-up. The original baseline was measured on the previously loaded engine;
other arms were freshly loaded. Repeated and larger-context checks follow any
promising screening result.

| Configuration | Actual cold input | Prefill tok/s | Generation tok/s | Output tokens |
|---|---:|---:|---:|---:|
| Installer layout, explicit 16K chunks | 16,394 | 540.3 | 32.7 | 512 |
| Same layout, auto chunks (selected 8K) | 16,392 | 463.5 | 33.8 | 512 |
| Same layout, fast prompt kernels, 16K chunks | 16,393 | 1,027.3 | 32.0 | 512 |
| Fast prompt kernels, repeat | 16,397 | 1,082.3 | 32.9 | 512 |
| Fast prompt kernels, 64K | 65,547 | 1,234.0 | 30.7 | 512 |
| Fast prompt kernels, 128K | 131,078 | 1,211.3 | 32.2 | 512 |
| All GPU experts, direct PLE, own prompt buffers | 16,393 | 990.2 | 28.4 | 512 |
| All GPU experts, mmap PLE, own prompt buffers | 16,392 | 1,223.6 | 42.2 | 512 |
| Same layout, full GPU KV | 65,548 | 1,240.1 | 39.3 | 512 |
| Same layout, full GPU KV | 131,073 | 1,202.1 | 37.9 | 512 |

The fast prompt set is opt-in on Linux Halo in this release. It was absent
from the generated installation. The benchmark changes only these environment
settings from the original 16K arm:

```sh
STRATA_PF_FUSED=1
STRATA_PF_FUSED_KQ=1
STRATA_PF_GEMM=1
STRATA_HC_UPMIX=1
STRATA_PA_FAST=1
STRATA_HIP_WMMA=1
STRATA_SELECT_WMMA=1
STRATA_PF_SWITCH_MIN_T=4096
STRATA_PREFILL_STREAM_MIN=128
```

These are packaged upstream kernels, not a locally modified engine. Some
change floating-point rounding; output identity or model-level equivalence
has not been established by this performance comparison.

The 128K request completed with zero reused prompt tokens in 108.209 seconds
of prefill, then generated 512 tokens. This reproduces the vicinity of the
published prefill result on our custom fixture; it does not reproduce the
upstream benchmark protocol or its decode result.

To reproduce the input, download the [pinned public fixture](https://github.com/LeoStehlik/qwen3.6-35b-a3b-strix-halo/blob/4c1186a727b8e3b45422266563b6cee089f89679/benchmarks/fixtures/prompt.txt)
and verify the SHA-256 above. With the isolated server loaded and the API key
available as `STRATA_API_KEY`, run:

```sh
python3 benchmarks/strata-prefill.py \
  --url http://127.0.0.1:8084 \
  --model qwen3.8-flash-next-unsloth-ud-q4_k_xl \
  --fixture /path/to/prompt.txt \
  --sizes 16384 65536 131072 --repeat 1 --max-tokens 512 \
  --out results.json
```

## Memory layout to investigate next

The installer selected 38 GiB of pinned host experts and a numeric GPU cache
of 5,080 maximum-sized slots, realized as 6,474 variable-sized slots / 18.89 GiB.
Total expert storage is about 71.7 GiB. The 26.8 GiB PLE table is faulted into
RAM but its lock is refused by the service's 8 MiB memlock limit. KV data beyond
32K cells per attention layer streams from 3.09 GiB of pinned RAM.

Prompt scratch space borrows GPU expert-cache slots. Host and GPU copies share
the same physical RAM on this APU. Logs show expert file reads and non-GPU
execution during generation. This makes residency a concrete experimental
target; it is not yet proof that residency explains the full decode deficit.

The all-expert GPU layout removes `--resident-budget-gib 38`, sets
`--expert-cache auto`, adds `--mmap-experts --no-prefill-borrow`, and changes
`--ple-io ram` first to `direct`, then independently to `mmap`. The automatic
cache realized all 24,576 experts / 71.73 GiB, with no host expert arena and
about 25 GiB OS memory available during loading. Context and KV settings were
unchanged. Startup took about 90 seconds.

Direct PLE was slower overall despite eliminating expert misses. Changing
only PLE access to mmap improved both measures: 1,223.6 prefill / 42.2 generation
at 16K. No expert-file reads occurred during that measured request. The first
small warm-up had a 6.6-second prefill, so cold lookup-table access still matters.
These are single screening runs; larger-context validation and a generation
profile are next. The memory-layout bundle is not evidence for attributing the
whole gain to any one of cache size, arena removal or prompt-buffer ownership.

Do not simply increase the pinned host budget: driver accounting and duplicate
storage can exhaust the shared pool. The PLE table is still used in every arm;
`--no-ple` is not a performance option for a real deployment.

## Generation profile and rejected experiments

With the all-expert GPU / mmap PLE layout, `STRATA_DECODE_TIMING=1` and
`STRATA_VERIFY_PROFILE=1` measured 229 generation windows after a cold 16K
prompt, averaging 2.24 emitted tokens/window:

| Wall-time component | ms/window | Share |
|---|---:|---:|
| Main-model verification | 49.80 | 84.8% |
| Drafting | 8.94 | 15.2% |
| Other, commit/emission, adaptation | about 0.02 | below 0.1% |

CPU expert work, PCIe expert work and adaptive swaps were zero in this layout.
The GPU event profile reported 49.62 ms/window (cumulative over 230 windows),
with expert matrix operations at 17.70 ms: about 35.7% of profiled GPU work.
This is not the same denominator as total request wall time. The profiler
slows generation: this instrumented run reached 38.0 tok/s, versus 42.2 in the
earlier uninstrumented screen. Do not quote the instrumented result as a new
speed baseline.

Adding `--mtp-q4 all` quantizes only the draft projections/head. Its first
16K run stalled for several seconds around output token 238, resumed without
an engine restart, and averaged 24.3 tok/s. An SVM restore workqueue warning
appeared around the same time; this is correlation, not an established cause.
A repeat without the stall reached 41.4 tok/s. Request-local draft confidence
floors 0.7 and 0.3 reached 41.0 and 40.7 respectively, versus 0.5's 41.4. These
single screens show no benefit over the original drafter's 42.2; neither the
smaller drafter nor a new confidence floor is selected.

The telemetry and unsuccessful arms are retained alongside successful ones.
The main-model quant, context and user-facing sampling settings were unchanged.
`--spec-min-p` in the benchmark sets only a request-local proposal-confidence
threshold; it does not change the request's sampling temperature.

Full GPU KV residency completed 64K and 128K requests as recorded above.
Its first 16K request also stalled
and measured 1,092.7 prefill / 27.1 generation. The new layout is therefore
not yet a stable deployment recommendation. A relevant existing safeguard is
`STRATA_VERIFY_EARLY_PLE_FLAG=1`: the release-pinned verifier documents raising
the lookup-table-ready flag before *every* graph launch, whereas HIP normally
does so only for each graph's first launch. Testing it may distinguish the
lookup/GPU wait interaction from ordinary compute cost; no fix is claimed yet.

With that safeguard, the first 16K request completed at 1,224.7 / 40.6 tok/s
without a generation stall, although the tiny warm-up still took 7.35 seconds
in prefill. Adding the existing `STRATA_EXPERT_V2K=1` kernel gave 1,020.2 / 41.8;
the small generation difference is insufficient to select it from one run.
The initial stall is not proven fixed.

### Protocol correction for subsequent comparisons

Version 1's tiny warm-up plus a random hexadecimal nonce ranged across the
engine's 64-token short-read boundary. In particular the V2K arm warmed with
64 input tokens, taking a different prompt path from the preceding arm's 67.
This confounds small first-request prefill differences. The source-text probe
itself still used fresh nonces and reported zero prompt reuse.

Protocol version 2 uses the same fixed 151-token warm-up for each fresh load,
above that threshold. The measured request retains its fresh nonce. A new
control and F16 prompt-kernel comparison use this corrected protocol; old
results are preserved under version 1, not silently rewritten.

### Last results before the reboot pause

| Protocol v2 configuration | Actual input | Prefill tok/s | Generation tok/s |
|---|---:|---:|---:|
| All experts + KV on GPU, mmap PLE, early PLE flag | 16,395 | 815.4 | 41.4 |
| Same, `STRATA_PF_F16=1` | 16,394 | 1,390.5 | 41.8 |
| Same F16, 64K | 65,547 | 1,411.7 | 37.9 |

All three generated 512 tokens and reused zero prompt tokens. The control
contained a several-second pause during prefill; do not attribute its entire
gap to F16. F16's 151-token warm-up also paused (8.772 seconds). The F16 128K
request was deliberately cancelled for the user's reboot; it is incomplete,
not a failed correctness or throughput result. F16 changes rounding and has
not received model-quality validation here. No candidate was promoted.

The new kernel-memory sampler records a stronger explanation for the pauses:
the inference process's KFD `evicted_ms` reached 12,433 ms while background
compaction scanned about 25.8 million pages and successful page migrations
rose sharply. The vision process was also evicted. This establishes actual
GPU queue eviction overlapping memory compaction, but does not yet prove
which migration policy triggered it. NUMA balancing is already zero on this
single-node machine. `vm.compaction_proactiveness` is still its original 20.

After reboot, repeat the same F16 configuration with the original host policy
first. If pauses recur, compare a fresh load with
`sudo sysctl -w vm.compaction_proactiveness=0`, recording/restoring the original
20 as appropriate. This is a proposed reversible experiment, not a change
already made. [Kernel documentation](https://docs.kernel.org/admin-guide/sysctl/vm.html#compaction-proactiveness)
describes both the background migration and the potential latency spikes.

Generation's 50–60 tok/s target remains unmet. The public workload subset in
`benchmarks/strata-generation.py` is prepared and syntax-checked but has **not
been run**. Tool-call investigation remains parked.

## Clean-boot comparison and remaining stalls

Boot ID `35917f23-eead-456d-8ed2-d368f0e68f36`, kernel taint zero, original
`vm.compaction_proactiveness=20`, `kernel.numa_balancing=0`. Only the same F16
candidate was loaded. It took 88.04 seconds; the 151-token warm-up prefill
completed in 631 ms.

| Cold input | Prefill tok/s | Generation tok/s | Reused / output tokens |
|---:|---:|---:|---:|
| 16,393 | 1,074.3 | 40.3 | 0 / 512 |
| 65,550 | 1,417.5 | 40.9 | 0 / 512 |
| 131,075 | 1,363.2 | 38.9 | 0 / 512 |

KFD reported 2.801 seconds evicted at readiness and 7.097 seconds during the
first 16K prefill. Successful page migrations reached 1,416,691 while daemon
compaction scanned 2,924,729 pages. This reproduces the pauses after reboot;
stale processes from earlier installations cannot be their sole explanation.
A fresh identical arm with temporary `vm.compaction_proactiveness=0` completed:

| Cold input | Prefill tok/s | Generation tok/s | Reused / output tokens |
|---:|---:|---:|---:|
| 16,392 | 1,388.5 | 42.5 | 0 / 512 |
| 65,551 | 1,397.5 | 41.4 | 0 / 512 |
| 131,072 | 1,350.2 | 37.5 | 0 / 512 |

After readiness, inference-process eviction increased by only 130 ms, versus
4,339 ms with policy 20. Successful page migrations after readiness fell from
1,186,367 to 4,780. Eviction during loading still occurred (2.010 seconds by
readiness). Large-prompt throughput differed by approximately 1–2%, so this
supports a reduction in pauses, not a compute-speed gain. The runs occurred
sequentially in different memory/cache states; an interleaved repeat is needed
before claiming a durable fix. The setting remains temporary, not persisted.
The next arm profiles prefill on this configuration; generation tuning is
parked until the user's prioritized prefill work is finished.

**Later counterexample:** with the same temporary zero policy, the chunked-GDN
arm's 151-token warm-up stalled again: 2.647 seconds prefill and 7.152 seconds
generation. KFD eviction rose from 4.301 seconds at readiness to 13.921 seconds,
while successful page migrations rose from 2.787 million to 4.178 million.
The long measured request then ran without that pause. This refutes treating
`compaction_proactiveness=0` alone as a fix: allocation-driven background/direct
compaction is still possible. No persistent change or stability claim is made.

### Public generation subset and sampling caveat

`benchmarks/strata-generation.py` completed its three public cases on the
clean-boot F16 candidate: 49.8 tok/s for the short prose question, 45.2 for the
16,347-token document (1,476.1 tok/s cold prefill), and 57.7 for the LRU code
prompt. Each generated 512 tokens. This is a custom subset, not the official
full Strata protocol, and does not establish 50–60 tok/s on long agent turns.

The server source also establishes an inherited setting omitted from the
initial benchmark report: non-thinking Flash-Next requests default to
`presence_penalty=1.5`. The private config has no sampling block and
`GET /settings` returned no shared defaults. Our temperature-zero probes did
not override that penalty. OpenClaw explicitly sends zero. Existing results
remain valid for their actual requests but are not sampling-matched OpenClaw
results. Both probes now accept an explicit `--presence-penalty`; a comparison
with zero is deferred until after the prioritized prefill work. Historical
measurements are not overwritten.

## Profile of the faster prefill path

With `STRATA_PREFILL_TIMING=1` and `STRATA_DRAFT_TIMING=1`, the F16 candidate
processed a cold 65,552-token request at 1,380.7 tok/s (47.477 seconds).
The prompt-path timer covers 65,545 tokens and reports a 47.319-second GPU
timeline. Event intervals include waiting gaps; this is not a memory-bandwidth
or occupancy counter capture. The 16-token completion is only a termination
check, not a generation benchmark.

| Aggregate on that timeline | Time | Share |
|---|---:|---:|
| Routed expert computation | 11.796 s | 24.9% |
| GDN projections, convolution/gates, recurrence and output | 11.319 s | 23.9% |
| Hyper-connection read/write | 9.904 s | 20.9% |
| QSA projections, selection, attention and preparation | 9.515 s | 20.1% |
| Remaining routing/shared, combine, lookup and setup | about 4.785 s | 10.1% |

The fused-expert interval is labelled `gemm gate/up` but includes the fused
expert down work; the tiny separate `gemm down` entry is not its total cost.
GDN recurrence alone is 3.163 seconds (6.7%), actual QSA attention 4.745 seconds
(10.0%), HC write 4.026 seconds (8.5%). Host grouping is 6 ms, below 0.02%.
CPU expert staging is zero. Draft-layer work after chunks is 379 ms. Do not
optimize host grouping or treat the full old attention share as current.

Next experiments keep every model/context setting fixed: first a 32K chunk
versus the current 16K, then the existing chunked GDN kernel independently.
The latter changes recurrence rounding and needs quality validation before
promotion. Its theoretical gain from a 1.6x recurrence speedup here is about
2.6% overall, not 60%. The broader profile also gives concrete targets for
further kernel work if the packaged switches stop paying.

### Larger-chunk screen: not selected

Changing only `--prefill 16384` to `32768` with automatic expert-cache sizing
reached 1,375.0 tok/s on 65,546 uncached input tokens. Automatic sizing reduced
the GPU expert cache from 24,576 to 23,083 slots (67.38 GiB). The measured
request read 9.502 GB of expert blobs and caused 1.094 GB of OS storage reads.
It is therefore a combined chunk/residency outcome, not an isolated tile-size
comparison. It showed no gain and is not selected. OS memory available during
prefill was approximately 18.5 GiB; a later fixed-residency comparison can
hold all 24,576 slots explicitly, with memory telemetry retained.

The independent screen kept the 16K/all-resident layout and changed only
`STRATA_GDN_CHUNKED=1`: 65,552 uncached tokens at 1,404.5 tok/s and 131,075 at
1,363.1. Those differences are within the observed control spread, so this
rounding-changing path is not selected. Both generated 16 tokens only; their
reported decode rates are not sustained-speed comparisons. `STRATA_PF_BATCH=512` is not a candidate for this packaged
HIP build: `kBatchRoom` is capped at 128 in `moe_fused.hpp`, so that setting
would not perform the hoped-for larger expert launch.

The follow-up explicitly held `--expert-cache 24576` at 32K chunks. It loaded
all experts, completed 65,547 uncached input tokens at **1,392.5 tok/s**, and
left about 14.3 GiB OS memory available during prefill. This resolves the
residency confounder and shows no useful advantage over 16K. The automatic
conversation-cache budget also shrank from 6,912 to 4,864 MiB due to the larger
scratch buffers. That cache was not reused in the cold request. The 8K screen retained all experts but reached only **1,350.1 tok/s** on
65,549 uncached tokens. Keep 16K. A final packaged-kernel screen forces
`STRATA_PF_F16_BN=64` instead of the automatic 128-row choice at this chunk
size. The source chooses from average rows per expert, which may conceal
uneven real routing. The measured 65,549-token request reached **1,376.8 tok/s**,
so forcing the narrow layout is not selected either. The chosen packaged
configuration remains 16K chunks, automatic F16 tile width, without chunked
GDN. A longer 192K cold request now checks that path with an explicit zero
presence penalty; it remains a temperature-zero/non-thinking performance
probe, not a full match to OpenClaw's thinking/sampling settings.

### Expert-dispatch code experiment: rejected

The release-pinned F16 expert path in `moe_fused_iq.cu` constructs a launch
bound from the whole layer's routed-row count plus the current expert batch.
`moe_f16_kq.cu` launches that bound times the feature-block count. On device,
`work_item` in `moe_f16_common.cuh` exits blocks past the batch's actual tile
count; 128-row operation also skips every second 64-row tile entry. Thus some
blocks perform no matrix work. Their cost is not measured by the phase profile,
and the number of empty blocks is not the fraction of time that can be saved.

The bounded persistent-dispatch experiment is now complete and **rejected**.
At a 16K chunk on the dominant Q4_K/Q5_1 format, the original operator took
54.000 / 54.326 ms before/after the screen. Grid sizes of 1, 2, 4, 8 and 16
blocks per compute unit took 85.467, 62.468, 65.332, 58.897 and 58.651 ms.
Even the best opt-in case was about 8% slower. All output hashes matched.
The patched default-off path took 54.148 / 54.261 ms and matched the original
binary's outputs. CPU-reference, empty-range, non-contiguous routing and boundary
checks passed for all three model quant pairs and both tile sizes.

[Archived patch, reproduction and limitations](../experiments/strata-f16-persistent-dispatch/README.md)
include the pinned source, isolated SDK, raw logs and output-bit comparisons.
The isolated SDK did not change the driver or packaged runtime. No full-model
run or deployment of this losing patch was warranted. The next measured target
is the hyper-connection residual write/normalization (4.026 seconds / 8.5% of
64K prefill), beginning with an operator bandwidth measurement.

## Long-context check of the selected packaged configuration

The 16K / automatic-F16-tile candidate completed the following fresh requests
with explicit `presence_penalty=0`, temperature zero, thinking disabled, and
512 output tokens. Zero presence penalty matches that one OpenClaw setting;
this remains a custom public fixture, not a live agent replay.

| Actual uncached input | Prefill tok/s | Prefill seconds | Generation tok/s |
|---:|---:|---:|---:|
| 65,546 | 1,390.4 | 47.142 | 40.0 |
| 196,609 | 1,300.9 | 151.129 | 37.3 |

Both reused zero tokens and completed their streams. The inherited presence
penalty was not the missing generation-speed explanation on this workload.
The 50–60 tok/s generation target remains unmet; the prefill configuration
meets the original target even at 192K, with further code work still active.

After these tests, the engine was stopped and `vm.compaction_proactiveness`
restored to its original **20**. No persistent sysctl file was changed. The
packaged settings are preserved. A separate pinned checkout and user-local
compiler were used for the rejected expert-dispatch experiment. No model
weights are changed or downloaded for that work.

## Prefill follow-ups: bandwidth and matrix calibration

The unmodified `hip_prefill_gr_write_bench` at the pinned source/SDK gave:

| Tokens in operator | Best / mean ms | Estimated traffic | Best effective bandwidth |
|---:|---:|---:|---:|
| 4,096 | 2.361 / 2.391 | 0.46 GB | 195 GB/s |
| 16,384 | 9.663 / 9.711 | 1.85 GB | 191 GB/s |

The byte estimate counts residual read/write, one read of the shared output
vector and the BF16 output. It does not count every hardware transaction or
norm-weight reload. A separate validated float4 GPU copy of 671,088,640 bytes
per buffer reached median 212.9–232.8 GB/s depending on dispatch size. This is
an empirical comparison, not a hardware bandwidth-counter measurement.
If residual write reached the fastest copy rate at the same estimated traffic,
the 8.5%-of-prefill phase would save about 1.5% overall. Different read/write
mixes and arithmetic mean this is only a rough headroom estimate. No residual
kernel patch was promoted; this is not a promising standalone 10–20% target.
[Source, checksums, build and run evidence](../evidence/strata-performance-2026-11-07/grwrite/).

The existing `tune_hipblaslt` tool also screened the three large FP16 projection
shapes at T=16,384 with 32 MiB workspace, two warm-ups and three measured calls
per candidate, using its reference-error gate:

| Output columns N | Reduction K | Best solution | Mean ms |
|---:|---:|---:|---:|
| 10,240 | 2,560 | 2390 | 30.306; repeated 30.187 |
| 6,144 | 2,560 | 2390 | 18.679 |
| 2,560 | 6,144 | 2390 | 25.659 |

All winners are already in the packaged gfx1151 / hipBLASLt 100401 table.
This searched the upstream tool's returned heuristic candidates, not every
possible kernel implementation. No table replacement or performance gain is
claimed. The emitted partial candidate table is evidence only; it must not
replace the complete serving table.
[Calibration arguments and raw results](../evidence/strata-performance-2026-11-07/lt-calibration/).

The measured packaged prefill candidate remains selected. The next phase is
generation: compare draft-window sizes with the same public prompt and then
validate with the recorded OpenClaw sampling settings. Protocol v3 adds an
explicit sampling preset and reproducible nonce seed; default greedy request
behaviour is unchanged. Fresh server instances prevent prefix reuse between
arms; each request still checks actual cache accounting. The 512-token output
allowance applies only to the benchmark, not the provider's response limit.

## Generation control and user-requested pause

A fresh packaged control with `--spec 4` completed 65,548 uncached input tokens
at **1,416.0 tok/s prefill**, followed by 512 output tokens at **39.3 tok/s**.
Draft counts were 468 proposed / 287 accepted. The engine reports a maximum
verification window of 6 because suffix lookup can extend the MTP window;
`mtp_max=4` confirms the MTP cap. The comparison uses reproducible nonce seed
`generation-screen-v1`, zero temperature, no thinking and zero presence penalty.
Startup took 102.1 seconds and the first warm-up again had a multi-second pause.
No claim is made that the earlier startup/eviction issue is solved.

The user then requested pausing experiments to test real OpenClaw traffic.
The thinking-enabled probe was interrupted after its warm-up; there is no
completed thinking-enabled long-context result, and no spec-6/spec-8 comparison
was run. No losing source patch or partial tuning table is deployed.
[Control and interruption evidence](../evidence/strata-performance-2026-11-07/gpu-mmap-f16-spec4/).
The selected packaged settings loaded at the existing authenticated Tiercel
endpoint `100.96.8.54:8083` at 16:08:49 UTC (88.1-second startup). The Mac mini
successfully read its authenticated model catalog; OpenClaw PID 369 is unchanged.
The user's first real request was observed at 15,388 prompt tokens, about
1,284 tok/s prefill and about 45 tok/s generation while thinking. These are
in-progress observations, not a completed agent-quality evaluation.
The source experiments remain offline. No benchmark is running.

## Reproduce the current packaged candidate

This is the best performance candidate from these screens, not a claim that
agent quality or the intermittent queue-eviction issue is resolved. Use the
same signed v0.2.11 / engine 0.1.57 HIP-Halo package and original UD-Q4_K_XL
model revision. No engine fork is required for these settings.

Keep the generated profile's pack, native GGUF, MTP, vision and credential
fields. In both `args` and `args_written`, remove the pair
`--resident-budget-gib 38`, and set/add:

```text
--expert-cache auto
--prefill 16384
--ple-io mmap
--kv-resident 0
--mmap-experts
--no-prefill-borrow
```

Keep `--max-context 262144`, `--kv int8`, `--spec 4`, `--spec-min-p 0.5`,
`--vision`, and the existing 700 MiB VRAM reserve. Launch with:

```sh
export STRATA_ROUTE_TAIL_SKIP=0
export STRATA_PF_FUSED=1 STRATA_PF_FUSED_KQ=1 STRATA_PF_F16=1
export STRATA_PF_GEMM=1 STRATA_HC_UPMIX=1 STRATA_PA_FAST=1
export STRATA_HIP_WMMA=1 STRATA_SELECT_WMMA=1
export STRATA_PF_SWITCH_MIN_T=4096 STRATA_PREFILL_STREAM_MIN=128
export STRATA_VERIFY_EARLY_PLE_FLAG=1
```

Do not carry `STRATA_GDN_CHUNKED`, `STRATA_PF_F16_BN`, profiling switches,
or `--mtp-q4 all` into this candidate. Verify the loaded metrics show all
24,576 expert slots (73,450 MiB), `kv_resident=0`, and `prefill_cap=16384`.
Automatic sizing can change with host memory use; a smaller actual cache is a
different residency configuration. The sanitized exact configs and environment
changes are under `evidence/strata-performance-2026-11-07/`.

The temporary host-policy experiment is separate: the tests recorded here
used both the original proactive-compaction value 20 and experimental 0.
Zero did not eliminate stalls and is not a permanent tuning recommendation.
Record the host policy and GPU eviction counters with any reproduction.

## Operational state during measurements

The optimized preview is loaded at private `100.96.8.54:8083` for the user
test. Local readiness, authenticated Mac-mini access and initial user traffic
are recorded in the evidence above.
During the comparisons the service ran isolated arms at `127.0.0.1:8084`, using a runtime
drop-in at `$XDG_RUNTIME_DIR/systemd/user/strata-flash-next.service.d/90-benchmark.conf`.
The override was removed for the reboot pause, then recreated for the resumed
comparisons. The benchmark override was removed for the user test. A separate runtime
`90-live-preview.conf` selects the optimized preview on private 8083; the
preview config retains the existing API credential. Boot startup remains disabled. Persistent production configuration is preserved, but it is
the original slow installer layout. Do not enable it blindly on boot; the live
preview is a runtime override pending real-user validation and boot promotion.

No OpenClaw restart, Mac reboot, GPU driver reload or model download was
performed for these comparisons. The source-only operator experiment is
separate from the packaged full-model measurements. Old 27B and Qwen3.6 remain
stopped, disabled and retained.

Local private artifacts: `~/.cache/strata-evaluation-20261107/performance/`.
Files ending in `.private.json` contain the API key and must not be published.

## Upstream references and limits

- [Halo guide](https://github.com/Niko1221/Strata/blob/main/docs/STRIX_HALO.md):
  the historical Q4_K_XL 128K result is 1,211 prefill and **42.64 generation**,
  not 50–60 generation at 128K. Its all-resident setup and older engine differ
  from our initial deployment. The 50–60 goal at long context is additional work.
- [PLE memlock issue](https://github.com/Niko1221/Strata/issues/4671): explains
  the refused lock. Its reported speedup was measured on a discrete NVIDIA GPU;
  it is not an established speedup on this Halo.
- [Release-pinned architecture defaults](https://github.com/Niko1221/Strata/blob/v0.2.11/include/strata/core/arch_defaults.hpp)
  and [engine configuration](https://github.com/Niko1221/Strata/blob/v0.2.11/src/program/generate.cpp).

## Attention selection replay and instruction trace

The [attention experiment record](../experiments/strata-attention-replay/README.md)
contains two completed public 64K captures (24 large layer/chunk records),
gated synthetic-value replay, GPU counters and a successful gfx1151 Advanced
Thread Trace. The published parser checks complete/stable captures; an initial
in-flight parse was discarded. Diagnostics are not new throughput baselines.

Four-query groups have a pooled ideal KV-read sharing factor of 1.59×, ranging
1.37–2.20× across layers/runs. Layer-7 L2 hits measured 20.25%; external L2
read requests are not direct DRAM bandwidth. The fast gated kernel uses 200
VGPRs/thread, 18,432 LDS bytes/block and no scratch spills. The trace localizes
large waits to scale loads and dependent selected-ID/page-table lookups.
Repeated INT8 conversions also contribute substantial instruction work.
Summed wave instruction latency is not GPU wall time or an Amdahl fraction.

Independent off/on/on/off screens preserved output hashes and row padding:
early V staging was noise (−0.04% to +0.51%); plain deferred scales produced
essentially the same ISA; an empty compiler value barrier reduced static vector
wait instructions from 27 to 21 but gave only +0.45% to +1.75% in three replay
records. These small operator changes are not promoted and have no full-model
or state/continuation result. Production attention source was restored; the
restored replay binary exactly matches the saved gated control. The harness
extension alone is retained. The packaged live endpoint was restored at
17:30:07 UTC with authenticated readiness/model checks; no Mac gateway restart.

Next candidate work is physical-row address preprocessing or exact INT8
conversion reduction, with the corresponding page-table/exhaustive-code tests.
Actual attention is about 10% of prefill, so this cannot alone establish the
updated 1,700–2,000 tok/s objective. Generation tuning still follows prefill.


## Prepared physical rows and real-task latency audit

The [prepared-row operator experiment](../experiments/strata-attention-rows/README.md)
retains a measured small gain: 2.47–4.63% across three 4K attention replays,
**3.16% on a full 16K layer-7 chunk**, GPU preprocessing included. Exact
output checks passed across 24 page-table/width/boundary fixtures. At attention's
~10% share, predicted whole-prefill gain is only ~0.3%; this was not measured.
The ~256.4 MiB scratch allocation and production integration are still pending.
No source patch is deployed. The unchanged packaged service was restored at
17:45:26 UTC. Native INT8 conversion is a separate unimplemented candidate.

The user's expanded scope includes latency outside token processing. The
[existing Telegram task audit](STRATA-TURN-LATENCY-2026-11-07.md) partitions
334.025 seconds into generation (210.272), prefill (62.963), tool-result windows
(55.073) and other time (~5.7). Ten model turns and ten tool calls; post-tool
gaps are only 109 ms median / 127 ms maximum. The constant 15,015-token reused
prefix, despite a growing prompt, is a concrete caching lead. Surrounding
turns show ~6.65-second session preparation and ~2.3-second prompt assembly.
Background skill-learning ran after the answer was delivered and must be
accounted separately. The earlier first-13-call aggregate mixes these phases;
it is not a main-task-only latency measurement. All public evidence is stripped
of transcript text, tool arguments/results and user/channel identifiers.
