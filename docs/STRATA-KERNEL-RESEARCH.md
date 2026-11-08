# Separate research: further Flash-Next kernel improvements

This research record was separated from deployment completion on November 7.
Checkpoint validation, publication and reliable restart used the packaged engine.
On November 8 the user authorized cache fixes and an assessment of sustained
60–70 tok/s generation. That assessment does not promote any kernel below.
The earlier 1,700–2,000 prefill target remains an unmet research aspiration;
returns from deeper rewrites remain uncertain.

Preserve the same model/quant/context and the measured packaged baseline.
Keep isolated source branches and opt-in patches outside the serving process.
Do not carry an operator percentage into a whole-model speed claim.

Retained candidates, all undeployed:

| Candidate | Measured scope | Remaining work before deployment |
|---|---|---|
| Cooperative expert epilogue | 2.4–2.5% expert operator gain | Integration, full-model/state/tool checks |
| Prepared attention rows | About 3.2% attention operator gain | Scratch budget, integration and full-model/state checks |
| [Compact expert weights](STRATA-EXPERT-COMPACT-WEIGHTS-2026-11-07.md) | Repeated 2.2–2.3% warm expert gain | Preparation amortization, memory policy, integration and full-model checks |

The compact candidate loses when preparation is included per operation. Do not
deploy a large weight cache simply because RAM is available. Do not assume the
three candidate gains add together; they have never been combined in a model.

Possible larger work is a substantive expert operand/pipeline redesign to reduce
movement and synchronization while overlapping loads with matrix work. Existing
prefetch already overlaps some work. Instruction-latency shares are not wall-time
shares, so a large barrier percentage does not promise an equal removable cost.
Projection shared-memory/register constraints are another research question;
the simple narrow and wide tile experiments already lost.

Before another rewrite, define one distinct mechanism and its expected time
budget from the current profile. Require exact/reference checks, captured routing,
reversed-order controls, preparation and memory costs, then full-model cold
prefill and tool/state validation. Stop a losing direction instead of repeating
flag sweeps. No hardware ceiling has been proved.

Already rejected: prepared activations, direct FP16 weight loading, persistent
expert dispatch, four-stage unrolling, tested projection geometry/grouping,
larger MTP windows and cost-aware MTP policy. Their evidence remains in the
repository; reopening them requires new evidence or a different mechanism.
