# Experimental Qwen3.6 35B-A3B ROCmFP4/MTP fast path

**Historical deployment snapshot, 2026-10-31.** Current Qwen3.6 source patches,
64K prefill measurements, validation decisions and operational state are now
maintained in the separate
[Qwen3.6 Strix Halo repository](https://github.com/LeoStehlik/qwen3.6-35b-a3b-strix-halo),
including its [Francis handoff](https://github.com/LeoStehlik/qwen3.6-35b-a3b-strix-halo/blob/main/handoff.md).

This is the high-throughput companion to the Qwen3.8 Q4/Q5 deployment. It uses
Strix-specific Vulkan ROCmFP4 kernels and the model's native MTP head. It is a
separate runtime and API endpoint because the ROCmFP4 tensor type is not
supported by the Qwen3.8 llama.cpp build.

Validated on the reference Ryzen AI Max+ 395 / Radeon 8060S / 128 GB machine on
2026-10-31. This is an experimental community stack, not upstream llama.cpp.

## Pinned artifacts

| Component | Pin |
|---|---|
| Runtime source | `charlie12345/rocmfp4-llama`, branch `mtp-rocmfp4-strix` |
| Runtime commit | `4795079b04f5e0ada6e5d2e85b12bac1e27e7873` |
| Model repository | `plunderstruck/Qwen3.6-35B-A3B-MTP-ROCmFP4-GGUF` |
| Model | `Qwen3.6-35B-A3B-MTP-ROCmFP4-STRIX-embF16-headQ6.gguf` |
| Model SHA-256 | `a6775c0ff1d215f8385505d5b334ce8b81d6f70ff293a095c948c7f3d8b85a4c` |
| Vision projector | `mmproj-F32.gguf` |
| Projector SHA-256 | `2c52a4ccbc8f0fdb716fb526bfee9506ed0092b2e6dc5d593759f7d200146663` |
| Chat template SHA-256 | `27d22ab352efbb63cdcc379cc58924f16b2949931e6f185b959f8930efc9520b` |

Sources:

- <https://github.com/charlie12345/rocmfp4-llama/tree/mtp-rocmfp4-strix>
- <https://huggingface.co/plunderstruck/Qwen3.6-35B-A3B-MTP-ROCmFP4-GGUF>
- <https://github.com/hec-ovi/llama-vulkan-strix/blob/main/docs/qwen3.6-35b-a3b-mtp-rocmfp4.md>

## Build

The working source tree is `/home/less/src/rocmfp4-sparse`; binaries are in
`build-vulkan/bin`. The important detail is to set the release flags explicitly.
This branch otherwise produced binaries with assertions and compiler
optimisation disabled even with `CMAKE_BUILD_TYPE=Release`.

```bash
cmake -S . -B build-vulkan -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG' \
  '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG' \
  -DGGML_VULKAN=ON \
  -DGGML_NATIVE=ON

cmake --build build-vulkan --target llama-server llama-bench -j 16
```

The resulting runtime detected RADV `STRIX_HALO`, Vulkan integer-dot support,
and `KHR_coopmat`. It was built with GCC 15.2 and glslc 2026.1. The service sets
`GGML_VK_PREFER_HOST_MEMORY=1`.

## Measured performance

The old Qwen3.8 target was unloaded for every controlled run. One slot was used.

### Raw llama-bench, no MTP

Command shape: `-dev Vulkan0 -ngl 999 -fa 1 -ub 1024 -p 2048 -n 128 -r 3`.

| Build | pp2048 | tg128 |
|---|---:|---:|
| Accidental unoptimised build | 1,130.61 tok/s | 74.91 tok/s |
| Explicit `-O3 -DNDEBUG` Release build | **1,164.48 tok/s** | **77.47 tok/s** |

### Native MTP server

The apples-to-apples 32K test used F16 target and draft KV, `-b 2048`,
`-ub 1024`, `--spec-draft-n-max 5`, and `--spec-draft-p-split 0.10`.

| Workload | Result |
|---|---:|
| 28,761-token prompt prefill | 838.91 tok/s |
| Decode at 28,761-token depth | **101.16 tok/s** |
| Predictable technical prose | **129.92 tok/s** |
| Code-oriented generation | **100.63 tok/s** |
| Less predictable continuation | 69.79 tok/s |

MTP speed depends on draft acceptance, so the useful measured band is roughly
70-130 tok/s rather than one fixed number. The 32K result closely reproduces the
published 101 tok/s figure. It is still far above the 35 tok/s acceptance floor
for every tested workload.

### API capabilities

| Check | Result |
|---|---|
| OpenAI streaming | Passed; `STREAMING_OK`, 0.110 s HTTP first byte |
| Function selection | Correct `get_weather({"city":"Prague"})` call at 114.62 tok/s |
| Vision | Correctly identified an orange tabby cat; 84.33 tok/s decode |
| Vision prompt processing | 2,524 tokens at 250.92 tok/s |

The first-byte number includes streamed reasoning chunks; visible answer latency
also depends on how long the model reasons before emitting normal content.

## Prefix-cache result

Production enables a 24 GiB RAM prompt cache, idle-slot caching, 32 context
checkpoints, and a checkpoint every 8,192 tokens. A 28,759-token cold prompt
took 36.65 seconds at 784.64 tok/s. A second request with the same long prefix
reused 27,731 tokens and processed the remaining 1,028 tokens in 2.13 seconds.

After an unrelated prompt displaced the active slot, the same long prefix still
restored 27,731 cached tokens from RAM and completed residual prefill in 2.17
seconds. This is a measured 17x reduction in repeated-prefix prefill time. The
checkpoint machinery costs about 6.5% on the cold 28.8K prefill versus the
cache-disabled benchmark; the warm-prefix saving is much larger.

Clients must send `cache_prompt: true` and keep the stable prefix byte/token
identical to obtain this result.

## Deployed service

The user service is `qwen36-rocmfpx.service` and currently exposes:

```text
http://100.96.8.54:8082/v1
model: tiercel-qwen36-a3b-fast
```

The production configuration uses:

- 131,072-token context, one slot
- F16 target and MTP KV for throughput
- Vulkan ROCmFP4 body and native MTP, maximum draft width 5
- 1,024 minimum vision tokens and the F32 projector
- temperature 0.3, top-k 20, top-p 0.95, min-p 0.05
- 24 GiB RAM prompt cache and 8K checkpoints

With the model and projector loaded, measured GTT use was 27.1 GiB and system
memory still showed 83 GiB available. Both Qwen3.8 targets were API-unloaded.

The Qwen3.8 router remains running without a resident model. Use its model API
to load Q4 or Q5 when switching back; stop or unload the Qwen3.6 service first
when maximum bandwidth isolation matters. Do not run heavy generation on both
stacks concurrently: they share unified-memory bandwidth.

## Caveats and next tests

- Correctness and stability still need longer OpenClaw/OpenCode runs.
- Measure tool-loop throughput and MTP acceptance on representative agent work,
  not only synthetic prompts.
- Benchmark 64K, 128K, and compaction/restore behavior under real OpenClaw
  prefixes.
- Compare this Vulkan route with ROCm/vLLM only after preserving this result as
  the reproducible baseline.
- The source fork and model are experimental community artifacts; preserve the
  commit and hashes above before upgrading either.
