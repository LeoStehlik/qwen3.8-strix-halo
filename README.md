# Qwen3.8 inference on Strix Halo

Reproducible Qwen3.8 inference on AMD Ryzen AI Max+ 395 / Radeon 8060S systems.
This repository covers Strata and llama.cpp deployments, long-context
performance experiments, and OpenClaw integration. It includes both the
current Flash-Next work and the earlier 27B/DFlash2 deployment.

## Current work: Flash-Next on Strata

The active deployment, performance investigation and OpenClaw handoff are
on the `investigate/strata-performance-20261107` branch:

- [Flash-Next deployment guide](https://github.com/LeoStehlik/qwen3.8-strix-halo/blob/investigate/strata-performance-20261107/docs/STRATA-FLASH-NEXT.md)
- [Current handoff and serving state](https://github.com/LeoStehlik/qwen3.8-strix-halo/blob/investigate/strata-performance-20261107/handoff.md)
- [Performance objectives and evidence](https://github.com/LeoStehlik/qwen3.8-strix-halo/blob/investigate/strata-performance-20261107/docs/STRATA-NEXT-TARGETS-2026-11-07.md)

The instructions and measurements below describe the earlier 27B setup.
Use the linked Strata guide for Flash-Next.

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
The server is usable once a session is warm; OpenClaw must reduce and stabilise
its initial prompt to make a new session interactive.

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
