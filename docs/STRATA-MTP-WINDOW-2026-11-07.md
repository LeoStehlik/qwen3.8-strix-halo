# MTP windows 4/6/8: retain 4

Increasing the packaged MTP window did not deliver the requested additional
10–20 tok/s. Keep `--spec 4`. Window 6 showed no reliable gain; window 8 was
slower in this screen. These are two public performance fixtures, not a broad
quality evaluation or actual OpenClaw traffic.

## Conditions and results

Same packaged Strata 0.2.11 / HIP-Halo engine 0.1.57, Qwen3.8-Flash-Next
UD-Q4_K_XL, 262,144 context, INT8 KV, all 24,576 experts resident, existing fast
flags and boundary-checkpoint trial. Automatic clocks. Only `--spec` changed
between arms; `STRATA_DECODE_TIMING=1` was common to all. Source inspection
shows that switch reports host timings already collected in the serial loop;
the detailed GPU verification profiler stayed off.

The existing public source fixture was expanded to 16K and 64K. Nonces and
messages matched across fresh engine instances. Requests used the recorded
OpenClaw preset: thinking on, temperature 0.3, top-p 0.95, top-k 20, min-p 0.05,
presence penalty 0, repeat penalty 1, seed 1. The 1,024-token output allowance
applies only to these probes. No provider response limit was changed.

Native generated tokens divided by native generation time, rounded:

| Context | Window 4, first | Window 6 | Window 8 | Window 4, return |
|---|---:|---:|---:|---:|
| 16K | 40.3 tok/s | 39.6 | 30.3 | 40.9 |
| 64K | 41.3 tok/s | 39.7 | 36.2 | 39.2 |

Window 6 falls between the 64K controls, whose rates varied by about 5%.
It is below both controls at 16K. There is no demonstrated improvement.
Window 8 is below both controls at both contexts. Its first 16K native segment
spent 86.27 ms/window verifying, versus 57.06 in the continuation; initialization
or transient stalls may contribute, but were not isolated. That cost remains
in the reported result. The 64K loss also persists after that first request.

These rates are specific to this fixture and thinking budget. They do not
replace the earlier real-task measurement of 47.7 tok/s. Initial prefill and
warm-up varied materially, including a slow return-control 16K prompt. No raw
prefill improvement or resolution of GPU stalls is claimed.

## Why a bigger window did not help

At 64K, the first window-4 control emitted 2.42 tokens/window, with 48.34 ms
verification and 10.28 ms drafting. Window 6 emitted 2.71 tokens/window, but
needed 54.33 ms verification and 13.90 ms drafting. About 12% more tokens came
at about 16% more combined cost. Window 8 emitted only 2.70 tokens/window,
with 58.40 ms verification and 16.16 ms drafting.

The setting counts the current token plus drafts: 4/6/8 allows at most 3/5/7
MTP proposals. The unchanged default suffix-lookup policy also expands the
maximum verification window to 6/8/8. Metrics confirmed those effective limits.
This compares the packaged setting, not a perfectly isolated MTP-only cap.
Existing confidence-based shortening and lookup selection remain enabled.

An existing opt-in cost-aware policy, `STRATA_SPEC_COST=1`, was found in source;
it is not enabled in these arms or in serving. Do not invent a new adaptive
controller without evaluating the existing implementation. No performance
claim for that option on this machine follows from source inspection.

## Output checks and collector correction

All four 16K output hashes match. At 64K, both window-4 controls and window 6
match; window 8 differs. The difference was not classified as harmless or as a
quality regression. A commentary initially overstated parity; it was corrected
as soon as the full hash analysis exposed the 64K exception. No candidate
qualified for promotion or further tool/state validation.

The first collector incorrectly expected one native timing record per API
request. The first window-4 arm completed both probes, then failed that check
and restored serving automatically. Thinking-budget transitions can create a
second native generation inside one API response. The corrected collector
groups those segments and reconciles their draft counts and summed durations
with the API, allowing only logged millisecond rounding. The completed first
control was retained; the sequence continued with 6/8/4 rather than rerunning it.
The original failed runner report is preserved as evidence.

Each measured API response reported 1,024 completion tokens, while native
generation emitted 1,007 or 1,008 tokens; injected transition tokens account
for the differing counting domains. Use native decoded tokens with native
decode duration. Both segment timing records and API counters are retained.

## Reproduce

```sh
python3 benchmarks/strata-mtp-window.py \
  --profile /path/to/private/serving-profile.json \
  --fixture /path/to/pinned/public/prompt.txt \
  --out /tmp/mtp-window \
  --live-url http://PRIVATE_HOST:8083 \
  --windows 4 6 8 4 --sizes 16384 65536 \
  --max-tokens 1024 --sampling-preset openclaw
python3 benchmarks/analyze-strata-mtp.py /tmp/mtp-window \
  --out /tmp/mtp-window-analysis.json
```

The runner requires idle serving, temporarily redirects the existing backend
unit to authenticated loopback 8084, and restores its original runtime override
in `finally`. It never calls OpenClaw. Profiles containing credentials stay
private. The public fixture and its pinned hash are linked in the
[performance record](STRATA-PERFORMANCE-2026-11-07.md).

[Raw results and accounting](../evidence/strata-performance-2026-11-07/mtp-window/).
