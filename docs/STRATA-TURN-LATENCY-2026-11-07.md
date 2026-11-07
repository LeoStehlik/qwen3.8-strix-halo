# Flash-Next: latency of the real Telegram task

The user expanded the investigation beyond throughput: count model turns,
tool waits, cache work, preparation and gaps before useful action. This audit
uses the already completed beta-release/PR-inclusion task. No synthetic agent
turn, channel message, configuration change or gateway restart was performed.
Private transcript contents and credentials are not published.

## Task attribution

The task user message was recorded at 16:09:32.662 UTC. Telegram send-success
for the answer was 16:15:06.687: **334.025 seconds**. This is a gateway
acknowledgement, not a measured client-display timestamp. The preceding greeting
and later skill-learning work are separate from this interval.

| Work | Seconds | Share of answer latency |
|---|---:|---:|
| Model generation, including thinking and tool arguments | 210.272 | 63.0% |
| Prefill of newly processed tokens | 62.963 | 18.9% |
| Waiting for tool results, including dispatch/serialization | 55.073 | 16.5% |
| Other time inside model request windows | 3.328 | 1.0% |
| Gaps after the last tool result and before the next request | 0.986 | 0.3% |
| Initial request handoff and final send acknowledgement | 1.403 | 0.4% |

Rounded percentages need not sum to 100. The disjoint intervals reconcile
to the full 334.025 seconds. Backend log milliseconds are rounded; the
request-window remainder is not proven to be idle time.

There were **10 model turns and 10 tool calls**: nine `exec` calls and one
`process` poll. One assistant turn launched two commands; their wait is
counted once through the last result. One command returned exit code 4.
A long-running command and its later poll contributed noticeable waiting;
these observations do not by themselves establish that a call was unnecessary.
The first tool-producing response completed after 5.771 seconds; the runtime
recorded the tool call at about 5.823 seconds. Subsequent post-tool gaps had
**109 ms median / 127 ms maximum**, so large idle gaps between tools are not
the main problem in this sample.

The task processed **83,745 input tokens at 1,330.07 tok/s**, reused 150,150
tokens, and generated **10,031 tokens at 47.70 tok/s**. The previous rolling
first-13-request aggregate (1,327 / 47.25) remains a valid backend aggregate,
but includes the greeting and the beginning of background work. It must not
be described as this task alone.

## Cache reuse is the first cross-layer lead

Every main-task request reused exactly **15,015 tokens**. Fresh work grew from
730 to 15,865 tokens per request while prompt length grew from 15,745 to
30,880. The engine logged only two checkpoints throughout those ten calls.
It repeatedly parked the growing conversation, about 75–126 ms per call;
that parking cost is small compared with repeated prefill.

This establishes repeated processing of a growing tail, not its cause or
the amount safely avoidable. Candidate causes include changes in rendered
prefix tokens, message/turn boundary selection, and checkpoint retention.
Next: compare consecutive provider payloads and rendered token-prefix lengths
using content-free hashes/positions, then compare the matching checkpoint.
Do not reuse state across differing tokens or disable reasoning to manufacture
a cache hit. The hybrid model requires its recurrent state as well as KV.

The eight later backend calls instead show advancing reuse (0 on their first
request, then 35,210 through 44,813). This makes the difference between the
two request paths worth investigating; it does not isolate the cause.

## Preparation before a new user turn

Two surrounding turns have gateway preparation spans:

| Stage | Initial greeting | Later user follow-up |
|---|---:|---:|
| Entire recorded preparation | 9.518 s | 10.759 s |
| `agent-session` | 6.648 s | 6.654 s |
| `system-prompt` | 2.392 s | 2.299 s |
| `session-resource-loader` | 0.192 s | 1.539 s |

The gateway's model-start milestones were about 10.14 and 11.41 seconds after
its respective turn timer began. These are two observations, not a distribution.
Some smaller preparation spans overlap; do not sum every stage blindly.
The release task entered the existing run after the greeting, so charging
either startup delay to its 334-second interval would double-count unrelated
work. The roughly 6.65-second session stage warrants finer instrumentation;
the current trace does not say which operation inside it is slow.

## Background work is not delayed answer delivery

The main model completed at 16:15:05.358; Telegram send-success followed
**1.329 seconds later**. A transcript delivery-mirror entry at 16:17:53 was
a **skill-learning notification**, not the original answer. Its eight later
backend calls must not be charged to answer latency.

The gateway identifies a `skill-workshop-review` run. It records two tool
failures during that work: invalid schema arguments, then a required-view
check. A later auth-success bookkeeping span took 4.566 seconds. These are
possible background-efficiency leads; this sample does not prove they delayed
an overlapping user request. Preserve learning behaviour unless a measured,
reviewable change improves it.

## Priorities and reproduction

1. Diagnose the fixed-prefix cache pattern with exact payload/token comparisons.
2. Profile the roughly 6.65-second session setup stage and 2.3-second prompt stage.
3. Continue prefill kernels toward 1,700–2,000 tok/s; retain repeatable small gains.
4. Measure generation improvements toward 50–70 tok/s and identify redundant
   turns or retries without truncating needed reasoning or useful tool work.
5. Distinguish user latency from background GPU occupancy in every comparison.

For scale, a hypothetical 5% prefill speedup at unchanged work would save
about 3 seconds in this task. A 5% generation speedup would save about 10
seconds. These are arithmetic estimates, not measured candidate wins. Cache
reuse may change the amount of work rather than just its processing rate.

The [sanitized evidence](../evidence/strata-performance-2026-11-07/turn-latency/)
contains per-turn timing/token counts and gateway stage metadata. The
[auditor](../benchmarks/strata-turn-latency.py) matches backend records uniquely
by prompt/reused/read/generated token counts, rejects ambiguous matches, and
checks that the wall-time partition reconciles. To use it with private inputs:

```sh
python3 benchmarks/strata-turn-latency.py \
  --transcript /private/transcript-export.json \
  --backend-log /private/backend.log \
  --first-seq 19247 --last-seq 19276 \
  --delivery-at 2026-11-07T16:15:06.687Z > /tmp/task-timing.json
```

The source transcript is a read-only export from the Mac's SQLite WAL-backed
store, with compressed events decoded locally. No full transcript, tool
argument, result body, user/channel identifier or reasoning text is included
in the public audit output. This is one user-approved task, not a general
latency benchmark or independent assessment of the answer's correctness.
