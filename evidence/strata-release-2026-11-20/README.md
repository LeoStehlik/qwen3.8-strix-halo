# Packaged Strata release trial — 20 November 2026

Read the [report](../../docs/STRATA-RELEASE-TRIAL-2026-11-20.md) for interpretation.

- `baseline-*`: engine/control 0.1.57, MTP.
- `candidate-*`: engine/control 0.1.63, MTP.
- `dflash-*`: engine/control 0.1.63, tuned DFlash2.
- `*-prefill.json`: cold public-fixture 64K/128K timings, greedy, thinking off.
- `*-generation.json`: public 512-token performance probes at temperature 0.2,
  medium thinking; truncated outputs are not a quality benchmark.
- `*-state-tools.json`: exact arguments, synthetic tool-result continuation,
  interleaved conversation and checkpoint restoration.
- `*-capacity.json`: cold 192K capacity smoke test; only 32 output tokens.
- `metadata.json`: hardware, package/fixture identities and unchanged service
  environment. The engine archive and executable have different digests.
- `candidate-profile-public.json` and `deployed-profile-public.json`: reference configurations with credentials
  removed and paths abbreviated. They are not installable private profiles.
- `deployed.service`: the pinned persistent unit; `promotion-status.json` records
  restart, capacity and completion verification; `mac-health.json` records
  reachability from the OpenClaw host.
- Controller status files record completion/restoration, not a substitute for
  the individual probe results.

All prompts are public or synthetic. No live user messages, credentials or
OpenClaw session files are included. Timing runs are single samples; do not
quote a small point difference as a statistically established speedup.
