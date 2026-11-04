"""Tests for skills/new-agent/scripts/scaffold.py: lint rules, agent, plugin, register."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import NamedTuple

import pytest

import scaffold

ROOT = Path(__file__).resolve().parent.parent
SCOUT = ROOT / "agents" / "scout.md"
ROUTING = json.loads(scaffold.ROUTING.read_text(encoding="utf-8"))
PROFILES = ROUTING["profiles"]
BODY = "You are the demo.\n"
BASE = {"name": "demo", "description": "A demo agent.", "model": "haiku", "effort": "low"}
SUMMARY = re.compile(r"(\d+) agent files linted, (\d+) errors, (\d+) warnings")


class Lint(NamedTuple):
    code: int
    findings: list[str]
    files: int
    errors: int
    warnings: int

    @property
    def codes(self) -> list[str]:
        return [line[:5] for line in self.findings]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def field(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}: (.*)$", text, re.M)
    assert match, f"{key} missing from:\n{text}"
    return match.group(1)


def write_agent(
    folder: Path,
    fields: dict[str, str | None] | None = None,
    *,
    body: str = BODY,
    filename: str = "demo.md",
) -> Path:
    merged = {**BASE, **(fields or {})}
    lines = [f"{key}: {value}" for key, value in merged.items() if value is not None]
    path = folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + body, encoding="utf-8", newline="\n")
    return path


def run_lint(capsys: pytest.CaptureFixture[str], *paths: Path) -> Lint:
    code = scaffold.main(["lint", *(str(p) for p in paths)])
    out = capsys.readouterr().out
    match = SUMMARY.search(out)
    assert match, f"no summary line in:\n{out}"
    files, errors, warnings = (int(n) for n in match.groups())
    findings = [line for line in out.splitlines() if line.startswith("FA")]
    return Lint(code, findings, files, errors, warnings)


def make_plugin_root(root: Path) -> None:
    manifest = root / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}\n", encoding="utf-8")


def make_plugin(dest: Path, *extra: str, name: str = "my-plug") -> int:
    return scaffold.main(
        [
            "plugin",
            name,
            "--dest",
            str(dest),
            "--author",
            "Ada Lovelace",
            "--description",
            "Audits things.",
            *extra,
        ]
    )


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "my-plug"
    make_plugin(dest, "--agent", "auditor:review", "--agent", "fixer:implement")
    return dest


def register(project: Path, *argv: str) -> int:
    return scaffold.main(["register", *argv, "--project", str(project)])


def routes_of(project: Path) -> dict:
    return json.loads(read(project / ".claude" / "foreman" / "routing.json"))


# lint: clean file, exit codes, directories


def test_lint_valid_agent_copy_has_no_findings(tmp_path, capsys):
    copy = tmp_path / "scout.md"
    shutil.copy(SCOUT, copy)

    result = run_lint(capsys, copy)

    assert result.findings == []
    assert (result.code, result.errors, result.warnings) == (0, 0, 0)


def test_lint_exits_1_when_there_is_an_error(tmp_path, capsys):
    path = write_agent(tmp_path, {"model": "gpt-4o"})

    result = run_lint(capsys, path)

    assert (result.code, result.errors) == (1, 1)


def test_lint_exits_0_on_warnings_only(tmp_path, capsys):
    path = write_agent(tmp_path, {"flavor": "mint"})

    result = run_lint(capsys, path)

    assert (result.code, result.errors, result.warnings) == (0, 0, 1)


def test_lint_exits_1_when_one_of_two_files_has_an_error(tmp_path, capsys):
    good = write_agent(tmp_path)
    bad = write_agent(tmp_path, {"effort": "ultra"}, filename="bad.md")

    result = run_lint(capsys, good, bad)

    assert (result.code, result.files, result.errors) == (1, 2, 1)


def test_lint_directory_argument_lints_every_md_recursively(tmp_path, capsys):
    folder = tmp_path / "agents"
    write_agent(folder, filename="a.md")
    write_agent(folder, {"model": "gpt-4o"}, filename="nested/deeper/b.md")

    result = run_lint(capsys, folder)

    assert result.files == 2
    assert any("b.md" in line for line in result.findings)


def test_lint_directory_argument_skips_non_md_files(tmp_path, capsys):
    folder = tmp_path / "agents"
    write_agent(folder, filename="a.md")
    (folder / "notes.txt").write_text("not an agent\n", encoding="utf-8")

    result = run_lint(capsys, folder)

    assert (result.code, result.files, result.findings) == (0, 1, [])


# lint: FA001 frontmatter


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("Just prose, no frontmatter.\n", id="no-frontmatter"),
        pytest.param("\n---\nname: demo\n---\nbody\n", id="blank-line-before-opening"),
        pytest.param("---\nname: demo\nbody never closes\n", id="never-closed"),
    ],
)
def test_fa001_error_when_frontmatter_missing_or_not_first(tmp_path, capsys, text):
    path = tmp_path / "demo.md"
    path.write_text(text, encoding="utf-8", newline="\n")

    result = run_lint(capsys, path)

    assert result.codes == ["FA001"]
    assert (result.code, result.errors, result.warnings) == (1, 1, 0)


# lint: FA002 name


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(None, id="missing"),
        pytest.param("my-plugin:demo", id="colon"),
        pytest.param("-demo", id="leading-dash"),
        pytest.param("a" * 257, id="over-256-chars"),
    ],
)
def test_fa002_error_for_unusable_name(tmp_path, capsys, name):
    path = write_agent(tmp_path, {"name": name})

    result = run_lint(capsys, path)

    assert result.codes == ["FA002"]
    assert (result.code, result.errors, result.warnings) == (1, 1, 0)


def test_fa002_name_of_exactly_256_chars_is_accepted(tmp_path, capsys):
    path = write_agent(tmp_path, {"name": "a" * 256})

    result = run_lint(capsys, path)

    assert result.findings == []


def test_fa002_warns_when_name_is_not_kebab_case(tmp_path, capsys):
    path = write_agent(tmp_path, {"name": "Demo_Agent"})

    result = run_lint(capsys, path)

    assert result.codes == ["FA002"]
    assert (result.code, result.errors, result.warnings) == (0, 0, 1)


# lint: FA003 description


def test_fa003_error_when_description_missing(tmp_path, capsys):
    path = write_agent(tmp_path, {"description": None})

    result = run_lint(capsys, path)

    assert result.codes == ["FA003"]
    assert (result.code, result.errors) == (1, 1)


def test_fa003_error_when_plain_description_contains_colon_space(tmp_path, capsys):
    path = write_agent(tmp_path, {"description": "Use when needed: always"})

    result = run_lint(capsys, path)

    assert result.codes == ["FA003"]
    assert (result.code, result.errors) == (1, 1)


@pytest.mark.parametrize(
    "description",
    [
        pytest.param('"Use when needed: always"', id="quoted"),
        pytest.param(">-\n  Use when needed: always", id="folded"),
    ],
)
def test_fa003_colon_space_is_fine_in_quoted_or_folded_description(tmp_path, capsys, description):
    path = write_agent(tmp_path, {"description": description})

    result = run_lint(capsys, path)

    assert result.findings == []


@pytest.mark.parametrize(("length", "warnings"), [(1000, 0), (1001, 1)])
def test_fa003_warns_only_when_description_passes_1000_chars(tmp_path, capsys, length, warnings):
    path = write_agent(tmp_path, {"description": "a" * length})

    result = run_lint(capsys, path)

    assert (result.code, result.errors, result.warnings) == (0, 0, warnings)


# lint: FA004 unknown fields


def test_fa004_warns_on_unknown_field_and_suggests_the_likely_name(tmp_path, capsys):
    path = write_agent(tmp_path, {"allowed-tools": "Read"})

    result = run_lint(capsys, path)

    assert result.codes == ["FA004"]
    assert "did you mean tools" in result.findings[0]
    assert (result.code, result.errors, result.warnings) == (0, 0, 1)


def test_fa004_warns_on_unknown_field_without_a_suggestion(tmp_path, capsys):
    path = write_agent(tmp_path, {"flavor": "mint"})

    result = run_lint(capsys, path)

    assert result.codes == ["FA004"]
    assert "did you mean" not in result.findings[0]


# lint: FA005 plugin agents


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("hooks", "x"),
        ("mcpServers", "x"),
        ("permissionMode", "plan"),
        ("initialPrompt", "hello"),
    ],
)
def test_fa005_warns_on_ignored_field_inside_a_plugin(tmp_path, capsys, key, value):
    make_plugin_root(tmp_path / "plug")
    path = write_agent(tmp_path / "plug" / "agents", {key: value})

    result = run_lint(capsys, path)

    assert result.codes == ["FA005"]
    assert key in result.findings[0]
    assert (result.code, result.errors, result.warnings) == (0, 0, 1)


def test_fa005_does_not_fire_outside_a_plugin(tmp_path, capsys):
    path = write_agent(tmp_path / "loose" / "agents", {"permissionMode": "plan"})

    result = run_lint(capsys, path)

    assert result.findings == []


def test_fa005_does_not_fire_when_only_marketplace_json_exists(tmp_path, capsys):
    market = tmp_path / "plug" / ".claude-plugin" / "marketplace.json"
    market.parent.mkdir(parents=True)
    market.write_text("{}\n", encoding="utf-8")
    path = write_agent(tmp_path / "plug" / "agents", {"permissionMode": "plan"})

    result = run_lint(capsys, path)

    assert result.findings == []


# lint: FA006 model


def test_fa006_error_when_model_is_not_an_alias_or_model_id(tmp_path, capsys):
    path = write_agent(tmp_path, {"model": "gpt-4o"})

    result = run_lint(capsys, path)

    assert result.codes == ["FA006"]
    assert (result.code, result.errors, result.warnings) == (1, 1, 0)


@pytest.mark.parametrize(
    "model",
    ["haiku", "sonnet", "opus", "fable", "inherit", "claude-sonnet-5-5", "us.anthropic.x"],
)
def test_fa006_accepts_aliases_inherit_and_model_ids(tmp_path, capsys, model):
    path = write_agent(tmp_path, {"model": model})

    result = run_lint(capsys, path)

    assert result.findings == []


# lint: FA007 enumerated values


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("effort", "ultra"),
        ("color", "magenta"),
        ("isolation", "container"),
        ("memory", "global"),
        ("background", "maybe"),
    ],
)
def test_fa007_error_for_invalid_value(tmp_path, capsys, key, value):
    path = write_agent(tmp_path, {key: value})

    result = run_lint(capsys, path)

    assert result.codes == ["FA007"]
    assert key in result.findings[0]
    assert (result.code, result.errors, result.warnings) == (1, 1, 0)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("effort", "max"),
        ("color", "cyan"),
        ("isolation", "worktree"),
        ("memory", "project"),
        ("background", "true"),
    ],
)
def test_fa007_accepts_valid_value(tmp_path, capsys, key, value):
    path = write_agent(tmp_path, {key: value})

    result = run_lint(capsys, path)

    assert result.findings == []


# lint: FA008 model without effort


def test_fa008_warns_when_model_is_set_without_effort(tmp_path, capsys):
    path = write_agent(tmp_path, {"effort": None})

    result = run_lint(capsys, path)

    assert result.codes == ["FA008"]
    assert (result.code, result.errors, result.warnings) == (0, 0, 1)


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"model": "inherit", "effort": None}, id="inherit"),
        pytest.param({"model": None, "effort": None}, id="no-model"),
    ],
)
def test_fa008_silent_when_there_is_nothing_to_inherit_wrongly(tmp_path, capsys, fields):
    path = write_agent(tmp_path, fields)

    result = run_lint(capsys, path)

    assert result.findings == []


# lint: FA009 placeholders, FA010 empty body


def test_fa009_warns_when_a_fill_placeholder_is_left(tmp_path, capsys):
    path = write_agent(tmp_path, body="You are the demo. <<fill: what you do>>\n")

    result = run_lint(capsys, path)

    assert result.codes == ["FA009"]
    assert (result.code, result.errors, result.warnings) == (0, 0, 1)


@pytest.mark.parametrize("body", ["", "\n   \n"], ids=["empty", "whitespace"])
def test_fa010_warns_when_body_is_empty(tmp_path, capsys, body):
    path = write_agent(tmp_path, body=body)

    result = run_lint(capsys, path)

    assert result.codes == ["FA010"]
    assert (result.code, result.errors, result.warnings) == (0, 0, 1)


# agent


@pytest.mark.parametrize("kind", ["review", "implement", "locate"])
def test_agent_writes_model_effort_and_tools_for_the_kind(tmp_path, kind):
    route = ROUTING["kinds"][kind]

    scaffold.main(["agent", "demo", "--kind", kind, "--dest", str(tmp_path)])

    text = read(tmp_path / "demo.md")
    assert field(text, "model") == route["model"]
    assert field(text, "effort") == route["effort"]
    assert field(text, "tools") == PROFILES[route["profile"]]


def test_agent_model_and_effort_flags_override_the_kind_defaults(tmp_path):
    tools = PROFILES[ROUTING["kinds"]["locate"]["profile"]]

    scaffold.main(
        [
            "agent",
            "demo",
            "--kind",
            "locate",
            "--dest",
            str(tmp_path),
            "--model",
            "opus",
            "--effort",
            "max",
        ]
    )

    text = read(tmp_path / "demo.md")
    assert (field(text, "model"), field(text, "effort")) == ("opus", "max")
    assert field(text, "tools") == tools


def test_agent_writes_the_name_into_the_file(tmp_path):
    scaffold.main(["agent", "demo-agent", "--kind", "review", "--dest", str(tmp_path)])

    assert field(read(tmp_path / "demo-agent.md"), "name") == "demo-agent"


def test_agent_folds_the_description_into_a_block_scalar(tmp_path):
    description = (
        "Reads a diff and reports findings with file and line evidence. Called by the foreman\n"
        "for review subtasks; also use it directly for a second opinion. Never edits files."
    )

    scaffold.main(
        ["agent", "demo", "--kind", "review", "--dest", str(tmp_path), "--description", description]
    )

    block = re.search(r"^description: >-\n((?:  .*\n)+)", read(tmp_path / "demo.md"), re.M)
    assert block, "description is not a >- block"
    lines = block.group(1).splitlines()
    assert len(lines) > 1
    assert all(len(line) <= 76 for line in lines)
    assert " ".join(line.strip() for line in lines) == " ".join(description.split())


def test_agent_without_description_leaves_fill_markers_that_lint_warns_about(tmp_path, capsys):
    code = scaffold.main(["agent", "demo", "--kind", "review", "--dest", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "FA009" in out
    assert "0 errors" in out


def test_agent_refuses_to_overwrite_an_existing_file(tmp_path):
    target = tmp_path / "demo.md"
    target.write_text("keep me\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        scaffold.main(["agent", "demo", "--kind", "review", "--dest", str(tmp_path)])

    assert "--force" in str(exc.value.code)
    assert read(target) == "keep me\n"


def test_agent_force_overwrites_an_existing_file(tmp_path):
    target = tmp_path / "demo.md"
    target.write_text("keep me\n", encoding="utf-8")

    scaffold.main(["agent", "demo", "--kind", "review", "--dest", str(tmp_path), "--force"])

    assert read(target).startswith("---\nname: demo\n")


def test_agent_unknown_kind_exits_with_the_known_kinds_and_writes_nothing(tmp_path):
    with pytest.raises(SystemExit) as exc:
        scaffold.main(["agent", "demo", "--kind", "bogus", "--dest", str(tmp_path)])

    message = str(exc.value.code)
    assert "unknown kind 'bogus'" in message
    assert all(kind in message for kind in ROUTING["kinds"])
    assert not (tmp_path / "demo.md").exists()


# plugin


def test_plugin_writes_manifest_as_valid_json(plugin_dir):
    manifest = json.loads(read(plugin_dir / ".claude-plugin" / "plugin.json"))

    assert manifest["name"] == "my-plug"
    assert manifest["description"] == "Audits things."
    assert manifest["author"] == {"name": "Ada Lovelace"}


def test_plugin_marketplace_has_the_same_version_as_the_manifest(plugin_dir):
    manifest = json.loads(read(plugin_dir / ".claude-plugin" / "plugin.json"))
    market = json.loads(read(plugin_dir / ".claude-plugin" / "marketplace.json"))

    assert market["plugins"][0]["version"] == manifest["version"]


def test_plugin_marketplace_has_metadata_description(plugin_dir):
    market = json.loads(read(plugin_dir / ".claude-plugin" / "marketplace.json"))

    assert market["metadata"]["description"] == "Audits things."


def test_plugin_marketplace_lists_the_plugin_with_source_dot_slash(plugin_dir):
    market = json.loads(read(plugin_dir / ".claude-plugin" / "marketplace.json"))

    assert len(market["plugins"]) == 1
    assert market["plugins"][0]["name"] == "my-plug"
    assert market["plugins"][0]["source"] == "./"


def test_plugin_writes_one_agent_file_per_agent_flag(plugin_dir):
    names = sorted(p.name for p in (plugin_dir / "agents").glob("*.md"))

    assert names == ["auditor.md", "fixer.md"]


def test_plugin_agent_uses_the_model_of_its_kind(plugin_dir):
    text = read(plugin_dir / "agents" / "auditor.md")

    assert field(text, "model") == ROUTING["kinds"]["review"]["model"]


def test_plugin_agent_without_a_kind_defaults_to_implement(tmp_path):
    dest = tmp_path / "my-plug"

    make_plugin(dest, "--agent", "helper")

    text = read(dest / "agents" / "helper.md")
    assert field(text, "model") == ROUTING["kinds"]["implement"]["model"]
    assert field(text, "tools") == PROFILES[ROUTING["kinds"]["implement"]["profile"]]


def test_plugin_lints_its_agents_and_exits_0(tmp_path, capsys):
    code = make_plugin(tmp_path / "my-plug", "--agent", "auditor:review", "--agent", "fixer")

    out = capsys.readouterr().out
    assert code == 0
    assert "2 agent files linted, 0 errors" in out


def test_plugin_readme_has_a_row_per_agent(plugin_dir):
    readme = read(plugin_dir / "README.md")
    review = ROUTING["kinds"]["review"]

    assert readme.startswith("# my-plug\n")
    assert f"| auditor | {review['model']} | {review['effort']} |" in readme
    assert "| fixer |" in readme


def test_plugin_changelog_has_a_dated_first_release_listing_the_agents(plugin_dir):
    changelog = read(plugin_dir / "CHANGELOG.md")

    assert re.search(r"^## \[0\.1\.0\] - \d{4}-\d{2}-\d{2}$", changelog, re.M)
    assert "auditor, fixer" in changelog


def test_plugin_license_carries_the_author(plugin_dir):
    text = read(plugin_dir / "LICENSE")

    assert text.startswith("MIT License")
    assert re.search(r"^Copyright \(c\) \d{4} Ada Lovelace$", text, re.M)


def test_plugin_gitignore_excludes_env_files(plugin_dir):
    lines = read(plugin_dir / ".gitignore").splitlines()

    assert ".env" in lines
    assert "__pycache__/" in lines


def test_plugin_without_skill_flag_writes_no_skill(plugin_dir):
    assert not (plugin_dir / "skills").exists()


def test_plugin_skill_flag_writes_skill_md_that_launches_the_agents(tmp_path):
    dest = tmp_path / "my-plug"

    make_plugin(dest, "--agent", "auditor:review", "--skill")

    text = read(dest / "skills" / "my-plug" / "SKILL.md")
    assert field(text, "name") == "my-plug"
    assert "`my-plug:auditor`" in text


def test_plugin_author_defaults_to_the_git_user(tmp_path, monkeypatch):
    monkeypatch.setattr(scaffold, "git_user", lambda: "Git Person")
    dest = tmp_path / "my-plug"

    scaffold.main(["plugin", "my-plug", "--dest", str(dest)])

    manifest = json.loads(read(dest / ".claude-plugin" / "plugin.json"))
    assert manifest["author"] == {"name": "Git Person"}


@pytest.mark.parametrize("name", ["MyPlug", "my_plug", "my--plug", "my plug"])
def test_plugin_non_kebab_name_exits_and_writes_nothing(tmp_path, name):
    dest = tmp_path / "out"

    with pytest.raises(SystemExit) as exc:
        make_plugin(dest, name=name)

    assert "kebab-case" in str(exc.value.code)
    assert not dest.exists()


# register


def test_register_existing_kind_writes_agent_and_model(tmp_path):
    code = register(tmp_path, "my-plug:auditor", "--kind", "review", "--model", "opus")

    assert code == 0
    assert routes_of(tmp_path)["kinds"]["review"] == {"agent": "my-plug:auditor", "model": "opus"}


def test_register_keeps_other_keys_and_other_kinds(tmp_path):
    path = tmp_path / ".claude" / "foreman" / "routing.json"
    path.parent.mkdir(parents=True)
    seed = {"theme": "keep", "kinds": {"triage": {"agent": "me:triager", "what": "triage"}}}
    path.write_text(json.dumps(seed), encoding="utf-8")

    register(tmp_path, "my-plug:auditor", "--kind", "review", "--model", "opus")

    data = routes_of(tmp_path)
    assert data["theme"] == "keep"
    assert data["kinds"]["triage"] == seed["kinds"]["triage"]
    assert data["kinds"]["review"]["agent"] == "my-plug:auditor"


@pytest.mark.parametrize(
    "flags",
    [
        pytest.param([], id="nothing"),
        pytest.param(["--what", "triage bugs"], id="what-only"),
        pytest.param(["--read-only"], id="read-only-only"),
        pytest.param(["--writes"], id="writes-only"),
    ],
)
def test_register_new_kind_without_what_and_a_writes_flag_exits(tmp_path, flags):
    with pytest.raises(SystemExit) as exc:
        register(tmp_path, "me:triager", "--kind", "triage", *flags)

    assert "needs --what" in str(exc.value.code)
    assert not (tmp_path / ".claude").exists()


def test_register_new_read_only_kind_gets_sonnet_medium_and_the_read_profile(tmp_path):
    register(tmp_path, "me:triager", "--kind", "triage", "--what", "triage bugs", "--read-only")

    assert routes_of(tmp_path)["kinds"]["triage"] == {
        "agent": "me:triager",
        "what": "triage bugs",
        "writes": False,
        "model": "sonnet",
        "effort": "medium",
        "profile": "read",
    }


def test_register_new_writing_kind_gets_the_edit_profile(tmp_path):
    register(tmp_path, "me:fixer", "--kind", "patch", "--what", "patch bugs", "--writes")

    entry = routes_of(tmp_path)["kinds"]["patch"]
    assert (entry["writes"], entry["profile"]) == (True, "edit")


def test_register_same_kind_again_updates_the_entry_in_place(tmp_path):
    register(tmp_path, "me:triager", "--kind", "triage", "--what", "triage bugs", "--read-only")

    register(tmp_path, "me:triager-v2", "--kind", "triage", "--model", "opus")

    kinds = routes_of(tmp_path)["kinds"]
    assert list(kinds) == ["triage"]
    assert kinds["triage"]["agent"] == "me:triager-v2"
    assert kinds["triage"]["model"] == "opus"
    assert kinds["triage"]["what"] == "triage bugs"


def test_register_without_project_writes_under_the_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    scaffold.main(["register", "my-plug:auditor", "--kind", "review"])

    assert routes_of(tmp_path)["kinds"]["review"]["agent"] == "my-plug:auditor"


# frontmatter()


def test_frontmatter_returns_scalar_keys_and_the_body():
    meta, body = scaffold.frontmatter("---\nname: demo\nmodel: haiku\n---\nBody line.\n")

    assert meta == {"name": "demo", "model": "haiku"}
    assert body == "Body line."


@pytest.mark.parametrize("indicator", [">-", ">", "|", "|-"])
def test_frontmatter_joins_block_scalar_lines_with_spaces(indicator):
    text = f"---\ndescription: {indicator}\n  line one\n  line two\nmodel: haiku\n---\nbody\n"

    meta, _ = scaffold.frontmatter(text)

    assert meta == {"description": "line one line two", "model": "haiku"}


def test_frontmatter_joins_yaml_list_items_without_dashes():
    text = "---\ntools:\n  - Read\n  - Grep\n  - Glob\nmodel: haiku\n---\nbody\n"

    meta, _ = scaffold.frontmatter(text)

    assert meta == {"tools": "Read Grep Glob", "model": "haiku"}


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("Just prose.\n", id="no-frontmatter"),
        pytest.param("\n---\nname: demo\n---\nbody\n", id="leading-blank-line"),
        pytest.param("---\nname: demo\nnever closed\n", id="never-closed"),
    ],
)
def test_frontmatter_returns_none_without_a_leading_block(text):
    meta, body = scaffold.frontmatter(text)

    assert meta is None
    assert body == text


def test_plugin_with_unknown_agent_kind_writes_nothing(tmp_path):
    dest = tmp_path / "half"

    with pytest.raises(SystemExit, match="unknown kind"):
        make_plugin(dest, "--agent", "checker:bogus")

    assert not dest.exists()
