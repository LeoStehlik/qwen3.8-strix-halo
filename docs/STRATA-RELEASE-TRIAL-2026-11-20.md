# Strata v0.2.17 release trial — 20 November 2026

This is the local follow-up to the [ecosystem review](ECOSYSTEM-REVIEW-2026-11-20.md).
It compares packaged engine/control 0.1.63 against the retained 0.1.57 deployment
on Linux. The model remains Unsloth Qwen3.8 Flash-Next UD-Q4_K_XL. No custom kernel
patch, model requantization or OpenClaw configuration change is part of this trial.

## Deployment decision

**Promoted: release v0.2.17, engine/control 0.1.63, tuned DFlash2.** The model,
quantization, authenticated endpoint, 262,144 context limit and OpenClaw routing
are preserved. The new generation path offers modest gains in the controlled
probes; this trial does not demonstrate a substantial raw-prefill improvement.

The final DFlash2 cold 192K check completed at **1,281.0 tok/s**, with zero cached
tokens and the same output hash as the new-engine/MTP capacity check. A subsequent
real completion through the normal endpoint returned the expected `STRATA-READY`.
The queue was idle afterwards. The Mac mini separately reached the loaded model
through Tailscale. Synthetic tool/state checks passed for all three arms.

The pinned persistent service restarted in **75.6 seconds**, is enabled, and
user linger is active. No host reboot was performed for this upgrade; the old
service had already survived today's user-operated BIOS reboot. Real OpenClaw
answer quality under the user's normal `xhigh` prompts remains a live-use check.
The old 0.1.57 engine, bundle, MTP pack and private deployment backups are retained.
No experiment listener or measurement job remains running.

## Protocol and limits

The machine is a Ryzen AI Max+ 395 / Radeon 8060S with 128 GB unified memory,
Ubuntu kernel 7.0.0-44-generic. BIOS GPU reserve is 512 MiB, Linux sees about
122 GiB and the GTT budget is 112 GiB. Both engines hold all 24,576 experts
(73,450 MiB). The earlier 96 GiB BIOS-reserve incident is not a baseline.

Each arm runs alone on loopback port 8084 with the production service stopped.
The existing service environment, target weights, tokenizer, 262,144 context
limit, INT8 KV, prefill chunk 16,384, memory mapping and checkpoint settings are
held constant. A controller restores the original service even after failure.

First compare the engine/control update with MTP retained. Then evaluate the
upstream tuned DFlash2 package separately. This distinction matters: an improved
drafter is not evidence of faster target-model kernels.

Cold probes use the same public fixture and deterministic nonce, temperature 0,
thinking disabled, presence penalty 0 and 512 output tokens. Actual prompt
counts are 65,546 and 131,076, with zero cached tokens. Short warm-ups are excluded.
The capacity probe uses 196,606 prompt tokens and only 32 generated tokens; its
decode number is not a sustained-generation measurement.

The three additional generation probes use temperature 0.2, **medium thinking**
and 512-token caps. They are performance samples, not finished-answer quality
scores and not the live Discord `xhigh` workload. Tool/state checks use synthetic
records and execute no real tools. Passing them is necessary but does not replace
the user's real OpenClaw evaluation.

Raw public-fixture results, request hashes and package identities are in
[evidence/strata-release-2026-11-20](../evidence/strata-release-2026-11-20/).
Private API credentials and user conversations are excluded.

## Engine-only comparison, MTP retained

| Probe | Engine 0.1.57 | Engine 0.1.63 |
|---|---:|---:|
| Cold 64K prefill, tok/s | 1,271.2 | 1,376.8 |
| 64K generation, tok/s | 40.7 | 39.4 |
| Cold 128K prefill, tok/s | 1,320.5 | 1,325.7 |
| 128K generation, tok/s | 39.9 | 40.1 |
| Short explanation, sampled generation, tok/s | 44.9 | 44.1 |
| 16K prompt, sampled generation, tok/s | 50.0 | 50.3 |
| Code prompt, sampled generation, tok/s | 54.6 | 52.3 |

The 128K comparison is effectively flat. The 64K point is 8.3% higher, but this
is one run per arm and the first baseline can include cold-start effects. It
does not establish a repeatable 8.3% upgrade gain. No decode gain is demonstrated
with MTP unchanged. One short candidate request reports a 663 ms driver pause
while Linux moves GPU-used memory; this is recorded rather than discarded.

The cold 192K capacity check completes at 1,274.4 tok/s with zero cached tokens.
Its 32-token output is intentionally too short for a sustained decode claim.

Output hashes match between engine versions at 128K and on two of the three
sampled-generation prompts. The 64K and sampled-code outputs differ. This is
not a claim of bitwise equivalence across engine releases.

Both arms pass exact typed tool arguments, tool-result continuation, unrelated
conversation isolation, and restoration of the prior result. The new engine's
reused prefix advances from 11,614 to 11,784 tokens across follow-ups.

## DFlash2 comparison on engine 0.1.63

The tuned Q4_0/selected-Q4 drafter uses the upstream Halo defaults: `--spec 8`,
`--draft-conf 0.35`, `--draft-fallback none`, and the existing draft vocabulary.
Startup arguments confirm DFlash2 alone; the MTP head is not running beside it.

| Probe | MTP | DFlash2 | DFlash2 point difference |
|---|---:|---:|---:|
| Cold 64K prefill, tok/s | 1,376.8 | 1,383.3 | +0.5% |
| 64K generation, tok/s | 39.4 | 42.1 | +6.9% |
| Cold 128K prefill, tok/s | 1,325.7 | 1,330.9 | +0.4% |
| 128K generation, tok/s | 40.1 | 43.1 | +7.5% |
| Short explanation, sampled generation, tok/s | 44.1 | 45.0 | +2.0% |
| 16K prompt, sampled generation, tok/s | 50.3 | 58.0 | +15.3% |
| Code prompt, sampled generation, tok/s | 52.3 | 54.0 | +3.3% |

Both cold-output hashes and all three sampled-output hashes match the new
engine's MTP arm. Exact tool arguments,
tool-result continuation and interleaved checkpoint restoration all pass; reused
prefix lengths again advance from 11,614 to 11,784. The four short synthetic
tool/state replies generate at 72.5, 53.2, 70.7 and 53.1 tok/s, but these short,
predictable replies must not be sold as sustained Discord conversation speed.

These are single-run point estimates. Prefill is essentially unchanged when
changing the drafter. Generation improves on these probes, most clearly on the
16K sampled prompt and the long-context greedy runs. Relative to the **original
0.1.57/MTP deployment**, the 64K and 128K decode differences are +3.4% and +8.0%.
Do not attribute the new-engine/DFlash2 combined difference solely to kernels.
The new engine reports four driver memory-movement pauses in the DFlash2 arm
(235, 243, 760 and 341 ms). These samples are retained, not excluded as outliers.
The log excerpts preserve these diagnostics; they do not establish that older
engines had no comparable stalls.

## Reproduction

Start from the [existing deployment](STRATA-FLASH-NEXT.md), retaining its model
files and authenticated profile. This is an upgrade path, not a new weight
download. The signed feed is pinned to the tested release:

```bash
strata update \
  --feed https://github.com/Niko1221/Strata/releases/download/v0.2.17/strata-feed.json \
  --backend hip-halo --yes --model-config /path/to/private-profile.json --output json
```

The updater performs a real model-load/generation smoke test. Run it in a
maintenance window with the old model stopped so two copies do not compete for
memory. Keep the old engine/control installation. Engine and control versions
are **0.1.63**; **v0.2.17** is the release label. Archive and executable SHA-256s
are separate fields in the evidence metadata.

The new control entry point is
`~/.local/share/strata/components/control/0.1.63/python/bin/python3`
followed by `~/.local/share/strata/components/control/0.1.63/strata.py`.
Set `STRATA_NO_HANDOVER=1` to keep the selected control version pinned. Updating
the global control pointer alone does not upgrade our deliberately pinned unit.

For the isolated trial, copy the private profile, change only the engine/control
and vision executable paths, set host `127.0.0.1`, port `8084`, and set
`drafting` explicitly to `mtp` or `dflash2`. Preserve credentials privately.
Run with the environment from the repository's systemd unit. Export the test
API key into `STRATA_API_KEY` without putting it into command history or logs.

```bash
python3 benchmarks/strata-prefill.py \
  --fixture /path/to/public-prompt.txt --url http://127.0.0.1:8084 \
  --model qwen3.8-flash-next-unsloth-ud-q4_k_xl \
  --sizes 65536 131072 --repeat 1 --max-tokens 512 \
  --presence-penalty 0 --nonce-seed release-20261120 --out prefill.json

python3 benchmarks/strata-generation.py \
  --strata-bundle ~/.local/share/strata/terminal/0.1.57 \
  --model qwen3.8-flash-next-unsloth-ud-q4_k_xl \
  --temperature 0.2 --thinking --presence-penalty 0 --out generation.json

python3 benchmarks/strata-checkpoint-tools.py \
  --profile /path/to/private-isolated-profile.json \
  --runtime-padding-rows 100 --out state-tools.json
```

Using the old bundle for generation fixtures deliberately holds the prompt
source constant. The fixture URL and digest are in `metadata.json`.

For DFlash2, the tested signed-feed artifact is
`qwen3.8-flash-next-dflash2.strata1.q4_0-selq4.pack` from release v0.2.16,
339,694,592 bytes. Put it in the model root's `dflash2/` directory. Its SHA-256 is
`4df2e5ab2b47c064afbe662e16e4f06569877125c2d0e2123a4ac755266c664c`.
This is an additional drafter; the target GGUF is unchanged. Verify the control
package's `drafting plan --config ... --mode dflash2 --output json`
and the actual engine startup arguments before recording results.

The persistent installer accepts `--release 0.1.63 --drafting mtp` or
`--drafting dflash2`, verifies the pinned engine (and DFlash2 file where selected),
backs up private profile/unit files, and installs/enables the service without
restarting it. Its default remains 0.1.57 for historical reproduction. Supply
the production profile, not the isolated loopback profile, to preserve the
endpoint and credentials.

```bash
python3 scripts/install-strata-service.py \
  --source-profile ~/.local/share/strata/flash-next/strata-known-good.json \
  --release 0.1.63 --drafting dflash2
systemctl --user restart strata-flash-next.service
```

The unit uses the existing readiness helper, automatic restart and user linger.
Rollback consists of restoring the backed-up private profile and unit, running
`systemctl --user daemon-reload`, then restarting the service. Keep the old
bundle, engine, MTP pack and target weights until deliberately retiring rollback.
