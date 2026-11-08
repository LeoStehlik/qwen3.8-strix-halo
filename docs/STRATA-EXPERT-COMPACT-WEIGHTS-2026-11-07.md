# Compact prepared weights: small warm gain, substantial preparation cost

The final stage-major Q4_K gate/up layout improves the complete expert operator
by **2.29%**, repeated in reverse order at **2.19%**. Checked outputs are exact.
It remains an undeployed research candidate: preparation inside each operation
makes it **26.2% slower in throughput**, and no live cache manager was built.
This does not establish a whole-model speedup or justify production integration.

## Mechanism and memory

Preserve every packed four-bit code and the original rounded FP16 scale/bias;
prepare the metadata once. Matrix products, activation quantization, accumulation
order, down projection and epilogue stay unchanged. The initial row-major
representation is neutral/slower. The final stage-major representation places
each 64-value stage's codes and scale pairs together for more contiguous loads.

Original gate/up storage is 1,843,200 bytes per expert; prepared storage is
2,048,000 bytes, **11.11% larger**. However, this prototype retains the original
copy, so the extra allocation is **1,000 MiB for 512 experts in one layer**.
Duplicating all 43 applicable Q4_K layers would add about 42 GiB. Spare RAM is
not equivalent to free bandwidth, nor does the representation's 11% growth
describe the prototype's additional resident allocation.

## Correctness and compiler inspection

All three source variants ran six original/control/candidate reference processes
at 64- and 128-row tiles. CPU-reference and row-ownership checks pass. All H
hashes are `c5cf77f999f3ac13`; final reference hashes are `79b8359e4299f6e5`.
All ten original compiled kernels remain instruction/resource-identical.

The initial local `uint4` variable caused 32 bytes of compiler scratch despite
zero reported register spills. Replacing it with scalar fetched components
removed scratch before performance testing. The final stage-major 128/64-row
kernels use 156/108 VGPRs, 22,144/13,696 bytes of LDS and no scratch. Lower
register allocation is not itself a measured occupancy or performance result.

## Complete-operator timing

16,384 tokens, 512 experts, top 10, synthetic weights/activations with captured
model routing. Cooperative epilogue is off. Each entry is the existing harness's
upper-middle sample of eight back-to-back GPU timings. Preparation is excluded
from warm samples; allocation is outside every measured GPU event.

| Screen | Controls ms | Candidate ms | Throughput vs mean controls |
|---|---|---|---:|
| Row-major, median padding | 58.630 / 57.815 | 58.928 | −1.20% |
| Stage-major, median padding | 57.534 / 57.850 | 56.399 | +2.29% |
| Stage-major, reversed order | 57.792 | 56.532 / 56.573 | +2.19% |
| Stage-major, most padding | 58.039 / 59.689 | 57.198 | +2.91% |
| Stage-major, prepare every operation | 57.867 / 57.946 | 78.483 | −26.22% |

The most-padding controls drift by 2.8%; its candidate still beats both, but
the +2.91% estimate is less stable than the repeated median case. All 15 timing
processes preserve their input-specific output hashes and pass sampled CPU
checks. The live server remained loaded and idle, with zero actual requests.

First stage-major preparation events took about 23–24 ms for one layer,
compared with roughly 1.2 ms saved per warm operation. First-use events can
include initialization/queue effects; the prepare-every-operation screen
independently demonstrates the overhead. A 64K prompt provides only four full
16K chunks per layer. Persistent reuse across requests would need memory
management and eviction policy, with a measured net benefit before integration.

## Reproduce and retain separately

Start from Strata `c3b3f5035506f3e966f1b4b7b188aeaabae92f1d`. Apply
`experiments/strata-cooperative-epilogue/cooperative-epilogue.patch`, then
`test-harness.patch` from that directory. Keep a control binary. Apply
`experiments/strata-expert-profile/compact-weight.patch`, and build
`hip_prefill_fused_iq` using the documented TheRock 7.14.1 environment.

```sh
python3 experiments/strata-expert-profile/compact-weight-run.py \
  --binary /path/to/candidate --control /path/to/control \
  --sdk /path/to/sdk --profile /private/serving-profile.json \
  --out /tmp/compact-reference --phase reference
python3 experiments/strata-expert-profile/compact-weight-run.py \
  --binary /path/to/candidate --control /path/to/control \
  --sdk /path/to/sdk --profile /private/serving-profile.json \
  --out /tmp/compact-warm --phase screen --routes /tmp/median.ids.i32 \
  --modes control compact control
```

Decompress routing inputs from the existing expert-profile evidence. Repeat with
`--modes compact control compact`, then the most-padding file. Add
`--prepare-each` for preparation-inclusive timing. The runner requires an idle
authenticated endpoint and checks that no serving requests arrive during tests.

`compact-weight-row-major.patch` and `compact-weight-initial-scratch.patch`
are independent alternatives to the final patch, not patches to stack. All
three reproduce eight measured source files from the pinned upstream plus the
two prerequisites. Only the HIP gfx1151 operator was built; no full-model,
cache, tools or other-backend validation is claimed for these source changes.

[Builds, references, timing, resource inspection and checksums](../evidence/strata-performance-2026-11-07/expert-compact-weights/).
