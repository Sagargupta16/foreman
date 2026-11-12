#!/usr/bin/env python3
"""foreman capture hook: one line per finished foreman agent, read from its own transcript.

Registered for SubagentStop in hooks/hooks.json and off unless the plugin option
`capture_runs` is on. It reads the hook payload on stdin, sums the agent's token usage from
`agent_transcript_path` and appends one JSON line to ~/.claude/foreman/agents.jsonl (or
$FOREMAN_CAPTURE_LOG). `plan.py log` joins these lines to subtasks by id: the Agent call's
description, which dispatch sets to the subtask id, or else the `id:` line of the brief.

It stores numbers and identifiers only: no prompt text and no result text. It never blocks
and never fails the session: any problem ends in exit 0 with nothing written.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time
from pathlib import Path

MAX_LINES = 5000  # the capture file keeps its newest lines
MAX_BYTES = 16 * 1024 * 1024  # a transcript larger than this is skipped
WAIT = 1.0  # the transcript is written asynchronously, so give the last turn time to land
ON = {"1", "true", "yes", "on"}


def capture_file() -> Path:
    env = os.environ.get("FOREMAN_CAPTURE_LOG")
    if env:
        return Path(env)
    log = os.environ.get("FOREMAN_LOG")
    base = Path(log).parent if log else Path.home() / ".claude" / "foreman"
    return base / "agents.jsonl"


def brief_id(content: object) -> str | None:
    """The subtask id from the head of a foreman brief ("id:      build-api")."""
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    if not isinstance(content, str):
        return None
    for line in content.splitlines()[:5]:
        key, _, value = line.partition(":")
        if key.strip() == "id" and value.strip():
            return value.strip()[:128]
    return None


def meta_of(transcript: Path) -> dict:
    """Claude Code's note beside an agent transcript: the Agent call's description and shape.

    agent-<id>.meta.json was seen on Claude Code 2.1.322 and is not documented, so a missing
    or unreadable file is simply no metadata.
    """
    try:
        data = json.loads(
            transcript.with_name(f"{transcript.stem}.meta.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def when(stamp: object) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None


def summarize(lines: list[str]) -> dict | None:
    """Usage, models, tool calls and duration of one agent transcript; None when it has no turn.

    A response is written once per content block with the same message id and usage, so
    usage is counted once per message id.
    """
    sid = None
    stamps: list[datetime.datetime] = []
    usage: dict[str, dict] = {}
    models: list[str] = []
    tool_uses = 0
    for raw in lines:
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        stamp = when(entry.get("timestamp")) if entry.get("timestamp") else None
        if stamp:
            stamps.append(stamp)
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        if entry.get("type") == "user" and sid is None:
            sid = brief_id(message.get("content"))
        if entry.get("type") != "assistant":
            continue
        blocks = message.get("content")
        if isinstance(blocks, list):
            tool_uses += sum(isinstance(b, dict) and b.get("type") == "tool_use" for b in blocks)
        model = message.get("model")
        if isinstance(model, str) and model not in models:
            models.append(model)
        mid, use = message.get("id"), message.get("usage")
        if isinstance(mid, str) and isinstance(use, dict):
            usage[mid] = use  # the last block of a message carries its final usage
    if not usage:
        return None

    def num(use: dict, key: str) -> int:
        value = use.get(key)
        return value if isinstance(value, int) else 0

    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}
    for use in usage.values():
        totals["input"] += num(use, "input_tokens")
        totals["output"] += num(use, "output_tokens")
        totals["cache_read"] += num(use, "cache_read_input_tokens")
        split = use.get("cache_creation")
        if isinstance(split, dict):
            totals["cache_write_5m"] += num(split, "ephemeral_5m_input_tokens")
            totals["cache_write_1h"] += num(split, "ephemeral_1h_input_tokens")
        else:
            totals["cache_write_5m"] += num(use, "cache_creation_input_tokens")
    last = list(usage.values())[-1]
    final = sum(
        num(last, k)
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        )
    )
    span = (max(stamps) - min(stamps)).total_seconds() if stamps else 0
    return {
        "id": sid,
        "models": models,
        "model": models[-1] if models else None,
        "turns": len(usage),
        "tool_uses": tool_uses,
        "duration_ms": int(span * 1000),
        "tokens": final,  # the size of the last request, the same number the Agent tool reports
        **{f"{k}_tokens": v for k, v in totals.items()},
    }


def record(payload: dict) -> dict | None:
    """The line to store for one SubagentStop payload, or None when there is nothing to store."""
    agent = payload.get("agent_type")
    path = payload.get("agent_transcript_path")
    if payload.get("hook_event_name") != "SubagentStop" or not isinstance(agent, str):
        return None
    if not agent.startswith("foreman:") or not isinstance(path, str):
        return None
    transcript = Path(os.path.expanduser(path))
    if not transcript.is_file() or transcript.stat().st_size > MAX_BYTES:
        return None
    text = transcript.read_text(encoding="utf-8", errors="replace")
    summary = summarize(text.splitlines())
    if summary is None:
        return None
    meta = meta_of(transcript)
    label = meta.get("description")
    if isinstance(label, str) and label.strip():
        summary["id"] = label.strip()[:128]
    shape = meta.get("requestShape")
    effort = payload.get("effort")
    return {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "session": payload.get("session_id"),
        "project": Path(str(payload.get("cwd") or ".")).as_posix(),
        "agent_id": payload.get("agent_id"),
        "agent": agent,
        "effort": effort.get("level") if isinstance(effort, dict) else None,
        "shape": shape if shape in ("foreground", "background") else None,
        **summary,
    }


def append(path: Path, line: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as fh:
        fh.write(json.dumps(line).encode("utf-8") + bytes([10]))
    rows = path.read_bytes().splitlines(keepends=True)
    if len(rows) > MAX_LINES:
        path.write_bytes(b"".join(rows[-MAX_LINES:]))


def main() -> int:
    if os.environ.get("CLAUDE_PLUGIN_OPTION_CAPTURE_RUNS", "").strip().lower() not in ON:
        return 0
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        if not isinstance(payload, dict):
            return 0
        time.sleep(WAIT)
        line = record(payload)
        if line:
            append(capture_file(), line)
    except (OSError, ValueError, TypeError, KeyError):
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
