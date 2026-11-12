# Handoff for Francis — Flash-Next performance envelope, 2026-11-12

Repository: [Qwen3.8 inference on Strix Halo](https://github.com/LeoStehlik/qwen3.8-strix-halo),
renamed from the earlier 27B/DFlash2-specific name on 7 November. `main` is the
canonical branch for deployment, experiments, evidence and this handoff. Completed
topic branches were consolidated into `main` and retired on 8 November.

## Completed performance-envelope study — November 12

The [new findings](docs/STRATA-PERFORMANCE-ENVELOPE-2026-11-12.md) establish
measured calibration and model-work accounting. Read bandwidth repeated at
242 GB/s, mixed traffic at 209–211 GB/s and register-only FP16 WMMA at 57 TFLOP/s.
The large native Q8 decode operators already achieve approximately 224–248 GB/s
of logical payload throughput. These are not physical DRAM counters.

At 197K, actual routing averages about 22 distinct experts per layer and
3.06 candidate rows per window. Dense plus distinct expert payload is about
8 GB/window; the normal control emits 2.398 accepted tokens/window. The former
“1.7 GB/token, one third of bandwidth” argument is withdrawn. Matrix work in
prefill is also about 12 GFLOP/token before non-matrix costs, rather than the
earlier active-parameter-only estimate.

The conditional weight-streaming scenarios leave little room for 60–70 tok/s
with unchanged serial drafting and acceptance. Better reuse/work per accepted
token must be part of that design. Prefill 1,700–2,000 is not excluded by matrix
capacity, but needs gains across several stages; representative dense matrices
already achieve 40–43 TFLOP/s. Do not quote either target as an achievable result.

The report supplies bounded next designs for expert gate/up operand reuse and
the draft/verify schedule. Existing losing config/layout trials remain closed.
The earlier Q5_1 patch remains optional, unpromoted research.

Both context probes match the prior input/output hashes. Reporting adds
diagnostic work, so its throughput is not a replacement baseline. Exclusive
calibration/operator runs restored the original service; the known-good profile
and packaged executable remain in place. No OpenClaw routing was changed and
no measurement job remains active from this study. Source, raw measurements,
counter limitations and [reproduction instructions](experiments/strata-envelope/README.md)
are published on `main`.

## Completed research pass — November 11

The [research program](docs/STRATA-RESEARCH-PROGRAM-2026-11-11.md) now has an
external timeline of the packaged engine with normal fusion and stream overlap
preserved. Control generation is **41.95/41.86 tok/s at 49K** and
**40.74/40.61 at 197K**, with all corresponding output hashes matching the traced
arm. The weight inventory also corrects the earlier bandwidth argument: routed
experts alone are about 1.5 GB per selected set, but substantial dense weights,
speculative reuse and other traffic prevent a "one third of the memory wall"
conclusion. No hardware ceiling has been established.

The [Q5_1 down-projection prototype](experiments/strata-decode-q51/README.md)
preserves exact outputs while assigning eight lanes to a row instead of 32.
Standalone rotating-bank gains are 11–25% for one entry per expert, larger for
multiple entries. They are operator results, not an overall speedup. Counter
evidence shows four times fewer waves and essentially unchanged outgoing L2
read volume. Both isolated correctness and the integrated Strata parity suite
pass. The full control/candidate/control comparison is complete:

| Context | Control | Candidate | Return control | Gain vs mean controls |
|---|---:|---:|---:|---:|
| 49K generation, tok/s | 41.88 | 42.70 | 41.85 | +2.00% |
| 197K generation, tok/s | 40.70 | 41.38 | 40.65 | +1.73% |

All corresponding input/output hashes match the packaged baseline, including
warm-up. Native work counts also match at 197K; at 49K the candidate accepts one
extra draft and uses one fewer window, with identical output. Each arm passes
exact tool arguments, tool-result continuation and interleaved checkpoint
restoration; reused prefixes advance from 11,614 to 11,782 tokens. These are
synthetic API checks, not a new live OpenClaw quality evaluation.

No prefill gain is demonstrated. The 49K candidate/return control give
1,368.9/1,371.4 tok/s; 197K arms range from 1,280.0 to 1,289.2. The slow first 49K
control must not be counted as a gain. **No new source kernel is promoted:**
1.7–2.0% is below the program's approximately 5% threshold. The optional patch,
build instructions and [complete evidence](evidence/strata-research-2026-11-11/q51-engine-trial/)
are retained for separate research. The larger throughput targets remain unmet.

The normal persistent profile remains the packaged baseline. Final restoration
took 77.0 seconds; independent verification confirms the packaged executable,
unchanged profile, absent experiment flags/temporary override, loaded model and
idle queue at the normal endpoint. **No further benchmark or deployment change
is pending from this research pass.** The earlier profiling controller
was interrupted while loading its final control; restoration was verified and
only the missing control was rerun. Raw and curated evidence preserve that fact.
Do not infer completed validation from a process merely starting.

The remaining November 8 material below is historical context for the baseline.

## Latest incident — compact tool calls, November 8

The `no-slop-ui` lookup failure is an undeclared-tool/interface error, not a timeout
or cache regression. Qwen called hidden `skills_search`/`skills_read` directly
instead of the declared `tool_call` wrapper; its reader argument was also wrong
(`skillName` instead of `name`). Strata rejected the undeclared names; OpenClaw's
generic empty-answer retry repeated the failure. The symptom predates the cache
fix. Thirty-six offline parser checks reproduce it. The investigation made no
changes to the inference backend.
[Investigation and targeted remedies](docs/OPENCLAW-TOOL-SURFACE-FAILURE-2026-11-08.md).

**Upstream already fixed these paths:**
[#184133](https://github.com/openclaw/openclaw/pull/184133) makes skill guidance
dispatcher-aware; [#183165](https://github.com/openclaw/openclaw/pull/183165)
includes deferred names in bounded native correction. Both changes are present
in `v2026.11.5-beta.1` source and the main revision examined, but missing from the
incident's 2026.10.9 version and checked stable `v2026.11.1`. No duplicate PR was
made. Validate model/tool recovery on a build containing both fixes before
considering another workaround; parser tests alone do not prove model recovery.

## Current state — November 8

**Objective and result:** avoidable cache misses are fixed; the generation
feasibility assessment found no demonstrated path to sustained 60–70 tok/s in
the tested configuration. The user switched Francis off the local model for
maintenance and profiling; this comparison is now finished and serving restored. Do not send
synthetic OpenClaw turns, restart the Mac gateway, or reboot either machine.

**Cache fix promoted:** `--tail-role-token 846` in the persistent profile, in
addition to `STRATA_CACHE_MESSAGE_BOUNDARY=1`. It preserves the checkpoint before
OpenClaw's changing final user-role runtime carrier, including carriers longer
than 1,024 tokens. The exact tokenizer and start-position effort template matter.
[Full diagnosis, controls and limits](docs/STRATA-CACHE-MISSES-2026-11-08.md).

- Public control/candidate/control: 28–42% shorter follow-ups; all 18 canaries and
  corresponding output hashes match. Exact tool arguments/result continuation
  and interleaved state restoration pass.
- Captured Discord request replay: reuse advances to 105,745 then 107,781 tokens,
  instead of staying at 97,678. Fresh input falls 72–84%. These eight-token probes
  execute no real tools and establish no answer-quality/decode-speed claim.
- Authorized instruction edits and different background prompts legitimately
  invalidate prefixes. Preserve them. The older 230K session's exact miss cause
  remains unproven because its complete wire prompts were not captured.
- The user-reported 10:55/11:00 local Discord timeouts were connection refusals
  during our maintenance, not a demonstrated model generation hang.

**Persistent deployment:** enabled systemd user unit, Linger=yes, pinned packaged
engine, `Restart=always`, readiness check, no experiment override in steady state.
Private profile: `~/.local/share/strata/flash-next/strata-known-good.json`.
Normal restart 87.3 s and forced-process recovery 96.3 s passed on November 7.
[Evidence](evidence/strata-performance-2026-11-07/deployment-completion/).
Host reboot validation remains unperformed. Local profiling temporarily redirects
serving to loopback and restores the persistent profile in `finally`.

Model/quant, 262,144 context, INT8 KV, vision, MTP window 4, all 24,576 resident
experts, short-read 64 and stream minimum 128 remain unchanged. No source kernel
is deployed. The updated profile/service helpers reproduce the cache setting.

**Generation assessment complete:** normal/profiled/normal at 49K and 197K.
Normal results: **41.42/40.95** and **39.85/39.80 tok/s**, respectively; all
corresponding output hashes match. Roughly 83% of time is target verification.
The clean 197K GPU profile attributes 33.9% of GPU time to routed experts;
halving that entire stage would still be insufficient for 60 tok/s. The 49K
profile suffered queue evictions and must not drive an attention rewrite.
Detailed profiling also disables shared-expert overlap. Full
[assessment and limits](docs/STRATA-DECODE-ASSESSMENT-2026-11-08.md).

No further generation change is promoted. A positive 60–70 feasibility case has
not emerged, but no hardware ceiling is proved. The persistent profile and unit
are restored without profiling overrides; authenticated Mac health/model checks
pass. Francis can return to this provider when the user chooses. Live post-fix
OpenClaw quality and host reboot validation remain user-time checks, not claims
made by the offline probes. The [compact-weight findings](docs/STRATA-EXPERT-COMPACT-WEIGHTS-2026-11-07.md)
and [kernel research](docs/STRATA-KERNEL-RESEARCH.md) remain separate. Do not repeat
the losing sweeps or start a rewrite without a distinct measured mechanism.

## November 7 experiment history

The following restoration times and trial statuses are historical. The current
persistent state and November 8 objective above supersede them.

**The user authorized the bounded follow-up proposed at the stopping checkpoint.**
Latest: the [prepared FP16 weight prototype](docs/STRATA-EXPERT-PREPARED-WEIGHTS-2026-11-07.md)
preserves all ten reference hashes and all eight timing-run hashes, but loses
even when expansion is excluded. Captured routing: complete operator about
58 ms control, 105 ms prepared gate/up, 63 ms prepared down. A deliberately
favorable 16-expert/high-reuse case also loses, about 53 vs 55 ms. Reject this
direct FP16 loader; no selective-cache manager, combined performance screen,
or full-model integration was justified. All ten original kernel instruction
sequences remain identical. Serving stayed loaded and idle throughout.

The subsequent [cost-aware MTP screen](docs/STRATA-MTP-COST-2026-11-07.md)
also found no reliable gain: off/on/off gave 41.42/39.86/41.31 tok/s at 16K
and 41.35/40.77/38.95 at 64K. The latter is inconclusive within control drift;
do not compare only against the slower return control. All 16K hashes match;
the enabled 64K output differs from both matching controls. No quality claim
or promotion follows. The original runtime override was restored byte for
byte at **21:59:11 UTC**, with cost-aware mode unset and serving idle/loaded.

The [prepared-weight capacity analysis](docs/STRATA-EXPERT-WEIGHT-CAPACITY-2026-11-07.md)
narrows the spare-RAM idea: full FP16 expert copies would add 225 GiB if the
original quantized copies remain for decode. An 8 GiB selective cache, ranked
on the first full chunk, covers 23.2% of routed rows in the next three chunks;
16 GiB covers 34.5%. This is one repeated-source fixture, not a measured time
saving or a safe live allocation recommendation. The later direct FP16 kernel
screen above failed; no cache manager has been built. The later compact representation has a small warm operator win but loses with
preparation included; see the current finding above. No cache integration follows. Spare capacity alone has not delivered speed.

The [MTP 4/6/8/4 comparison](docs/STRATA-MTP-WINDOW-2026-11-07.md) found no
reliable generation improvement. Window 4 and the original runtime override
were restored at 21:16:19 UTC; serving is loaded. The subsequent
[expert ATT/source mapping](docs/STRATA-EXPERT-ATT-2026-11-07.md) identified
repeated activation conversion, prompting a
[prepared-activation prototype](docs/STRATA-EXPERT-PREPARED-2026-11-07.md).
Ten reference runs preserved exact intermediate/output hashes, and all ten
original compiled kernels remained identical after isolating the candidate.
With actual captured routing and preparation cost included, gate/up input
preparation changed operator throughput by +1.21% then −0.83%; down input
preparation by −0.59% then +0.11%. Neither is repeatable. Extra memory fits
(80/200 MiB independently), but this implementation is rejected; no combined
performance run or full-model integration was justified. Serving stayed loaded
and idle, with zero actual requests during these operator runs.

The bounded MTP/trace/one-rewrite follow-up is complete. Retain window 4 and
the packaged baseline. The goal remains active; the higher targets—1,700–2,000
tok/s prefill and 50–70 tok/s generation—remain unmet, and the hardware ceiling
remains unproven. Do not repeat these losing screens or silently promote the
small earlier operator candidates. Further kernel work needs a different
mechanism and a new bounded experiment; no 100–200 / 10–20 tok/s gain emerged.

**Historical trial state, restored November 7 at 21:59:11 UTC:** the packaged optimized endpoint has
`STRATA_CACHE_MESSAGE_BOUNDARY=1` for a [limited live trial](docs/STRATA-CACHE-LIVE-TRIAL-2026-11-07.md).
Short-read remains 64 and stream minimum 128; no experimental source kernel
or tracing is serving. Health and actual-process flags were verified, and the
Mac's configured provider passed a read-only health check. Real OpenClaw reuse
and quality validation are pending. This is runtime-only; boot promotion is
still pending. Do not confuse it with the undeployed 8/32 candidate below.

The [projection-padding off/on/off screen](docs/STRATA-PROJECTION-PADDING-2026-11-07.md)
was initially misclassified as a new candidate. **Correction: `STRATA_PF_PAD=1`
is already applied internally by the packaged gfx1151 defaults.** Second cold 64K
requests measured 1,329 / 1,395 / 1,352 tok/s: +4.08% throughput against the
combined controls, +3.21% against the return control, with matching outputs
and draft counts. First 64K results were inconsistent and included GPU queue
evictions. Only one enabled arm ran; internal projection dispatch was not
traced. This measures an existing optimization against explicit disabling,
not headroom above the current baseline; skip its proposed promotion tests.
Padding is **on through the hardware default in serving**. The inherited
`/proc/PID/environ` snapshot does not include defaults added by the engine's
`setenv` calls. The startup log and source default table resolve that ambiguity.
The same original runtime override was restored
byte for byte, and read-only health from the Mac passed. No gateway restart.

The subsequent [projection block-grouping screen](experiments/strata-projection-grouping/README.md)
changed only launch ordering in an isolated copy of the existing padded BK64
kernel. Groups 1/2/4/8/16/32/64 at three 16K-row matrix shapes yielded best
operator medians only 0.2–1.2% above group 8; several alternatives were much
slower. Set this path aside; no selector or throughput gain is promoted.
All 49 GPU comparisons matched the control bit for bit, including partial
blocks/groups and beta 1. Four smaller CPU-reference cases passed 1e-6
absolute tolerance (max 1.34e-7); the initial mistaken exact-CPU check failed
on the unchanged control and is retained in evidence. Serving stayed loaded
and idle with the same PID and zero requests. No source worktree or serving
binary changes. Before changing projection tiles, measure the current kernel's
resource limits; block order alone did not reveal significant headroom.

That [projection resource profile](docs/STRATA-PROJECTION-PROFILE-2026-11-07.md)
is now complete: 248 VGPRs, 54 KiB LDS, no spills, and four resident waves
on the sampled SIMD in two traces. LDS waits, matrix instructions and
barriers dominate summed instruction latency; those shares are not wall
time. L2 external traffic is not DRAM bandwidth. One of 45 counter records
returned zeros and was excluded explicitly; a five-dispatch repeat worked
but showed lower read traffic at similar duration, so a simple bandwidth-only
diagnosis is unsupported. The fragment-load scheduling candidate was neutral
(−0.05/+0.20/+0.21% operator medians), preserved all 14 GPU comparisons and
left resources unchanged. Reject it; code/evidence archived, nothing serving.
The subsequent independent tile screen rejected both candidates: narrow
128×128/K64 was 13.4–13.5% slower; wide 128×512/K32 was 28.6–32.2% slower.
All 21 GPU comparisons matched exactly. Narrow lowered LDS from 54 to 36 KiB
without a performance gain; wide incurred 17 VGPR spills and 56 scratch bytes.
The control's instructions were unchanged. These are isolated operator results,
not model-level measurements. No spill-free wide rewrite or further unrolling
experiment was started. Code, resource inspection and 61-sample distributions
are in the [checkpoint](docs/STRATA-OPTIMIZATION-CHECKPOINT-2026-11-07.md).

The earlier [factory clock-policy screen](docs/STRATA-CLOCK-POLICY-2026-11-07.md)
kept this endpoint/configuration running. Cold 64K `auto / high / auto /
profile_peak / auto` measured **1,398 / 1,417 / 1,394 / 1,275 / 1,396 tok/s**.
High's single-arm +1.48% is inconclusive amid uneven memory stalls; peak lost
8.58%. Neither is selected. **Automatic clocks restored, endpoint loaded and
idle at 19:21:03 UTC.** Boundary checkpoint remains on, 64/128 unchanged;
no real OpenClaw request arrived during this screen. No restart or persistent
clock change. The new raw-throughput targets remain unmet.

The user reviewed Francis's real GitHub beta-release/co-authored-PR investigation
and was pleased with the result. The first 13 completed backend calls (greeting and initial background work
included) averaged
**1,327 tok/s prefill / 47.2 generation**, excluding reused prompt tokens.
This validates that task by the user's assessment; broader quality is not proven.
The measured packaged configuration remains the baseline and serves private
8083. No losing kernel experiment or partial tuning table is deployed.
The thinking-enabled synthetic probe was interrupted for that live test;
spec-6/spec-8 were not run at that time; the later comparison linked above now
covers them. The [expert profile and routing replay](experiments/strata-expert-profile/README.md)
now separate the expert cost: gate/up about 62%, down about 37%, grouping
negligible. All 192 full layer/chunk routing records from a public 64K probe
were captured. Three real-routing replays were only 1–3% slower than uniform
routing, with row ownership/reference checks passing. No register spills
were reported. Expert hardware counters returned unexplained zeros despite
a successful copy-counter control; bandwidth/occupancy classification remains
unresolved. Separate per-kernel memory collection now works; the combined
filter still gives zeros and gate/up instruction counters remain unusable.
The [cooperative gate/up epilogue](experiments/strata-cooperative-epilogue/README.md)
passed exact intermediate/output checks and improved captured-routing
operator times by 2.4–2.5%, only about 0.6% estimated whole-prefill gain.
It is retained as an undeployed opt-in candidate, without full-model/state
validation. A four-stage loop unroll lost and was removed. Broader dense
tuning retained the existing library solutions. No production source patch
is deployed. The [attention-selection replay and instruction trace](experiments/strata-attention-replay/README.md)
are now complete. Two public 64K captures cover every QSA layer; gated replay
matches the production kernel's output format. Four-query ideal KV-read sharing
averages 1.59×. A later-layer replay showed 20.25% L2 hits; external L2 requests
are not direct DRAM bandwidth. Advanced Thread Trace worked on gfx1151 and
identified scale-load and ID/page-table waits plus repeated INT8 conversions.
Early V staging was noise; deferred scale conversion with a compiler barrier
gave only 0.5–1.8% operator gain and remains shelved without full-model evidence.
The user wants repeatable small gains retained and accumulated. The new
[prepared physical-row candidate](experiments/strata-attention-rows/README.md)
gives **3.16% net operator speedup on a full 16K chunk**, preprocessing included,
and 2.47–4.63% on three 4K replays. All output hashes match; 24 page/boundary
cases passed. It is retained **undeployed**: ~256.4 MiB scratch, no production
allocation/integration or full-model/state validation yet. Estimated overall
gain is ~0.3%, not a measured throughput result. Source commit `41021fb` is
local only; its patch and evidence are in this repo. The subsequent
[native INT8 conversion screen](experiments/strata-attention-native-i8/README.md)
passed 1,048,576 exact conversion checks per variant and preserved all replay
outputs, but the assembly form was neutral (−0.34%) and the vector form slower
(−2.92%) on a captured 4K later-layer replay. Neither is selected. All 28 old
attention kernels retained identical instructions. The patch is archived;
active source and control binaries were restored exactly at 19:36:29 UTC.
No full-model native-conversion test or serving change occurred.

The user also added end-to-end latency investigation. The
[real Telegram task audit](docs/STRATA-TURN-LATENCY-2026-11-07.md) reconciles
334.025 seconds: 210.272 generation, 62.963 prefill, 55.073 tool-result waits,
about 5.7 elsewhere. Ten model turns / ten tool calls; post-tool gaps only
109 ms median. Cache reuse stayed at **15,015 tokens** while the reread tail
grew; next diagnose exact payload/token/checkpoint differences. Surrounding
turns spent **~6.65 s in session setup** and ~2.3 s in prompt assembly. The
later skill-learning notification was not delayed answer delivery. No Mac
configuration was changed and no new agent task was launched for this audit.

The [boundary-checkpoint follow-up](docs/STRATA-CACHE-BOUNDARY-2026-11-07.md)
confirmed that OpenClaw's installed message helper moves transient runtime
context behind tool history. An isolated packaged-engine off/on/off replay of
that pattern tested existing `STRATA_CACHE_MESSAGE_BOUNDARY=1`: **45% shorter
warm continuation latency, 74% fewer reread tokens**, all eight output hashes
identical across the three arms. All moving-context canaries passed. The fixed
case already cached efficiently; three follow-ups emitted identical unwanted
lookup text in every arm and count only as output/cache parity. Cold timings
varied (control 19.8/24.3 s, enabled 25.9 s), so it was initially kept off for
the follow-up trace below. It is now in a live trial, not a persistent default.
The subsequent traced off/on/off comparison passed all 12 moving-context
canaries, with identical outputs. Both 43- and 267-token tails benefited:
first-continuation latency fell about 32% and 36%, respectively. Multi-second
cold variability coincided with GPU queue evictions before the extra checkpoint
was reached; checkpoint copies themselves took 24–41 ms. A 43-token window
read took 516 ms, almost the same as 267 tokens batched (533 ms). The subsequent
[64/8/64 cutoff comparison](docs/STRATA-SHORT-READ-2026-11-07.md) rejected 8:
the short continuation took 4.180 s versus 3.522/3.520 s at 64, with its
43-token segment rising from ~514 to 1,201 ms. All 12 value canaries passed;
one cold response changed only JSON whitespace, so raw hashes were not all
identical. The [128/32/128 threshold comparison](docs/STRATA-SMALL-BATCH-2026-11-07.md)
then held short-read 8 fixed: the 43-token segment fell from ~1,191 to 270 ms,
and continuation time from ~4.22 to 3.33 s. All 12 canaries and output hashes
matched; the larger-tail case was essentially unchanged. That is about 5.5%
below the earlier 64/128 winner, a preliminary cross-experiment comparison.
Retain 8/32 **undeployed** pending direct comparison with 64/128, substantial
cold prefill and longer generation checks. Draft acceptance varied even
between controls; do not claim unchanged generation performance.
The checkpoint flag alone is now on for actual-traffic evaluation using 64/128.
This is avoided work, not higher raw prefill throughput.
The original user payload was not fully captured, so the historical task's
exact cache miss remains unproven. Source/model throughput targets remain active.

The tool-sequence audit also identified a failed GitHub CLI authentication
attempt, 16 independent comparison requests issued serially, and repeated
fetches that added missing status/full-body checks. A polling model turn used
11.058 seconds of GPU time while the command kept running; do not count that
as an equal removable wall delay. No tool/prompt/authentication policy changed.

Fresh packaged 64K screens: control **1,389.1 tok/s**, HC exact **1,217.2**,
HC fused **1,382.8**. The exact arm includes a separate 5.83-second cache-park
stall; its GPU timeline was also slower (47.904 versus 47.029 seconds).
The fused arm saved only 168 ms within down/inject and showed no total gain.
All short output hashes matched. Neither HC flag is selected. See the
[full comparison and caveats](docs/STRATA-PERFORMANCE-2026-11-07.md#subsequent-expert-and-hc-screens).

The investigation resumed after the user's clean reboot at 14:51:52 UTC.
The original-policy F16 comparison completed: cold 16K **1,074.3 / 40.3 tok/s**,
64K **1,417.5 / 40.9**, and 128K **1,363.2 / 38.9** (prefill/generation).
The first request overlapped GPU queue evictions; long requests were faster.
Rebooting did not eliminate the memory-restore warnings or page migrations.

**Prefill is the first priority, now targeting 1,700–2,000 tok/s.** The
faster build has been profiled; use that profile to choose further changes. Generation's revised 50–70 tok/s target
remains active but comes second. End-to-end timing and turn/retry efficiency
are now explicitly in scope; preserve useful tool behaviour. Public
probes reached 49.8 tok/s prose, 45.2 on a 16K document, and 57.7 code. These
are workload-dependent results, not a broad 50–60 tok/s baseline.

A reversible `vm.compaction_proactiveness=0` comparison completed with identical
engine configuration: 1,389 / 1,398 / 1,350 tok/s cold prefill at 16K / 64K / 128K.
Its first run reduced eviction after readiness from 4,339 ms to 130 ms, but
a later GDN-arm warm-up paused for seconds with the policy still zero. This
setting alone is NOT a fix; it has been reverted to the original 20.
The 64K prefill profile is complete: routed experts 24.9%, GDN 23.9%,
hyper-connections 20.9%, attention-related work 20.1%. Host grouping is negligible.
The 32K/automatic-cache screen gave 1,375 tok/s but shrank the expert cache to
23,083 slots, so it is not selected. The independent 16K chunked-GDN test gave 1,405 / 1,363 tok/s at 64K / 128K,
within control spread, so it is not selected. The 32K arm with all 24,576 experts
explicitly resident reached 1,393 tok/s with greater memory use; not selected.
The 8K screen reached 1,350 tok/s, also slower. Current best remains the
16K F16 configuration. The narrower 64-row F16 expert-kernel screen reached 1,377 tok/s; not selected.
The chosen 16K configuration completed a 64K / 192K cold check at
1,390.4 / 1,300.9 tok/s prefill and 40.0 / 37.3 generation, with zero presence
penalty and 512 output tokens. Other sampling remained greedy/non-thinking.
Generation tuning follows the prioritized prefill work. The bounded expert
persistent-dispatch experiment is **rejected**: every tested grid was slower
(58.7–85.5 ms versus 54.0–54.3 ms), despite identical outputs and passing routing
checks. [Patch, tests and reproduction](experiments/strata-f16-persistent-dispatch/README.md)
are archived. Residual write/normalization measured 191–195 GB/s against
213–233 GB/s for a simple GPU copy: modest remaining headroom, roughly 1.5%
overall under a simple estimate. The matrix calibration selected solution 2390
for all three large FP16 shapes, already in the packaged table. No kernel or
table change was promoted. The user has now resumed optimization with the higher targets; prefill work
comes before the remaining generation comparisons.

The packaged engine is serving the optimized private-8083 preview for the
user test; loopback benchmarks are stopped. Proactive compaction is back at the original **20**; no persistent
host-policy change remains.
`kernel.numa_balancing` was already zero. Do not call the stall fixed until
the eviction and migration counters support it.

The Tiercel listener at 8083 is loaded and serving user traffic. The Strata service remains
disabled at boot. Its `90-live-preview.conf` runtime override selects the
optimized preview; `90-benchmark.conf` was removed. The old 27B and Qwen3.6 units remain stopped/disabled. No
OpenClaw gateway restart or Mac reboot was performed. Persistent 8083 config
is still the original installer layout; do not enable it blindly. The optimized
preview is selected for live testing; boot promotion remains pending. Read the [performance record](docs/STRATA-PERFORMANCE-2026-11-07.md).

After the subsequent expert and HC screens, the unchanged optimized preview
loaded again at **17:06:46 UTC**. Authenticated health, metrics and model
listing passed; the endpoint was idle. `90-benchmark.conf` was removed and
`90-live-preview.conf` restored. Neither HC option nor the source epilogue is
enabled in serving. The Mac gateway was untouched.

After attention capture/replay, the same optimized preview was restored at
**17:30:07 UTC**. Authenticated health, metrics and model listing passed, idle
with zero queued requests. The temporary `91-qsa-profile.conf` is removed;
`90-live-preview.conf` remains. No attention experiment, profiling switch or
cooperative expert epilogue is enabled in serving. Boot promotion is still
pending. Full public evidence and replay inputs are committed with the handoff.

After prepared-row tests, the unchanged packaged preview was restored at
**17:45:26 UTC**. The private-address health/model checks passed again during
the latency audit. The listener binds its Tailscale address, not loopback.
No experimental kernel is serving and boot promotion remains pending.

After the cache comparison, the same preview was restored at **18:21:53 UTC**,
loaded and idle. `91-cache-boundary.conf` is removed; the message-boundary flag
is off. No source experiment, trace flag or short-read override is deployed.

Latest restoration, after the traced cache comparison: **18:38:35 UTC**.
Health and idle state verified on 8083; only `90-live-preview.conf` remains.
The temporary trace override is removed and the same baseline is serving.

Latest restoration, after the short-read comparison: **18:49:50 UTC**.
`91-cache-short-read.conf` is removed. Default short-read 64, stream minimum
128, message-boundary off, no tracing; no source kernel changes deployed.

After the threshold test, that baseline was restored at **19:00:59 UTC**.
At **19:04:22 UTC**, only the boundary-checkpoint flag was then enabled for
the live trial. The actual engine environment confirms it. Only the normal
`90-live-preview.conf` override remains; service boot enablement is unchanged.

**Flash-Next is connected to the existing `tiercelmoe` provider.** Select
`/model qwen-flash-next`, or the full reference
`tiercelmoe/qwen3.8-flash-next-unsloth-ud-q4_k_xl`.
The Mac mini's authenticated streaming check and Francis's live gateway catalog
passed. OpenClaw applied the provider/alias change through hot reload, with PID
369 unchanged. Subsequent real traffic exposed low throughput and one native
verification watchdog exit/reload. Broader quality validation remains pending.

Read the [connection record and reproducible provider patch](docs/STRATA-OPENCLAW-2026-11-07.md),
[first-load evidence](docs/STRATA-FIRST-LOAD-2026-11-07.md) and
[deployment checklist](docs/STRATA-FLASH-NEXT.md).

**Picker correction:** the initial configured-catalog check did not catch the
old Qwen3.6 references in agent allowlists. At 13:52 UTC those were replaced for
Francis and discord-local, and the new reference added to the default policy.
Both agents' live `models.list` **default/allowed** views now include Flash-Next.
The gateway was not restarted. Reopen an already-sent chat model menu to refresh it.
See the [policy check evidence](evidence/strata-2026-11-07/openclaw-picker-policy.json).

## Persistent listener and resources

- API for the live preview (loaded, Mac access verified): `http://100.96.8.54:8083/v1`, Tailscale
  address only, existing provider credential required.
- Model: `qwen3.8-flash-next-unsloth-ud-q4_k_xl`.
- Unit: `strata-flash-next.service`, enabled at boot with `Restart=always` and
  a loaded-engine readiness check. Normal/crash recovery passed; host reboot validation remains open.
- Strata v0.2.11, engine/control 0.1.57, signed HIP-Halo build `0bdcef4682c5+rocm`.
- Context 262,144, INT8 KV, one slot, MTP depth 4, prefill 16,384, GPU vision.
- Route-tail skipping explicitly off; bundled gfx1151 hipBLASLt tuning active.
- Promoted memory layout: all 24,576 experts / 71.73 GiB in the GPU
  cache, no host expert arena, full GPU KV, own prefill scratch, mmap PLE.
  Model quantization and 262,144 context capacity are unchanged.
- Roughly 17–20 GiB system RAM available during large-context tests.
  GPU driver is live, taint zero, 112 GiB GTT active.

The user explicitly authorized stopping the old 27B server and retaining it.
`qwen38-dflash2.service` is stopped and disabled to prevent resource competition.
Its old `http://100.96.8.54:8080/v1` listener is offline. Its weights, source,
configuration and pre-existing local edits remain intact. To roll back, stop
Flash-Next before enabling/starting the old unit; do not run both together.
Qwen3.6 also remains stopped and disabled, with frozen evidence and files retained.

## Evidence and next work

The direct completion returned exactly `READY`. The synthetic tool check passed
exact typed arguments and tool-result continuation; the continuation reused 540
prompt tokens. A streamed completion from the Mac also passed. Disk checkpoints, streaming
tool calls, an actual image request, above-150K completion
and broader fresh-start reliability remain untested. The upstream historical 1,211 tok/s is not a local
measurement. Do not claim broad agent quality from this smoke check.

The user has tested Flash-Next successfully through Ollama Cloud. Continue with
local performance and real-prompt checks. Only the existing Tiercel provider and
its model alias were changed; agent defaults and current session selections were
not. Do not restart/reboot the Mac or send synthetic agent/channel turns.
The user can select the new alias after the private listener is restored.

Implementation and evidence are on `main`. The local worktree
`/home/less/worktrees/qwen38-strata-20261106` was synchronized to the consolidated
`main` commit on 8 November and retained in detached state for existing runtime
paths. Make future repository changes on `main` in `/home/less/qwen38-dflash2`.
Current local results:
`~/.cache/strata-evaluation-20261107/`; public synthetic evidence:
`evidence/strata-2026-11-07/`. Model data: `~/models/strata-flash-next/`.
Config and engine log: `~/.local/share/strata/flash-next/`.

The [November 6 recovery record](docs/STRATA-RECOVERY-RESULT-2026-11-06.md) and
[pre-reboot incident](docs/STRATA-RECOVERY-2026-11-06.md) are historical.
**Do not repeat the failed live amdgpu reload.** The authorized reboot applied
112 GiB GTT successfully; no additional driver reload or reboot occurred here.

## Deferred dense-model investigation

The cold 64K profile is complete: quantized dense GEMM 62.65% of GPU time,
attention 20.20%. Q5_K and IQ4_XS are the largest dense buckets. Multi-row attention,
F16 staging and fused convolution already exist in this runtime. Draft prefill
is only 0.50%; removing the drafter will not solve prefill.

The earlier next step was a selective dense prefill weight-cache experiment.
That work is deferred for the packaged Flash-Next trial; do not restart it merely
because it appears in the historical handoff. No new dense kernel was applied.
[Full analysis, conditions and ranked experiments](docs/PREFILL-RETURN-2026-11-05.md).

Historical uninstrumented baseline: 367.33 tok/s at cold 64K, one sample. The
new 371.40 tok/s run is instrumented and is not a speedup claim. Preserve the
model/context; judge useful task completion, not isolated throughput alone.

Local raw evidence: `~/.cache/qwen38-return-20261105/`; historical comparison:
`~/.cache/qwen38-ubatch-compare.fp9Hef/`. Public evidence excludes user transcripts.
That profiling work is archived on `main`; its local worktree at
`/home/less/worktrees/qwen38-prefill-analysis-20261105` was synchronized to the
consolidated commit and retained in detached state. The profiling investigation
made no source changes or deployment replacement. The diagnostic listener is stopped.
