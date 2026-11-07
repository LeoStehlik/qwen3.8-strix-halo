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

## Decision and next checks

Keep the option as a concrete cache candidate. The warm benefit is clear,
but cold-request timing varies substantially even between the two controls.
The enabled arm's slower cold request is not yet attributed to the option,
initial memory stalls, or another startup cost. Only one enabled arm ran.

The next diagnostic should use `STRATA_TRACE=1` for checkpoint timing and
memory-eviction/migration counters. The 43-token message is also below the
engine's default `--short-read 64` threshold: adding a checkpoint exposes a
short segment processed through decode windows. That is a source-based lead,
not a measured explanation of the cold delay. Measure representative larger
runtime-context messages too; do not tune solely for this tiny fixture.

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
