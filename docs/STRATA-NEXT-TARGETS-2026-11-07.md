# Flash-Next: resumed optimization target, 2026-11-07

**Latest decision:** the user authorized a bounded MTP comparison and expert
instruction trace after the [stopping checkpoint](STRATA-OPTIMIZATION-CHECKPOINT-2026-11-07.md).
The [MTP screen](STRATA-MTP-WINDOW-2026-11-07.md) is complete: no reliable gain,
window 4 restored. The [expert instruction trace](STRATA-EXPERT-ATT-2026-11-07.md)
then motivated [prepared activations](STRATA-EXPERT-PREPARED-2026-11-07.md).
Exact operator outputs were preserved, but neither independent preparation
path showed a repeatable gain in the reverse-order screen. That bounded
follow-up is complete; no candidate is promoted. The target remains unmet
and the hardware ceiling unproven.

The later [cost-aware MTP screen](STRATA-MTP-COST-2026-11-07.md) also found no
reliable improvement; serving was restored at 21:59:11 UTC. The
[prepared-weight capacity study](STRATA-EXPERT-WEIGHT-CAPACITY-2026-11-07.md)
provides constraints for another possible mechanism, not a measured gain.
Keep it distinct from the rejected prepared-activation implementation.
The subsequent [prepared-weight operator](STRATA-EXPERT-PREPARED-WEIGHTS-2026-11-07.md)
preserved checked outputs but lost in both captured-routing and high-reuse
screens. It is also rejected; no live cache or source patch is promoted.

The user raised the objective and manually resumed the Codex goal. These
objectives supersede the earlier 1,100 / 50–60 tok/s target, even if the goal
panel still displays that older wording:

- Prefill first: **1,700–2,000 tokens/s**, measured on substantial uncached input.
- Generation second: **50–70 tokens/s sustained**, including reasoning and tool
  output, not a brief instantaneous peak.
- Keep Qwen3.8-Flash-Next UD-Q4_K_XL, 262,144 context capacity, INT8 KV and useful
  OpenClaw capability. Do not substitute a smaller model, weaker quant or
  shorter context. Record floating-point changes and validate their effect.
- Keep repeatable gains, including 5% overall improvements (about 70 tok/s at
  the measured ~1,400 baseline). Small operator wins can be accumulated; do not
  present them as whole-model gains or promote them without integration tests.
- Also measure end-to-end useful-action and answer latency: model/tool turn
  counts, preparation, cache save/restore, tool waits, retries, background work
  and gaps. The user explicitly added this scope; raw throughput remains active.
- Preserve the current working configuration, independently switch experiments,
  and publish reproduction steps and evidence. Do not restart the Mac gateway
  or reboot either machine. Check for active requests before backend work.

## Working baseline and user validation

The user asked Francis through Telegram to find OpenClaw's latest beta on
GitHub and determine whether their co-authored PRs were included. The user
reviewed the result and reported being pleased. This is a successful real
agent test by the user's assessment, not an independent audit of the answer
or a broad model-quality evaluation.

The first 13 completed backend calls (including the greeting and the beginning
of background work, not just the main task) measured 136,630 newly processed input tokens in
102.9643 seconds (**1,326.96 tok/s**), and 11,068 generated tokens in 234.2528
seconds (**47.25 tok/s**). Prefix reuse totalled 185,360 tokens. Completed
request generation ranged about 42–52 tok/s; context grew from 15K to 38K.
Earlier cold controlled probes reached 1,416 at 64K, about 1,350–1,360 at 128K,
and 1,301 at 192K. Controlled long-context generation was about 37–40 tok/s.
Keep the greedy synthetic and thinking-enabled live results distinct.

The existing service is a packaged Strata 0.1.57 HIP-Halo preview, all 24,576
experts resident, full GPU KV, 16,384-token prefill chunks, MTP depth 4, PLE mmap,
and the measured upstream fast kernels. It serves authenticated private
`100.96.8.54:8083/v1`; the Mac uses the existing `tiercelmoe` provider and
`qwen-flash-next` alias. Source experiments are not deployed. Boot promotion
remains pending; the live selection uses `90-live-preview.conf`.

## End-to-end evidence added by user request

The [real-task timing audit](STRATA-TURN-LATENCY-2026-11-07.md) measures 334.025 s
to Telegram send-success: 210.272 s generation, 62.963 s prefill, 55.073 s
tool-result windows, about 5.7 s elsewhere. Ten model turns / ten tool calls.
Post-tool gaps were only 109 ms median; cache reuse remained fixed at 15,015
tokens. Two surrounding turns spent ~6.65 s in session setup and ~2.3 s in
system-prompt preparation. Investigate exact prompt/checkpoint differences and
finer setup spans. Later skill-learning calls happened after answer delivery;
do not label them idle time or charge them to the answer. This is read-only
evidence from the existing task, not a new synthetic OpenClaw run.

A [backend-only boundary-checkpoint replay](STRATA-CACHE-BOUNDARY-2026-11-07.md)
now demonstrates the interaction with moving runtime context. The existing
`STRATA_CACHE_MESSAGE_BOUNDARY=1` option reduced three continuation times by
45% and reread tokens by 74%, with identical outputs across off/on/off arms.
All moving-context state canaries passed; fixed-context follow-ups only passed
output parity, emitting the same unwanted lookup text in every arm. Cold
startup varied materially. A traced follow-up passed 12 moving-context canaries
with matching outputs at 43- and 267-token tails. It found multi-second GPU
eviction activity before the extra checkpoint, versus 24–41 ms checkpoint
copies. The larger tail also benefited. The option is now enabled in a
[limited live trial](STRATA-CACHE-LIVE-TRIAL-2026-11-07.md) using 64/128;
actual OpenClaw reuse and quality remain to be checked before boot promotion.
The [short-read 64/8/64 comparison](STRATA-SHORT-READ-2026-11-07.md) rejected
8 at the current stream minimum of 128: about 19% slower continuation latency.
Source inspection shows the threshold excludes 43-token batches from fused
experts. The [128/32/128 experiment](STRATA-SMALL-BATCH-2026-11-07.md) then
reduced the short segment from ~1,191 to 270 ms and its continuation to 3.33 s.
Retain 8/32 undeployed: its ~5.5% advantage over the earlier best needs direct
comparison plus substantial cold-prefill and longer generation checks.
These are latency findings, not a higher raw-prefill baseline. The live
checkpoint trial loaded at 19:04:22 UTC. No Mac gateway restart or configuration change.

## Next experiment priorities

**Correction to the preceding update:** packaged **`STRATA_PF_PAD=1`**
[off/on/off screen](STRATA-PROJECTION-PADDING-2026-11-07.md) delivered
1,329 / 1,395 / 1,352 tok/s on second uncached 64K requests, with matching
outputs: +4.08% throughput against combined controls, +3.21%
against the return control, but only one enabled arm and inconsistent
first-64K results with memory stalls. Source pads projection activation and
dequantized-weight row strides by 64 half values; actual internal dispatch
was not traced. **Padding was already on in the serving baseline**, supplied
by `apply_arch_defaults` for gfx1151 before the engine reads its settings.
Its startup log lists `PF_PAD`; the inherited environment alone missed that
internal change. Thus this is an ablation of an existing default, not a new
candidate. Cancel the proposed padding promotion/128K confirmation ladder.
Serving was restored at 19:55:46 UTC with the original hardware defaults and
the cache trial still on. Audit effective defaults before further switches.

The subsequent [projection block-grouping screen](../experiments/strata-projection-grouping/README.md)
tested groups 1/2/4/8/16/32/64 on three padded 16K-row matrix shapes. The
existing group 8 was close to best: only 0.2–1.2% operator median improvements,
with substantial regressions elsewhere. All 49 GPU output comparisons matched
bit for bit; four CPU-reference cases passed 1e-6 tolerance. No selector is
selected. This was an isolated operator probe with the live server idle and
unchanged, not a new full-model result. Next investigate the projection
kernel's LDS/register usage and instruction/memory limits before changing its
tile shape. Launch-order tuning alone is not a promising source of the needed gain.

The [projection resource profile](STRATA-PROJECTION-PROFILE-2026-11-07.md)
now supplies that evidence: 54 KiB LDS / 248 VGPRs, no spills, observed four
waves per sampled SIMD, substantial shared-memory waits and barriers alongside
matrix work. L2 external requests do not establish a DRAM bottleneck; a repeat
changed traffic at similar time. A fragment-load reorder preserved exact GPU
outputs but remained within −0.05% to +0.21% of control, with unchanged resource
allocation, and is rejected. The subsequent narrow K64 and wide K32 candidates
were implemented and tested independently: narrow lost 13.4–13.5% operator
throughput, wide lost 28.6–32.2%. All 21 GPU output comparisons matched exactly.
Wide spills registers; narrow lowers LDS without a measured speed benefit.
Both are rejected in their current form. No source candidate is serving.
See the [final tile evidence and assessment](STRATA-OPTIMIZATION-CHECKPOINT-2026-11-07.md).

A 64K profile of this configuration charged 24.9% to routed experts, 23.9% to
GDN work, 20.9% to hyper-connections and 20.1% to attention-related work.
Actual attention is only 10% of total; recurrence alone is 6.7%. The larger
target will probably require gains across multiple substantial operations.
A 2x expert improvement alone would predict about 14% overall, not 2x prefill.

1. The [expert interval split and routing capture](../experiments/strata-expert-profile/README.md)
   are complete: roughly 62% gate/up, 37% down, negligible grouping; no scratch
   spills. Three captured 16K distributions cost only 1–3% more than uniform
   routing. The [cooperative gate/up epilogue](../experiments/strata-cooperative-epilogue/README.md)
   now gives a measured 2.4–2.5% operator improvement on captured routing with
   exact outputs, only about 0.6% estimated whole-prefill gain. Keep it as an
   undeployed opt-in candidate; no full-model/state test yet. Four-stage loop
   unrolling lost and was removed. Separate per-kernel memory counter
   collection works, while the combined filter gives zeros; do not infer a
   roofline from the remaining missing instruction counters. Broader dense
   tuning and packaged HC exact/fused screens gave no promotion-worthy gain.
   The rejected bounded-dispatch patch is not a candidate for promotion.
2. The [attention capture and instruction trace](../experiments/strata-attention-replay/README.md)
   are complete: all 12 QSA layers from two public 64K requests, gated replay,
   useful memory/instruction counters and one gfx1151 Advanced Thread Trace.
   Four-query ideal read sharing averages 1.59×; later-layer L2 hits were only
   20.25%. The trace exposes waits after scales and selected-ID/page-table
   loads, plus repeated INT8 conversion work. Its summed instruction-latency
   shares are not GPU wall-time shares. Early V staging gave no gain; deferred
   scales with a compiler barrier gave only 0.5–1.8% operator gain and is shelved.
   The [prepared physical-row candidate](../experiments/strata-attention-rows/README.md)
   now gives 2.47–4.63% on three 4K replays and 3.16% on a full 16K chunk,
   preprocessing included, with exact outputs across 24 boundary/page-table
   cases. Retain it, undeployed: its ~256 MiB scratch and production lifetime
   still need integration/full-model testing. Estimated overall gain is only
   ~0.3%. The subsequent [native INT8 conversion screen](../experiments/strata-attention-native-i8/README.md)
   passed exhaustive exact-value checks and replay output parity, but its
   assembly form was neutral and vector form slower. Both were removed from
   active source; patch/evidence archived. No full-model trial justified by
   that screen. Trim/read-prefetch already default on. Actual attention is
   only 10% of total prefill.
3. Compare any operator winner against a same-source control, then validate
   cold 64K/128K and a 192K stress case. Report newly processed tokens, cache
   reuse, full durations and output checks; no warm-cache substitution.
4. The later MTP 4/6/8/4 comparison used matched 16K/64K prompts and OpenClaw
   sampling. Window 6 showed no reliable gain; window 8 was slower. Keep 4.
   All 16K hashes match; at 64K window 8 differs while both controls and 6 match.
   No candidate qualified for further tool/state validation. Head-mix fusion
   and the existing opt-in cost-aware MTP policy remain untested here.

Rejected or low-value paths remain documented: persistent expert dispatch was
slower with identical outputs; 8K/32K chunks, forced 64-row F16 tiles and chunked
GDN gave no convincing win; residual write is already around 191–195 GB/s;
hipBLASLt calibration picked the existing solution 2390. Proactive compaction
zero did not fix stalls and was restored to 20.

The [factory clock-policy screen](STRATA-CLOCK-POLICY-2026-11-07.md) also
retained automatic clocks: cold 64K auto/high/auto/peak/auto measured
1,398/1,417/1,394/1,275/1,396 tok/s. High's single +1.48% arm is not established
as repeatable; peak was slower. Original auto restored at 19:21:03 UTC with
the boundary-checkpoint live trial unchanged. No service restart, source
promotion, power-limit change or new throughput baseline.

See [the full performance record](STRATA-PERFORMANCE-2026-11-07.md) and
[the current handoff](../handoff.md). This is the resumed objective and
experiment order, not a claim that the new target is already attainable.
