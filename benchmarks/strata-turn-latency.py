#!/usr/bin/env python3
"""Produce content-free timings from a local transcript export and Strata log.

Input transcript: [{seq, created_at (milliseconds), event: {message: ...}}].
Private transcript text, tool arguments/results, identifiers and paths are never
copied into the output. Select one user task explicitly; unrelated/background
requests in the backend log must not be charged to its latency.
"""

import argparse
import datetime as dt
import json
import re
import statistics
from pathlib import Path


PATTERN = re.compile(
    r"prompt (\d+) tokens = (\d+) reused \+ (\d+) read in ([\d.]+) ms "
    r"\([^)]*\), (\d+) generated in ([\d.]+) ms"
)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transcript", type=Path, required=True)
    ap.add_argument("--backend-log", type=Path, required=True)
    ap.add_argument("--first-seq", type=int, required=True)
    ap.add_argument("--last-seq", type=int, required=True)
    ap.add_argument("--delivery-at", required=True, help="ISO 8601 send-success timestamp")
    args = ap.parse_args()
    events = [r for r in json.loads(args.transcript.read_text())
              if args.first_seq <= r["seq"] <= args.last_seq]
    message = lambda r: r["event"].get("message", {})
    assert message(events[0])["role"] == "user", "Selection must begin at the task user message"
    turns = [r for r in events if message(r).get("role") == "assistant"
             and message(r).get("model") != "delivery-mirror"]
    assert turns and message(turns[-1])["stopReason"] == "stop", "Select through the final answer"
    backend = [tuple(map(float, m)) for m in PATTERN.findall(args.backend_log.read_text())]
    origin = message(events[0])["timestamp"]
    delivery = dt.datetime.fromisoformat(args.delivery_at.replace("Z", "+00:00"))
    assert delivery.tzinfo is not None, "Delivery timestamp needs an explicit timezone"
    delivery_ms = delivery.timestamp() * 1000
    rows, used = [], set()
    for index, r in enumerate(turns):
        m = message(r)
        u = m["usage"]
        prompt = u["contextUsage"]["promptTokens"]
        candidates = [(i, b) for i, b in enumerate(backend)
                      if b[0] == prompt and b[1] == u["cacheRead"]
                      and b[2] == u["input"] and b[4] == u["output"]]
        assert len(candidates) == 1, "Backend match must be unique; narrow the source log if ambiguous"
        bi, b = candidates[0]
        assert bi not in used, "Backend record matched more than once"
        used.add(bi)
        calls = [x for x in m.get("content", []) if isinstance(x, dict) and x.get("type") == "toolCall"]
        next_seq = turns[index + 1]["seq"] if index + 1 < len(turns) else r["seq"] + 1
        results = [x for x in events if r["seq"] < x["seq"] < next_seq
                   and message(x).get("role") == "toolResult"]
        row = {
            "turn": index + 1,
            "request_start_offset_s": (m["timestamp"] - origin) / 1000,
            "transcript_completion_offset_s": (r["created_at"] - origin) / 1000,
            "prompt_tokens": int(b[0]), "reused_tokens": int(b[1]),
            "read_tokens": int(b[2]), "generated_tokens": int(b[4]),
            "prefill_s": b[3] / 1000, "generation_s": b[5] / 1000,
            "request_window_s": (r["created_at"] - m["timestamp"]) / 1000,
            "tool_names": [x["name"] for x in calls],
            "tool_exit_codes": [message(x).get("details", {}).get("exitCode") for x in results],
        }
        if index + 1 < len(turns):
            assert results, "Intermediate model turn has no recorded tool result"
            last_result = max(x["created_at"] for x in results)
            row["tool_result_window_s"] = (last_result - r["created_at"]) / 1000
            row["post_tool_gap_s"] = (message(turns[index + 1])["timestamp"] - last_result) / 1000
        rows.append(row)
    total = lambda key: sum(r.get(key, 0) for r in rows)
    gaps = [r["post_tool_gap_s"] for r in rows if "post_tool_gap_s" in r]
    prefill, generation = total("prefill_s"), total("generation_s")
    summary = {
        "task_wall_s": (delivery_ms - origin) / 1000,
        "model_turns": len(rows), "tool_calls": sum(len(r["tool_names"]) for r in rows),
        "first_tool_model_completion_s": rows[0]["transcript_completion_offset_s"],
        "prefill_s": prefill, "generation_s": generation,
        "model_request_other_s": total("request_window_s") - prefill - generation,
        "tool_result_window_s": total("tool_result_window_s"),
        "post_tool_gap_s": sum(gaps), "post_tool_gap_median_s": statistics.median(gaps) if gaps else None,
        "post_tool_gap_max_s": max(gaps) if gaps else None,
        "task_start_to_request_s": rows[0]["request_start_offset_s"],
        "final_transcript_to_send_success_s": (delivery_ms - turns[-1]["created_at"]) / 1000,
        "read_tokens": total("read_tokens"), "reused_tokens": total("reused_tokens"),
        "generated_tokens": total("generated_tokens"),
        "prefill_tok_s": total("read_tokens") / prefill,
        "generation_tok_s": total("generated_tokens") / generation,
    }
    accounted = sum(summary[k] for k in (
        "prefill_s", "generation_s", "model_request_other_s", "tool_result_window_s",
        "post_tool_gap_s", "task_start_to_request_s", "final_transcript_to_send_success_s"))
    assert abs(accounted - summary["task_wall_s"]) < 0.001
    print(json.dumps({
        "schema": 1,
        "method": "Match backend records uniquely by prompt/reused/read/output token counts; transcript and gateway timestamps delimit wall intervals.",
        "caveats": [
            "Backend log milliseconds are rounded; API request windows also include transport, rendering, cache work and persistence.",
            "Tool-result windows include dispatch/serialization overhead and take the last result of parallel calls, avoiding double counting.",
            "Post-tool gaps are elapsed time to the next recorded request, not a direct GPU-idle measurement.",
            "Send-success is the gateway acknowledgement, not measured client display time.",
            "Generated tokens include thinking and tool arguments; no token-level split is inferred from character counts."
        ],
        "summary": summary, "turns": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
