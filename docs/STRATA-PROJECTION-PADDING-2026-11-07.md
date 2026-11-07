# Projection row padding: 3–4% ablation of an existing default

**Correction, 7 November:** the original report misclassified padding as
an undeployed optimization and serving as padding-off. Strata's
`apply_arch_defaults` sets `STRATA_PF_PAD=1` internally on gfx1151 when the
caller supplies no override. The serving startup log explicitly lists
`PF_PAD` among the defaults it applied, as do earlier baseline/profile logs.
Padding was already part of the ~1,400 tok/s baseline. The measurements below
remain valid comparisons of explicit 0/1/0, but do not show a new improvement
over serving. No new padding deployment or further promotion test is needed.

The packaged `STRATA_PF_PAD=1` option improved the **second uncached 64K
request** to **1,394.9 tok/s**, versus controls at **1,329.2 and 1,351.5**.
That is a **4.08% throughput gain versus the two controls combined**, or
**3.21% versus the return control**, saving 1.92 or 1.51 seconds respectively.
Retain this as a measurement of an existing default; one enabled arm does not establish a
repeatable gain. First-64K results were inconsistent, with GPU queue evictions.
The enabled arm also does not exceed earlier 1,416–1,418 tok/s screens: this
is a within-screen comparison with slower controls, not a new absolute record.

The serving configuration was restored at **19:55:46 UTC**, with padding
unset in the launch environment and **enabled internally by the hardware
default**, boundary checkpoints still enabled and short-read 64 / stream
minimum 128. A subsequent health request from the Mac using its existing
provider credentials succeeded. No OpenClaw gateway restart or agent request.

## What changed and what was measured

Pinned source `prefill.cpp::pf_pad` and `Gemm::native` describe this existing
option: add 64 half values to supported projection activation/weight row
strides to avoid memory-channel conflicts. The K=6144 GDN and attention
output projections are explicit targets; supported dequantized weights can
also receive padded strides. Logical dimensions and quantization stay the
same. The source's historical performance claims are not our measurements.

This screen used the installed **Strata 0.2.11 / HIP-Halo 0.1.57** package,
Unsloth UD-Q4_K_XL, all 24,576 experts resident, 262,144 context, INT8 KV,
16,384 prefill capacity, MTP depth 4 and the existing fast-kernel flags.
No source patch, tracing or timing instrumentation was enabled. The native
process environment confirmed padding **0 / 1 / 0**, retaining boundary
checkpoint 1 and 64/128 in every arm. GPU clock policy stayed automatic.

Each arm started a fresh engine, ran the common 151-token warm-up, then two
different cold 64K prompts. Therefore “first” below means the first **64K**
request after that small warm-up, not the very first inference after loading.
Both 64K requests reused **zero tokens**. The second request follows a full
large-input allocation/workload pass, but is still a cold prompt.

The public fixture, request bodies/nonces and sampling were identical across
arms at each position. Sampling was greedy with presence penalty zero and
128 output tokens **for these probes only**. No production context or output
limit changed. Every stream completed. Prompt/output hashes matched at all
three positions across the arms, including the warm-up, and measured draft
accepted/offered counts matched too. This is a short output/state consistency
check, not comprehensive tool-use or model-quality validation.

## Results

| Measurement | Padding off, first | Padding on | Padding off, return |
|---|---:|---:|---:|
| First 64K prefill, tok/s | 1,220.7 | 1,271.6 | 1,352.7 |
| First 64K prefill, seconds | 53.696 | 51.548 | 48.460 |
| Second 64K prefill, tok/s | 1,329.2 | 1,394.9 | 1,351.5 |
| Second 64K prefill, seconds | 49.316 | 46.990 | 48.499 |
| First 64K sampled main-process eviction increase, ms | 5,813 | 4,380 | 0 |
| Second 64K sampled main-process eviction increase, ms | 933 | 5 | 0 |

Actual sizes were 65,549 and 65,548 tokens, identical across arms for each
position. The first-64K enabled arm's throughput was **0.91% below the combined
control rate**, so there is no consistent first-request benefit established here.
The small warm-up itself took 1.694 / 0.687 / 5.208 seconds of prefill: stalls
also moved between startup phases. Do not silently omit them from cold-start
or end-to-end claims.

The second enabled request was faster than both controls. Its median sampled
clock was 2,579 MHz versus 2,612 / 2,600 for the controls; higher clocks do not
explain the result. The cleaner return control had no observed reading-counter
increase and the same automatic conversation-cache budget as the enabled arm
(7,168 MiB; first control 6,656 MiB). Comparing that control still gives 3.21%.
This supports the existing default, but does not isolate the projection
kernel as the cause: internal dispatch/phase timings were **not traced**.

Eviction figures are max-minus-min per-process counters over sampled API
`reading` intervals, at one-second resolution. They are not independent wall
durations, and cannot simply be subtracted to calculate a “corrected” rate.
VM compaction, migration and reclaim counters are included in the evidence.
Generation was 39.8–40.6 tok/s for the short fixed-length outputs. This screen
does not establish sustained representative generation performance.

## Why the original interpretation was wrong

The collector read `/proc/PID/environ`, which describes the inherited
environment and does not reliably expose later `setenv` allocations. It
reported `<unset>` for padding in serving; that did not establish effective
padding-off. Source `src/core/arch_defaults.cpp` supplies `PF_PAD=1`, honors
explicit overrides, and prints each default it actually adds. The caller in
`src/program/generate.cpp` runs before the engine first reads its switches.
The existing startup logs supply runtime corroboration. Explicit 0/1/0 arm
settings were respected; only their relationship to serving was misreported.

The [default audit](../evidence/strata-performance-2026-11-07/default-audit/audit.json)
preserves source hashes, selected launch flags and content-free startup lines.
The driver now labels inherited values and separately records the applied
defaults and padding interpretation. Original raw evidence/checksums are
unchanged. The proposed phase/128K/continuation promotion ladder is cancelled:
it would retest an optimization already in the baseline. The current
1,700–2,000 prefill and 50–70 generation targets remain unachieved.

## Reproduction and evidence

The [driver](../benchmarks/strata-padding.py) inherits the existing optimized
runtime override, adds a temporary `91-padding-screen.conf`, and redirects
the backend to loopback 8084 for isolated runs. It preserves the original
override byte for byte and restores the endpoint in `finally`. A live model
loader is polled rather than restarted because a wait has elapsed. The
private API profile is copied with mode 600; credentials are excluded from
published metadata. Allow for three model loads and the final restoration.

```sh
python3 benchmarks/strata-padding.py \
  --profile /path/to/private-strata-profile.json \
  --fixture /path/to/public-prompt.txt \
  --out /tmp/strata-padding-screen \
  --live-url http://100.96.8.54:8083
```

Use a new output directory, the existing optimized user service, and the
same public fixture pinned in the [clock-policy report](STRATA-CLOCK-POLICY-2026-11-07.md).
The [evidence](../evidence/strata-performance-2026-11-07/projection-padding/)
contains redacted profiles, actual process flags, exact commands, full public
logs, API results, telemetry, comparison calculations and restoration health.
Private profiles and live conversation logs are excluded.
