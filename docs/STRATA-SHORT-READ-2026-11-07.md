# Short-read cutoff: keep 64, reject 8 in the current configuration

The [cache trace](STRATA-CACHE-BOUNDARY-2026-11-07.md) showed a 43-token
runtime message taking about as long through verify windows as 267 tokens
batched. A controlled cutoff comparison resolves that question: **forcing
the 43-token segment through batched prefill made its continuation about
19% slower.** No serving change is retained.

## Isolated comparison

Packaged Strata 0.2.11 / HIP-Halo engine 0.1.57, gfx1151, the same Unsloth
UD-Q4_K_XL model, 262,144 context, INT8 KV and all 24,576 resident experts.
The extra message checkpoint and `STRATA_TRACE=1` were enabled in every arm.
The only requested setting change was **`--short-read 64 / 8 / 64`**.
`STRATA_PREFILL_STREAM_MIN=128` and the other fast settings stayed fixed.

Each fresh engine ran a cold request plus one continuation, first with a
43-token runtime message and then with 267 tokens. Distinct system prefixes
prevented cache sharing between sizes. Requests and rendered-prompt hashes
matched across all arms. The six-token assistant header still used verify
windows in every case. No real tool or OpenClaw agent turn was executed.

| Wall seconds | 64, first | 8 | 64, return |
|---|---:|---:|---:|
| 43-token message, cold | 18.584 | 21.554 | 19.345 |
| 43-token message, continuation | 3.522 | 4.180 | 3.520 |
| 267-token message, cold | 17.324 | 16.907 | 17.012 |
| 267-token message, continuation | 4.841 | 3.765 | 3.525 |

The 43-token continuation's segment itself took **514.2 / 1,201.0 / 513.5 ms**
(windows / batched / windows). Its unchanged 1,869-token history segment took
1,871.9 / 1,885.5 / 1,872.3 ms. Main-process eviction deltas were only
11 / 14 / 7 ms for those requests. The regression is in the selected short
read path, not a large memory stall or increased history work.

The 267-token segment took **519.7 / 521.9 / 531.0 ms** through the same
batched path in every continuation. Its whole-request variation is not a
cutoff win: main-process eviction deltas were 890 / 252 / 7 ms, and the first
control's preparation and preceding history segment were both slow. Cold
requests also encountered variable memory stalls. Do not average those
outliers into a claimed improvement for 267 tokens.

All **12 root/latest-value canaries passed**. Raw output was identical at
three of the four request positions. The first 43-token cold response changed
from single-line to indented JSON in the candidate: the parsed values were
identical, but its raw hash and output token count differed (39 versus 48).
There is no bitwise model-output parity claim for the cutoff change.

## Next hypothesis from source inspection

In pinned source `c3b3f5035506f3e966f1b4b7b188aeaabae92f1d`,
`src/prefill/prefill.cpp` requires `T >= stream_all_min()` for `stream_all`,
and requires `stream_all` before choosing the fused native expert path.
With the current threshold of 128, a batched 43-token segment is excluded;
267 tokens can take it. This is a concrete dispatch distinction, **not yet
a measured explanation of the entire timing difference**.

The next isolated hypothesis is a lower small-batch threshold with the
8-token short-read cutoff held fixed, followed by comparison with the winning
64/128 configuration. Such a change also affects buffer sizing and can change
numerical results. Keep its contribution separate, verify canary/state results,
and check substantial cold prefill before considering adoption. A segment
speedup would not itself establish 1,700–2,000 tok/s raw prefill.

The earlier prepared-row and cooperative-expert source experiments remain
undeployed. No source kernel was edited or compiled during this comparison.
The boundary-cache option also remains off in serving pending a real-traffic
trial. The production short-read setting remains its original default of 64.
The original endpoint was restored loaded and idle at **18:49:50 UTC**;
`91-cache-short-read.conf` was removed and tracing is off.

## Reproduction

Use the [public replay](../benchmarks/strata-cache-boundary.py) on an isolated
listener with the same configuration. Set `STRATA_CACHE_MESSAGE_BOUNDARY=1`
and `STRATA_TRACE=1` in all arms, changing only the engine's `--short-read`.
Use `--modes moving --turns 2 --runtime-padding-rows 0` or `16`, and
`--host-metrics`. Use distinct seeds per size, identical across arms. The
[evidence](../evidence/strata-performance-2026-11-07/cache-short-read/) includes
redacted profiles, exact commands, logs, process IDs for the KFD counters,
complete responses and the trace summary. Private API keys are excluded.

```sh
python3 benchmarks/strata-cache-trace.py --root EVIDENCE_DIRECTORY \
  --arms read64a read8 read64b
```

The summary preserves the failed raw-output hash comparison explicitly,
separately from the passing parsed-value canaries.
