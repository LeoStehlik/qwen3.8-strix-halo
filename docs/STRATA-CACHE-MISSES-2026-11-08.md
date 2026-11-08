# Cache misses: exact incoming-prompt investigation

Status: controlled comparison, tool/state checks and captured-request replay
passed. The fix is persistent in the known-good profile as of 10:09 UTC.
The active objective is to fix avoidable cache misses first, then assess whether
sustained 60–70 tok/s generation is achievable before further optimization.

## What the live evidence establishes

A passive capture of Mac-to-Strata HTTP requests was decoded offline using the
installed frontend, template and tokenizer. No agent turn or tool was created.
Raw requests, packet headers and rendered prompts remain private. Public evidence
must contain only timing, counts, hashes and field positions.

The captured prompt counts reconcile with the native engine log. At first,
ordinary Discord turns and tool continuations reused growing history:

| Prompt tokens | Reused tokens | Common prefix with previous captured prompt |
|---:|---:|---:|
| 65,480 | 63,621 | 63,622 |
| 65,887 | 64,586 | 64,587 |
| 86,424 | 64,910 | 64,911 |
| 102,993 | 81,294 | 85,448 |

The final row leaves about 4,154 matching tokens un-reused. A later ordinary
Discord request of 108,872 tokens has a 105,746-token common prefix with an
earlier request in the same conversation, but reuses only 97,678. Its final
runtime message is 1,086 tokens. A preceding runtime message was 1,675 tokens.
This is evidence of unused matching prefixes, not permission to restore state
at arbitrary positions: the hybrid model needs a full checkpoint there.

Interleaved background skill-review prompts differ in the system/tool region.
They must be compared to their own previous requests. Two earlier zero-reuse
calls (43,207 and 50,105 tokens) were background skill reviews, as identified by
the gateway completion records. The recent ordinary cold turns also followed
user-authorized AGENTS.md changes. Such edits must take effect; the optimization
must not preserve stale instructions. Aggregate zero-reuse counts alone
overstated the ordinary conversation's cache problem.

The older pre-reset ~230K conversation's fixed 16,384-token reuse was not captured
on the wire. Its historical trajectory omitted the full system prompt and parts
of history. The causes below are candidates for that pattern, not retrospective
proof of its exact cause.

## Two limitations of the extra message checkpoint

The enabled `STRATA_CACHE_MESSAGE_BOUNDARY=1` helper only selects the final
message boundary when that message is at most 1,024 tokens. Captured Discord
runtime messages started at 889–972 tokens and subsequently crossed this limit.
A public offline replay with a 1,163-token moving message also selects no extra
checkpoint despite a long common prefix.

Source inspection additionally shows that this checkpoint is tagged as a tail
checkpoint. At capacity, retention drops a non-newest tail before ordinary
checkpoints. Saving the later assistant-turn checkpoint can therefore discard
the very boundary required by the next full-resend request. This retention
mechanism was reproduced with traced inference: a checkpoint at 68,264 was
saved, then a later assistant checkpoint at 68,531 caused an eviction; the next
request could restore only 66,005. The final-role option retained the required
68,264 checkpoint under the same 7,168 MiB cache budget.

## Promoted fix: existing final-role checkpoint

The installed binary supports `--tail-role-token`. With this exact tokenizer,
`user` encodes as the single token **846**. The candidate adds
`--tail-role-token 846`, leaving the final user-role runtime carrier outside the
ordinary reusable-history checkpoint. This existing path has no 1,024-token
limit and retains the boundary as an ordinary checkpoint. Exact token/image
prefix checks still govern restoration. No prompt text or model changes.

This setting is tokenizer/template-specific. It must not be copied to other
models using the numeric ID without verifying their tokenizer and prompt shape.
Interactions with a trailing system-role reasoning-effort message need separate
validation; the current profile does not enable `effort_position=end`.

The completed trial used the same packaged engine in control/candidate/control
order, on authenticated loopback. Public fixtures have 68–73K tokens, three
requests each, and moving runtime messages of 267 and 1,163 tokens. It also
checks exact tool arguments, result continuation, and restoration after another
conversation, with a long moving message. The runner restores the original
service/profile in `finally`. It refuses to begin while live work is active.

Tools:

- [Private wire-prefix auditor](../benchmarks/strata-wire-prefix-audit.py)
- [Capture integrity tests](../benchmarks/test-strata-wire-prefix-audit.py): six
  passing checks cover reordered/duplicate TCP segments, sequence wrap, gaps,
  conflicting retransmissions, incomplete requests and incomplete capture tails.
- [Prepared trial runner](../benchmarks/strata-tail-role-trial.py): preparation
  completes without inference; `--execute` performs the service comparison.

## Controlled results

All 18 public state canaries passed, with identical corresponding output hashes
and exact request/render parity across arms. Exact tool arguments, tool-result
continuation and restoration after an interleaved conversation also passed.

| Final runtime message | Control 1: two follow-ups | Candidate | Control 2 | Time reduction vs mean controls |
|---|---:|---:|---:|---:|
| 267 tokens | 12.036 s | 7.458 s | 13.660 s | 42.0% |
| 1,163 tokens | 12.306 s | 8.849 s | 12.147 s | 27.6% |

Controls kept reusing about 66,005 tokens. Candidate reuse advanced to 68,264
and 70,132–70,133 tokens. Cold runs are recorded separately: this is avoided
rereading, not higher raw prefill throughput. There was one complete
control/candidate/control sequence; short canary outputs are not decode benchmarks.

## Captured-request replay after promotion

Three real captured request bodies were replayed directly against the promoted
endpoint, with output limited to eight tokens for these probes only. No tools
were executed and no OpenClaw turn was created. This verifies prefix handling,
not answer quality or sustained generation speed.

| Prompt tokens | Historical reuse | Replay reuse | Fresh tokens before → after |
|---:|---:|---:|---:|
| 107,425 | 97,678 | 0, cold setup | — |
| 108,872 | 97,678 | 105,745 | 11,194 → 3,127 (−72.1%) |
| 109,744 | 97,678 | 107,781 | 12,066 → 1,963 (−83.7%) |

Both warm requests restored exactly the intended matching boundary. Replay
prefill took 7.932 and 4.401 seconds; small-remainder throughput was only
394 and 446 tok/s. The cache fix does not eliminate all short-prefill overhead.
Historical and replay wall times are not a controlled A/B comparison.

The persistent deployment retains the packaged engine, model quantization,
262,144 context, INT8 KV, MTP and all-resident experts. No source kernel,
instruction text or serving output cap changed. The Mac's configured endpoint
passed authenticated health/model checks; the OpenClaw gateway was untouched.

Maintenance did interrupt the endpoint before the user moved Francis elsewhere:
the reported Discord 10:55/11:00 local-time timeout notices coincide with
connection-refused errors during the offline trial. They are maintenance impact,
not evidence of a new generation hang. The user subsequently reserved the local
backend for testing. Live post-fix OpenClaw quality remains to be observed.

## Evidence and reproduction

[Curated evidence](../evidence/strata-cache-2026-11-08/) contains counts, hashes,
public-fixture results, promotion metadata and the captured replay's metrics.
Raw network capture, credentials, user prompts and rendered tokens stay private.

Run `benchmarks/strata-tail-role-trial.py --help` for the comparison. It accepts
either the original profile or the promoted profile, removes the tail-role option
for control arms, and restores the supplied persistent profile unchanged.
Use the pinned Terminal Python, the private profile and a new private output
directory. `--execute` restarts local serving and needs a maintenance window.
Analyze the completed run with `benchmarks/analyze-strata-tail-role.py`.

The updated [profile helper](../scripts/prepare-strata-profile.py) adds the
verified role ID, and the [service installer](../scripts/install-strata-service.py)
checks it. These preserve the existing API credential. Normal restart and crash
recovery were tested on November 7; host reboot validation remains unperformed.

The subsequent [generation assessment](STRATA-DECODE-ASSESSMENT-2026-11-08.md)
is complete: roughly 40–42 tok/s, with no demonstrated path to sustained 60–70
under the tested configuration. This cache improvement makes no decode claim.
