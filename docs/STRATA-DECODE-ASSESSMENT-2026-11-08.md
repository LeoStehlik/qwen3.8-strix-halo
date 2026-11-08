# Sustained generation: current baseline and the 60–70 tok/s target

Status: normal/profiled/normal comparison complete; persistent serving restored
and authenticated Mac health/model checks passed. All corresponding output hashes
match. No new generation optimization is promoted: sustained 60–70 tok/s remains
unsupported by the tested configuration, and a hardware ceiling is not proved.

The cache fix is independent: it avoids rereading matching history, but does not
make generated tokens faster. See the [cache record](STRATA-CACHE-MISSES-2026-11-08.md).

## Same model, current packaged deployment

Pinned engine SHA `bce2f61ca0f970a1640aafa77925c0908f060243cffcd1ad10e3843b35eed476`,
UD-Q4_K_XL, 262,144 context, INT8 KV, all 24,576 resident experts, MTP window 4,
vision and the promoted tail-role checkpoint. No kernel/model/sampling changes.
All three arms add `STRATA_DECODE_TIMING=1`; only the middle arm adds
`STRATA_VERIFY_PROFILE=1`. Temporary service overrides use authenticated loopback
and restore the persistent endpoint in `finally`.

Public source fixture, about 49K and 197K prompt tokens, OpenClaw sampling preset,
1,024 output allowance per probe. That allowance does not change serving defaults.
The 49K response crosses the frontend thinking budget and has two native decode
segments; sum their native generated tokens and times. API completion counts
include injected tokens and cannot simply replace the native numerator.

| Approximate context | First normal | GPU-profiled | Return normal |
|---|---:|---:|---:|
| 49K | 41.42 tok/s | 33.63 tok/s, stalled | 40.95 tok/s |
| 197K | 39.85 tok/s | 37.62 tok/s | 39.80 tok/s |

The first normal arm spends about 83% of decode time verifying against the
target model and 17% drafting. Host adaptation, commit/emission and other time
are negligible in these logs. All experts are resident; no CPU-expert/PCIe
service or expert swaps are reported. Sampled normal generation intervals have
no GPU queue evictions. This is not a measurement of maximum hardware bandwidth.

## Profiler limitations and useful stage evidence

Source `src/core/verify.cpp` disables shared-expert stream overlap when detailed
profiling is active. The profile is therefore not the ordinary critical path.
The 49K profile also suffered 3,941 ms of native GPU queue eviction inside sampled
generation intervals; its apparent 11.52 ms attention stage in the second native
segment is not credible evidence of an expensive attention kernel. Preserve this
run, but do not optimize from that inflated stage number.

The 197K profile had zero queue eviction inside its sampled generation interval:

| Profiled work | ms/window | Share of 52.48 ms GPU stage total |
|---|---:|---:|
| Routed experts | 17.81 | 33.9% |
| Hyper-connections | 6.27 | 11.9% |
| Sparse attention selection/resolve/attention | 4.95 | 9.4% |
| Output head | 3.12 | 5.9% |
| Shared experts | 2.14 | 4.1% |

Other projections, recurrent work, normalization, routing and combination fill
the remaining 34.6%. Stage timing includes an extra initialization window;
the full records retain both GPU-profile and native-window counts. Telemetry is
sampled every two seconds, so absence of observed eviction inside an interval is
not proof about its omitted boundary samples. Automatic conversation-cache
budgets also differ across launches; report them rather than claiming an exact
measurement of profiler overhead alone. Cache budgets were 6,656 / 7,168 /
7,168 MiB; expert residency remained 24,576 in every arm. Profile throughput
was 18.4% below the mean controls at 49K and 5.5% below at 197K.

## What the target requires

At approximately 40–41 tok/s, 60–70 requires roughly one-third to two-fifths less
time per accepted token. Even hypothetically removing the entire drafting cost
would produce only about 48–50 tok/s on the first normal arm. That is an upper
bound for drafting-only improvements with the same accepted-token sequence,
not a realizable free-draft implementation.

At 197K, verification alone would have to shrink from about 50.15 ms/window to
29.95 ms for 60 tok/s, or 24.23 ms for 70, holding drafting and accepted tokens
fixed. Halving the entire 17.81 ms routed-expert stage would still yield only
about 47 tok/s under optimistic critical-path arithmetic. A small expert-kernel
gain cannot account for the target gap.

Larger MTP windows, cost-aware MTP, draft/confidence choices and the earlier
prepared-weight/activation screens already failed to demonstrate the required
gain. Do not repeat those sweeps or weaken sampling/model quality to improve a
benchmark score. The present evidence does not establish a route to sustained
60–70 tok/s on this model/quant/hardware. It also does not prove a hardware ceiling.
Reaching it would require a substantial verification-kernel improvement, much
better speculative acceptance per unit of work, or both. Those remain separate
research hypotheses with uncertain returns.

The decision for the current deployment is to retain the validated cache fix
and plan around roughly 40–42 tok/s on this fixture, with workload-dependent
variation in live traffic. A positive feasibility case for 60–70 has not emerged,
so a further generation rewrite is not justified by these measurements alone.
The [separate research record](STRATA-KERNEL-RESEARCH.md) preserves the next
questions without presenting them as a scheduled performance gain.

[Curated results, native accounting, stage profiles and telemetry](../evidence/strata-decode-2026-11-08/).
Normal endpoint restored with the same profile and no tracing/profiling overrides;
Mac health and model listing both returned HTTP 200. The Mac gateway was untouched.

## Reproduction

Use the fixture from repository `LeoStehlik/qwen3.6-35b-a3b-strix-halo`, commit
`4c1186a727b8e3b45422266563b6cee089f89679`, path
`benchmarks/fixtures/prompt.txt`. The result records its SHA256 and exact request
hashes. No captured user prompt is required for this test.

```sh
python3 benchmarks/strata-decode-profile.py \
  --profile /private/strata-known-good.json \
  --terminal "$HOME/.local/share/strata/terminal/0.1.57" \
  --fixture /path/to/prompt.txt --out /private/new-decode-run --execute
python3 benchmarks/analyze-strata-decode-profile.py \
  --trial /private/new-decode-run --out /private/new-decode-run/analysis.json
```

`--execute` needs an authorized maintenance window and restarts local serving.
The default preparation path starts nothing. The full private run includes
credentials in private profiles; publish only curated public-fixture metrics,
native timing lines and telemetry.
