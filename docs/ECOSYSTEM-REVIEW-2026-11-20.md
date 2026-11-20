# Strix Halo inference review — 20 November 2026

Research window: 6–20 November 2026. Target: Ryzen AI Max+ 395 / Radeon 8060S
(`gfx1151`), 128 GB unified memory, Linux. This is a source review, not a local
qualification of another engine. External benchmark numbers below must not be
presented as gains measured on this deployment.

## Decision

Keep Qwen3.8 Flash-Next as the primary model candidate. Its observed agent
capability is more useful than a faster model that needs tool-use hand-holding.
Test packaged Strata v0.2.17 / engine 0.1.63 against the retained v0.2.11 /
engine 0.1.57 baseline first. Halogen 0.20.7 is the strongest subsequent
performance lead; Gufo 0.35.0 is an open-source alternative using the existing
UD-Q4_K_XL target format. No engine comparison in this report is yet promoted.

This is a bounded release evaluation, not a reopening of the completed custom
kernel research program. The historical controls measured cold prefill of
1,416 / 1,363 / 1,301 tok/s at 64K / 128K / 192K. Live generation generally falls
around 40–50 tok/s, depending on prompt, sampling and speculative acceptance.

## Engine developments

### Halogen 0.20.7 — 18 November

[Published measurements](https://github.com/peonist-ai/halogen-flash-server/blob/main/docs/performance.md)
use Ryzen AI Max+ 395 / 128 GB, Ubuntu kernel 7.0, about 85 W sustained package
power, the engine's own v2 checkpoint, greedy decoding and thinking disabled.

| Workload | Published result |
|---|---:|
| Cold synthetic prefill, 8,192 tokens | 1,983 tok/s |
| Cold synthetic prefill, 32,768 tokens | 1,876 tok/s |
| Cold synthetic prefill, 131,072 tokens | 1,796 tok/s |
| English prose generation | 70.2 tok/s |
| Agent tool-call generation | 87.6 tok/s |
| Writing code | 100.2 tok/s |

These are not our sampling settings or our quantization. The
[precision documentation](https://github.com/peonist-ai/halogen-flash-server/blob/main/docs/precision.md)
lists a 62.1 GiB main checkpoint, 47.7 GiB paged n-gram table and 1.39 GiB drafter.
The main checkpoint is about 4.16 bits/weight; the table is accounted separately.
Quality must be checked on representative agent tasks, not inferred from speed.

The [November changelog](https://github.com/peonist-ai/halogen-flash-server/blob/main/CHANGELOG.md)
adds faster drafting, better concurrent throughput, reply-end caching, a fix for
shared prefixes just beyond 32,768-token boundaries, and a fix for stale cached
state being reused across concurrent conversations. Version 0.20.7 makes the new
concurrency mode default for its supported native checkpoints. Its ROCm 10.1
image reports 9–15% less package energy at similar generation speed.

The default cache resumes at message/request boundaries and does not promise
bit-identical cold/warm answers; fixed-checkpoint mode does. This is a measured
numerical trade, not proof of an agent-quality regression or of quality parity.
[Cache modes and validation](https://github.com/peonist-ai/halogen-flash-server/blob/main/docs/configuration.md#choosing-a-cache-mode).

Do not apply the native-checkpoint headlines to our existing GGUF. Its
[GGUF documentation](https://github.com/peonist-ai/halogen-flash-server/blob/main/docs/gguf.md)
retains a concurrent UD-Q4_K_XL empty-response warning.
[Issue #172](https://github.com/peonist-ai/halogen-flash-server/issues/172) was
closed as not planned on November 3; the reporter later found chat-completions
worked, but the documented warning remains. Test the actual API and overlapping
requests if evaluating this route.

### Strata 0.2.12–0.2.17 — 7–20 November

The [latest release](https://github.com/Niko1221/Strata/releases/tag/v0.2.17)
contains Terminal 0.2.17 and engine/control 0.1.63. Our baseline is Terminal's
0.1.57 bundle from release v0.2.11; package and engine version numbers differ.

- [0.2.12](https://github.com/Niko1221/Strata/releases/tag/v0.2.12): tuned DFlash2
  drafter, Halo prefill kernels and tool-call fixes. The published Halo speed
  comparisons are Windows measurements; Linux Halo was not exercised there.
- [0.2.13](https://github.com/Niko1221/Strata/releases/tag/v0.2.13): revised
  DFlash2 defaults, including a larger Halo window.
- [0.2.14](https://github.com/Niko1221/Strata/releases/tag/v0.2.14): Strata's own
  prefill kernels. Windows Halo UD-Q4_K_XL measured 32,000 prompt tokens in
  19.151 seconds (about 1,671 tok/s) and mean generation 54.47 tok/s with DFlash2.
  The comparison includes a drafter change; it is not an isolated kernel gain.
- [0.2.16](https://github.com/Niko1221/Strata/releases/tag/v0.2.16): engine code
  no longer uses ggml/llama.cpp matrix kernels; serving/startup fixes.
- [0.2.17](https://github.com/Niko1221/Strata/releases/tag/v0.2.17): route-tail
  skipping disabled by default after quality reports, plus Linux/HIP and
  serving fixes. Our existing service already explicitly disables this skip.

These releases justify a Linux test, not a promised performance uplift.

### Gufo 0.35.0 — 17 November

[Release notes](https://github.com/gufo-org/gufo/releases/tag/v0.35.0) include
Flash-Next draft-head optimization, cache retention/transfers, and NPU support
for embeddings and speech. Gufo is MIT-licensed and supports the existing
Unsloth UD-Q4_K_XL format with its shared-Q8 MTP companion.

An [independent operator's November 17 measurements](https://github.com/huppiflupp/strix-halo-llm-speeds)
report 1,678 / 1,748 tok/s at approximately 3.7K / 15.9K prompts, 70.1 tok/s for
greedy code, and 34.0 / 47.7 / 37.5 tok/s for sampled German prompts. Those are
shorter contexts than our hard cases, with a different harness. Their prose
numbers do not establish a decode gain over our deployment.

Gufo's official long-depth tables remain dated October 18. They measure a
small new prompt after a cached prefix, not a cold 128K prefill. Do not relabel
them as new November measurements or directly compare them to a full cold run.

## Models and adjacent developments

- **Qwen3.8 Flash-Next:** remains the first choice to evaluate across engines;
  capability is already operationally useful here.
- **Ripple-65B Preview:** model published just before this review window.
  [GGUF compatibility was corrected November 13](https://huggingface.co/prometheusAIR/Ripple-65B-Preview-GGUF).
  Q6_K weights are 49.50 GiB and Q8_0 64.11 GiB, leaving room for runtime state
  on 128 GB. It is a dense 65B model, so fitting is not evidence of low latency.
  No qualified Halo speed result was found. Treat as a capability experiment.
- **Recursive Flint:** October model, not a new fortnight release. About 40B
  total / 2.5B active, approximately 21 GB INT4. Halogen's
  [separate preview](https://github.com/peonist-ai/halogen-flash-server/blob/main/docs/flint-preview.md)
  reports 2,450 tok/s prefill and 75 tok/s decode at 32K, but prefill falls to
  around 900 tok/s at 256K. The preview predates current Halogen fixes. It is
  not yet a demonstrated replacement for Francis.
- **Qwen4:** [Max launched November 16](https://qwen.ai/blog?id=qwen4-max).
  Smaller open models are announced as forthcoming; this is a watchlist item,
  not an available local model recommendation.
- **GLM-5.3-Flash / DeepSeek V4.1 Flash:** neither is new in this fortnight.
  Aggressive GLM quants can approach the memory budget, but fit alone does not
  establish quality or useful long-context speed. DeepSeek's large resident
  footprint/SSD-streaming cost still makes it a poor first choice for this
  interactive deployment. No new verified result overturning that was found.
- **Lemonade 2026.46.2, November 11:**
  [container integrations](https://github.com/lemonade-sdk/lemonade/releases/tag/v2026.46.2)
  make Halogen, Gufo, strix-llama, Nathan's fork, ROCmFPX and DwarfStar easier
  to try. Packaging convenience is not itself an inference speed increase.

## Local trial protocol

1. Preserve the existing package, private profile and persistent unit.
2. Acquire and verify signed v0.2.17 packages while the working server serves.
3. Use an exclusive GPU window and isolated loopback listener. Run the same
   public cold 64K/128K fixtures against both engines, recording actual uncached
   tokens, native prompt/decode time, client latency, output hashes and residency.
4. Keep engine-only/MTP comparisons separate from a DFlash2 policy change.
   Evaluate temperature 0.2 with thinking separately from greedy timing probes.
5. Verify exact typed tool arguments, tool-result continuation, interleaved
   conversation/cache restoration and a prompt above 150K before promotion.
6. Restore a working endpoint on success or failure. Publish the result and
   exact version/configuration; do not infer readiness from `/health` alone.

The user authorized this release trial after reviewing the findings. Existing
model files and prior research are retained. OpenClaw gateway configuration,
Discord routing and the main/Telegram session are outside this release trial.
