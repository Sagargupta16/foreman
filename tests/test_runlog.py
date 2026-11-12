"""Tests for the run log additions in plan.py: failure reasons, the size cap, captured usage,
cost estimates, and the recency, trend and gap lines of `stats`."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import plan


def sub(sid: str, kind: str = "verify", **extra) -> dict:
    return {"id": sid, "kind": kind, "goal": "g", "verify": "v", **extra}


def finished(**b_extra) -> dict:
    b = sub("b", kind="mechanical", owns=["b.md"], status="done", verified=True, **b_extra)
    return {
        "template": "custom",
        "subtasks": [sub("a", status="done", verified=True, tokens=1200), b],
    }


def log_plan(tmp_path: Path, done: dict) -> tuple[int, Path]:
    log = tmp_path / "runs.jsonl"
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(done), encoding="utf-8")
    code = plan.main(["--project", str(tmp_path), "log", str(source), "--log", str(log)])
    return code, log


def lines_of(log: Path) -> list[dict]:
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]


def ago(days: float = 0) -> str:
    when = datetime.datetime.now().astimezone() - datetime.timedelta(days=days)
    return when.isoformat(timespec="seconds")


def captured(tmp_path: Path, **over) -> dict:
    base = {
        "ts": ago(),
        "project": tmp_path.resolve().as_posix(),
        "id": "b",
        "agent": "foreman:mechanic",
        "model": "claude-haiku-5-5",
        "tokens": 9000,
        "duration_ms": 4000,
        "input_tokens": 1000,
        "output_tokens": 2000,
        "cache_read_tokens": 10000,
        "cache_write_5m_tokens": 4000,
        "cache_write_1h_tokens": 0,
    }
    return {**base, **over}


def capture(tmp_path: Path, *rows: dict) -> None:
    text = "".join(json.dumps(r) + "\n" for r in rows)
    (tmp_path / "agents.jsonl").write_text(text, encoding="utf-8")


def rec(tmp_path: Path, days_ago: float = 0, **over) -> dict:
    base = {
        "ts": ago(days_ago),
        "run": f"run-{days_ago}",
        "project": tmp_path.resolve().as_posix(),
        "id": "a",
        "kind": "implement",
        "model": "sonnet",
        "final_model": "sonnet",
        "effort": "medium",
        "final_effort": "medium",
        "status": "done",
        "attempts": 1,
        "verified": True,
    }
    return {**base, **over}


def stats(tmp_path: Path, capsys, records: list[dict], *extra: str) -> str:
    log = tmp_path / "runs.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    assert plan.main(["--project", str(tmp_path), "stats", "--log", str(log), *extra]) == 0
    return capsys.readouterr().out


# log


def test_log_keeps_the_failure_reason_as_one_short_line(tmp_path):
    done = {
        "subtasks": [
            sub("a", status="failed", failure_reason="the build\nbroke  twice " + "x" * 300)
        ]
    }
    code, log = log_plan(tmp_path, done)
    reason = lines_of(log)[0]["failure_reason"]
    assert code == 0
    assert reason.startswith("the build broke twice")
    assert len(reason) == 200


def test_log_keeps_only_its_newest_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(plan, "MAX_LOG_LINES", 3)
    for _ in range(3):
        _, log = log_plan(tmp_path, finished())
    assert [r["id"] for r in lines_of(log)] == ["b", "a", "b"]


def test_log_fills_missing_usage_from_a_captured_run(tmp_path):
    capture(tmp_path, captured(tmp_path))
    _, log = log_plan(tmp_path, finished())
    b = lines_of(log)[1]
    assert (b["tokens"], b["duration_ms"], b["launches"]) == (9000, 4000, 1)
    assert b["resolved_model"] == "claude-haiku-5-5"


def test_log_records_whether_the_agent_call_waited(tmp_path):
    capture(tmp_path, captured(tmp_path, shape="background"))
    _, log = log_plan(tmp_path, finished())
    assert lines_of(log)[1]["shape"] == "background"


def test_log_prefers_the_plans_own_tokens(tmp_path):
    capture(tmp_path, captured(tmp_path, id="a", tokens=21000))
    _, log = log_plan(tmp_path, finished())
    assert lines_of(log)[0]["tokens"] == 1200


def test_log_estimates_cost_at_the_listed_rates(tmp_path):
    capture(tmp_path, captured(tmp_path, id="a", model="claude-sonnet-5-5"))
    _, log = log_plan(tmp_path, finished())
    # sonnet 5.5: (1000 * 2 + 2000 * 10 + 10000 * 0.10 + 4000 * 2.50) / 1e6
    assert lines_of(log)[0]["cost_usd"] == 0.033


def test_log_gives_no_cost_for_a_model_without_a_rate(tmp_path):
    capture(tmp_path, captured(tmp_path, model="some-other-model"))
    _, log = log_plan(tmp_path, finished())
    assert "cost_usd" not in lines_of(log)[1]


def test_log_adds_up_two_launches_of_one_subtask(tmp_path):
    capture(tmp_path, captured(tmp_path), captured(tmp_path, duration_ms=6000))
    _, log = log_plan(tmp_path, finished())
    b = lines_of(log)[1]
    assert (b["launches"], b["duration_ms"], b["output_tokens"]) == (2, 10000, 4000)


def test_log_ignores_a_capture_from_before_the_last_logged_run(tmp_path):
    log_plan(tmp_path, finished())
    capture(tmp_path, captured(tmp_path, ts=ago(0.5)))
    _, log = log_plan(tmp_path, finished())
    assert "launches" not in lines_of(log)[-1]


def test_log_ignores_a_capture_from_another_project(tmp_path):
    capture(tmp_path, captured(tmp_path, project="/somewhere/else"))
    _, log = log_plan(tmp_path, finished())
    assert "launches" not in lines_of(log)[1]


def test_log_counts_a_resumed_agent_once(tmp_path):
    first = captured(tmp_path, agent_id="x1", output_tokens=1000)
    again = captured(tmp_path, agent_id="x1", output_tokens=2500)
    capture(tmp_path, first, again)
    _, log = log_plan(tmp_path, finished())
    b = lines_of(log)[1]
    assert (b["launches"], b["output_tokens"]) == (1, 2500)


def test_log_never_reuses_an_agent_an_earlier_run_took(tmp_path):
    capture(tmp_path, captured(tmp_path, agent_id="x1"))
    log_plan(tmp_path, finished())
    # the same agent again, on a line dated after that run was logged
    capture(tmp_path, captured(tmp_path, agent_id="x1", ts=ago(-0.001)))
    _, log = log_plan(tmp_path, finished())
    assert "launches" not in lines_of(log)[-1]


def test_log_joins_only_the_session_that_ran_last(tmp_path):
    old = captured(tmp_path, agent_id="x1", session="s-old", ts=ago(0.01))
    new = captured(tmp_path, agent_id="x2", session="s-new")
    capture(tmp_path, old, new)
    _, log = log_plan(tmp_path, finished())
    assert lines_of(log)[1]["agent_ids"] == ["x2"]


def test_log_says_when_recent_runs_matched_nothing(tmp_path, capsys):
    capture(tmp_path, captured(tmp_path, project="/somewhere/else"))
    log_plan(tmp_path, finished())
    assert "captured usage: 0 of 2 subtasks; 1 recent agent runs" in capsys.readouterr().out


def test_log_reports_how_many_subtasks_had_captured_usage(tmp_path, capsys):
    capture(tmp_path, captured(tmp_path))
    log_plan(tmp_path, finished())
    assert "captured usage: 1 of 2 subtasks, est. 0.00 USD" in capsys.readouterr().out


def test_project_rates_replace_a_listed_price(tmp_path):
    ext = tmp_path / ".claude" / "foreman"
    ext.mkdir(parents=True)
    rate = {"input": 1, "output": 1, "cache_read": 1, "cache_write_5m": 1, "cache_write_1h": 1}
    (ext / "routing.json").write_text(
        json.dumps({"rates": {"models": {"haiku-5-5": rate}}}), encoding="utf-8"
    )
    capture(tmp_path, captured(tmp_path))
    _, log = log_plan(tmp_path, finished())
    assert lines_of(log)[1]["cost_usd"] == 0.017


# stats


def test_stats_rejects_days_below_one(tmp_path, capsys):
    log = tmp_path / "runs.jsonl"
    log.write_text(json.dumps(rec(tmp_path)), encoding="utf-8")
    code = plan.main(["--project", str(tmp_path), "stats", "--log", str(log), "--days", "0"])
    assert code == 2
    assert "--days takes a whole number" in capsys.readouterr().err


def test_stats_days_keeps_only_recent_runs(tmp_path, capsys):
    out = stats(tmp_path, capsys, [rec(tmp_path, 40), rec(tmp_path, 1)], "--days", "7")
    assert "subtasks: 1 |" in out
    assert "last 7 days" in out


def test_stats_names_the_kinds_with_no_logged_run(tmp_path, capsys):
    out = stats(tmp_path, capsys, [rec(tmp_path)])
    gaps = next(line for line in out.splitlines() if line.startswith("no logged runs for:"))
    assert "solve" in gaps
    assert "implement" not in gaps


def test_stats_reports_a_worsening_week(tmp_path, capsys):
    older = [rec(tmp_path, 20) for _ in range(5)]
    recent = [rec(tmp_path, 1, status="failed", verified=False) for _ in range(3)]
    out = stats(tmp_path, capsys, older + recent)
    assert "trend: implement on sonnet: 0% done in the last 7 days (3)" in out
    assert "against 62% in 30 (8), worsening" in out


def test_stats_stays_quiet_about_a_steady_week(tmp_path, capsys):
    out = stats(tmp_path, capsys, [rec(tmp_path, d) for d in (20, 19, 18, 17, 16, 2, 1, 0)])
    assert "trend:" not in out


def test_stats_shows_the_cost_of_a_verified_result(tmp_path, capsys):
    records = [rec(tmp_path, cost_usd=0.2), rec(tmp_path, cost_usd=0.4)]
    out = stats(tmp_path, capsys, records)
    assert "est. USD per verified" in out
    assert "| 0.300 |" in out


def test_stats_cost_ignores_results_with_no_captured_cost(tmp_path, capsys):
    records = [rec(tmp_path, cost_usd=0.2), rec(tmp_path), rec(tmp_path)]
    assert "| 0.200 |" in stats(tmp_path, capsys, records)


def test_stats_lists_the_latest_failure_reasons(tmp_path, capsys):
    failed = rec(tmp_path, status="failed", verified=False, failure_reason="tests still red")
    out = stats(tmp_path, capsys, [rec(tmp_path, 3), failed])
    assert "recent failures:" in out
    assert "a (implement, sonnet): tests still red" in out
