# Native INT8 conversion screen: not selected

2026-11-07, gfx1151. Two ways of replacing attention's K-side INT8 → FP32 →
FP16 conversion passed exhaustive value checks but **did not improve the
captured workload**. The candidate code was removed from the active source
branch. The serving engine and its configuration were never changed.

## Hypothesis and implementation

The earlier attention instruction trace showed repeated integer-to-float32
and float32-to-half conversions. The same GPU already emits signed-int16 to
half instructions in the V-side path. Every INT8 value, including −128, is
exactly representable in FP16, so removing the intermediate conversion does
not require a numerical tolerance.

The experiment used a separate opt-in kernel symbol and
`STRATA_PA_NATIVE_I8=1`. Its selector required gfx11, the existing trim-2
layout and read prefetch. The original wrapper and its default selection
remained intact. Prepared physical rows stayed **off** for both timing screens.

Two helpers were tested:

1. **Assembly:** sign-extend each byte, then `v_cvt_f16_i16_e64` with explicit
   low-half registers. The inline assembly output is converted to half bits.
2. **Vector:** construct 16 signed-int16 values, then use Clang's
   `__builtin_convertvector` to produce the FP16 fragment.

All **28 original attention kernels retained identical machine-code hashes**
after building either variant. That checks their instructions, not an entire
engine binary or an unbuilt backend. The experimental wrapper's arithmetic
after conversion was unchanged.

## Correctness and timing

The shared conversion helper passed **1,048,576 exact GPU/CPU comparisons**
for each variant: every one of 65,536 ordered byte pairs in all eight aligned
pair positions of a 16-value fragment. CPU expected half bits were constructed
with integer arithmetic; every encoded byte, including −128, was covered.
An output-buffer guard also passed.

Timing used the public layer-7 selection record at position 61,440, **4,096
queries**, gated FP16 output, synthetic Q/K/V values and real captured IDs.
Each screen used separate off/on/on/off processes, 31 GPU-timed repetitions
per process after a warm-up. The existing server remained loaded but idle;
request counters confirmed no endpoint traffic during the screens. Compare
within each screen, not against earlier timings with a different resident
memory state.

| Helper | Control process medians, ms | Candidate process medians, ms | Mean-based operator speedup |
|---|---:|---:|---:|
| Assembly | 26.779 / 26.476 | 26.355 / 27.083 | −0.34% |
| Vector | 26.004 / 26.833 | 26.941 / 27.488 | −2.92% |

All eight replay output hashes were **`03e1afd508d8a383`**, and gated-output
padding stayed intact. Neither form earns a full-model trial from these
results. No full-16K native-conversion replay, full-model/state test, combined
prepared-row experiment, CUDA build or gfx12 test was performed.

The disassembly explains why fewer conversions were not sufficient:

| Static instructions in the fast gated kernel | Control | Assembly | Vector |
|---|---:|---:|---:|
| INT32 → FP32 | 128 | 0 | 8 |
| FP32 → FP16 | 128 | 0 | 8 |
| INT16 → FP16 | 128 | 256 | 248 |
| All instructions | 2,946 | 2,884 | 2,985 |

The assembly form added packing work elsewhere, and the vector form increased
the total static instruction count. These are static counts, not dynamic
latency shares or a complete causal explanation. Code-object metadata reported
181 VGPRs and zero private scratch/spills for all three fast gated kernels;
the declared LDS size was also unchanged at 17,984 bytes. Allocation granularity
can make profiler resource figures larger than these declarations.

## Test-development findings

The first assembly spelling used 32-bit register operands and was rejected
by the compiler. Explicit low-half operands with the e64 encoding compiled.
No rejected build was benchmarked or served.

The first test exported `__builtin_bit_cast(uint16_t, h[i])` directly from a
vector component. Its generated IR and machine code repeated component zero,
so the CPU check failed immediately. Materializing `_Float16 scalar = h[i]`
before bit-casting exported each component correctly; both helpers then passed
the exhaustive check. The failed log and IR are retained. This was a test
export problem observed with the pinned compiler, not evidence that an unsafe
conversion should be accepted. No upstream issue was filed.

## Reproduction and cleanup

The [archived vector patch](native-i8-vector.patch) applies to pinned upstream
`c3b3f5035506f3e966f1b4b7b188aeaabae92f1d` after
`strata-attention-replay/gated-replay.patch` and
`strata-attention-rows/prepared-rows.patch`. That application chain was checked
in a temporary Git index. Build with the previously documented ROCm lab setup:

```sh
cmake --build "$BUILD" --target hip_pa_native_i8 hip_pa_bench -j 2
"$BUILD/hip_pa_native_i8"
STRATA_HIP_WMMA=1 STRATA_PA_FAST=1 STRATA_PF_SWITCH_MIN_T=4096 \
  PA_BENCH_GATE=1 PA_BENCH_ROWS=0 STRATA_PA_NATIVE_I8=0 \
  "$BUILD/hip_pa_bench" /tmp/record-019-layer-07-pos-61440.bin 31
STRATA_HIP_WMMA=1 STRATA_PA_FAST=1 STRATA_PF_SWITCH_MIN_T=4096 \
  PA_BENCH_GATE=1 PA_BENCH_ROWS=0 STRATA_PA_NATIVE_I8=1 \
  "$BUILD/hip_pa_bench" /tmp/record-019-layer-07-pos-61440.bin 31
```

Run in off/on/on/off order. To reproduce the assembly form, replace
`src/kernels/cuda/hip_native_i8_half.cuh` with this directory's
[archived helper](asm-helper.cuh) and rebuild both targets. Use the same
[published selection fixture](../../evidence/strata-performance-2026-11-07/attention-replay/record-019-layer-07-pos-61440.bin.gz)
as the earlier attention replay, decompressed to the path above. These are
rejected experimental sources, not deployment instructions.

At **19:36:29 UTC**, source was clean at `41021fb`; the rebuilt attention
object and replay executable matched their original SHA-256 hashes exactly.
The endpoint was idle, automatic clocks remained selected, and the independent
boundary-checkpoint live trial remained enabled with short-read 64 / stream
minimum 128. No restart, new OpenClaw turn or serving change occurred.
The [evidence](../../evidence/strata-performance-2026-11-07/attention-native-i8/)
contains commands, timings, conversion checks, instruction/resource counts,
control-code hashes and restoration checks. The raw-prefill target is unchanged.
