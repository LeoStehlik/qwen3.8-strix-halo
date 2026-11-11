# Flash-Next kernel research program — 11 November 2026

Status: active measurement work. No new inference kernel is deployed and no new
speedup is claimed. The packaged 0.1.57 engine and the validated cache settings
remain the deployment baseline. This program replaces further broad flag sweeps
with measured kernel and memory-path work.

## Objective and decision points

Seek 1,700–2,000 tok/s cold prefill and 60–70 tok/s sustained generation on the
existing UD-Q4_K_XL model. These are research targets, not promised outcomes.
A repeatable gain around 5% is worth retaining. Preserve model weights, quant,
262,144-token capacity, tools, state continuation and useful answer quality.

1. Correct the weight, bandwidth and speculative-token accounting.
2. Profile the packaged engine at approximately 49K and 197K context without
   enabling Strata's internal detailed profiler, which changes execution paths.
3. Identify critical-path time, kernel shapes, queue overlap and stalls. Use
   hardware counters only after establishing what they actually count.
4. Write one design brief with a distinct mechanism, expected time budget,
   numerical contract and a bounded experiment. Avoid repeating the losing
   directions in [the earlier research record](STRATA-KERNEL-RESEARCH.md).
5. If the evidence supports it, implement an opt-in operator prototype in an
   isolated source checkout. Compare against a preserved control, including
   preparation, memory and scheduling costs. Advance only a repeatable winner
   to full-model prefill/decode, continuation and tool checks.
6. Publish the method, results and negative findings. Preserve the known-good
   service and restore its endpoint after each measurement run. A research
   result is separate from deployment promotion.

## Accounting correction

The actual four GGUF shards contain 77,017,907,200 bytes of routed expert
payload. Ten selected experts out of 512 across 48 layers account for
**1,504,256,000 bytes**. This independently matches the deployed pack's native
expert index.

Non-expert tensors, excluding the token and per-layer embedding lookup tables,
contain another **4,830,154,240 bytes**. That includes dense projections, shared
experts, routing, hyper-connections and the output head. A selected expert set
plus this non-expert inventory is **6,334,410,240 stored bytes**.

None of these numbers is measured DRAM traffic. Runtime representations can
differ from GGUF; multiple speculative rows may reuse weights and expert IDs;
rejected candidates still cost work; caches can satisfy reads; and recurrent
state, KV/indexer traffic, activations and draft-model work add other traffic.
Embedding tables are sparse lookups, not whole-table reads per evaluation.

Therefore multiplying an assumed 1.7 GB by emitted tokens/s does not establish
that decode uses one third of the memory ceiling. The earlier 212–233 GB/s copy
probe counts **read plus write bytes**, not read-only throughput or inference
DRAM transactions. The previous 25% experts / 24% GDN / 21% hyper-connections /
20% attention breakdown describes a **64K prefill profile**, not decode.
No hardware ceiling or particular amount of remaining headroom is established.

Reproduce the header-only inventory without reading model tensor payloads:

```sh
python3 benchmarks/strata-weight-accounting.py \
  --strata-source /path/to/pinned/Strata \
  --model-dir /path/to/unsloth-UD-Q4_K_XL \
  --pack /path/to/unsloth-ud-q4_k_xl \
  --out /private/weight-accounting.json
```

The output records header and reader hashes, quant block payloads, tensor shapes
and the cross-check against `native_experts.txt`.

## External timeline protocol

Use the unchanged packaged engine and bundled HIP/HSA libraries. The harness
checks their loaded paths and hashes, leaves `STRATA_VERIFY_PROFILE` unset,
and keeps `STRATA_DECODE_TIMING=1` in every arm. The public source-text fixture,
sampling, prompt hashes and 1,024-token probe output allowance match the earlier
generation assessment. The allowance affects only these synthetic requests.

External attachment requires `ROCP_TOOL_ATTACH=1` at process startup. The
packaged registration library supports it, but attachment is not enabled in the
normal deployment. Enable it in every measurement arm, with the packaged
library directory preceding the SDK directory. Attaching does not replace the
engine's HIP or HSA runtime. AMD documents the
[attachment mechanism](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/develop/how-to/using-rocprofv3-process-attachment.html).

The short qualification captured 178,277 kernel dispatches, multiple queues,
and memory copies; attachment and synchronous detachment succeeded. It also
recorded queue evictions and swap-ins. Its long outlier durations must not be
treated as kernel execution costs or a performance baseline.

```sh
python3 benchmarks/strata-decode-profile.py \
  --profile /private/strata-known-good.json \
  --terminal /path/to/terminal/0.1.57 \
  --fixture /path/to/public/prompt.txt \
  --out /private/new-external-run \
  --profile-mode external --sdk /path/to/rocm-sdk \
  --external-sudo --sizes 49152 196608 --max-tokens 1024 --execute
```

`--external-sudo` elevates only the attachment tool when local ptrace policy
requires it. It does not change the machine's ptrace policy. Omit it where
attachment is permitted without elevation. `--arms profile --sizes 1024
--max-tokens 256` selects a short qualification instead of the full comparison.

Compare control → trace → control, preserving exact outputs and native MTP
accounting. Report trace overhead, GPU interval unions, overlapping queue time,
kernel distributions by launch shape, eviction intervals and cache allocation
differences. Sums of overlapping kernel durations are not the critical path.
Streaming first-token timestamps delimit an observable decode window; they do
not identify an exact internal prefill/decode boundary.

Private profiles contain credentials. Publish curated measurements and public
fixture evidence only.

## External trace findings

The full traced arm captured **1,407,740 kernel dispatches**. At 197K context,
the observable window through the first streaming token lasted 153.932 seconds;
GPU kernel intervals covered 152.897 seconds. The subsequent generation window
lasted 26.563 seconds, with 25.222 seconds covered by kernels. At 49K the same
coverage is 98.5% before the first token and 94.1% afterward. This is timestamp
coverage, not an execution-utilization counter: an evicted queue can inflate a
dispatch duration. It nevertheless gives no evidence for a large ordinary
host-dispatch gap to remove.

197K prefill remains distributed across expert matrices, dense projections,
hyper-connections, recurrent work and attention. The largest individual kernel
shape is the Q4_K expert gate/up operation: 20.282 seconds across 2,256 calls.
Q5_1 expert down calls account for 12.624 seconds; prompt attention's main shape
14.414 seconds. Dense matrix families together take 35.218 seconds. The family
classification is heuristic; generic matrix kernels serve several model stages.
The complete table preserves launch shape and original symbol names.

49K prefill has a conspicuous outlier: a rope/normalization shape totals 6.811
seconds but has a 7.680 ms median over 36 calls, alongside 6.563 seconds of native
queue eviction in sampled intervals. Rewriting that kernel based on its raw
total would attack a stall instead of its usual execution cost. 197K generation
also has 875 ms of sampled native queue eviction. Retain those costs in total
latency, but distinguish them from clean operator distributions.

Routed expert matrix kernels total 7.462/7.800 seconds after the first token at
49K/197K. The Q5_1 down kernel alone contributes 2.676/2.842 seconds, roughly
10.8%/10.7% of observable generation wall time. Shape buckets expose the ordinary
40-group-capacity median at 180.3/182.0 microseconds. A capacity of 40 is a launch
bound, not proof of 40 unique active experts; group count and entry multiplicity
are device data. Do not convert launch dimensions directly into memory bytes.

All corresponding control and traced output hashes match at both contexts:

| Context | First control | Traced | Return control |
|---|---:|---:|---:|
| 49K generation | 41.95 tok/s | 41.11 tok/s | 41.86 tok/s |
| 197K generation | 40.74 tok/s | 38.50 tok/s | 40.61 tok/s |

The traced rates are 1.9% and 5.3% below the mean controls; this includes the
different eviction behavior and cache allocations, not just profiler overhead.
49K cold prefill varies from 1,186.9 to 1,238.2 tok/s between controls; both 197K
controls are approximately 1,285 tok/s. These runs include startup/stall effects
and do not replace the earlier best measured cold-prefill figures.

The original
controller was interrupted during loading of the final control, after both
completed arms and the trace had been saved. The original endpoint and profile
were verified restored. Only the missing control is rerun separately under a
transient systemd unit, with the same profiling environment and benchmark.
The original incomplete manifest is retained, not rewritten into a completed run.
The resumed control completed and restored the original profile and endpoint;
the restoration readiness check took 76.2 seconds.

## Selected design brief

Test a narrower row schedule for the **Q5_1 expert down projection**, preserving
the integer dot expression and the exact FP32 addition tree. The 640-input dot
has 40 partial terms mapped onto 32 lanes today. Eight- and sixteen-lane rows
increase the number of independent output rows per block. No larger model,
different quantization, weight expansion or speculative policy change is involved.

This is distinct from the existing `STRATA_EXPERT_V2K` multi-entry weight reuse
path, the prefill prepared-weight experiments and the earlier tile sweeps.
Its cost budget is modest: halving a roughly 10.8% component would yield at most
about 5.7% overall throughput before overlap and replacement costs. A small
operator gain would be insufficient to justify integration. See the
[full contract, isolated code and reproduction](../experiments/strata-decode-q51/README.md).

The standalone prototype passes 31 correctness cases and produces 360 timing
samples, of which three are explicitly flagged for eviction. Eight-lane rows
improve rotating-bank operator throughput by about 11–25% with one entry per
expert, and more when experts handle multiple entries. The counter run shows
roughly unchanged 49.2 MB outgoing L2 reads and four times fewer launched waves
for its 40-group test. It does not measure DRAM saturation.

These results warrant an opt-in full-engine comparison. The packaged engine is
still the deployment baseline. Building and testing the isolated candidate is
ongoing; no whole-model speedup, tool/state validation or promotion is claimed.

[Curated results and native accounting](../evidence/strata-research-2026-11-11/).
