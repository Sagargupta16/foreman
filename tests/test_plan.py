"""Tests for skills/dispatch/scripts/plan.py: check rules, templates, run log, stats, workflow."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import plan

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "feature-plan.json"
HARNESS = Path(__file__).resolve().parent / "workflow_harness.mjs"


def routing(project: Path | None = None) -> dict:
    return plan.load_routing(project or ROOT)


def sub(sid: str, kind: str = "verify", **extra) -> dict:
    base = {"id": sid, "kind": kind, "goal": "g", "verify": "v"}
    return {**base, **extra}


def report_for(*subtasks: dict) -> dict:
    return plan.check_plan({"subtasks": list(subtasks)}, routing())


def codes(lines: list[str]) -> set[str]:
    return {line.split()[0] for line in lines}


# check


def test_example_plan_passes_with_three_waves():
    # Arrange
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    # Act
    report = plan.check_plan(example, routing())
    # Assert
    assert report["errors"] == []
    assert report["waves"] == [["map"], ["build-api", "build-ui"], ["docs", "review", "verify"]]


def test_fm001_plan_without_subtasks():
    report = plan.check_plan({"task": "x"}, routing())
    assert codes(report["errors"]) == {"FM001"}


def test_fm002_duplicate_id():
    report = report_for(sub("a"), sub("a"), sub("b"))
    assert "FM002" in codes(report["errors"])


def test_fm003_unknown_kind():
    report = report_for(sub("a", kind="polish"), sub("b"))
    assert "FM003" in codes(report["errors"])


def test_fm004_model_not_an_alias():
    report = report_for(sub("a", model="gpt-5", why="x"), sub("b"))
    assert "FM004" in codes(report["errors"])


def test_fm004_effort_not_a_level():
    report = report_for(sub("a", effort="extreme"), sub("b"))
    assert "FM004" in codes(report["errors"])


def test_fm005_model_change_needs_why():
    report = report_for(sub("a", model="opus"), sub("b"))
    assert "FM005" in codes(report["errors"])


def test_fm005_model_change_with_why_passes():
    report = report_for(sub("a", model="opus", why="security lens"), sub("b"))
    assert report["errors"] == []


def test_fm006_after_names_no_subtask():
    report = report_for(sub("a", after=["ghost"]), sub("b"))
    assert "FM006" in codes(report["errors"])


def test_fm006_cycle():
    report = report_for(sub("a", after=["b"]), sub("b", after=["a"]))
    assert any(e.startswith("FM006 cycle") for e in report["errors"])


def test_fm007_read_only_owns_paths():
    report = report_for(sub("a", kind="review", owns=["src/x.py"]), sub("b"))
    assert "FM007" in codes(report["errors"])


def test_fm008_writer_owns_nothing():
    report = report_for(sub("a", kind="implement"), sub("b"))
    assert "FM008" in codes(report["errors"])


def test_fm009_same_wave_overlap_is_an_error():
    report = report_for(
        sub("a", kind="implement", owns=["src/**"]),
        sub("b", kind="implement", owns=["src/api/users.py"]),
    )
    assert "FM009" in codes(report["errors"])


def test_fm009_overlap_in_different_waves_is_fine():
    report = report_for(
        sub("a", kind="implement", owns=["src/**"]),
        sub("b", kind="implement", owns=["src/api/users.py"], after=["a"]),
    )
    assert report["errors"] == []


def test_fm009_loose_globs_only_warn():
    report = report_for(
        sub("a", kind="implement", owns=["web/*.tsx"]),
        sub("b", kind="implement", owns=["web/*.css"]),
    )
    assert "FM009" in codes(report["warnings"])
    assert report["errors"] == []


def test_fm010_no_verify():
    report = report_for(sub("a", verify=""), sub("b"))
    assert "FM010" in codes(report["errors"])


def test_fm011_wave_wider_than_max():
    many = [sub(f"r-{n}") for n in range(routing()["max_wave"] + 1)]
    report = report_for(*many)
    assert "FM011" in codes(report["warnings"])


def test_fm012_single_subtask_warns_inline():
    report = report_for(sub("a"))
    assert "FM012" in codes(report["warnings"])


def test_fm013_unknown_agent_warns():
    report = report_for(sub("a", agent="someone:else", why="custom"), sub("b"))
    assert "FM013" in codes(report["warnings"])


def test_fm014_template_hint_left():
    report = report_for(sub("a", fan_out="one per lane"), sub("b"))
    assert "FM014" in codes(report["warnings"])


def test_after_prefix_waits_for_whole_group():
    report = report_for(
        sub("build-a", kind="implement", owns=["a.py"]),
        sub("build-b", kind="implement", owns=["b.py"]),
        sub("check", after=["build"]),
    )
    assert report["waves"] == [["build-a", "build-b"], ["check"]]


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("src/a.py", "src/a.py", "same"),
        ("./src/a.py", "src/a.py", "same"),
        ("src", "src/a.py", "same"),
        ("src/**", "src/api/x.py", "same"),
        ("web/**", "web/*.tsx", "same"),
        ("src/a.py", "src/b.py", None),
        ("src/**", "docs/x.md", None),
        ("web/*.tsx", "web/*.css", "maybe"),
    ],
)
def test_overlap(a, b, expected):
    assert plan.overlap(a, b) == expected


def test_project_route_override_changes_the_default(tmp_path):
    # Arrange
    ext = tmp_path / ".claude" / "foreman"
    ext.mkdir(parents=True)
    (ext / "routing.json").write_text(
        json.dumps({"kinds": {"review": {"model": "opus"}}}), encoding="utf-8"
    )
    # Act
    report = plan.check_plan(
        {"subtasks": [sub("a", kind="review", model="opus"), sub("b")]}, routing(tmp_path)
    )
    # Assert
    assert report["errors"] == []


# templates


def test_every_shipped_template_validates():
    kinds = routing()["kinds"]
    for path in sorted((ROOT / "skills" / "dispatch" / "templates").glob("*.json")):
        template = json.loads(path.read_text(encoding="utf-8"))
        assert plan.validate_template(template, kinds) == [], path.name


def test_new_skeleton_only_lacks_owns_and_hints():
    for name, (template, _) in plan.load_templates(ROOT).items():
        skeleton = plan.new_plan(template, "task", routing())
        report = plan.check_plan(skeleton, routing())
        assert codes(report["errors"]) <= {"FM008"}, name


def test_project_template_is_listed(tmp_path):
    # Arrange
    folder = tmp_path / ".claude" / "foreman" / "templates"
    folder.mkdir(parents=True)
    shipped = (ROOT / "skills" / "dispatch" / "templates" / "docs.json").read_text(encoding="utf-8")
    (folder / "house-docs.json").write_text(
        shipped.replace('"name": "docs"', '"name": "house-docs"'), encoding="utf-8"
    )
    # Act
    templates = plan.load_templates(tmp_path)
    # Assert
    assert templates["house-docs"][1] == "project"


# log and stats


def finished(status_b: str = "done", model_b: str | None = None) -> dict:
    b = sub("b", kind="mechanical", owns=["b.md"], status=status_b, verified=True)
    if model_b:
        b.update(model=model_b, why="test")
    return {
        "template": "custom",
        "subtasks": [sub("a", status="done", verified=True, tokens=1200), b],
    }


def test_log_appends_one_line_per_subtask(tmp_path):
    # Arrange
    log = tmp_path / "runs.jsonl"
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(finished()), encoding="utf-8")
    # Act
    code = plan.main(["--project", str(tmp_path), "log", str(source), "--log", str(log)])
    # Assert
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert code == 0
    assert [r["id"] for r in lines] == ["a", "b"]
    assert lines[0]["tokens"] == 1200
    assert lines[1]["route_model"] == "haiku"


def test_log_rejects_unknown_status_and_writes_nothing(tmp_path):
    log = tmp_path / "runs.jsonl"
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(finished(status_b="great")), encoding="utf-8")
    code = plan.main(["--project", str(tmp_path), "log", str(source), "--log", str(log)])
    assert code == 1
    assert not log.exists()


def test_log_file_follows_foreman_log_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FOREMAN_LOG", str(tmp_path / "env.jsonl"))
    assert plan.log_file(None) == tmp_path / "env.jsonl"


def log_runs(tmp_path: Path, count: int, status_b: str, model_b: str | None = None) -> Path:
    log = tmp_path / "runs.jsonl"
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(finished(status_b, model_b)), encoding="utf-8")
    for _ in range(count):
        plan.main(["--project", str(tmp_path), "log", str(source), "--log", str(log)])
    return log


def test_stats_hints_raise_when_a_route_fails_often(tmp_path, capsys):
    log = log_runs(tmp_path, 5, status_b="failed")
    capsys.readouterr()
    plan.main(["--project", str(tmp_path), "stats", "--log", str(log)])
    assert "raise mechanical to sonnet" in capsys.readouterr().out


def test_stats_hints_lower_when_the_tier_below_succeeds(tmp_path, capsys):
    log = tmp_path / "runs.jsonl"
    source = tmp_path / "plan.json"
    done_on_haiku = {
        "subtasks": [
            sub(
                "a",
                kind="implement",
                owns=["a.py"],
                model="haiku",
                why="t",
                status="done",
                verified=True,
            ),
            sub("b", status="done", verified=True),
        ]
    }
    source.write_text(json.dumps(done_on_haiku), encoding="utf-8")
    for _ in range(5):
        plan.main(["--project", str(tmp_path), "log", str(source), "--log", str(log)])
    capsys.readouterr()
    plan.main(["--project", str(tmp_path), "stats", "--log", str(log)])
    assert "lower implement to haiku" in capsys.readouterr().out


def test_stats_gives_no_hint_below_min_samples(tmp_path, capsys):
    log = log_runs(tmp_path, plan.MIN_SAMPLES - 1, status_b="failed")
    capsys.readouterr()
    plan.main(["--project", str(tmp_path), "stats", "--log", str(log)])
    assert "none yet" in capsys.readouterr().out


def test_stats_filters_to_the_project(tmp_path, capsys):
    log = log_runs(tmp_path, 1, status_b="done")
    other = tmp_path / "other"
    other.mkdir()
    capsys.readouterr()
    plan.main(["--project", str(other), "stats", "--log", str(log)])
    assert "no logged subtasks" in capsys.readouterr().out


def test_cell_shows_zero():
    assert plan.cell(0) == "0"


# workflow


def compile_example(tmp_path: Path) -> Path:
    out = tmp_path / "feature.js"
    code = plan.main(["--project", str(ROOT), "workflow", str(EXAMPLE), "--out", str(out)])
    assert code == 0
    return out


def test_workflow_refuses_a_plan_with_errors(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"subtasks": [sub("a", kind="implement"), sub("b")]}), "utf-8")
    assert plan.main(["workflow", str(bad), "--out", str(tmp_path / "x.js")]) == 1


def test_workflow_meta_has_one_phase_per_wave(tmp_path):
    script = compile_example(tmp_path).read_text(encoding="utf-8")
    meta = json.loads(script.split("export const meta = ", 1)[1].split("\n\n", 1)[0])
    assert meta["name"] == "foreman-feature"
    assert [p["title"] for p in meta["phases"]] == ["Wave 1", "Wave 2", "Wave 3"]


def test_workflow_uses_no_clock_or_randomness(tmp_path):
    script = compile_example(tmp_path).read_text(encoding="utf-8")
    assert "Date.now" not in script
    assert "Math.random" not in script
    assert "new Date()" not in script


def run_harness(script: Path, fail_once: str = "", blocks: str = "") -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    out = subprocess.run(
        [node, str(HARNESS), str(script), fail_once, blocks],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return json.loads(out.stdout)


def test_workflow_calls_set_agent_type_model_and_schema(tmp_path):
    result = run_harness(compile_example(tmp_path))
    assert len(result["calls"]) == 6
    assert all(c["agentType"].startswith("foreman:") for c in result["calls"])
    assert all(
        c["model"] in ("haiku", "sonnet", "opus") and c["hasSchema"] for c in result["calls"]
    )


def test_workflow_failed_subtask_retries_once_a_tier_up(tmp_path):
    result = run_harness(compile_example(tmp_path), fail_once="build-api")
    retries = [c for c in result["calls"] if c["id"] == "build-api"]
    assert [c["model"] for c in retries] == ["sonnet", "opus"]
    assert retries[1]["retry"] is True
    assert result["statuses"]["build-api"] == {
        "status": "done",
        "attempts": 2,
        "final_model": "opus",
    }


def test_workflow_blocked_subtask_skips_its_dependents(tmp_path):
    result = run_harness(compile_example(tmp_path), blocks="map")
    assert len(result["calls"]) == 1
    assert result["statuses"]["map"]["status"] == "blocked"
    assert {result["statuses"][i]["status"] for i in ("build-api", "docs", "verify")} == {"skipped"}
