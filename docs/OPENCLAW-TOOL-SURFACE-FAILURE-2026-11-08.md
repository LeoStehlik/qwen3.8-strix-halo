# OpenClaw skill lookup fails at the compact tool interface

## Confirmed failure

On November 8, the Discord request asking whether the agent had used the
`no-slop-ui` skill ended with “Agent couldn't generate a response. Please try
again.” OpenClaw 2026.10.9 classified it as `format`, not `timeout`.

At 12:02:56 local time (11:02:56 UTC), the model emitted a complete Qwen XML call
to `skills_search`. At 12:03:08, its retry emitted a call to `skills_read`.
Both were returned as text, with `stopReason=stop`, and neither tool executed.
OpenClaw logged empty-response recovery followed by an incomplete-turn error.

Strata's frontend logged the exact reason on both requests: the named tool was
not declared in the API request. The public XML format itself is supported.
Native generation completed normally: 101 and 220 output tokens, no cancellation.
The requests reused 154,287/155,726 and 154,531/155,890 prompt tokens (about 99%).
This is not an output-limit or failed-cache observation.

## The contract mismatch

OpenClaw's compact surface keeps file/shell tools directly visible and puts
other capabilities behind `tool_search`, `tool_describe` and `tool_call`.
Captured requests and the current session prompt report show these 12 declared
names:

```text
apply_patch edit exec ls process read sessions_yield
tool_call tool_describe tool_search view_image write
```

`skills_search`, `skills_read` and `skill_workshop` exist in OpenClaw's internal
registry but are absent from that declared list. The warning's
`registeredTool=true` refers to the internal registry, not the request's schemas.
The model attempted the hidden names directly. Strata's installed parser only
turns declared names or unambiguous aliases into structured calls on this route.
It reports rejected names in logs and `strata_rejected_tool_calls` metadata.

There was a second error: the attempted reader used `skillName`; the installed
`skills_read` schema requires `name`. The correct compact-surface invocation is:

```json
{"name":"tool_call","arguments":{"id":"skills_read","args":{"name":"no-slop-ui"}}}
```

This is an illustration of the structured call, not a tool executed during this
investigation. If the input schema is unknown, the agent can first use
`tool_describe` or `tool_search`.

The prompt does include an instruction to use the wrapper even when another
section names a deferred tool directly. Qwen did not follow that instruction in
this turn. This is evidence of a model/tool-interface failure; it does not by
itself prove a general capability limit or that every historical error has this
cause.

## Recovery loses useful information

OpenClaw recognizes the XML-looking text and logs the attempted tool name. Its
empty-response retry nevertheless says only to continue and produce a visible
answer. The tool-specific recovery branches require other terminal conditions,
such as a `toolUse` stop with no call, or a structured argument-rejection error.
Here the provider returned ordinary content and `stop`, so generic recovery ran.
The model then repeated the same class of error with a different hidden tool.

Relevant installed source regions:

- Strata `serve/frontend.py`: `OutputParser._callable`, `unread_names`.
- Strata `serve/server.py`: rejected-call diagnostics and response metadata.
- OpenClaw `src/agents/tool-search.ts` / bundled catalog functions:
  `isDirectVisibleCatalogTool`, `applyToolSearchCatalog`.
- OpenClaw `src/agents/tools/installed-skill-tools.ts`: actual skill schemas.
- OpenClaw `src/agents/embedded-agent-runner/run/incomplete-turn-recovery.ts`:
  `resolveEmptyResponseRetryInstruction`.

The Mac's authoritative daily log for this investigation was
`/tmp/openclaw/openclaw-2026-11-08.log`. Checking only `gateway.log` and
`gateway.err.log` misses these warnings and the final dispatch errors.

## Timing rules out active maintenance as the explanation

The normal service was restored and ready at 11:35 local time, before this
12:02–12:03 failure. It was not being modified during the failed requests.
The same XML-leak symptom was logged for a background `skill_workshop` call at
10:21 local time, before the tail-role cache fix was promoted at 11:09 local.
An additional `sessions_search` warning appeared at 10:44 local, and another
background `skill_workshop` rejection at 12:06 local.

Earlier connection-refused timeouts during the maintenance window were real
maintenance impact and are documented separately. They must not be used to
explain this later format error. No claim is made that every earlier warning
caused a user-visible failed turn.

## Offline validation and remedy

[Reproduction](../benchmarks/strata-tool-surface-repro.py) runs the installed
parser without inference, network requests or tool execution. All **36** checks
pass across whole, seven-character and one-character chunks, with streamed tool
arguments both enabled and disabled:

- Hidden direct skill names return text.
- Declaring the search schema makes that same XML a structured call.
- Declaring the reader alone still leaves the model's wrong `skillName` argument.
- The correct wrapped reader call parses with exact nested arguments.
- A correctly declared direct reader with `name` also parses.

[Results](../evidence/openclaw-tool-surface-2026-11-08/parser-repro.json).
These are parser/contract checks, not a live model quality test.

The narrower OpenClaw fixes to develop are: keep skill search/read primitives
directly declared, and/or recover an undeclared-name attempt with precise
wrapper/schema feedback. Recovery should re-enter the authorized tool interface,
not execute arbitrary XML text. That latter change would help other deferred
tools as well. Test permission boundaries, quoted XML, unknown names, malformed
arguments, retry limits and the actual model before deployment.

The installed schema accepts `tools.toolSearch=false`, but it is a global switch;
the per-agent tool schema has no `toolSearch` field and this version has no
per-tool pin setting. Disabling compaction broadly increases tool schemas and
changes other agents' prompts. It was not applied as part of this investigation.

No live configuration, prompt, kernel, model, service or gateway was changed.
No message was sent to Discord/Telegram and no synthetic OpenClaw turn was run.
