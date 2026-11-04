"""evals/: the `claude plugin eval` suite is well formed and its deterministic graders discriminate.

Offline only: no model calls and no `claude` command. A case is a directory under evals/ with
prompt.md (frontmatter plus the prompt), case.yaml (the scaffold script) and graders/*.md.
Regex graders run as JavaScript regexes inside `claude plugin eval`; here they run through Python
`re`, so patterns must stay in the syntax both engines read the same way (checked below).
Field names follow code.claude.com/docs/en/plugin-evals; PyYAML is not needed.
"""

from __future__ import annotations

import fnmatch
import functools
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
SCAFFOLD = ROOT / "skills" / "new-agent" / "scripts" / "scaffold.py"
SKILLS = sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md"))
EXPECTED_CASES = {
    "dispatch-two-packages",
    "dispatch-one-unit-inline",
    "new-agent-project-agent",
    "new-agent-lint-broken",
    "routing-no-trigger",
}

# Documented case and grader fields (code.claude.com/docs/en/plugin-evals); unknown keys fail.
PROMPT_KEYS = {
    "schema_version",
    "name",
    "description",
    "tags",
    "plugins",
    "runs",
    "expected_outcome",
    "model",
    "max_turns",
    "timeout_seconds",
    "allowed_tools",
    "append_system_prompt",
    "env",
}
CASE_YAML_KEYS = {"schema_version", "name", "description", "tags", "plugins", "runs"} | {
    "expected_outcome",
    "execution",
    "context",
    "graders",
}
CONTEXT_KEYS = {"scaffold_script", "history_file", "add_dirs"}
GRADER_KEYS = {
    "regex": {"pattern", "flags", "match", "target"},
    "tool_used": {"tool", "input_match", "min", "max"},
    "tool_order": {"before", "after"},
    "file_exists": {"path", "exists"},
    "llm": {"criteria", "focus"},
    "baseline": {"baseline_file", "criteria"},
}
TARGETS = {"last_message", "trace", "files", "mock_calls"}
TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "NotebookRead",
    "Skill",
    "AskUserQuestion",
    "Agent",
    "TodoWrite",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskUpdate",
    "TaskStop",
    "Bash",
    "Write",
    "Edit",
    "WebFetch",
    "WebSearch",
}
# Python and JavaScript read these differently, or one of them lacks them.
NOT_PORTABLE = re.compile(r"\(\?P|\(\?<[=!]|\(\?<\w|\(\?>|\(\?[aiLmsux-]+[:)]|\\[AZzpP]")
BARE_DOLLAR = re.compile(r"(?<!\\)\$")

# ---------------------------------------------------------------- loading


def scalar(raw: str, where: str) -> Any:
    """One YAML scalar from the subset the suite uses."""
    if re.fullmatch(r"'(?:[^']|'')*'", raw):
        return raw[1:-1].replace("''", "'")
    if raw.startswith('"'):
        return json.loads(raw)
    if raw.startswith("[") and raw.endswith("]"):
        items = [item.strip() for item in raw[1:-1].split(",") if item.strip()]
        if not all(re.fullmatch(r"[\w./*-]+", item) for item in items):
            raise ValueError(f"{where}: flow list items must be plain words: {raw}")
        return items
    if re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
        return float(raw) if "." in raw else int(raw)
    if raw in ("true", "false"):
        return raw == "true"
    if re.match(r"[\[\]{}!&*?|>'\"%@`#,]", raw) or ": " in raw or " #" in raw or raw[-1] == ":":
        raise ValueError(f"{where}: quote this value, YAML cannot read it plain: {raw}")
    return raw


def mini_yaml(text: str, where: str) -> dict[str, Any]:
    """key: scalar lines, flow lists of words, and one level of nested mapping."""
    out: dict[str, Any] = {}
    nested: dict[str, Any] | None = None
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.fullmatch(r"( *)([\w-]+):(?: +(.*))?", line)
        if not m:
            raise ValueError(f"{where}:{n}: expected 'key: value', got {line!r}")
        indent, key, raw = m.group(1), m.group(2), (m.group(3) or "").strip()
        scope = out if not indent else nested
        if scope is None or (indent and not raw):
            raise ValueError(f"{where}:{n}: unexpected indent or nesting: {line!r}")
        if key in scope:
            raise ValueError(f"{where}:{n}: duplicate key {key!r}")
        if indent:
            scope[key] = scalar(raw, f"{where}:{n}")
        elif raw:
            scope[key] = scalar(raw, f"{where}:{n}")
            nested = None
        else:
            nested = scope[key] = {}
    return out


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    rel = path.relative_to(ROOT).as_posix()
    m = re.match(r"---\n(.*?)\n---\n?(.*)\Z", read(path), re.S)
    if not m:
        raise ValueError(f"{rel}: needs --- frontmatter ---")
    return mini_yaml(m.group(1), rel), m.group(2).strip()


def case_dirs() -> list[Path]:
    found = {p.parent for name in ("prompt.md", "case.yaml") for p in EVALS.rglob(name)}
    return sorted(d for d in found if "results" not in d.relative_to(EVALS).parts)


CASE_DIRS = case_dirs()
CASE_IDS = [d.relative_to(EVALS).as_posix() for d in CASE_DIRS]


@functools.cache
def load(case: str) -> dict[str, Any]:
    d = EVALS / case
    meta, prompt = frontmatter(d / "prompt.md") if (d / "prompt.md").exists() else ({}, "")
    yml = (
        mini_yaml(read(d / "case.yaml"), f"{case}/case.yaml") if (d / "case.yaml").exists() else {}
    )
    graders = {p.stem: frontmatter(p) for p in sorted((d / "graders").glob("*.md"))}
    prompt = prompt or str(yml.get("execution", {}).get("prompt", ""))
    return {"meta": meta, "yaml": yml, "prompt": prompt, "graders": graders}


GRADER_IDS = [(c, p.stem) for c in CASE_IDS for p in sorted((EVALS / c / "graders").glob("*.md"))]


def grader(case: str, name: str) -> dict[str, Any]:
    return load(case)["graders"][name][0]


def file_target(g: dict[str, Any]) -> str | None:
    target = g.get("target") if g.get("type") == "regex" else None
    return target["path"] if isinstance(target, dict) else None


def py_regex(pattern: str, flags: str = "") -> re.Pattern[str]:
    bits = {"i": re.I, "m": re.M, "s": re.S}
    mode = 0
    for flag in flags:
        mode |= bits[flag]
    return re.compile(pattern, mode)


def passes(g: dict[str, Any], text: str) -> bool:
    """A regex grader's verdict on text, the way `claude plugin eval` scores it."""
    rx = py_regex(str(g["pattern"]), str(g.get("flags", "")))
    match = str(g.get("match", ""))
    if match == "not_contains":
        return rx.search(text) is None
    if match.startswith("count:"):
        return len(list(rx.finditer(text))) == int(match[6:])
    return rx.search(text) is not None


# ---------------------------------------------------------------- scaffold

HEREDOC = re.compile(r"^cat > (\S+) <<'EOF'\n(.*?)^EOF$", re.M | re.S)


def scaffold_script(case: str) -> Path | None:
    name = load(case)["yaml"].get("context", {}).get("scaffold_script")
    return EVALS / case / name if name else None


def staged(case: str) -> dict[str, str]:
    """Files the case's scaffold script writes into the run workspace (its heredocs)."""
    script = scaffold_script(case)
    return {m[1]: m[2] for m in HEREDOC.finditer(read(script))} if script else {}


def git_bash() -> str | None:
    if sys.platform == "win32":
        git = Path("C:/Program Files/Git/bin/bash.exe")
        return git.as_posix() if git.is_file() else None
    return shutil.which("bash")


# ---------------------------------------------------------------- known answers

ROLE = "Reviews SQL migration files for unsafe operations. Use when the user asks for an audit."


def run_scaffold(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCAFFOLD), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )


@functools.cache
def scaffolded_agent() -> str:
    """What `scaffold.py agent migration-auditor --kind review` writes, fill markers included."""
    with tempfile.TemporaryDirectory() as tmp:
        done = run_scaffold(
            "agent", "migration-auditor", "--kind", "review", "--dest", tmp, "--description", ROLE
        )
        assert done.returncode == 0, done.stdout + done.stderr
        return (Path(tmp) / "migration-auditor.md").read_text(encoding="utf-8")


def lint_codes(text: str) -> tuple[int, list[str]]:
    """Exit code and rule ids from `scaffold.py lint` on one agent file."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "agent.md"
        path.write_bytes(text.encode("utf-8"))
        done = run_scaffold("lint", str(path))
    return done.returncode, re.findall(r"^(FA\d{3}) ", done.stdout, re.M)


def filled(text: str) -> str:
    return re.sub(r"<<fill.*?>>", "done", text, flags=re.S)


@functools.cache
def good(case: str) -> dict[str, str]:
    """A known-good workspace per case: what the scaffold stages plus what a good run writes."""
    files = dict(staged(case))
    if case == "dispatch-two-packages":
        files["textkit/__init__.py"] += (
            "\n\ndef reverse(text: str) -> str:\n    return text[::-1]\n"
        )
        files["mathkit/__init__.py"] += (
            "\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n"
        )
        files["tests/test_textkit.py"] = (
            files["tests/test_textkit.py"].replace("import shout", "import reverse, shout")
            + '\n\ndef test_reverse():\n    assert reverse("abc") == "cba"\n'
        )
        files["tests/test_mathkit.py"] = (
            files["tests/test_mathkit.py"].replace("import add", "import add, multiply")
            + "\n\ndef test_multiply():\n    assert multiply(2, 3) == 6\n"
        )
        files["README.md"] += (
            "- `textkit.reverse(text)`: reverse\n- `mathkit.multiply(a, b)`: product\n"
        )
    elif case == "dispatch-one-unit-inline":
        files["calc.py"] = files["calc.py"].replace("total", "sum_all")
    elif case == "new-agent-project-agent":
        files[".claude/agents/migration-auditor.md"] = filled(scaffolded_agent())
    elif case == "new-agent-lint-broken":
        path = ".claude/agents/reviewer.md"
        files[path] = (
            files[path]
            .replace("name: code:reviewer", "name: code-reviewer")
            .replace("allowed-tools: Read", "tools: Read")
            .replace("effort: extreme", "effort: high")
        )
    return files


def edited(case: str, path: str, old: str, new: str) -> str:
    text = good(case)[path]
    assert old in text, (path, old)
    return text.replace(old, new)


AUDITOR = ".claude/agents/migration-auditor.md"
REVIEWER = ".claude/agents/reviewer.md"
TK_TESTS = "tests/test_textkit.py"
MK_TESTS = "tests/test_mathkit.py"

# (case, grader) -> a wrong answer the file grader must reject
BAD_FILES: dict[tuple[str, str], str] = {
    ("dispatch-two-packages", "reverse-added"): staged("dispatch-two-packages")[
        "textkit/__init__.py"
    ],
    ("dispatch-two-packages", "multiply-added"): staged("dispatch-two-packages")[
        "mathkit/__init__.py"
    ],
    ("dispatch-two-packages", "reverse-tested"): staged("dispatch-two-packages")[TK_TESTS].replace(
        "import shout", "import reverse, shout"
    ),
    ("dispatch-two-packages", "multiply-tested"): staged("dispatch-two-packages")[MK_TESTS].replace(
        "import add", "import add, multiply"
    ),
    ("dispatch-two-packages", "readme-lists-both"): staged("dispatch-two-packages")["README.md"]
    + "- `textkit.reverse(text)`: reverse\n",
    ("dispatch-one-unit-inline", "renamed"): staged("dispatch-one-unit-inline")["calc.py"],
    ("dispatch-one-unit-inline", "old-name-gone"): (
        "def total(xs): return sum(xs)\ndef sum_all(xs): return sum(xs)\n"
    ),
    ("dispatch-one-unit-inline", "body-kept"): "def sum_all(xs): return len(xs)\n",
    ("new-agent-project-agent", "name-matches"): filled(scaffolded_agent()).replace(
        "name: migration-auditor", "name: auditor"
    ),
    ("new-agent-project-agent", "model-sonnet"): filled(scaffolded_agent()).replace(
        "model: sonnet", "model: opus"
    ),
    ("new-agent-project-agent", "effort-high"): filled(scaffolded_agent()).replace(
        "effort: high", "effort: medium"
    ),
    ("new-agent-project-agent", "tools-read-only"): filled(scaffolded_agent()).replace(
        "Bash\n", "Bash, Edit, Write\n", 1
    ),
    ("new-agent-project-agent", "no-fill-marker"): scaffolded_agent(),
    ("new-agent-lint-broken", "name-has-no-colon"): staged("new-agent-lint-broken")[REVIEWER],
    ("new-agent-lint-broken", "uses-tools-field"): staged("new-agent-lint-broken")[REVIEWER],
    ("new-agent-lint-broken", "no-allowed-tools"): staged("new-agent-lint-broken")[REVIEWER],
    ("new-agent-lint-broken", "valid-effort"): staged("new-agent-lint-broken")[REVIEWER],
    (
        "new-agent-lint-broken",
        "body-kept",
    ): "---\nname: code-reviewer\ntools: Read\n---\n\nReview.\n",
}

# ---------------------------------------------------------------- tool calls and text samples

PROMPT = 'id: build-textkit\ntask: add reverse\nreturn: a block like {"model": "haiku"}'


def bash(command: str) -> tuple[str, dict[str, Any]]:
    return "Bash", {"command": command, "description": "run it"}


def agent(model: str | None = "haiku", kind: str = "foreman:mechanic") -> tuple[str, dict]:
    fields: dict[str, Any] = {"description": "build-textkit", "subagent_type": kind}
    if model:
        fields["model"] = model
    return "Agent", fields | {"run_in_background": False, "prompt": PROMPT}


def skill(name: str) -> tuple[str, dict[str, Any]]:
    return "Skill", {"skill": name}


PLAN = "python3 /p/skills/dispatch/scripts/plan.py"
CHECK = bash(PLAN + ' check - <<\'EOF\'\n{"task": "x"}\nEOF')
LINT = bash("python3 /p/skills/new-agent/scripts/scaffold.py lint .claude/agents")
AGENT_FILE = bash("python3 /p/skills/new-agent/scripts/scaffold.py agent migration-auditor")
QUOTED = bash('python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" check /tmp/plan.json')

# (case, grader) -> [(calls, expected verdict)]
CALLS: dict[tuple[str, str], list[tuple[list[tuple[str, dict]], bool]]] = {
    ("dispatch-two-packages", "ran-plan-check"): [
        ([bash(PLAN + " templates"), CHECK], True),
        ([QUOTED], True),
        ([bash(PLAN + ' new feature --task "check the readme"')], False),
        ([bash("python3 -m pytest")], False),
    ],
    ("dispatch-two-packages", "check-before-launch"): [
        ([bash(PLAN + " templates"), CHECK, agent()], True),
        ([agent(), CHECK], False),
        ([bash(PLAN + " templates"), agent()], False),
        ([CHECK], False),
    ],
    ("dispatch-two-packages", "foreman-agent-used"): [
        ([agent(kind="foreman:builder")], True),
        ([agent(kind="general-purpose")], False),
        ([agent(kind="Explore")], False),
    ],
    ("dispatch-two-packages", "agent-sets-model"): [
        ([agent("sonnet")], True),
        ([agent(None)], False),
        ([bash("echo model haiku")], False),
    ],
    ("dispatch-two-packages", "no-agent-without-model"): [
        ([agent("haiku"), agent("opus")], True),
        ([], True),
        ([agent("haiku"), agent(None)], False),
    ],
    ("dispatch-one-unit-inline", "no-agent-launched"): [
        ([bash("python3 -m pytest")], True),
        ([agent()], False),
    ],
    ("new-agent-project-agent", "ran-lint"): [([AGENT_FILE, LINT], True), ([AGENT_FILE], False)],
    ("new-agent-lint-broken", "ran-lint"): [([LINT], True), ([bash("cat reviewer.md")], False)],
    ("new-agent-lint-broken", "skill-fired"): [
        ([skill("foreman:new-agent")], True),
        ([skill("new-agent")], True),
        ([skill("foreman:dispatch")], False),
    ],
    ("routing-no-trigger", "no-dispatch-skill"): [
        ([("Read", {"file_path": "textkit/__init__.py"})], True),
        ([skill("foreman:new-agent")], True),
        ([skill("foreman:dispatch")], False),
        ([skill("dispatch")], False),
    ],
}


def dump(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"))


def skill_line(name: str) -> str:
    """A trace line holding a Skill tool call."""
    call = {"name": "Skill", "input": {"skill": name}}
    return dump({"type": "assistant", "message": {"content": [call]}})


def escaped_line(name: str) -> str:
    """A trace line where the Skill call sits inside a JSON string, so its quotes are escaped."""
    return dump({"content": dump({"skill": f"foreman:{name}"})})


def read_line(path: str) -> str:
    return dump({"name": "Read", "input": {"file_path": path}})


def user_line(name: str) -> str:
    """The user's own slash prompt: it names the skill without any skill having run."""
    return dump({"type": "user", "message": {"content": f"/foreman:{name} do the thing"}})


# (case, grader) -> [(text, expected verdict)] for regex graders on the trace, files or reply
TEXTS: dict[tuple[str, str], list[tuple[str, bool]]] = {
    ("dispatch-two-packages", "skill-fired"): [
        (skill_line("foreman:dispatch"), True),
        (escaped_line("dispatch"), True),
        (read_line("/w/plugin/skills/dispatch/references/decompose.md"), True),
        (read_line("C:\\w\\plugin\\skills\\dispatch\\scripts\\plan.py"), True),
        (user_line("dispatch"), False),
        (skill_line("foreman:new-agent"), False),
        (read_line("/w/plugin/skills/new-agent/references/agent-format.md"), False),
    ],
    ("dispatch-one-unit-inline", "skill-fired"): [
        (skill_line("dispatch"), True),
        (read_line("/w/plugin/skills/dispatch/SKILL.md"), True),
        (user_line("dispatch"), False),
        (read_line("/w/calc.py"), False),
    ],
    ("new-agent-project-agent", "skill-fired"): [
        (skill_line("foreman:new-agent"), True),
        (escaped_line("new-agent"), True),
        (read_line("/w/plugin/skills/new-agent/references/agent-format.md"), True),
        (user_line("new-agent"), False),
        (skill_line("foreman:dispatch"), False),
        (read_line("/w/plugin/skills/dispatch/SKILL.md"), False),
    ],
    ("dispatch-two-packages", "no-extra-source-files"): [
        ("", True),
        ("textkit/__pycache__/__init__.cpython-312.pyc\n.pytest_cache/README.md\n", True),
        ("/w/textkit/__pycache__/x.py\n", True),
        ("tests/test_reverse.py\n", False),
        ("/w/textkit/strings.py\n", False),
        ("mathkit/ops.py\nREADME.md\n", False),
    ],
    ("routing-no-trigger", "answers"): [
        ('It returns "HI!" for "hi".', True),
        ("It upper-cases the text and adds an exclamation mark.", False),
        ('It returns "hi!".', False),
    ],
}

# ---------------------------------------------------------------- suite structure


def test_suite_has_the_five_cases() -> None:
    assert EXPECTED_CASES <= set(CASE_IDS), sorted(EXPECTED_CASES - set(CASE_IDS))


def test_every_eval_folder_is_a_case_with_a_prompt_or_case_yaml() -> None:
    folders = [p for p in EVALS.iterdir() if p.is_dir() and p.name != "results"]
    bare = [
        p.name for p in folders if not ((p / "prompt.md").exists() or (p / "case.yaml").exists())
    ]
    assert bare == []


def test_case_names_are_unique_and_match_the_folder() -> None:
    names = [load(c)["meta"].get("name") or load(c)["yaml"].get("name") or c for c in CASE_IDS]
    assert names == CASE_IDS


@pytest.mark.parametrize("case", CASE_IDS)
def test_case_has_a_prompt(case: str) -> None:
    assert len(load(case)["prompt"]) > 20


@pytest.mark.parametrize("case", CASE_IDS)
def test_case_has_a_grader(case: str) -> None:
    assert load(case)["graders"] or load(case)["yaml"].get("graders")


@pytest.mark.parametrize("case", CASE_IDS)
def test_prompt_frontmatter_uses_known_keys(case: str) -> None:
    assert set(load(case)["meta"]) <= PROMPT_KEYS


@pytest.mark.parametrize("case", CASE_IDS)
def test_run_limits_are_modest_and_in_range(case: str) -> None:
    meta = load(case)["meta"]
    assert 1 <= meta.get("max_turns", 10) <= 60
    assert 1 <= meta.get("timeout_seconds", 300) <= 900
    assert 1 <= meta.get("runs", 3) <= 50


@pytest.mark.parametrize("case", CASE_IDS)
def test_allowed_tools_are_known(case: str) -> None:
    tools = load(case)["meta"].get("allowed_tools", [])
    assert tools and set(tools) <= TOOLS


@pytest.mark.parametrize("case", [c for c in CASE_IDS if (EVALS / c / "case.yaml").exists()])
def test_case_yaml_has_the_documented_shape(case: str) -> None:
    yml = load(case)["yaml"]
    assert yml["schema_version"] == "1.1"
    assert yml["name"] == case
    assert set(yml) <= CASE_YAML_KEYS
    assert set(yml.get("context", {})) <= CONTEXT_KEYS


@pytest.mark.parametrize("case", [c for c in CASE_IDS if load(c)["yaml"].get("context")])
def test_scaffold_script_exists_and_is_strict_bash(case: str) -> None:
    script = scaffold_script(case)
    assert script is not None and script.is_file(), script
    text = read(script)
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text
    assert "&&" not in text


@pytest.mark.parametrize("case", [c for c in CASE_IDS if scaffold_script(c)])
def test_scaffold_runs_and_writes_exactly_the_parsed_files(case: str, tmp_path: Path) -> None:
    bash_exe = git_bash()
    if bash_exe is None or shutil.which("git") is None:
        pytest.skip("needs bash and git")
    script = scaffold_script(case)
    assert script is not None
    done = subprocess.run(
        [bash_exe],
        input=read(script),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    written = {
        p.relative_to(tmp_path).as_posix()
        for p in tmp_path.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(tmp_path).parts
    }
    assert written == set(staged(case))
    for path, text in staged(case).items():
        assert read(tmp_path / path) == text


@pytest.mark.parametrize("case", [c for c in CASE_IDS if staged(c)])
def test_staged_python_is_valid(case: str) -> None:
    for path, text in good(case).items():
        if path.endswith(".py"):
            compile(text, path, "exec")


def test_results_dir_is_gitignored() -> None:
    assert "results/" in read(EVALS / ".gitignore").splitlines()


# ---------------------------------------------------------------- graders


@pytest.mark.parametrize(("case", "name"), GRADER_IDS)
def test_grader_frontmatter_is_valid(case: str, name: str) -> None:
    g = grader(case, name)
    kind = g.get("type")
    assert kind in GRADER_KEYS
    assert set(g) <= {"type", "weight", "arm"} | GRADER_KEYS[kind]
    assert g.get("arm") in (None, "with-only", "both")
    assert float(g.get("weight", 1)) > 0
    required = {
        "regex": "pattern",
        "tool_used": "tool",
        "tool_order": "before",
        "file_exists": "path",
    }.get(kind)
    assert required is None or g.get(required) not in (None, "")


@pytest.mark.parametrize(("case", "name"), GRADER_IDS)
def test_tool_names_are_known(case: str, name: str) -> None:
    g = grader(case, name)
    named = [g.get("tool")] if g["type"] == "tool_used" else []
    if g["type"] == "tool_order":
        for side in (g["before"], g["after"]):
            if isinstance(side, dict):
                assert set(side) <= {"tool", "input_match"}
            named.append(side["tool"] if isinstance(side, dict) else side)
        assert g.get("after") is not None
    assert set(named) <= TOOLS


@pytest.mark.parametrize(("case", "name"), GRADER_IDS)
def test_regexes_are_portable_and_compile(case: str, name: str) -> None:
    g = grader(case, name)
    patterns = [str(g[k]) for k in ("pattern", "input_match") if k in g]
    for side in (g.get("before"), g.get("after")):
        if isinstance(side, dict) and "input_match" in side:
            patterns.append(str(side["input_match"]))
    flags = str(g.get("flags", ""))
    assert set(flags) <= {"i", "m", "s"}
    for pattern in patterns:
        assert not NOT_PORTABLE.search(pattern), f"{pattern} uses non-portable syntax"
        assert "m" in flags or not BARE_DOLLAR.search(pattern), "bare $ needs the m flag"
        py_regex(pattern, flags)
    assert str(g.get("match", "not_contains")) == "not_contains" or re.fullmatch(
        r"count:\d+", str(g["match"])
    )


@pytest.mark.parametrize(("case", "name"), GRADER_IDS)
def test_grader_target_is_known(case: str, name: str) -> None:
    g = grader(case, name)
    target = g.get("target", g.get("focus", "last_message"))
    if isinstance(target, dict):
        assert target.get("source") == "file" and set(target) == {"source", "path"}
        assert ".." not in target["path"] and not target["path"].startswith("/")
    else:
        assert target in TARGETS


@pytest.mark.parametrize(("case", "name"), [i for i in GRADER_IDS if grader(*i)["type"] == "llm"])
def test_llm_rubrics_state_pass_and_fail(case: str, name: str) -> None:
    body = load(case)["graders"][name][1]
    assert "PASS if" in body and "FAIL if" in body


@pytest.mark.parametrize(("case", "name"), [i for i in GRADER_IDS if grader(*i)["type"] != "llm"])
def test_grader_body_is_one_paragraph_of_prose(case: str, name: str) -> None:
    body = load(case)["graders"][name][1]
    assert len(body) > 20 and "\n\n" not in body


@pytest.mark.parametrize(("case", "name"), GRADER_IDS)
def test_file_graders_read_files_the_run_can_produce(case: str, name: str) -> None:
    g = grader(case, name)
    path = file_target(g) or (g.get("path") if g["type"] == "file_exists" else None)
    if path is None:
        return
    assert any(fnmatch.fnmatch(p, str(path)) for p in good(case)), path
    if g["type"] == "file_exists":
        # file_exists counts only files created during the run, never ones the scaffold staged
        assert not any(fnmatch.fnmatch(p, str(path)) for p in staged(case)), path


# ---------------------------------------------------------------- skills


def skill_graders() -> list[tuple[str, str]]:
    """Graders that look for a skill firing: a Skill tool call or the skill folder in the trace."""
    return [
        i
        for i in GRADER_IDS
        if re.search(r'"skill', str(grader(*i).get("input_match", grader(*i).get("pattern", ""))))
    ]


def skill_named(g: dict[str, Any]) -> set[str]:
    text = str(g.get("input_match", g.get("pattern", "")))
    return {s for s in SKILLS if re.search(rf"(?<![\w-]){re.escape(s)}(?![\w-])", text)}


@pytest.mark.parametrize(("case", "name"), skill_graders())
def test_skill_graders_name_one_real_skill(case: str, name: str) -> None:
    assert len(skill_named(grader(case, name))) == 1


def test_every_skill_has_a_case_that_expects_it() -> None:
    for skill_dir in SKILLS:
        expects = [
            i
            for i in skill_graders()
            if grader(*i).get("max") != 0 and skill_named(grader(*i)) == {skill_dir}
        ]
        assert expects, skill_dir


@pytest.mark.parametrize("case", [c for c in CASE_IDS if load(c)["prompt"].startswith("/foreman:")])
def test_slash_prompts_call_a_real_skill(case: str) -> None:
    named = re.match(r"/foreman:([\w-]+) ", load(case)["prompt"])
    assert named and named.group(1) in SKILLS


@pytest.mark.parametrize(("case", "name"), GRADER_IDS)
def test_plugin_only_graders_are_with_only(case: str, name: str) -> None:
    """A grader that needs foreman's own scripts, agents or skill folders cannot pass without it."""
    g = grader(case, name)
    sides = [g.get("before"), g.get("after")]
    text = " ".join(
        str(x.get("input_match", "") if isinstance(x, dict) else x)
        for x in [g.get("input_match", ""), g.get("pattern", ""), *sides]
    )
    if (
        g.get("tool") == "Skill"
        or g.get("max") == 0
        or not re.search(r"plan\\\.py|scaffold\\\.py|foreman:|skills\[/", text)
    ):
        return
    assert g.get("arm") == "with-only"


# ---------------------------------------------------------------- graders vs known answers

FILE_GRADERS = [i for i in GRADER_IDS if file_target(grader(*i))]


@pytest.mark.parametrize(("case", "name"), FILE_GRADERS)
def test_file_grader_passes_a_known_good_answer(case: str, name: str) -> None:
    g = grader(case, name)
    assert passes(g, good(case)[file_target(g) or ""])


def test_every_file_grader_has_a_bad_answer() -> None:
    assert {i for i in FILE_GRADERS} - set(BAD_FILES) == set()


@pytest.mark.parametrize(("case", "name"), list(BAD_FILES))
def test_file_grader_rejects_a_bad_answer(case: str, name: str) -> None:
    g = grader(case, name)
    assert not passes(g, BAD_FILES[(case, name)])


TEXT_GRADERS = [
    i for i in GRADER_IDS if grader(*i)["type"] == "regex" and not file_target(grader(*i))
]


def test_every_trace_files_or_reply_grader_has_a_good_and_a_bad_sample() -> None:
    assert set(TEXT_GRADERS) == set(TEXTS)
    for verdicts in TEXTS.values():
        assert {ok for _, ok in verdicts} == {True, False}


@pytest.mark.parametrize(
    ("case", "name", "text", "expected"),
    [(c, n, t, ok) for (c, n), samples in TEXTS.items() for t, ok in samples],
)
def test_trace_files_and_reply_graders_give_the_right_verdict(
    case: str, name: str, text: str, expected: bool
) -> None:
    assert passes(grader(case, name), text) is expected


def encoded(inp: dict[str, Any]) -> str:
    """The JSON a tool_used grader's input_match is tried against."""
    return json.dumps(inp, separators=(",", ":"), ensure_ascii=False)


def matching(spec: str | dict[str, Any], call: tuple[str, dict[str, Any]]) -> bool:
    tool, inp = call
    if isinstance(spec, str):
        return tool == spec
    pattern = spec.get("input_match")
    return tool == spec["tool"] and (
        pattern is None or re.search(pattern, encoded(inp)) is not None
    )


def tool_verdict(g: dict[str, Any], calls: list[tuple[str, dict[str, Any]]]) -> bool:
    if g["type"] == "tool_used":
        spec = {"tool": g["tool"], "input_match": g.get("input_match")}
        hits = sum(matching(spec, c) for c in calls)
        return g.get("min", 1) <= hits <= g.get("max", len(calls) + 1)
    first = {
        side: next((i for i, c in enumerate(calls) if matching(g[side], c)), None)
        for side in ("before", "after")
    }
    return None not in first.values() and first["before"] < first["after"]


TOOL_GRADERS = [i for i in GRADER_IDS if grader(*i)["type"] in ("tool_used", "tool_order")]
NON_SKILL_TOOL_GRADERS = [i for i in TOOL_GRADERS if grader(*i).get("tool") != "Skill"]


def test_every_tool_grader_has_a_good_and_a_bad_call_sequence() -> None:
    wanted = {i for i in NON_SKILL_TOOL_GRADERS if i not in skill_graders()}
    wanted |= {i for i in TOOL_GRADERS if i in skill_graders() and i[1] != "skill-fired"}
    assert wanted <= set(CALLS), sorted(wanted - set(CALLS))
    for samples in CALLS.values():
        assert {ok for _, ok in samples} == {True, False}


@pytest.mark.parametrize(
    ("case", "name", "calls", "expected"),
    [(c, n, calls, ok) for (c, n), samples in CALLS.items() for calls, ok in samples],
)
def test_tool_graders_give_the_right_verdict(
    case: str, name: str, calls: list[tuple[str, dict]], expected: bool
) -> None:
    assert tool_verdict(grader(case, name), calls) is expected


# ---------------------------------------------------------------- fixtures against the scripts


def test_scaffolder_output_matches_what_the_agent_graders_expect() -> None:
    raw = scaffolded_agent()
    for name in ("name-matches", "model-sonnet", "effort-high", "tools-read-only"):
        assert passes(grader("new-agent-project-agent", name), raw), name
    assert "<<fill" in raw


def test_filled_agent_lints_clean() -> None:
    assert lint_codes(good("new-agent-project-agent")[AUDITOR]) == (0, [])


def test_unfilled_agent_lints_a_fill_warning() -> None:
    assert lint_codes(scaffolded_agent()) == (0, ["FA009"])


def test_broken_reviewer_trips_exactly_the_planted_rules() -> None:
    code, rules = lint_codes(staged("new-agent-lint-broken")[REVIEWER])
    assert code == 1
    assert sorted(rules) == ["FA002", "FA004", "FA007"]


def test_fixed_reviewer_lints_clean() -> None:
    assert lint_codes(good("new-agent-lint-broken")[REVIEWER]) == (0, [])


def test_the_dispatch_plan_checker_command_exists() -> None:
    plan = ROOT / "skills" / "dispatch" / "scripts" / "plan.py"
    done = subprocess.run(
        [sys.executable, str(plan), "check", "-"],
        input='{"task": "x", "subtasks": []}',
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert done.returncode == 1 and "FM001" in done.stdout + done.stderr
