# Q5_1 decode down-projection scheduling experiment

Status: standalone and full-engine comparisons complete. The candidate improves
generation by **2.00% at 49K and 1.73% at 197K**, with matching output hashes and
passing synthetic tool/state checks. No prefill gain. Retained as an opt-in
research patch; nothing is promoted to the serving deployment.

## Why this operator

The November 11 external trace of the packaged engine preserves normal fusion,
graphs and shared-expert overlap. `native_down_kernel<7>` takes 2.676 seconds of
the 24.670-second observable generation window at 49K, and 2.842 of 26.563
seconds at 197K. These duration sums are about 10.8% and 10.7% of wall time;
they are not an exact critical-path attribution. Queue evictions contaminate
some dispatches; corresponding clean median distributions are retained.

This is a narrower target within routed experts. It cannot deliver 60–70 tok/s
by itself: even halving its entire duration saves only about 5.4% of wall time
before overlap and replacement costs. That makes a large operator improvement
potentially useful, not a route to the whole goal.

## Mechanism and contract

The Q5_1 expert down matrix has 2,560 output rows and 640 inputs. The current
32-lane row dot produces 40 partial dot products: eight lanes evaluate two
parts and 24 evaluate one. Test 16- and 8-lane rows, respectively doubling and
quadrupling rows per 256-thread block. Keep the same per-entry work, raw weight
layout and pointer/entry traversal. This changes scheduling and reduction
placement; it does not add a prepared-weight cache or change quantization.

The reduced-width row reconstructs the original lane-zero addition tree,
including its initial zero additions, before its smaller shuffle reduction.
The reference kernel and dot expression are extracted verbatim from the pinned
Strata source. `build.json` records source, extracted-header, probe and binary
hashes. This is a standalone operator experiment, not proof that a rebuilt full
engine is identical to the packaged executable.

Requirements before accepting a candidate:

- Bitwise equality against the reference for every checked output, including
  untouched sentinel rows; finite values in every owned row.
- An independent host dequantize/double-dot reference on first, middle and final
  rows of every entry, with aggregate relative L1 error below 2e-6.
- Empty first/interior/final groups, zero groups, 1–11 entries, non-contiguous
  output destinations, partial output-row boundaries, and group-grid strides.
- Graph replay timing with alternating control/candidate order, five trials,
  10/20/30/40 groups and 1/2/4 entries per group. Some dense synthetic combinations
  exceed the ordinary four-token window; report them as coverage, not live routing.
- One weight bank and four rotating banks to expose cache dependence. No
  preparation cost is hidden: this candidate has no weight-preparation pass.

The original kernel remains compiled and directly selectable in the same
binary. Stop if correctness fails. A small isolated gain does not authorize
deployment. Full engine integration would need actual routing, bracketing
controls, exact output/state/tool checks and unchanged default behavior.

## Reproduction

Use an idle GPU. The serving model may stay loaded, but do not run these probes
concurrently with real requests or the full-model profiling comparison.

```sh
python3 experiments/strata-decode-q51/build.py \
  --source /path/to/Strata-at-c3b3f5035506f3e966f1b4b7b188aeaabae92f1d \
  --sdk /path/to/rocm-7.14.1 --out /private/new-q51-build
/private/new-q51-build/q51-probe
/private/new-q51-build/q51-probe --bench
```

`--counter 32 40 1 4` selects 16 reference dispatches with 40 groups, one entry
per group and four rotating banks. Replace 32 with 16 or 8 for a candidate.
This mode is for a profiler after correctness has passed, not a correctness test.

Unique stored weight bytes divided by time are only a payload-rate proxy.
They do not count all memory requests or prove DRAM saturation. In particular,
GL2 outgoing request counters include traffic satisfied by the last-level cache;
they must not be relabelled as physical DRAM traffic. Counter collection can
serialize dispatches and its timings are not the unprofiled benchmark.

## Measured operator result

31 cases pass, including bitwise reference equality and row ownership. The
maximum checked CPU-reference relative L1 error is below 8e-8. The second timing
run records eviction inside each timed graph replay: 3 of 360 samples were
evicted, leaving 357 clean samples. The report retains all three outliers and
uses clean paired trials for speed ratios.

Representative medians with **four rotating weight banks**:

| Groups × entries/group | 32 lanes, µs | 8 lanes, µs | Operator throughput ratio |
|---|---:|---:|---:|
| 10 × 1 | 62.46 | 56.03 | 1.11× |
| 20 × 1 | 119.26 | 106.56 | 1.12× |
| 40 × 1 | 270.03 | 215.38 | 1.25× |
| 20 × 2 | 147.78 | 108.20 | 1.37× |
| 10 × 4 | 131.58 | 60.85 | 2.16× |

Warm-cache ratios are larger and must not be substituted for the rotating-bank
results. These are synthetic uniform groups. The live launch-capacity buckets do
not establish the actual per-expert multiplicity distribution.

For 40 groups × one entry, the counters report 49.219 MB of L2 outgoing reads in
the reference and 49.207 MB in the eight-lane kernel. Wave count falls from
102,400 to 25,600. VGPR count rises from 64 to 104; scratch remains zero. This
supports a scheduling gain with essentially unchanged outgoing read volume, not
a reduction in the weights being evaluated. It is not a DRAM-saturation result.

[All cases, flagged samples, counters and raw outputs](../../evidence/strata-research-2026-11-11/).

The [opt-in engine patch](q51-subwarp.patch) adds `STRATA_Q51_DOWN_SUB8=1` for HIP
Q5_1 rows with 640 inputs. Unset keeps the original path. The source tree used is
`c3b3f5035506f3e966f1b4b7b188aeaabae92f1d`; its engine source, headers, CMake and
third-party trees are identical to packaged engine source commit
`0bdcef4682c5371f7bcf130c41791c7849d78205`. The built engine also passes Strata's
`iq_multi_parity` suite with the switch enabled and `STRATA_EXPERT_V2K=0`, including
the Q4_K/Q5_1 and Q5_K/Q5_1 native expert paths. Full-model performance and
continuation tests are complete below. CUDA and other AMD GPUs are untested.

## Full-model result

| Context | Control | Candidate | Return control | Gain vs mean controls |
|---|---:|---:|---:|---:|
| 49K generation, tok/s | 41.88 | 42.70 | 41.85 | +2.00% |
| 197K generation, tok/s | 40.70 | 41.38 | 40.65 | +1.73% |

All corresponding prompt/output hashes match the packaged baseline, including
warm-up. At 197K all arms generate 1,024 native tokens with 427 windows and
879/597 offered/accepted drafts. At 49K they generate 1,006 native tokens plus
18 frontend-injected tokens, with 421/420/421 windows and 585/586/585 accepted
drafts. Do not describe the latter as identical speculative behavior; the cause
of the small work-count difference is unproven.

The candidate is measured once between two controls, without a profiler. All
three arms have the same 7 GiB conversation-cache budget; fully sampled
generation intervals record no queue evictions. Each arm passes exact tool
arguments, result continuation and interleaved checkpoint restoration, with
reused prefixes advancing from 11,614 to 11,782 tokens. These are synthetic API
canaries, not a live OpenClaw quality evaluation.

No prefill gain is demonstrated: 49K candidate/return control give 1,368.9/1,371.4
tok/s, and 197K arms range from 1,280.0 to 1,289.2. The slow first 49K control is
not evidence of a gain from this decode-only kernel.

The result falls below the program's approximately 5% promotion threshold.
Keep the patch available for research and restore the packaged deployment.
[Full comparison and restoration evidence](../../evidence/strata-research-2026-11-11/q51-engine-trial/).

## Full-engine build and comparison

Apply the patch to a separate checkout, not an installed engine. The measured
build used the following options (`STRATA_SRC`, `ROCM_LAB`, and `GGML_SRC` are
absolute paths selected by the person reproducing the experiment):

```sh
git -C "$STRATA_SRC" apply /path/to/q51-subwarp.patch
cmake -S "$STRATA_SRC" -B "$STRATA_SRC/build-halo-lab" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=OFF -DSTRATA_ENABLE_HIP=ON \
  -DCMAKE_HIP_COMPILER="$ROCM_LAB/lib/llvm/bin/clang++" \
  -DCMAKE_HIP_ARCHITECTURES=gfx1151 -DGPU_TARGETS=gfx1151 \
  -DCMAKE_PREFIX_PATH="$ROCM_LAB" -DCMAKE_HIP_FLAGS="--rocm-path=$ROCM_LAB" \
  -DSTRATA_BUILD_TESTS=OFF -DSTRATA_BUILD_DSV41=OFF -DSTRATA_BUILD_SPLIT=OFF \
  -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_PREFILL_MMQ=ON -DSTRATA_MMQ_KQUANTS=ON \
  -DSTRATA_AMD_COMMUNITY_TUNING=ON -DSTRATA_GGML_DIR="$GGML_SRC"
cmake --build "$STRATA_SRC/build-halo-lab" --target strata iq_multi_parity -j 2
```

The pinned GGML checkout is
`3cf03257f219afbe7334045ff7c6a06ac68c627d`. The SDK is TheRock 7.14.1 for gfx1151.
Run the parity executable with `STRATA_Q51_DOWN_SUB8=1`,
`STRATA_EXPERT_V2K=0`, and `LD_LIBRARY_PATH` pointing at the packaged 0.1.57
HIP-Halo libraries. Stage the built `strata` beside symlinks to those packaged
libraries and tuning files; do not replace any installed file. The harness
checks loaded runtime library paths and hashes.

Use the existing private profile only as input. Candidate mode creates private
arm copies using the staged executable and sets the switch only in the middle
arm; it restores the original service afterward:

```sh
python3 benchmarks/strata-decode-profile.py \
  --profile /private/strata-known-good.json \
  --terminal /path/to/terminal/0.1.57 --fixture /path/to/prompt.txt \
  --out /private/new-q51-engine-trial --profile-mode candidate \
  --engine /private/staged-engine/strata \
  --candidate-env STRATA_Q51_DOWN_SUB8=1 \
  --expected-results /path/to/packaged-control/results.json \
  --checkpoint-checks --sizes 49152 196608 --max-tokens 1024 --execute
```

The legacy arm label `profile` means the candidate in this mode; no profiler is
attached. Output counts affect synthetic probes only. `--expected-results`
requires both request and answer hashes to match the packaged baseline, including
the warm-up. The checkpoint checks run after timed probes and execute no real
tools. Run the controller under a transient systemd unit if its terminal/tool
session may disconnect. Its original incomplete manifest must be retained if
interrupted, even when service restoration subsequently succeeds.
