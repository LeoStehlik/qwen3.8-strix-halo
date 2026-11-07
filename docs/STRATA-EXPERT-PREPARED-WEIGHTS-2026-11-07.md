# Prepared FP16 expert weights: reject this loader

The standalone prepared-weight prototype preserved the checked outputs but
lost performance even with expansion excluded. It also lost in a deliberately
favorable high-reuse case. Do not build a live cache around this implementation.
The packaged endpoint remains unchanged; no source engine was deployed.

This tests the next step after the
[capacity analysis](STRATA-EXPERT-WEIGHT-CAPACITY-2026-11-07.md), independently
of the earlier rejected prepared-activation path.

## What changed

The experiment expands Q4_K gate/up and Q5_1 down weights into natural-row FP16
buffers. The gate/up expansion retains the original separately rounded FP16
scale/bias and FP16 FMA; codes 0–31 are exactly representable as FP16. Down
uses its original FP16 scale/bias and the same FMA. Activations and intermediate
H keep their existing INT8 quantization. Matrix accumulation and epilogues
retain the existing order.

A new kernel loads FP16 weights directly into the matrix operands. Only
activations pass through LDS. It is a simple direct loader, not a tuned BLAS
implementation or a new asynchronous weight pipeline. `S20_PW_GU=1` and
`S20_PW_DOWN=1` independently select the two paths in the standalone harness.
Production continues to call the original APIs.

All expert copies are prepared for **one benchmark layer**. At 512 experts,
gate/up requires 3.125 GiB extra and down 1.5625 GiB. The combined reference
check uses 64 experts and 600 MiB. There is no attempt to allocate the 225 GiB
needed to expand the whole model while retaining its quantized copies.

## Validation and compiled resources

Ten reference processes cover original binary, rebuilt control, gate/up,
down and both at 64- and 128-row tiles. Existing CPU-reference and row-ownership
checks pass, including inactive experts, partial tiles, split expert ranges,
unrelated two-byte-aligned weight pointers and a zero activation row.
Every intermediate hash is `c5cf77f999f3ac13`; every final reference output
hash is `79b8359e4299f6e5`.

The candidate is in a separate translation unit. All ten original K-quant
kernel instruction sequences and resource records match the traced control
exactly. The prepared 128-row kernels use **134 VGPRs, 17,024 bytes of static
LDS and no scratch**. The 64-row variants unexpectedly use 206/204 VGPRs for
gate/up/down, also without scratch. Resource counts are not measured occupancy
and did not predict the runtime result.

Only the HIP gfx1151 operator target was built with TheRock 7.14.1. Q5_K gate/up,
other formats/backends, full-model quality, tools and cache restoration were
not validated. Q4_K/Q5_1 represents 43 of the selected model's 48 expert layers.

## Warm complete-operator results

16,384 input tokens, top 10, synthetic weights and activations, original
cooperative epilogue off. Entries are the existing harness's upper-middle
sample of eight back-to-back GPU timings. Preparation occurs once before the
timed warm samples. Controls bracket the independent candidates.

| Routing regime | First control ms | Prepared gate/up ms | Prepared down ms | Return control ms |
|---|---:|---:|---:|---:|
| Captured median-padding record, 512 experts | 58.414 | 105.311 | 63.018 | 57.863 |
| Uniform routing over only 16 experts | 52.926 | 55.198 | 55.743 | 53.641 |

Relative to the mean controls, complete-operator throughput falls **44.8% /
7.7%** for gate/up/down in the captured distribution, and **3.5% / 4.4%** in
the concentrated case. The latter gives about 10,240 routed rows per expert
on average and stores only 100/50 MiB for the independent gate/up/down copies.
It is intentionally favorable to reuse and is not the model's actual routing.

All captured-distribution output hashes remain `019f42e2855f67cc`; all
concentrated-case hashes are `5e88cd6dd4ef2076`. Each timing process also passes
the sampled CPU-reference checks. Serving stays loaded and idle with zero
actual requests during the tests; the runner checks this and host memory
headroom before each process.

## Preparation cost and decision

The first expansion events were also recorded: 184.6/71.2 ms for gate/up/down
at 512 experts, and 3.5/90.0 ms at 16 experts. The anomalously slow small down
expansion makes clear that these first-use events are **not stable conversion
throughput estimates**. They include initialization/queue effects not isolated
by this screen; no cause is assigned. Allocation is outside those GPU events.

The harness supports `S20_PW_EACH=1` to put expansion inside every operator
iteration, but no such cold screen was run after both independent warm paths
lost. No combined performance run or selective-cache manager was justified.
The combined path was exercised for correctness only.

Extra weight traffic and the changed load pipeline are plausible contributors;
no counter trace here isolates their shares. This rejects **this direct FP16
loader**, not every possible prepared representation or tiled GEMM. It does
not establish a hardware ceiling. A future compact representation would need
its own measured benefit before reviving the cache idea.

## Reproduce

Start with clean Strata `c3b3f5035506f3e966f1b4b7b188aeaabae92f1d`, then apply
the existing cooperative-epilogue and test-harness patches as in the
[earlier reproduction](../experiments/strata-cooperative-epilogue/README.md#reproduce).
Keep the cooperative switch off. Retain that original binary before applying
`experiments/strata-expert-profile/prepared-weight.patch`, then rebuild:

```sh
cmake --build build-halo-lab --target hip_prefill_fused_iq -j 2
python3 experiments/strata-expert-profile/prepared-weight-run.py \
  --binary /path/to/new/hip_prefill_fused_iq --control /path/to/original/hip_prefill_fused_iq \
  --sdk /path/to/rocm-sdk --profile /path/to/private/serving-profile.json \
  --out /tmp/weight-reference --phase reference
python3 experiments/strata-expert-profile/prepared-weight-run.py \
  --binary /path/to/new/hip_prefill_fused_iq --control /path/to/original/hip_prefill_fused_iq \
  --sdk /path/to/rocm-sdk --profile /path/to/private/serving-profile.json \
  --out /tmp/weight-median --phase screen --routes /tmp/median.ids.i32 \
  --modes control gu down control
```

For the favorable reuse case, omit `--routes`, use a new output directory and
add `--experts 16`. Use `inspect-prepared.py --candidate-source moe_f16_weights`
with the source, SDK, original code object and output arguments to reproduce
instruction/resource inspection. Ignore placeholder MMQ timing when disabled.
The patches reproduce the relevant measured sources from the pinned upstream
revision; unrelated attention experiments are unnecessary.

[Build, reference, timing and resource evidence](../evidence/strata-performance-2026-11-07/expert-prepared-weights/).
