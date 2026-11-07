# Small-batch expert threshold: retained continuation candidate

Lowering `STRATA_PREFILL_STREAM_MIN` from 128 to 32, with `--short-read 8`
held fixed, reduced the 43-token runtime segment from about **1.19 seconds
to 0.27 seconds**. Its whole continuation fell from about **4.22 seconds to
3.33 seconds**, a 21% reduction. This combination is **not enabled in serving**.

The relevant comparison is also the previous best, not just the deliberately
slow control: the earlier 64/128 configuration took 3.522 and 3.520 seconds.
The candidate is about **5.5% faster** than their mean for this fixture. That
cross-experiment comparison is preliminary; only one candidate arm ran here.
It is not a 5.5% raw-prefill gain or a measured improvement on an OpenClaw task.

## Protocol and results

Same packaged HIP-Halo engine 0.1.57, Strata 0.2.11, gfx1151, Unsloth
UD-Q4_K_XL, 262,144 context, INT8 KV, 24,576 resident experts and prefill
capacity 16,384. Message-boundary checkpoints and tracing were enabled in
all arms. **Short-read stayed 8; only stream minimum changed 128 / 32 / 128.**
The engine metrics confirmed each applied threshold. No source kernel changed.

The [public moving-context replay](../benchmarks/strata-cache-boundary.py)
used the same requests/seeds as the short-read experiment. Each fresh engine
ran a cold request and continuation for a 43-token runtime message, then a
separate system prefix with a 267-token runtime message. All **12 state
canaries passed**; request, rendered-prompt and raw-output hashes matched at
all four positions across the three arms.

| Wall seconds | 128, first | 32 | 128, return |
|---|---:|---:|---:|
| 43-token message, cold | 21.341 | 19.662 | 17.954 |
| 43-token message, continuation | 4.201 | 3.326 | 4.232 |
| 267-token message, cold | 16.971 | 16.930 | 17.098 |
| 267-token message, continuation | 3.547 | 3.521 | 3.569 |

For the short continuation:

* The changed 43-token segment took **1,185.1 / 270.0 / 1,196.8 ms**.
* Its preceding 1,869-token segment took 1,922.9 / 1,894.9 / 1,895.2 ms.
* The six-token assistant header stayed on verify windows at about 63 ms.
* All arms reused 20,568 tokens and processed 1,919 new tokens.
* Main-process eviction deltas were 15 / 12 / 12 ms, so multi-second memory
  stalls do not explain this warm result.

The 267-token continuation's corresponding segment took
528.5 / 525.6 / 524.0 ms: essentially unchanged. Cold requests remain noisy
with GPU queue evictions, including a generation stall in the first control.
Do not use the cold averages to claim a startup win.

Draft acceptance varied even between the controls. For the short continuation,
accepted/offered was **35/36, 35/42, 35/42**. Generation times were
801.1 / 873.5 / 844.7 ms for the same 48 output tokens. The experiment does
not establish either improved or unchanged representative generation speed.

## Interpretation and remaining checks

The pinned source gates `stream_all` on this threshold and then requires
`stream_all` for fused native experts. The measured selective improvement
is consistent with that dispatch distinction: 43 tokens cross the threshold,
267 tokens already exceeded it. The measured segment is a pass through the
whole model, not a timing of one expert kernel.

Retain the 8/32 pair as a small-input candidate. Before adopting it, compare
directly against 64/128 again, check substantial cold prefill and longer
generation, and retain semantic/state checks. Threshold changes also affect
scratch sizing and floating-point execution, so the unchanged large-batch
source condition is not sufficient proof of an unchanged full-model baseline.
Do not keep benching this same tiny fixture in place of that broader check.

The independent message-boundary checkpoint can be evaluated on actual
OpenClaw traffic using the existing 64/128 settings. Its live-trial status
is recorded separately in [handoff.md](../handoff.md). No synthetic OpenClaw
turn, channel message, Mac gateway restart or Mac configuration change was
performed here. Raw prefill 1,700–2,000 tok/s and generation 50–70 tok/s remain
unachieved targets; this experiment changes neither throughput baseline.

## Reproduction and evidence

Use the same public replay as the short-read report, with `--short-read 8`
in every engine profile and `STRATA_PREFILL_STREAM_MIN=128`, then `32`, then
`128`. Keep `STRATA_CACHE_MESSAGE_BOUNDARY=1` and `STRATA_TRACE=1` in all arms.
The [evidence](../evidence/strata-performance-2026-11-07/cache-stream-min/)
contains redacted profiles, exact replay commands, process IDs, per-request
VM/KFD counters, logs, complete responses and checksums.

```sh
python3 benchmarks/strata-cache-trace.py --root EVIDENCE_DIRECTORY \
  --arms stream128a stream32 stream128b
```

The pre-trial serving baseline was restored at **19:00:59 UTC**; the temporary
`91-cache-stream-min.conf` override was removed.
