"""Tests for hooks/capture.py: the SubagentStop hook that records one line per foreman agent.

The transcript fixture mirrors a real agent transcript captured on Claude Code 2.1.322: a
response is written once per content block, with the same message id and usage on each line.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import capture

ROOT = Path(__file__).resolve().parent.parent

FIRST = {
    "input_tokens": 2,
    "output_tokens": 212,
    "cache_creation_input_tokens": 19062,
    "cache_read_input_tokens": 0,
    "cache_creation": {"ephemeral_5m_input_tokens": 19062, "ephemeral_1h_input_tokens": 0},
}
LAST = {
    "input_tokens": 2,
    "output_tokens": 312,
    "cache_creation_input_tokens": 378,
    "cache_read_input_tokens": 19062,
    "cache_creation": {"ephemeral_5m_input_tokens": 378, "ephemeral_1h_input_tokens": 0},
}
BRIEF = "id:      map-a\ntask:    probe\ngoal:    list the secret-plan files"


def entry(kind: str, stamp: str, **message) -> str:
    return json.dumps({"type": kind, "timestamp": stamp, "message": message})


def transcript() -> list[str]:
    model = "claude-haiku-5-5"
    tool = [{"type": "tool_use"}]
    return [
        entry("user", "2026-11-12T06:57:01.846Z", role="user", content=BRIEF),
        json.dumps({"type": "attachment", "timestamp": "2026-11-12T06:57:01.862Z"}),
        entry(
            "assistant", "2026-11-12T06:57:04.307Z", id="m1", model=model, usage=FIRST, content=tool
        ),
        entry(
            "assistant", "2026-11-12T06:57:04.537Z", id="m1", model=model, usage=FIRST, content=tool
        ),
        "not json",
        entry(
            "assistant",
            "2026-11-12T06:57:08.658Z",
            id="m2",
            model=model,
            usage=LAST,
            content=[{"type": "text", "text": "id: map-a\nstatus: done"}],
        ),
    ]


def payload(tmp_path: Path, agent: str = "foreman:scout") -> dict:
    path = tmp_path / "agent-abc.jsonl"
    path.write_text("\n".join(transcript()) + "\n", encoding="utf-8")
    return {
        "hook_event_name": "SubagentStop",
        "session_id": "s1",
        "cwd": str(tmp_path),
        "agent_id": "abc",
        "agent_type": agent,
        "agent_transcript_path": str(path),
        "effort": {"level": "low"},
        "last_assistant_message": "id: map-a\nstatus: done",
    }


def feed(monkeypatch, data: bytes) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
    monkeypatch.setattr(capture, "WAIT", 0)


# summarize


def test_summarize_counts_usage_once_per_message():
    summary = capture.summarize(transcript())
    assert summary["turns"] == 2
    assert summary["output_tokens"] == 212 + 312


def test_summarize_reads_the_subtask_id_from_the_brief():
    assert capture.summarize(transcript())["id"] == "map-a"


def test_summarize_tokens_is_the_size_of_the_last_request():
    assert capture.summarize(transcript())["tokens"] == 2 + 312 + 378 + 19062


def test_summarize_splits_cache_writes_and_reads():
    summary = capture.summarize(transcript())
    assert summary["cache_write_5m_tokens"] == 19062 + 378
    assert summary["cache_read_tokens"] == 19062


def test_summarize_duration_spans_the_first_and_last_line():
    assert capture.summarize(transcript())["duration_ms"] == 6812


def test_summarize_counts_tool_calls_and_models():
    summary = capture.summarize(transcript())
    assert summary["tool_uses"] == 2
    assert summary["model"] == "claude-haiku-5-5"


def test_summarize_is_none_without_an_assistant_turn():
    assert capture.summarize(transcript()[:2]) is None


# record


def test_record_names_the_agent_project_and_effort(tmp_path):
    line = capture.record(payload(tmp_path))
    assert (line["agent"], line["effort"]) == ("foreman:scout", "low")
    assert line["project"] == tmp_path.as_posix()


def test_record_skips_an_agent_that_is_not_foreman(tmp_path):
    assert capture.record(payload(tmp_path, agent="Explore")) is None


def test_record_keeps_no_prompt_or_result_text(tmp_path):
    stored = json.dumps(capture.record(payload(tmp_path)))
    assert "secret-plan" not in stored
    assert "status: done" not in stored


def test_record_skips_a_missing_transcript(tmp_path):
    data = payload(tmp_path)
    data["agent_transcript_path"] = str(tmp_path / "gone.jsonl")
    assert capture.record(data) is None


def test_record_takes_the_id_from_the_agent_call_description(tmp_path):
    data = payload(tmp_path)
    meta = {"description": "build-ui", "requestShape": "background", "model": "haiku"}
    (tmp_path / "agent-abc.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    line = capture.record(data)
    assert (line["id"], line["shape"]) == ("build-ui", "background")


def test_record_falls_back_to_the_id_line_of_the_brief(tmp_path):
    line = capture.record(payload(tmp_path))
    assert (line["id"], line["shape"]) == ("map-a", None)


# main


def test_main_writes_nothing_while_the_option_is_off(tmp_path, monkeypatch):
    # Arrange
    out = tmp_path / "agents.jsonl"
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_CAPTURE_RUNS", raising=False)
    monkeypatch.setenv("FOREMAN_CAPTURE_LOG", str(out))
    feed(monkeypatch, json.dumps(payload(tmp_path)).encode())
    # Act
    code = capture.main()
    # Assert
    assert code == 0
    assert not out.exists()


def test_main_appends_one_line_when_the_option_is_on(tmp_path, monkeypatch):
    # Arrange
    out = tmp_path / "log" / "agents.jsonl"
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_CAPTURE_RUNS", "true")
    monkeypatch.setenv("FOREMAN_CAPTURE_LOG", str(out))
    feed(monkeypatch, json.dumps(payload(tmp_path)).encode())
    # Act
    code = capture.main()
    # Assert
    lines = out.read_text(encoding="utf-8").splitlines()
    assert code == 0
    assert [json.loads(x)["id"] for x in lines] == ["map-a"]


def test_main_exits_clean_on_unreadable_input(tmp_path, monkeypatch):
    out = tmp_path / "agents.jsonl"
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_CAPTURE_RUNS", "true")
    monkeypatch.setenv("FOREMAN_CAPTURE_LOG", str(out))
    feed(monkeypatch, b"{ not json")
    assert capture.main() == 0
    assert not out.exists()


def test_append_keeps_only_the_newest_lines(tmp_path, monkeypatch):
    out = tmp_path / "agents.jsonl"
    monkeypatch.setattr(capture, "MAX_LINES", 2)
    for n in range(4):
        capture.append(out, {"n": n})
    assert [json.loads(x)["n"] for x in out.read_text(encoding="utf-8").splitlines()] == [2, 3]


def test_capture_file_sits_beside_the_run_log(monkeypatch, tmp_path):
    monkeypatch.delenv("FOREMAN_CAPTURE_LOG", raising=False)
    monkeypatch.setenv("FOREMAN_LOG", str(tmp_path / "runs.jsonl"))
    assert capture.capture_file() == tmp_path / "agents.jsonl"


# registration


def test_hooks_json_registers_one_gated_background_hook():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    (group,) = hooks["SubagentStop"]
    (handler,) = group["hooks"]
    assert list(hooks) == ["SubagentStop"]
    assert group["matcher"] == "^foreman:"
    assert handler["async"] is True
    assert "CLAUDE_PLUGIN_OPTION_CAPTURE_RUNS" in handler["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/capture.py" in handler["command"]


def test_the_capture_option_is_off_by_default():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    option = manifest["userConfig"]["capture_runs"]
    assert (option["type"], option["default"]) == ("boolean", False)
