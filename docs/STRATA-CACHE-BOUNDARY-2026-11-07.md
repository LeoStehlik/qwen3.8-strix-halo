# Checkpoint placement for moving runtime context

**Retained candidate, not enabled in serving.** A backend-only off/on/off
comparison cut three synthetic tool-continuation latencies from about
19.2 seconds to 10.6 seconds (**45% shorter**) by avoiding repeated work.
This does not establish the 1,700–2,000 tok/s cold-prefill target or measure
the same improvement on a real OpenClaw task.

## Why this was tested

The [real-task audit](STRATA-TURN-LATENCY-2026-11-07.md) found reuse fixed at
15,015 tokens across ten requests, despite growing history. Source inspection
found a concrete interaction:

1. The installed OpenClaw 2026.10.9 full-resend path can move a transient
   runtime-context message behind the growing tool history.
2. Strata normally saves a checkpoint at the final assistant-turn boundary,
   after that transient message. On continuation, history replaces the old
   location of the transient message, so that checkpoint's prefix differs.
3. Even when most history still matches, the engine can fall back to its
   much earlier system checkpoint and reread the growing tail.

The [read-only projection probe](../benchmarks/openclaw-runtime-carrier.mjs)
executed the installed message helpers with public fixtures and confirmed the
relocation. It did not create an agent/session, send a message or execute a
tool. The installed bundle hashes are recorded in the evidence. The actual
task used `openai-completions`; the generic fallback policy does not retain
append-only runtime context.

This is a demonstrated interaction consistent with the task's cache pattern,
not an exact replay of its historical wire payload. The trajectory capture
omitted its 53,203-character system prompt because of the 32,768-character
field limit and truncated parts of its tool schemas. Exact original token
prefixes and the runtime-context length therefore cannot be reconstructed
from that trace alone.

## Existing engine option

The packaged engine already contains **`STRATA_CACHE_MESSAGE_BOUNDARY=1`**.
It saves an additional full-state checkpoint before a short final message.
Normal exact token/image-prefix checks still decide whether reuse is allowed.
It does not reuse state across changed tokens, remove instructions, truncate
history, disable reasoning in the live model, or replace recurrent state with
KV alone.

The selector requires a prefix of at least 8,192 tokens and a final message
of at most 1,024 tokens, with prompt caching enabled. Layer-split execution is
excluded. An extra checkpoint can add copying/allocation cost and split the
prefill differently. Source selector tests passed **21 checks**. The option
was tested on the packaged HIP-Halo engine, not our experimental kernel build.

## Controlled comparison

The [public replay](../benchmarks/strata-cache-boundary.py) creates synthetic
lookup history plus either moving or fixed runtime context. Four requests
per mode grow from about 20.6K to 26.2K tokens. It uses the same model/quant,
262,144 context capacity, INT8 KV, all-resident experts and existing fast
configuration. `max_tokens=128`, greedy non-thinking sampling and
`tool_choice=none` apply only to this backend fixture. No real tools run.

Fresh engine starts ran **off / on / off**, with identical request and rendered
prompt hashes. The root prefix in this public fixture is 16,856 tokens, not
the private task's 15,015. The moving message is 43 tokens before the assistant
header; performance at other message sizes remains to be measured.

| Moving-context measurement | Off, first | On | Off, return |
|---|---:|---:|---:|
| First cold request, wall seconds | 19.799 | 25.940 | 24.334 |
| Three continuations, wall seconds | 19.161 | 10.583 | 19.333 |
| Continuation prefill seconds | 16.721 | 8.164 | 16.781 |
| Newly processed continuation tokens | 22,501 | 5,757 | 22,501 |
| Cold request plus continuations, seconds | 38.960 | 36.522 | 43.667 |

The enabled continuations reused 20,568, 22,437 and 24,307 tokens, instead of
staying at 16,856. Each processed about 1,920 new tokens and took about 3.53
seconds. Compared with the mean of the two controls, continuation latency
fell **45.02%**, and newly processed tokens fell **74.41%**. The token-rate
denominator must remain actual newly processed tokens; do not advertise the
reused history as higher raw prefill throughput.

The fixed-context case already reused growing history with the option off.
Its three continuation wall totals were 7.561 / 7.591 / 7.548 seconds, with
5,564 tokens processed in every arm: no measured benefit there.

All eight per-position output hashes matched across all three arms. All four
moving-context answers in each arm correctly returned both the root identifier
and latest lookup values. **The fixed-context follow-ups did not pass those
answer checks:** in every arm the model wrote the same raw XML for another
lookup instead. None was executed. Those three positions support only cache
and output parity, not canary correctness or tool-quality claims. The results
retain this failure explicitly rather than reporting an all-pass suite.

Two preliminary control runs are archived separately: the first stopped on
a Markdown fence around otherwise correct JSON; the second stopped on the
unexpected lookup. The final protocol separates formatting from state values,
requests no new tools explicitly, and records all outcomes. Preliminary runs
are not mixed into the off/on/off performance comparison.

## Follow-up trace: memory stalls and short reads

A second off/on/off diagnostic enabled `STRATA_TRACE=1` in all arms and
recorded Linux VM/KFD counters around each request. It tested a cold request
plus one continuation with both a **43-token** and a **267-token** runtime
message. Each size used a distinct system prefix, preventing reuse between
the two cases. The original model, context, KV and resident-expert settings
were retained. Automatic conversation-cache capacity was 6,912 MiB in all
three arms, sufficient for these fixtures without conversation evictions.

| Wall seconds | Off, first | On | Off, return |
|---|---:|---:|---:|
| 43-token message, cold request | 19.683 | 21.281 | 16.620 |
| 43-token message, continuation | 5.086 | 3.464 | 5.094 |
| 267-token message, cold request | 16.533 | 16.891 | 16.643 |
| 267-token message, continuation | 5.617 | 3.465 | 5.276 |

All **12 responses passed the root/latest-value canaries**, with identical
request, rendered-prompt and output hashes at each matching position. This
is a new moving-context diagnostic; it does not erase the earlier fixed-case
canary failures. The larger message is a sensitivity test, not a measurement
of the original private request's runtime-context length.

The trace separates several costs that the aggregate prefill number hid:

* First control, cold: **3,211.7 ms before prompt processing**, with the
  inference process's KFD eviction counter increasing **3,196 ms** over the
  request. Its 16,850-token root segment then took 11,822.8 ms.
* Enabled, cold: preparation was only 25.2 ms, but that same root segment took
  **16,238.7 ms**, before reaching the additional message checkpoint. One
  process's eviction counter increased **4,229 ms**. The return control's root
  took 11,995.5 ms and its largest process eviction delta was 242 ms.
* Checkpoint copies in the enabled arm took **23.6–40.9 ms each**, not seconds.
  These timings include nested checkpoints inside some batched-read intervals;
  they must not all be added as disjoint costs.
* The enabled continuation read **43 tokens through verify windows in
  516.3 ms**, versus **267 tokens batched in 533.4 ms**. Both then read the
  six-token assistant header through windows in about 64 ms. The default
  short-read cutoff is 64 tokens; it merits a separate controlled comparison
  in this all-resident layout.

This identifies a substantial memory-stall contribution to the cold variability.
It does not prove an exact stall subtraction: KFD counters cover whole requests,
can overlap between the inference and vision processes, and VM counters are
host-wide. Do not report counter-adjusted throughput. The relatively quiet
267-token cold cases show a smaller enabled cost of about **0.25–0.36 seconds**;
that is a limited observation, not a universal startup penalty.

The [trace evidence](../evidence/strata-performance-2026-11-07/cache-boundary-trace/)
includes engine logs, per-request memory counters and exact prompt checks.
Reproduce with `--modes moving --turns 2 --runtime-padding-rows 0` or `16`,
plus `--host-metrics`, using a different `--seed` for each size and the same
seeds across arms. The [trace summarizer](../benchmarks/strata-cache-trace.py)
checks that each trace interval matches the API prefill time within 1 ms.

## Decision and next checks

Keep the option as a concrete cache candidate. The warm benefit has repeated
with both message sizes; cold timing is strongly affected by memory stalls.
Two enabled arms have now run, one untraced and one traced, with different
fixtures. They are not a large production latency distribution.

Next compare the short-read cutoff independently, preserving the six-token
header's current path and testing both message sizes. Do not assume that the
batched path wins for 43 tokens merely because it handles 267 efficiently.
Memory management remains a separate source of stalls; the earlier compaction
setting experiments did not establish a stable win and remain reverted.

Before making this a serving default, check the cold cost, then use a limited
real-traffic trial to confirm useful reuse on the actual request path. Continue raw kernel work
independently; this experiment has not changed its throughput baseline.
The roughly 6.65-second OpenClaw session-setup stage is still unresolved.
Source inspection narrows it to session preparation (including initial context
read, metadata settlement and tool/session setup), not a measured slow leaf
operation. No Mac code/configuration was changed for these investigations.

The unchanged private-8083 preview was restored at **18:21:53 UTC**, loaded
and idle. The temporary `91-cache-boundary.conf` override was removed; the
message-boundary option remains off, source experiments remain undeployed,
and boot promotion remains pending.

After the traced follow-up, the same preview was restored at **18:38:35 UTC**,
loaded and idle. `91-cache-boundary-trace.conf` was removed. Neither the cache
option nor tracing is enabled in serving; the short-read setting is unchanged.

## Reproduction

Use the existing optimized profile on an isolated loopback listener, preserving
the original profile/API key privately. Restart the engine with the option
unset/0, then 1, then 0. The environment is read by the engine, so changing
it in the client does not select an arm. Supply the API key through
`STRATA_API_KEY`, never in command text or published artifacts.

```sh
"$TERMINAL/python/bin/python3" benchmarks/strata-cache-boundary.py \
  --url http://127.0.0.1:8084 \
  --model qwen3.8-flash-next-unsloth-ud-q4_k_xl \
  --terminal "$TERMINAL" --tokenizer "$PACK/tokenizer" \
  --out /tmp/cache-boundary-results.json
```

`--offline` renders/tokenizes the same fixtures without inference. The replay
checks the serving API's prompt counts against offline tokenization and
records complete streams, expected values, raw output, tool deltas and hashes.
It does not turn a wrong model answer into a successful state check. Full
[evidence, hashes and preliminary failures](../evidence/strata-performance-2026-11-07/cache-boundary/)
are public; private profiles and actual user transcripts are excluded.
