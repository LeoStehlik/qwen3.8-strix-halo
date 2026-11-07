# Message-boundary checkpoint: live trial

Enabled at **19:04:22 UTC on 7 November 2026** on the existing endpoint:
`http://100.96.8.54:8083/v1`, model
`qwen3.8-flash-next-unsloth-ud-q4_k_xl`, OpenClaw provider `tiercelmoe`.

The sole live change is **`STRATA_CACHE_MESSAGE_BOUNDARY=1`** in the existing
runtime systemd override. This follows the isolated
[checkpoint comparisons](STRATA-CACHE-BOUNDARY-2026-11-07.md), which reduced
repeated processing with matching outputs in their moving-context cases.
It preserves the engine's exact-prefix checks and full recurrent state.

The serving configuration retains short-read **64**, stream minimum **128**,
262,144 context, INT8 KV, all resident experts, MTP and the packaged engine.
No source experiment or tracing is enabled. The separate 8/32 small-batch
candidate is **not** included in this trial.

Verification:

* Authenticated health reported loaded, and metrics reported idle.
* The actual inference process environment contains the boundary flag and
  stream minimum 128; its command line has no short-read override.
* A read-only health request from the Mac using its configured `tiercelmoe`
  provider credentials succeeded. This was not a model or agent request.
* No Mac gateway restart, Mac configuration change or channel message occurred.

**Actual OpenClaw reuse, answer quality and latency remain unverified for this
trial.** On the next real request, check whether reused tokens advance with
history, then check tool arguments, continuation and the delivered answer.
Synthetic cache gains are not a measured real-task speedup or higher raw
prefill throughput. Continue tracking preparation and GPU memory stalls.

This is a runtime trial, not boot promotion. `strata-flash-next.service` is
still disabled at boot; its persistent profile is unchanged. The runtime
override disappears on reboot. The [activation evidence](../evidence/strata-performance-2026-11-07/cache-live-trial/)
contains before/trial unit files, engine identity, health and actual-process
flag verification. Private API keys are excluded.

To revert only this option when the backend is idle, remove the exact
`Environment=STRATA_CACHE_MESSAGE_BOUNDARY=1` line from
`/run/user/1000/systemd/user/strata-flash-next.service.d/90-live-preview.conf`,
then reload the user units and restart **the Strata backend**. The Mac
OpenClaw gateway does not need restarting. Preserve other tuning lines.
