# Flash-Next on packaged Strata

Status on 2026-11-08: persistent authenticated API at
`http://100.96.8.54:8083/v1`, OpenClaw provider `tiercelmoe`, alias
`qwen-flash-next`. The user has moved Francis to another model while the local
backend is profiled. The gateway was not restarted.

Cold prefill measured 1,416 tok/s at 64K, 1,363 at 128K and 1,301 at 192K.
The user approved a real research/tool task. Recent generation was around
41 tok/s; sustained 60–70 remains unproven. See the [handoff](../handoff.md).
The [November 8 cache fix](STRATA-CACHE-MISSES-2026-11-08.md) is persistent.
The old 27B service is stopped and disabled, with files retained.

## Reproduce the persistent service

After acquiring the pinned Terminal 0.1.57, matching HIP-Halo engine and this
exact model/tokenizer, prepare a private profile from the installed profile:

```sh
python3 scripts/prepare-strata-profile.py --source-profile /private/installed-profile.json --out /private/optimized-profile.json
python3 scripts/install-strata-service.py --source-profile /private/optimized-profile.json
systemctl --user start strata-flash-next.service
loginctl show-user "$USER" -p Linger
```

The installer validates the engine SHA, preserves credentials, backs up existing
files and enables the unit without restarting an already running process. During
an authorized maintenance window, use `restart` to apply changes to a running
service. Linger must be enabled for startup without a login. The helper checks the
exact model and tokenizer before setting `--tail-role-token 846`; do not copy
that numeric ID to other models. Profile files remain private.

Normal restart (87.3 s), forced-process recovery (96.3 s), checkpoint/tool checks
and a remote streaming request passed on November 7. Host reboot validation has
not been run. [Deployment evidence](../evidence/strata-performance-2026-11-07/deployment-completion/).
The following acquisition and incident sections are historical.

The November 6 authorized reboot recovered the GPU after a failed live driver
reload. The [recovery result](STRATA-RECOVERY-RESULT-2026-11-06.md) records the
active 112 GiB GTT and corrected installer wrapper; the
[chronological incident record](STRATA-RECOVERY-2026-11-06.md) is historical.
Do not repeat the GPU hot reload.

## Host incident — 16:50 UTC

This section records the pre-reboot failure. The host subsequently recovered;
the current state is in the recovery result linked above.

A headless live reload of `amdgpu`, attempted after stopping the only GPU client,
crashed in `isp_genpd_remove_device` / `isp_v4_1_1_hw_fini` on Ubuntu kernel
`7.0.0-42-generic`. The module remains in `going` state and `/dev/dri` and
`/dev/kfd` disappeared. Reloading it fails. **Do not repeat this hot-reload path
on this kernel; a clean host reboot is required for recovery.**

The 27B unit briefly restarted with CPU fallback and returned healthy HTTP status;
that was not restored GPU service. It was stopped explicitly. Its enabled boot
configuration and model files remain intact. The Mac/OpenClaw gateway was untouched.

Recovery is prepared, not yet executed: `/etc/modprobe.d/70-strata-halo-ttm.conf`
sets `ttm.pages_limit=29360128` and `ttm.page_pool_size=29360128` for the next
driver initialization (112 GiB at 4 KiB/page). The updated initramfs contains this
configuration. [Incident evidence](../evidence/strata-2026-11-06/gpu-reload-incident.json).
Networking, Tailscale and SSH socket activation are enabled; the existing 27B
unit remains enabled. Model acquisition has its own enabled user service and
resumes from verified download pieces after boot. Confirm the actual GTT size,
GPU devices, offloaded layers and a completion after recovery; HTTP health alone
is insufficient. A reboot of the local workspace host needs a coordinated interruption.

## Why this direction

Qwen3.6's performance work succeeded, but it failed the operational requirement
for reliable OpenClaw tool use and recovery. The
[setback report](https://github.com/LeoStehlik/qwen3.6-35b-a3b-strix-halo/blob/main/docs/OPERATIONAL-SETBACK.md)
records the observations without claiming an isolated model/runtime root cause.
The user has already tested Flash-Next successfully through Ollama Cloud with
OpenClaw. That motivates the local trial; it is not a quality test of this quant
or this server. Further dense-27B kernel work is deferred.

## Pinned installation

- Host: Ryzen AI Max+ 395, Radeon 8060S (`gfx1151`), nominal 128 GB RAM,
  Ubuntu 26.04, kernel `7.0.0-42-generic`; 115 GiB visible to the OS.
- Release: [Strata v0.2.11](https://github.com/Niko1221/Strata/releases/tag/v0.2.11),
  Terminal/control and HIP-Halo engine version `0.1.57`.
  The installed engine is signed, build `0bdcef4682c5+rocm`; all 282 package files
  passed verification, GPU backend auto-detection passed, and `--version` ran.
  These checks establish installation integrity, not successful model inference.
  [Recorded engine metadata and hashes](../evidence/strata-2026-11-06/engine.json).
- Target: `unsloth/Qwen3.8-Flash-Next-GGUF`, `UD-Q4_K_XL`, revision
  `38bb39ee97821de2c9009abb7e93950eec396e66`.
- About 111.3 GB of target shards plus the 5.2 GB MTP companion and 0.9 GB image
  projector. Keep at least 150 GB of free storage for preparation and artifacts.
- Target configuration: 262,144 context, INT8 KV, one slot, MTP depth 4,
  16,384-token prefill chunks, vision enabled, route-tail skipping explicitly off.
  Request-specific test output caps do not impose a serving output limit.
- First listener: loopback port 8083. Do not configure OpenClaw to use it until
  actual generation, tools, and remote reachability have passed.

Acquire without starting a model:

```bash
bash scripts/install-strata-flash-next.sh
```

The installer verifies the signed component feed and the model's pinned hashes.
It uses the packaged engine; no driver, ROCm toolchain, or llama.cpp fork is built.
Model preparation may acquire the upstream preparation sources when required.
`STRATA_MODEL_DIR`, `STRATA_INSTALL_DIR`, `STRATA_BUNDLE_DIR`, and `STRATA_BIN` can override the local
paths. Preserve the generated config and the component manifest with results.
The script invokes the pinned bundle's setup.py with its Python in Control mode;
in 0.1.57, passing the destination via `STRATA_INSTALL_DIR` to `strata install`
itself makes that CLI look for the installer in the wrong directory.

On the current host, `strata-flash-next-acquire.service` finishes acquisition and
preparation in the background after the active shard downloads. It writes
`~/.cache/strata-evaluation-20261106/preparation-status.json` and
`finish-preparation.log`. It does not load the new model, stop the old service,
or change OpenClaw routing. A `prepared-awaiting-validation` status is not readiness.

After the download and memory preflight, free the GPU of other model servers,
inspect the plan, then launch the isolated evaluation listener:

```bash
bash scripts/launch-strata-flash-next.sh --plan
bash scripts/launch-strata-flash-next.sh
python3 benchmarks/strata-tool-smoke.py --out /tmp/flash-next-tools.json
```

The smoke check verifies exact typed tool arguments and result continuation
using synthetic data. It does not execute tools, send OpenClaw messages, or
establish broad agent quality. Real OpenClaw requests follow the technical checks.

The custom long-prefill probe accepts a public text fixture and reports actual
prompt/cache counts, native timings, client first-token latency, and output hashes.
It uses fresh prompt prefixes and rejects runs with more than 64 reused tokens.
Thinking is disabled and generation capped at 128 tokens only for this performance
probe; tool/quality evaluation is separate. The script has passed syntax checks;
its actual-model runs are pending the download.

```bash
curl --fail --location \
  https://raw.githubusercontent.com/LeoStehlik/qwen3.6-35b-a3b-strix-halo/e0bb26c66c9637b8d8f6042947414610a280bffe/benchmarks/fixtures/prompt.txt \
  -o /tmp/strata-public-prompt.txt
printf '%s  %s\n' \
  6efd5cb8693d5c7fc9fa826da0e454895172071c7d30283f6eb6c04978875346 \
  /tmp/strata-public-prompt.txt | sha256sum --check
python3 benchmarks/strata-prefill.py --fixture /tmp/strata-public-prompt.txt \
  --sizes 65536 131072 --repeat 2 --out /tmp/strata-prefill.json
```

This repeats/truncates the frozen public source text and token-counts it through
the server. It does not reproduce the maintainers' historical benchmark workload;
do not present a difference between those results as an isolated speedup.

## Deployment checks still required

1. Complete: acquire and verify the target shards, vision projector and signed engine; prepare the model pack and MTP. The local completion/tool smoke passed on November 7; the remaining checks below are still required.
2. GPU recovery and limit change are complete. Before the fault this host reported 61,905,670,144 bytes of GTT
   (about 57.7 GiB), plus an 8 GiB BIOS carve-out. The published benchmark host
   used a 112 GiB GTT. Linux initializes the AMD GTT manager and KFD limits from
   TTM at driver initialization; writing a larger sysfs TTM number alone does
   not prove that the active GPU limit increased. The authorized reboot applied
   the new limit: 120,259,084,288 GTT bytes and live GPU access are now verified.
3. Review the effective memory plan, expert residency, image encoder and native
   context. A small GPU cache with pinned host experts can count memory twice;
   do not force a large cache/budget merely to match a headline.
4. Test first-request readiness across fresh starts. The launcher warns about
   UD-Q4_K_XL first-request hangs observed on engine 0.1.54/0.1.55. Its presence
   is a reason to test 0.1.57, not evidence that 0.1.57 hangs here.
5. Verify ordinary output, exact tool arguments, streaming tool calls, tool
   result continuation, warm-prefix reuse, and explicit state save/restore.
6. Measure cold 64K and 128K prompts: actual token count, uncached tokens,
   engine prompt time, client first-token latency, decode speed, peak memory,
   configuration, fixture hash and at least two comparable runs. Test a prompt
   above 150K as a capacity check. Keep cold and cached results separate.
7. At the user's explicit request, the private endpoint and existing Tiercel provider were connected on November 7 after the small checks, ahead of long-context benchmarking. The service is enabled. Do not describe the pending performance/quality checks as passed. The OpenClaw gateway on the Mac must not be restarted.

## Performance evidence and next experiments

The upstream [Halo guide](https://github.com/Niko1221/Strata/blob/v0.2.11/docs/STRIX_HALO.md)
reports **1,211 tok/s prefill and 42.64 tok/s decode at 128K** for this quant on
the maintainers' 395/128GB Linux machine, using engine 0.1.40. These are historical
upstream measurements, not results from this installation or a promise for
0.1.57. The guide calls Halo support experimental.

First measure the packaged baseline. Then compare the documented fused prefill
experts (`STRATA_PF_FUSED` plus `STRATA_PF_FUSED_KQ` for this quant), prefill GEMM,
attention and hyperconnection switches independently. Preserve tool behavior
and assess numerical changes; do not enable an entire bundle and attribute its
gain to one switch. Profile the winning configuration before new kernel work.
Prefix reuse complements cold-prefill acceleration; it does not replace it.

The deployment is not an engine fork. Maintain reproducible configuration and
evidence here; consider upstream contributions only after a measured improvement.
