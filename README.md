# Qwen3.8 inference on Strix Halo

Reproducible Qwen3.8 inference on AMD Ryzen AI Max+ 395 / Radeon 8060S systems.
This repository covers Strata and llama.cpp deployments, long-context
performance experiments, and OpenClaw integration. It includes both the
current Flash-Next work and the earlier 27B/DFlash2 deployment.

## Current work: Flash-Next on Strata

`main` is the canonical branch for deployment, performance evidence and the
Francis handoff. The completed deployment and investigation branches have been
consolidated here and retired.

- [Flash-Next deployment guide](docs/STRATA-FLASH-NEXT.md)
- [Current handoff and serving state](handoff.md)
- [Performance objectives and evidence](docs/STRATA-NEXT-TARGETS-2026-11-07.md)

The earlier 27B/DFlash2 setup remains documented below and in its installation
guide. Use the Strata guide above for Flash-Next.

## Current direction — 2026-11-08

The packaged Flash-Next deployment is persistent and enabled at boot, with a
pinned engine and automatic crash recovery. Normal restart took 87.3 seconds;
forced-process recovery took 96.3 seconds. Host reboot validation remains open.
No experimental source kernel is serving.

The [cache investigation](docs/STRATA-CACHE-MISSES-2026-11-08.md) found and fixed
avoidable rereading of changing OpenClaw runtime messages. The existing
`--tail-role-token 846` option preserved the needed history checkpoint. Public
control/candidate/control tests reduced follow-up time by **28–42%**, with
identical answers and passing tool/state restoration checks. Captured Discord
requests subsequently processed **72–84% fewer input tokens**. These are cache
savings, not a raw throughput increase or a sustained decode result.

The [generation assessment](docs/STRATA-DECODE-ASSESSMENT-2026-11-08.md) is now
complete: repeated normal runs give **41.42/40.95 tok/s at 49K** and
**39.85/39.80 at 197K**, with matching outputs. Sustained 60–70 has no demonstrated
path in the tested configuration; the hardware ceiling remains unproven. The
persistent endpoint is restored. The [handoff](handoff.md) records the deployment
and separates uncertain kernel research from validated changes.
The [compact-weight experiment](docs/STRATA-EXPERT-COMPACT-WEIGHTS-2026-11-07.md)
is archived: ~2.2% warm operator gain, but preparation-inclusive throughput
loses 26.2%. Deeper kernels remain [separate research](docs/STRATA-KERNEL-RESEARCH.md).

The later [OpenClaw skill-call failure](docs/OPENCLAW-TOOL-SURFACE-FAILURE-2026-11-08.md)
is a compact-tool interface mismatch: direct calls to hidden skill tools were
rejected and generic recovery failed. It predates the cache fix. Offline parser
reproduction passed; no live workaround or service change was applied.
Upstream already merged the relevant guidance and recovery fixes; the
investigation records their presence in `v2026.11.5-beta.1` source and absence
from the incident's 2026.10.9 version. No duplicate PR was created. Offline parser
checks alone do not establish model recovery on a fixed OpenClaw build.

### Earlier November 7 experiments

**Bounded follow-up authorized; retain the working baseline.** The higher target
of 1,700–2,000 tok/s prefill and 50–70 tok/s generation remains unmet; the
hardware ceiling is unproven. The latest tile changes lost performance. The
subsequent [MTP 4/6/8/4 screen](docs/STRATA-MTP-WINDOW-2026-11-07.md) also found
no reliable generation gain, so window 4 is restored. The subsequent
[expert trace](docs/STRATA-EXPERT-ATT-2026-11-07.md) motivated a
[prepared-activation prototype](docs/STRATA-EXPERT-PREPARED-2026-11-07.md):
exact outputs, but no repeatable operator gain in reversed-order comparisons.
The extra 280 MiB fits; this implementation is rejected. No source patch is
serving. The later [cost-aware MTP comparison](docs/STRATA-MTP-COST-2026-11-07.md)
also found no reliable gain; the original policy is restored. A
[selective prepared-weight cache](docs/STRATA-EXPERT-WEIGHT-CAPACITY-2026-11-07.md)
received capacity/routing analysis, followed by a separate operator test of a
[direct FP16 weight loader](docs/STRATA-EXPERT-PREPARED-WEIGHTS-2026-11-07.md).
It preserved checked outputs but lost even without expansion cost, including
in a favorable high-reuse case. No cache manager or new source kernel is serving. The earlier
[checkpoint](docs/STRATA-OPTIMIZATION-CHECKPOINT-2026-11-07.md) records the
decision to narrow this investigation.

The selected packaged
configuration reached 1,416 tok/s cold prefill at 64K, 1,363 at 128K and 1,301
at 192K, retaining the same model quantization and 262,144 context capacity.
Generation on that fixture is about 37–41 tok/s, below the 50–70 target.
The private Tiercel preview is loaded and reachable from the Mac mini.
The user approved the result of a real beta-release/co-authored-PR research
task; the first 13 live calls averaged 1,327 prefill / 47.2 generation.
Read the [updated objective](docs/STRATA-NEXT-TARGETS-2026-11-07.md).

The latest [projection-padding screen](docs/STRATA-PROJECTION-PADDING-2026-11-07.md)
measured a 3–4% benefit over explicitly disabling padding, with matching
outputs. **Correction:** padding was already enabled by Strata's hardware
defaults in our serving baseline; this is an ablation, not a new gain. The initial
[boundary-checkpoint trial](docs/STRATA-CACHE-LIVE-TRIAL-2026-11-07.md) was
superseded by the November 8 cache investigation above.

The expert-dispatch experiment was slower and is rejected with
[code and evidence](experiments/strata-f16-persistent-dispatch/README.md).
Residual write has modest measured bandwidth headroom, and matrix calibration
selected the kernels already shipped. Intermittent GPU queue eviction remains
unresolved. See the [performance record](docs/STRATA-PERFORMANCE-2026-11-07.md)
and [handoff](handoff.md).

Flash-Next UD-Q4_K_XL was deployed on packaged Strata v0.2.11 / HIP-Halo 0.1.57
and connected to OpenClaw's existing `tiercelmoe` provider. For the live preview, select
`/model qwen-flash-next`. The authenticated private API is
`http://100.96.8.54:8083/v1`, with 262,144 context, INT8 KV, MTP and vision enabled.
The Strata unit is enabled at boot with automatic restart;
the old dense 27B service remains stopped and disabled,
with all files retained for rollback.

Direct generation, exact tool/result continuation, streaming from the Mac mini
and Francis's live model catalog passed. OpenClaw applied the change without a
gateway restart. Real agent quality remains under evaluation; the initial
deployment was slow and had one native verification watchdog exit. Later
isolated cold 64K/128K measurements are recorded above.
See the [OpenClaw connection record](docs/STRATA-OPENCLAW-2026-11-07.md),
[first-load evidence](docs/STRATA-FIRST-LOAD-2026-11-07.md),
[deployment guide](docs/STRATA-FLASH-NEXT.md) and [handoff](handoff.md).
The [pre-reboot record](docs/STRATA-RECOVERY-2026-11-06.md) and
[successful GPU recovery](docs/STRATA-RECOVERY-RESULT-2026-11-06.md) preserve
November 6's incident and the active 112 GiB GTT configuration.

## Previous direction — 2026-11-05

Qwen3.8 GPU serving is restored after Qwen3.6 was retired from daily OpenClaw use.
The new focus is faster long-context prefill while retaining this model's observed
agent capability and configured context. A 64K diagnostic places 62.65% of GPU
time in quantized dense matrix multiplication and 20.20% in attention; existing
attention/fusion optimizations are already present. No new kernel was deployed.
Read the [investigation](docs/PREFILL-RETURN-2026-11-05.md) and [Francis handoff](handoff.md).

## Earlier 27B/DFlash2 deployment

A reproducible local deployment of Qwen3.8-27B on a Ryzen AI Max+ 395 / Radeon
8060S, using llama.cpp Vulkan, DFlash2 speculative decoding, vision, a 245,760
token context, exact-request coalescing, a 24 GiB prompt cache, and
on-demand Q4/Q5 model routing.

The service exposes an OpenAI-compatible endpoint on localhost by default:

```text
http://127.0.0.1:8080/v1
```

Two API model IDs are available:

| API model | Target quant | Intended use |
|---|---|---|
| `qwen3.8-27b-q4-fast` | UD-Q4_K_XL | Default, faster agent/chat traffic |
| `qwen3.8-27b-q5-quality` | UD-Q5_K_XL | Quality-sensitive requests |

Both targets share the Q4_K_M DFlash2 drafter and F16 vision projector. The
router keeps one target resident at a time; Q4 loads at startup and Q5 loads on
demand. A streaming front proxy collapses concurrent byte-identical inference
requests into one upstream generation, which avoids duplicate work from client
retries without caching completed responses.

## Earlier 27B measurements

On the reference 128 GB Strix Halo machine, the controlled DFlash width sweep
produced:

| DFlash width | Q4 decode | Q5 decode |
|---:|---:|---:|
| 2 | 21.61 tok/s | 18.59 tok/s |
| **4** | **24.87 tok/s** | **20.73 tok/s** |
| 6 | 20.36 tok/s | 17.23 tok/s |

Width 4 is therefore the deployed setting. Short-prompt throughput varies with
the workload and draft acceptance; observed Q4 runs ranged roughly from 23 to
31 tok/s. See [the benchmark record](docs/BENCHMARKS.md) before comparing these
numbers with another system.

A controlled four-client cold-prefill comparison also tested one, two and four
slots. One slot had the best first response (25.1 s), last response (100.9 s)
and aggregate delivered throughput. Two slots delayed the first response to
52.7 s; four delayed it to 102.6 s. Production therefore deliberately queues
independent requests in one slot while coalescing byte-identical concurrent
requests. More admission concurrency was slower on this Vulkan/DFlash2 stack.

Francis's first real OpenClaw trace exposed the more important application
bottleneck. A 152,781-token cold prompt took 9m32s, but the next ten cached
tool-loop turns had a 47.5-second median and eight completed inside one minute.
The server was usable once that session was warm. The current investigation
targets backend prefill and exact-prefix reuse while retaining OpenClaw tools
and useful context; reducing its initial prompt is not a prerequisite.

A later OpenCode run demonstrated useful Q5 coding-agent work. One high-reasoning
session produced four merged, CI-green security pull requests addressing eight
alerts. It generated 72,053 tokens across 122 model turns and reached 155,534
context tokens. Weighted decode fell from 21.68 tok/s below 25K context to about
14 tok/s beyond 100K, showing why successful work per hour and context growth
matter more than a short-prompt peak. See the
[OpenCode Q5 case study](docs/OPENCODE-Q5-CASE-STUDY.md).

For agent and tool-calling traffic, the current starting point is:

```json
{
  "temperature": 0.2,
  "top_p": 0.95,
  "top_k": 20,
  "min_p": 0.0,
  "presence_penalty": 0.0,
  "repeat_penalty": 1.0
}
```

Sampling is deliberately set by the client rather than globally by the server.
Thinking is enabled by default, and reasoning is preserved across tool turns.

## 27B/DFlash2 quick start

Prerequisites: x86-64 Linux, a Strix Halo iGPU accessible through `/dev/dri`,
`curl`, `git`, Python 3, the Hugging Face `hf` CLI, and the system Vulkan loader.

```bash
git clone git@github.com:LeoStehlik/qwen3.8-strix-halo.git qwen38-dflash2
cd qwen38-dflash2

./scripts/download-runtime.sh
./scripts/download-models.sh
./scripts/verify-install.sh
./scripts/install-service.sh
```

Enable user-service startup before login once, if desired:

```bash
sudo loginctl enable-linger "$USER"
```

Check the service:

```bash
systemctl --user status qwen38-dflash2
curl http://127.0.0.1:8080/health
./smoke-test.py qwen3.8-27b-q4-fast
```

Vision check:

```bash
./make-vision-card.py
./smoke-test.py qwen3.8-27b-q4-fast --image vision-test-card.bmp
```

Full installation and operational details are in [docs/INSTALL.md](docs/INSTALL.md).

## 27B configuration summary

| Setting | Value |
|---|---|
| Runtime | llama.cpp Vulkan portable v0.8.0, build 11001, commit `629d2f7b4` |
| Live checkpoint candidate | build 11003, commit `a82001bd3`; validated locally, not yet the portable download |
| KV context | 245,760 tokens |
| Active slots | 1 (winner of controlled 1/2/4-slot comparison) |
| Target KV | Q8_0 K and V |
| Draft KV | Runtime default F16 |
| Flash attention | On |
| Logical / physical batch | 2048 / 2048 |
| CPU threads | 16 generation, 16 batch |
| DFlash width | 4 |
| Vision floor | 1,024 image tokens |
| Public binding | `127.0.0.1:8080` by default; configurable with `QWEN_BIND_HOST` |
| Internal router | `127.0.0.1:8081` by default |
| Prompt cache | 24 GiB host-RAM cache with idle-slot caching |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the reasoning behind the
design and [docs/TUNING.md](docs/TUNING.md) for the remaining experiments.
The separate [ROCm/vLLM investigation](docs/ROCM-VLLM.md) records the planned
AMD MXFP4/DFlash2 comparison without changing the known-good Vulkan service.
The [experimental Qwen3.6 ROCmFP4/MTP fast path](docs/QWEN36-ROCMFP4-MTP.md)
records the separate Strix-specific MoE deployment that reached 101 tok/s at
32K depth and supports tools, vision, streaming, and RAM prefix restoration.

Current Qwen3.6 development now lives in the separate
[Qwen3.6 35B-A3B Strix Halo repository](https://github.com/LeoStehlik/qwen3.6-35b-a3b-strix-halo).
It contains the ordered source patches, 64K prefill experiments, validation
limits, deployment instructions, and [Francis handoff](https://github.com/LeoStehlik/qwen3.6-35b-a3b-strix-halo/blob/main/handoff.md).
The Qwen3.6 page here remains the historical 2026-10-31 deployment snapshot.

## Repository contents

| Path | Purpose |
|---|---|
| `models.ini` | Router presets shared by Q4 and Q5 |
| `run-router.sh` | Production launcher and artifact checks |
| `coalescing-proxy.py` | Streaming exact-request single-flight proxy |
| `run-server.sh` | Simpler single-target launcher |
| `smoke-test.py` | Text and vision API smoke test |
| `tool-temperature-test.py` | Small tool-selection sampling probe |
| `dflash-width-bench.py` | Repeatable DFlash throughput/acceptance probe |
| `concurrency-bench.py` | Concurrent-slot and duplicate-coalescing probe |
| `prefill-fairness-bench.py` | Short decode latency during a cold long prefill |
| `make-vision-card.py` | Dependency-free generated vision fixture |
| `scripts/` | Pinned downloads, validation, service installation |
| `systemd/` | Portable user-service template |
| `docs/` | Cookbook, results, decisions and roadmap |

Model files, extracted runtime binaries, virtual environments and generated
fixtures are intentionally excluded from Git.

Capture the non-sensitive environment details needed with a benchmark report:

```bash
./scripts/capture-environment.sh
```

## Documentation

- [Installation cookbook](docs/INSTALL.md)
- [Architecture and decisions](docs/ARCHITECTURE.md)
- [Benchmarks and validation](docs/BENCHMARKS.md)
- [Tuning cookbook and roadmap](docs/TUNING.md)
- [ROCm and vLLM investigation](docs/ROCM-VLLM.md)
- [Experimental Qwen3.6 ROCmFP4/MTP fast path](docs/QWEN36-ROCMFP4-MTP.md)
- [OpenClaw, OpenCode and OpenWork benchmark plan](docs/AGENT-CLIENT-BENCHMARKS.md)
- [OpenCode Q5 security-remediation case study](docs/OPENCODE-Q5-CASE-STUDY.md)
- [OpenClaw integration](docs/OPENCLAW.md)
- [Sanitized OpenClaw live trace](docs/OPENCLAW-LIVE-TRACE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Sources and references](docs/REFERENCES.md)
- [Security](SECURITY.md)
- [Contributing benchmark results](CONTRIBUTING.md)

## License and third-party artifacts

The original scripts and documentation in this repository are released under
the [MIT License](LICENSE). Third-party models and runtime binaries are not
redistributed or relicensed; the installation scripts download them from their
original publishers and verify exact SHA-256 hashes. Review the respective
upstream licenses before use or redistribution.
