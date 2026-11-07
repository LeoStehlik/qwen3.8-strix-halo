# Prepared expert activations: no reliable gain

Extra memory capacity was sufficient, but preparing FP16 activations once did
not produce a repeatable speedup. Retain the code and evidence as a rejected
standalone experiment. No combined performance candidate was selected or
integrated, and nothing was deployed.

## Change and memory cost

The [instruction trace](STRATA-EXPERT-ATT-2026-11-07.md) identified repeated
INT8-to-FP16 activation conversion inside the expert kernels. The prototype
preserves the existing INT8 quantization, FP32 scale multiplication, FP16
rounding, matrix arithmetic and epilogues. It performs that conversion once,
stores the result, and uses a new activation loader in copied expert kernels.

Two independent harness switches select the work:

- `S20_PREPARED_X=1`: prepare the gate/up input once per input chunk. At 16,384
  tokens and 2,560 features, the extra buffer is **80 MiB**.
- `S20_PREPARED_H=1`: prepare populated intermediate rows after gate/up in each
  expert batch. At top 10 and 640 features, the extra buffer is **200 MiB**.

Together they require 280 MiB. All preparation launches are inside the timed
complete operator. Buffer allocation is outside timing. This experiment tests
the cost of extra reads/writes as well as conversion savings; available RAM
alone cannot determine the outcome. No production dispatch uses the new APIs.

## Validation and control preservation

Ten final reference processes covered original binary, rebuilt control, X,
H and both, at 64- and 128-row tiles. Existing CPU-reference and row-ownership
checks passed. Every intermediate byte hash was `c5cf77f999f3ac13`; every final
output bit hash was `79b8359e4299f6e5`. The skewed reference includes inactive
experts, partial rows and split expert batches. These are operator checks,
not a full-model quality or cache/state validation.

The first implementation put candidates in the control translation unit.
Although outputs matched, adding those definitions changed the compiler's
scheduling of the old down kernel. Moving candidates into a separate
`moe_f16_prepared.cu` resolved that confounder. The final **ten original kernel
instruction sequences and resource records match exactly**. Both earlier
failed isolation inspections are retained in evidence.

The prepared 128-row kernels use no scratch: gate/up uses 177 VGPRs and
22,144 bytes of static LDS; down uses 144 VGPRs and 23,168 bytes. These are
compiler metadata, not measured whole-GPU occupancy. `inspect-prepared.py`
records all variants and checks the control against the original code object.

## Complete-operator timing

Same gfx1151 / TheRock 7.14.1 setup, synthetic weights and activations, Q4_K /
Q5_1, 16,384 tokens, 512 experts, top 10. Routing is the captured median-padding
record from the public 64K fixture. Cooperative epilogue stays off. Each table
entry is the existing harness's median of eight back-to-back operator runs.
Independent processes reverse X/H order in the second pass; controls bracket
both passes. Serving was loaded and idle with zero real requests throughout.

| Pass | First control ms | X preparation ms | H preparation ms | Return control ms |
|---|---:|---:|---:|---:|
| Control / X / H / control | 57.561 | 56.966 | 57.995 | 57.750 |
| Control / H / X / control | 57.769 | 58.478 | 57.927 | 58.212 |

Relative to each pass's mean bracketing control, X changes throughput by
**+1.21% then −0.83%**; H by **−0.59% then +0.11%**. Neither establishes a
repeatable improvement. All eight full replay output hashes remain
`019f42e2855f67cc`, and sampled CPU-reference checks passed.

No combined performance run or further routing sweep was justified after
this screen. The combined path was checked for correctness only. The data
reject this implementation; they do not prove that every fused preparation
or alternative operand layout would fail. They also do not locate a hardware
ceiling or quantify exactly which cost cancels the saved conversion work.

## Reproduce

On clean Strata commit `c3b3f5035506f3e966f1b4b7b188aeaabae92f1d`, apply:

```sh
git apply /path/to/repo/experiments/strata-cooperative-epilogue/cooperative-epilogue.patch
git apply /path/to/repo/experiments/strata-cooperative-epilogue/test-harness.patch
# Build and retain this original operator binary/code object first.
git apply /path/to/repo/experiments/strata-expert-profile/prepared-act.patch
cmake --build build-halo-lab --target hip_prefill_fused_iq -j 2
```

Use the SDK/configure environment from the
[performance record](STRATA-PERFORMANCE-2026-11-07.md). A separate-index apply
check reproduced all eight relevant measured source files exactly with these
three patches; unrelated prior attention/tuning experiments are not required.
Only the standalone HIP gfx1151 target was built. CUDA, SYCL, other AMD targets
and full serving integration were not validated; this is not an upstream PR.

```sh
python3 experiments/strata-expert-profile/prepared-act-run.py \
  --binary /path/to/new/hip_prefill_fused_iq \
  --control /path/to/original/hip_prefill_fused_iq \
  --sdk /path/to/rocm-sdk --profile /path/to/private/serving-profile.json \
  --out /tmp/prepared-reference --phase reference
python3 experiments/strata-expert-profile/prepared-act-run.py \
  --binary /path/to/new/hip_prefill_fused_iq \
  --control /path/to/original/hip_prefill_fused_iq \
  --sdk /path/to/rocm-sdk --profile /path/to/private/serving-profile.json \
  --out /tmp/prepared-screen --phase screen \
  --routes /tmp/median.ids.i32 --modes control x h control
```

Repeat the screen with a new output directory and `--modes control h x control`.
The runner requires idle serving and checks request counts. It never calls
OpenClaw. Ignore the harness's placeholder MMQ time/ratio when `S20_NOMMQ=1`.
Use fused operator timings only.

[Results, commands, resource checks and build logs](../evidence/strata-performance-2026-11-07/expert-prepared-act/).
