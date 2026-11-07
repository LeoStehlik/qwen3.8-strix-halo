# Flash-Next: resumed optimization target, 2026-11-07

The user raised the objective and manually resumed the Codex goal. These
objectives supersede the earlier 1,100 / 50–60 tok/s target, even if the goal
panel still displays that older wording:

- Prefill first: **1,700–2,000 tokens/s**, measured on substantial uncached input.
- Generation second: **50–70 tokens/s sustained**, including reasoning and tool
  output, not a brief instantaneous peak.
- Keep Qwen3.8-Flash-Next UD-Q4_K_XL, 262,144 context capacity, INT8 KV and useful
  OpenClaw capability. Do not substitute a smaller model, weaker quant or
  shorter context. Record floating-point changes and validate their effect.
- Preserve the current working configuration, independently switch experiments,
  and publish reproduction steps and evidence. Do not restart the Mac gateway
  or reboot either machine. Check for active requests before backend work.

## Working baseline and user validation

The user asked Francis through Telegram to find OpenClaw's latest beta on
GitHub and determine whether their co-authored PRs were included. The user
reviewed the result and reported being pleased. This is a successful real
agent test by the user's assessment, not an independent audit of the answer
or a broad model-quality evaluation.

The first 13 completed calls measured 136,630 newly processed input tokens in
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

## Next experiment priorities

A 64K profile of this configuration charged 24.9% to routed experts, 23.9% to
GDN work, 20.9% to hyper-connections and 20.1% to attention-related work.
Actual attention is only 10% of total; recurrence alone is 6.7%. The larger
target will probably require gains across multiple substantial operations.
A 2x expert improvement alone would predict about 14% overall, not 2x prefill.

1. The [expert interval split and routing capture](../experiments/strata-expert-profile/README.md)
   are complete: roughly 62% gate/up, 37% down, negligible grouping; no scratch
   spills. Three captured 16K distributions cost only 1–3% more than uniform
   routing. Test a cooperative gate/up SwiGLU/int8 epilogue independently;
   it is a source-based hypothesis, not a measured improvement. Expert memory
   counters returned unexplained zeros even though a copy control worked, so
   resolve that before claiming bandwidth/occupancy limits. The rejected
   bounded-dispatch patch is not a candidate for promotion.
2. Measure attention's memory reuse and remaining scheduling cost. The current
   source already defaults to trimmed shared-memory rows and read prefetch;
   enabling those again is not a new optimization. Old experimental flag names
   in comments are not evidence that a switch still exists.
3. Compare any operator winner against a same-source control, then validate
   cold 64K/128K and a 192K stress case. Report newly processed tokens, cache
   reuse, full durations and output checks; no warm-cache substitution.
4. After the prefill investigation, complete the generation experiments:
   MTP depth 4/6/8 with matched prompts, then the measured winner under actual
   OpenClaw sampling. Only depth 4 has run; the thinking-enabled synthetic
   probe was interrupted for the user's live test. Head-mix fusion and other
   generation candidates remain untested.

Rejected or low-value paths remain documented: persistent expert dispatch was
slower with identical outputs; 8K/32K chunks, forced 64-row F16 tiles and chunked
GDN gave no convincing win; residual write is already around 191–195 GB/s;
hipBLASLt calibration picked the existing solution 2390. Proactive compaction
zero did not fix stalls and was restored to 20.

See [the full performance record](STRATA-PERFORMANCE-2026-11-07.md) and
[the current handoff](../handoff.md). This is the resumed objective and
experiment order, not a claim that the new target is already attainable.
