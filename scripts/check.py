#!/usr/bin/env python3
"""Deterministic repo gate, no LLM: run before every commit and in CI.

FC001 en or em dash             FC006 JSON file does not parse
FC002 secret-shaped string      FC007 plugin.json and marketplace.json versions differ
FC003 skill frontmatter         FC008 agent file fails scaffold.py lint, or keeps a <<fill marker
FC004 absolute home path        FC009 agent name, model or effort disagrees with routing.json
FC005 broken relative link      FC010 task template fails plan.py validation
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "dispatch" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "new-agent" / "scripts"))
import plan  # noqa: E402
import scaffold  # noqa: E402

DASHES = (chr(0x2013), chr(0x2014))
TEXT = {".md", ".py", ".json", ".yml", ".yaml", ".toml", ".txt", ".tmpl"}
TEXT_NAMES = {"LICENSE", "CODEOWNERS", ".gitignore", ".gitattributes", ".editorconfig"}
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".scratch",
    ".archify",
    "results",  # claude plugin eval output
}
SECRETS = [
    ("aws access key", re.compile(r"\bA(?:KIA|SIA)[0-9A-Z]{16}\b")),
    (
        "github token",
        re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|\bgithub_pat_\w{40,}"),
    ),
    ("api key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{24,}")),
]
HOME_PATH = re.compile(
    r"\b[A-Za-z]:[\\/]Users[\\/](?!\.\.\.)[\w.-]+|/c/Users/(?!\.\.\.)[\w.-]+"
    r"|/home/(?!runner\b)[a-z][\w.-]*/|/Users/(?!Shared\b)[A-Z][\w.-]+/"
)
MD_LINK = re.compile(r"\]\((?!https?:|mailto:|#)([^)\s]+)\)")
INLINE_CODE = re.compile(r"`[^`]*`")


def files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT).parts
        if p.is_file() and not SKIP_DIRS.intersection(rel):
            if p.suffix in TEXT or p.name in TEXT_NAMES:
                out.append(p)
    return sorted(out)


def check_skill(p: Path, rel: str, text: str) -> list[str]:
    meta, _ = scaffold.frontmatter(text)
    meta = meta or {}
    head = text.split("\n---", 1)[0]
    problems = []
    if meta.get("name") != p.parent.name:
        problems.append(
            f"{rel}:1 FC003 name {meta.get('name')!r} must equal folder {p.parent.name!r}"
        )
    desc = meta.get("description", "")
    if not desc:
        return problems + [f"{rel}:1 FC003 missing description"]
    if not re.search(r"^description:\s*>-?\s*$", head, re.M):
        problems.append(f"{rel}:1 FC003 description must be a folded block scalar (>-)")
    if len(desc) > 1024:
        problems.append(f"{rel}:1 FC003 description is {len(desc)} chars (max 1024)")
    if "Use when" not in desc:
        problems.append(f'{rel}:1 FC003 description needs "Use when ..." trigger phrases')
    return problems


def check_links(p: Path, rel: str, n: int, line: str) -> list[str]:
    problems = []
    for target in MD_LINK.findall(line):
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        resolved = (p.parent / clean).resolve()
        if resolved.is_relative_to(ROOT) and not resolved.exists():
            problems.append(f"{rel}:{n} FC005 broken link {target}")
    return problems


def check_manifests() -> list[str]:
    try:
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        market = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return []  # FC006 already reports the parse error
    entries = [e for e in market.get("plugins", []) if e.get("name") == manifest.get("name")]
    if not entries:
        return [f".claude-plugin/marketplace.json:1 FC007 no entry for {manifest.get('name')!r}"]
    versions = {manifest.get("version")} | {e.get("version") for e in entries}
    if len(versions) != 1:
        return [
            f".claude-plugin/marketplace.json:1 FC007 versions differ: {sorted(map(str, versions))}"
        ]
    return []


def check_agents() -> list[str]:
    problems = []
    kinds = json.loads((ROOT / "skills" / "dispatch" / "routing.json").read_text(encoding="utf-8"))[
        "kinds"
    ]
    routed = {r["agent"].removeprefix("foreman:"): (kind, r) for kind, r in kinds.items()}
    agents = sorted((ROOT / "agents").glob("*.md"))
    for path in agents:
        rel = path.relative_to(ROOT).as_posix()
        errors, warnings = scaffold.lint_file(path)
        kept = errors + [w for w in warnings if w.startswith(("FA004", "FA005", "FA009"))]
        problems += [f"{rel}:1 FC008 {line.replace(path.as_posix() + ': ', '')}" for line in kept]
        meta, _ = scaffold.frontmatter(path.read_text(encoding="utf-8"))
        meta = meta or {}
        if meta.get("name") != path.stem:
            problems.append(
                f"{rel}:1 FC009 name {meta.get('name')!r} must equal the file name {path.stem!r}"
            )
        if path.stem not in routed:
            problems.append(f"{rel}:1 FC009 no kind in routing.json routes to foreman:{path.stem}")
            continue
        kind, route = routed[path.stem]
        for key in ("model", "effort"):
            if meta.get(key) != route[key]:
                problems.append(
                    f"{rel}:1 FC009 {key} {meta.get(key)!r} but routing.json kind"
                    f" {kind!r} says {route[key]!r}"
                )
        if meta.get("tools") != scaffold.load_routing()["profiles"][route["profile"]]:
            problems.append(f"{rel}:1 FC009 tools differ from the {route['profile']!r} profile")
    names = {p.stem for p in agents}
    for kind, route in kinds.items():
        if route["agent"].removeprefix("foreman:") not in names:
            problems.append(
                f"skills/dispatch/routing.json:1 FC009 kind {kind!r}"
                f" routes to missing {route['agent']}"
            )
    return problems


def check_templates() -> list[str]:
    kinds = json.loads((ROOT / "skills" / "dispatch" / "routing.json").read_text(encoding="utf-8"))[
        "kinds"
    ]
    problems = []
    for path in sorted((ROOT / "skills" / "dispatch" / "templates").glob("*.json")):
        rel = path.relative_to(ROOT).as_posix()
        try:
            template = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # FC006 already reports it
        if template.get("name") != path.stem:
            problems.append(f"{rel}:1 FC010 name {template.get('name')!r} must equal the file name")
        problems += [f"{rel}:1 FC010 {line}" for line in plan.validate_template(template, kinds)]
    return problems


def main() -> int:
    problems: list[str] = []
    me = Path(__file__).resolve()
    checked = files()
    for p in checked:
        rel = p.relative_to(ROOT).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        fenced = False
        for n, line in enumerate(text.splitlines(), 1):
            if p.suffix == ".md" and line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
            elif p.suffix == ".md" and not fenced:
                problems += check_links(p, rel, n, INLINE_CODE.sub("", line))
            if any(d in line for d in DASHES):
                problems.append(f"{rel}:{n} FC001 en or em dash; use - or --")
            for label, rx in SECRETS:
                if rx.search(line):
                    problems.append(f"{rel}:{n} FC002 looks like a {label}")
            home = HOME_PATH.search(line) if p != me else None
            if home:
                problems.append(f"{rel}:{n} FC004 absolute home path {home.group(0)!r}")
        if p.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                problems.append(f"{rel}:{exc.lineno} FC006 invalid JSON: {exc.msg}")
        if p.name == "SKILL.md":
            problems += check_skill(p, rel, text)
    problems += check_manifests()
    problems += check_agents()
    problems += check_templates()
    for line in problems:
        print(line)
    print(f"{len(checked)} files checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
