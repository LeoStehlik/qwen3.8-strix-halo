# Recommended stopping point for this optimization session

Subsequent decision: the user authorized the bounded follow-up below. The
[MTP 4/6/8/4 screen](STRATA-MTP-WINDOW-2026-11-07.md) is now complete and retains
window 4. The [expert trace](STRATA-EXPERT-ATT-2026-11-07.md) and
[prepared-activation experiment](STRATA-EXPERT-PREPARED-2026-11-07.md) are also
complete: exact outputs, but no repeatable performance gain. Extra buffer
capacity was sufficient; it did not make this implementation faster. No new
code is deployed. The text below preserves the assessment made before that
follow-up; future-tense proposals below are historical, not pending tasks.

The user asked to step back after roughly seven hours and assess whether
further low-level work or hardware tuning has a credible larger payoff.
**Recommendation: stop the current raw-prefill search at the working baseline.**
The absolute hardware ceiling is unproven. The evidence does show diminishing
returns from local scheduling, tile and configuration changes. The higher
targets remain unmet; this recommendation is not a claim of goal completion.

## What is usable now

The same Qwen3.8-Flash-Next UD-Q4_K_XL, 262,144 context, INT8 KV and packaged
Strata engine remain serving on the private 8083 endpoint. Controlled cold
prefill previously reached about 1,416 tok/s at 64K, 1,350–1,363 at 128K and
1,301 at 192K. The user's approved OpenClaw research task measured 1,330 tok/s
prefill and **47.7 tok/s generation**, with reasoning and tools included.
These are different workloads; do not collapse them into one speed claim.

The boundary-checkpoint option is in a runtime-only live trial. The synthetic
moving-context replay reduced warm continuation latency by 45%; real
OpenClaw reuse and quality after activation are still unverified. It avoids
repeated work and does not raise raw cold-prefill throughput. No real requests
arrived during the latest isolated operator screens. Boot promotion remains
pending, and the service is still disabled at boot.

## What the target requires

At a representative 1,400 tok/s baseline, 65,536 fresh tokens take 46.81 s:

| Target | Processing time | Time that must be removed |
|---|---:|---:|
| 1,700 tok/s | 38.55 s | 8.26 s / 17.6% |
| 2,000 tok/s | 32.77 s | 14.04 s / 30.0% |

The latest small operator gains cannot supply that reduction. The 3–4%
padding result was corrected: padding was already a hardware default in the
baseline. Grouping and fragment-load scheduling yielded no selected gain.

## Final tile screen: both rejected

The [projection profile](STRATA-PROJECTION-PROFILE-2026-11-07.md) motivated
two independent geometries. Both retain group 8, padding, FP16 inputs and
the ascending sequence of WMMA products for each output. The original
control's instruction hash remains unchanged.

| Tile | Threads | K tile | LDS | VGPRs | Scratch / VGPR spills |
|---|---:|---:|---:|---:|---:|
| Control 128×256 | 256 | 64 | 54 KiB | 248 | 0 / 0 |
| Narrow 128×128 | 256 | 64 | 36 KiB | 247 | 0 / 0 |
| Wide 128×512 | 512 | 32 | 50 KiB | 256 | 56 bytes / 17 |

61 rotating/reversed samples per variant, 16,384 input rows, synthetic data
at the model's projection shapes:

| N / K | Control median | Narrow median | Wide median |
|---|---:|---:|---:|
| 10,240 / 2,560 | 19.796 ms | 22.853 ms | 27.725 ms |
| 6,144 / 2,560 | 11.828 ms | 13.682 ms | 17.451 ms |
| 2,560 / 6,144 | 11.276 ms | 13.030 ms | 16.278 ms |

Narrow operator throughput fell **13.4–13.5%**; wide fell **28.6–32.2%**.
All **21 GPU output comparisons** matched bit for bit, including partial
blocks/groups, padding and beta 0/1. Four smaller independent CPU cases
passed the existing 1e-6 tolerance, maximum error 1.34e-7. This is operator
validation, not full-model/state validation. No candidate was deployed.

The narrow variant reduced shared-memory allocation but lost performance;
we did not measure its actual residency. The wide variant spilled registers,
so its loss cannot be attributed solely to its memory-reuse design. A
spill-free rewrite could be investigated later, but no such version has
been built or measured. The user requested reflection before that next trial;
there was no unrolling experiment after this screen.

Reproduce using `experiments/strata-projection-grouping/build.py --tiles`
with the same source/SDK/output arguments as the earlier screen, then
`run.py --rounds 61`, `analyze.py`, and `inspect-code.py`. The new
`tile-kernels.cuh` contains both isolated candidates. Variant IDs 128 and
512 describe their output-column tile width; both use block group 8.
[Measurements and code inspection](../evidence/strata-performance-2026-11-07/projection-tiles/).

## Remaining opportunities, with limits

**Expert execution is the strongest remaining raw-prefill research target.**
It accounts for roughly 24.9% of the measured GPU timeline. Gate/up supplies
about 62% of expert cost. A substantial rewrite could change weight decoding,
operand layout and pipelining together, instead of adjusting its epilogue or
launch schedule. We have not demonstrated that such a rewrite can outperform
the existing kernel. A 1.5× expert speedup would imply about **9.1% overall**;
even 2× would imply **14.2% overall**, using that profile and assuming other
work unchanged. The needed gain would still require additional contributions.
An instruction-level trace of the dominant expert kernel is a prerequisite
to choosing that rewrite. Earlier gate/up instruction counters were unreliable;
the successful ATT work offers a way to investigate it later.

**Projection memory reuse / synchronization is a second research path.**
The latest profile provides concrete constraints, but the two straightforward
tile variants failed. Eliminating the wide variant's spills or changing its
shared-memory pipeline is substantive kernel work with uncertain payoff.
Higher occupancy alone is not a success criterion, and removing barriers
without proving dependencies is not an optimization.

**Sparse-attention reuse has a smaller whole-model ceiling.** Actual attention
was about 10% of the full prefill timeline. Reusing selected KV data across
queries could justify a different kernel, but the measured ideal four-query
sharing is only 1.59× and is not an expected speedup. Even halving the entire
attention phase would improve total prefill by about 5.3%. The retained
prepared-row experiment alone estimates only about 0.3% overall.

**No hardware setting has demonstrated a substantial safe gain.** Automatic
clocks remain selected. Factory `high` gave one inconclusive ~1.5% result;
`profile_peak` was slower. Compaction changes did not resolve GPU queue
evictions. Power, firmware or memory overclocking is not a demonstrated path
to the target, and none was applied. Memory-stall attribution could improve
consistency and cold-start latency, but does not establish higher steady
throughput than the existing best runs.

## Better follow-up value for actual OpenClaw use

The approved task spent **210.3 s generating**, **63.0 s in prefill** and
55.1 s waiting for tools. A 20% generation speedup would save about 35.0 s
on that fixed workload; a 20% prefill speedup would save about 10.5 s. Those
are arithmetic estimates, not measured new results.

MTP depth 4/6/8 has not been compared; only depth 4 has run. A later bounded
generation experiment can examine accepted tokens per verification window
and verification cost, preserving user sampling and quality. It may offer a
better return than another small raw-prefill kernel adjustment. First validate
the existing checkpoint trial with normal user requests. Neither workstream
should be represented as achieving the cold-prefill target.

## Proposed next session: an additional 100–200 prefill / 10–20 generation

The user subsequently asked where those smaller increments might come from.
These are research targets, not predicted gains:

1. **Generation: compare MTP depths 4, 6 and 8 before more kernel work.**
   Keep the model, quantization, context and sampling fixed. Measure emitted
   tokens per total draft-plus-verification second at representative contexts,
   including acceptance and rejected work. The earlier instrumented profile
   spent 84.8% in verification and 15.2% drafting; simply making the drafter
   faster cannot supply a 20–42% total improvement. Larger windows must amortize
   verification sufficiently to offset their extra cost. Adaptive depth is a
   possible later implementation only if the fixed-depth sweep exposes a
   repeatable regime. Existing adaptive behavior must be inspected first.
   At the observed live 47.7 tok/s, +10 and +20 require 21% and 42% improvement.
   Neither has been demonstrated; +20 is an ambitious target.
2. **Prefill: obtain an expert instruction trace, then decide on one rewrite.**
   At the measured 24.9% share, +100 tok/s from a 1,400 baseline requires
   about 1.37× faster complete expert execution; +200 requires about 2×.
   Candidate mechanisms are better overlap of quantized-weight fetch/decode
   with matrix work, or an operand layout that reduces intermediate movement
   and synchronization. Which applies is unresolved until the trace localizes
   stalls. Gate/up alone is roughly 15% of prefill, so a win confined to that
   kernel has a smaller payoff. Replay actual routing distributions, then
   require full-model cold-prefill and continuation checks before promotion.

Prioritize the bounded MTP comparison for effort versus possible value, despite
prefill remaining the primary objective. For prefill, stop after the expert
trace if it does not reveal avoidable work large enough to justify a rewrite.
Do not restart a broad tile/flag sweep. Hardware clocks and the smaller
attention/epilogue candidates do not currently support these increments.

At this checkpoint there is no benchmark still running, no new kernel in
serving, and no Mac gateway restart. The latest source worktree is clean;
experimental code is archived in this repository. The goal remains active
while next steps are discussed; no further benchmark has been started.
