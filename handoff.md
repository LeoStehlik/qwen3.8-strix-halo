# Handoff for Francis — Flash-Next performance investigation, 2026-11-07

Repository: [Qwen3.8 inference on Strix Halo](https://github.com/LeoStehlik/qwen3.8-strix-halo),
renamed from the earlier 27B/DFlash2-specific name on 7 November. The default
branch landing page links this active investigation; clone URLs are updated.

**Performance investigation resumed with higher targets: 1,700–2,000 tok/s
prefill first, then 50–70 tok/s sustained generation.** These supersede the old
goal wording. Read the [updated objective and experiment order](docs/STRATA-NEXT-TARGETS-2026-11-07.md).

**Current live state, restored at 19:55:46 UTC:** the packaged optimized endpoint has
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
Next compare narrower K64 tiles for residency and wider K32 tiles for reuse
independently, checking their synchronization and traffic costs. Geometries
and validation gates are in the report; neither has been built yet.

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
spec-6/spec-8 were not run. The [expert profile and routing replay](experiments/strata-expert-profile/README.md)
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

## Current listener and resources

- API for the live preview (loaded, Mac access verified): `http://100.96.8.54:8083/v1`, Tailscale
  address only, existing provider credential required.
- Model: `qwen3.8-flash-next-unsloth-ud-q4_k_xl`.
- Unit: `strata-flash-next.service`, serving the live preview on 8083, disabled at boot. Automatic systemd restart
  after failure remains off. Boot validation for this unit is pending.
- Strata v0.2.11, engine/control 0.1.57, signed HIP-Halo build `0bdcef4682c5+rocm`.
- Context 262,144, INT8 KV, one slot, MTP depth 4, prefill 16,384, GPU vision.
- Route-tail skipping explicitly off; bundled gfx1151 hipBLASLt tuning active.
- Current experimental memory layout: all 24,576 experts / 71.73 GiB in the GPU
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

Implementation worktree: `/home/less/worktrees/qwen38-strata-20261106`, branch
`investigate/strata-performance-20261107` (branched from deployment commit
`92c5521`). Current local results:
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
That profiling work is isolated in `/home/less/worktrees/qwen38-prefill-analysis-20261105` on
`investigate/dense-prefill-20261105`; no source changes or deployment replacement
were made by the profiling investigation. The diagnostic listener is stopped.
