# Measured Flash-Next performance envelope

This is a bounded hardware/model accounting study, not a faster deployment.
See the [findings](../../docs/STRATA-PERFORMANCE-ENVELOPE-2026-11-12.md) and
[measurements](../../evidence/strata-envelope-2026-11-12/).

The normal model, quantization, MTP settings, context capacity and OpenClaw
routing are preserved. Exclusive runners stop an idle serving process and
restore it afterward; schedule a maintenance window before using them.
Private profiles contain credentials and must not be committed.

## Pinned components

- Source: Strata `c3b3f5035506f3e966f1b4b7b188aeaabae92f1d`.
- GPU compiler/SDK: TheRock 7.14.1, target `gfx1151`.
- Packaged control: engine `0.1.57-linux-x86_64-hip-halo`, SHA-256
  `bce2f61ca0f970a1640aafa77925c0908f060243cffcd1ad10e3843b35eed476`.
- Model: existing four Unsloth UD-Q4_K_XL GGUF shards and native Strata pack.
- Probe fixture and sampling: same public source-text fixture and
  `decode-profile-20261108` nonce seed as the November 11 controls.

The reporting binary used the already built November 11 research checkout,
including its Q5_1 opt-in patch **with that switch unset**. The new reporting
patch changes only reporting. Exact public output hashes are checked against
the preserved control. The isolated source build uses the packaged runtime
libraries, copied/symlinked beside its binary as in the
[Q5_1 reproduction](../strata-decode-q51/README.md).

## Standalone calibration and operators

Substitute local paths; these commands build artifacts and do not stop serving:

```sh
python3 experiments/strata-envelope/build.py \
  --sdk /path/to/rocm-sdk --out /private/calibration-build

# Requires libstrata_kernels.a and libstrata_core.a already built in
# the pinned source's build-halo-lab directory.
python3 experiments/strata-envelope/build-q8.py \
  --source /path/to/Strata --sdk /path/to/rocm-sdk --out /private/q8-build

python3 experiments/strata-projection-grouping/build.py \
  --source /path/to/Strata --sdk /path/to/rocm-sdk --out /private/projection-build
```

`calibrate all` measures three working-set sizes and three dispatch sizes,
with seven trials. `calibrate counter 2` / `counter 512` select a read-only
counter qualification. All memory and arithmetic outputs are validated.
The device report's HIP multiprocessor field is not labelled CU count.

The Q8 probe rotates at least 128 MiB of matrices for each shape and tests
one, three and four columns. It registers packed weights only where the
deployed loader does, retaining the vocabulary head's original layout.
Independent CPU samples compare against the *quantized* activations; packed
results additionally require bitwise equality to the original-layout GPU path.
Quantization, registration and output validation are outside the timed region.
The probe reports every sample's self queue-eviction delta.

`exclusive.py` accepts a JSON array of named commands, for example:

```json
[
  {"name":"calibration-first","argv":["/private/calibration-build/calibrate","all"]},
  {"name":"q8-first","argv":["/private/q8-build/q8"],
   "env":{"STRATA_Q8_PACKED":"1","STRATA_TSUM":"1"}},
  {"name":"projection-reference","argv":["/private/projection-build/grouping","--check"]},
  {"name":"projection-qkv","argv":["/private/projection-build/grouping","10240","2560","0","7"]},
  {"name":"projection-gate","argv":["/private/projection-build/grouping","6144","2560","0","7"]},
  {"name":"projection-out","argv":["/private/projection-build/grouping","2560","6144","64","7"]},
  {"name":"q8-return","argv":["/private/q8-build/q8"],
   "env":{"STRATA_Q8_PACKED":"1","STRATA_TSUM":"1"}},
  {"name":"calibration-return","argv":["/private/calibration-build/calibrate","all"]}
]
```

Run under a transient user service so losing the terminal does not interrupt
restoration:

```sh
systemd-run --user --unit=strata-envelope-test --collect \
  --property=Type=exec --property=TimeoutStopSec=420 \
  /usr/bin/python3 /path/to/repo/experiments/strata-envelope/exclusive.py \
  --profile /private/known-good.json --plan /private/plan.json --out /private/run
```

It asserts the endpoint is idle, preserves the profile, records host telemetry,
and restores the service in `finally`. It handles SIGTERM but cannot protect
against SIGKILL, power loss or a host failure. Verify loaded health and the
original executable after any maintenance. The published plans include the
exact counter commands and environment used for this study.

## Routing and runtime accounting

Apply `reporting.patch` to the isolated source and rebuild `strata`. It exports
the existing `STRATA_ROUTE_STATS` counters, per layer/window width, and cumulative
dispatch JSON at the end of a native serve request. It does not instrument the
unrelated live OpenClaw agent. Enabling route statistics adds diagnostic GPU
kernels, so use the run for counts/parity, not performance promotion.

```sh
python3 benchmarks/strata-decode-profile.py \
  --profile /private/known-good.json --terminal /path/to/terminal/0.1.57 \
  --fixture /path/to/public/prompt.txt --out /private/routing-run \
  --profile-mode candidate --engine /private/reporting-engine/strata \
  --candidate-env STRATA_ROUTE_STATS=1 \
  --candidate-env STRATA_ENVELOPE_ROUTES=/private/routes.jsonl \
  --candidate-env STRATA_ENVELOPE_DISPATCH=/private/dispatch.json \
  --arms profile --sizes 49152 196608 --max-tokens 1024 \
  --expected-results /private/prior-control/results.json --execute

python3 experiments/strata-envelope/inventory.py \
  --weights evidence/strata-research-2026-11-11/weight-accounting.json \
  --index /path/to/native-pack/index.txt --out /private/runtime-inventory.json
```

`dispatch.json` is a stream of JSON objects, not a single JSON object. Graph
scope counts describe captured kernel choices; they must be interpreted with
graph-launch counts, not treated as executed calls on their own. Route reports
also include initial/restore evaluations, identified separately in the findings.

`analyze.py --root /private/study-root --out /private/analysis.json` reproduces
the aggregate tables with the directory structure used in the evidence.
`collect.py` copies an explicit artifact allowlist, checks successful restoration
and output parity, and rejects the API key if present. Native engine logs and
private profiles are never copied. `SHA256SUMS.json` covers the published input
artifacts; the documented analysis can be regenerated from them.

## Limits

The workload is public repeated source text, not a representative distribution
of all Discord tasks. Matrix replay uses synthetic weights/activations with
actual formats and shapes; expert routing evidence comes from public model
requests. This is neither a quality benchmark nor an intrinsic model ceiling.
Register peaks, logical weight payload, outgoing GL2 requests and physical
DRAM traffic are different measurements. The findings keep them separate.
