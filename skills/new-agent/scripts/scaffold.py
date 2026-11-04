#!/usr/bin/env python3
"""foreman scaffold: write agents and agent plugins, route a kind to an agent, lint agent files.

  scaffold.py agent NAME --kind KIND --dest DIR [--description TEXT] [--model M] [--effort E]
  scaffold.py plugin NAME --dest DIR [--agent NAME:KIND ...] [--skill] [--description TEXT]
  scaffold.py register AGENT --kind KIND [--project DIR] [--model M] [--effort E]
                       [--writes | --read-only] [--what TEXT]
  scaffold.py lint PATH [PATH ...]

The kind (scaffold.py agent --kind, see `plan.py routes`) sets the default model, effort and
tools. Existing files are never overwritten without --force.

lint rules (E = error, exit 1; W = warning):
  FA001 E no frontmatter, or the opening --- is not the first line (the file is skipped)
  FA002 E name missing, contains ':', starts with '-' or is over 256 chars; W not kebab-case
  FA003 E description missing, or a plain value with ': ' in it; W over 1000 chars
  FA004 W unknown field (Claude Code ignores it silently), with the likely intended name
  FA005 W field ignored in plugin agents (hooks, mcpServers, permissionMode, initialPrompt)
  FA006 E model is not an alias, inherit, or a model id
  FA007 E effort, color, isolation, memory or background has an invalid value
  FA008 W model set but no effort (a subagent on another model does not inherit the session's)
  FA009 W <<fill placeholder left in the file
  FA010 W empty body (the body is the agent's system prompt)
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from string import Template

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"
ROUTING = SKILL.parent / "dispatch" / "routing.json"

FIELDS = {
    "name",
    "description",
    "tools",
    "disallowedTools",
    "model",
    "permissionMode",
    "maxTurns",
    "autoCompactWindow",
    "skills",
    "mcpServers",
    "hooks",
    "memory",
    "background",
    "omitClaudeMd",
    "effort",
    "isolation",
    "color",
    "initialPrompt",
    "experimental",
}
PLUGIN_IGNORED = {"hooks", "mcpServers", "permissionMode", "initialPrompt"}
LIKELY = {
    "allowed-tools": "tools",
    "allowedTools": "tools",
    "allowed_tools": "tools",
    "disallowed-tools": "disallowedTools",
    "disallowed_tools": "disallowedTools",
    "max-turns": "maxTurns",
    "max_turns": "maxTurns",
    "permission-mode": "permissionMode",
    "mcp-servers": "mcpServers",
    "mcp_servers": "mcpServers",
    "auto-compact-window": "autoCompactWindow",
    "omit-claude-md": "omitClaudeMd",
    "initial-prompt": "initialPrompt",
    "when_to_use": "description",
    "version": "(drop it: agents have no version)",
    "argument-hint": "(skills only)",
}
ALIASES = {"haiku", "sonnet", "opus", "fable", "inherit"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
COLORS = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
MEMORY = {"user", "project", "local"}
BOOLS = {"true", "false", "yes", "no", "on", "off", "1", "0"}
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PALETTE = ["green", "blue", "orange", "purple", "cyan", "yellow", "pink", "red"]


def load_routing() -> dict:
    return json.loads(ROUTING.read_text(encoding="utf-8"))


def frontmatter(text: str) -> tuple[dict[str, str] | None, str]:
    """Top-level keys of a small YAML subset (scalars, folded blocks, lists): (meta, body)."""
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, text
    meta: dict[str, str] = {}
    key = None
    for raw in lines[1:end]:
        if key and raw[:1] in (" ", "\t"):
            item = raw.strip()
            meta[key] = f"{meta[key]} {item.removeprefix('- ')}".strip()
            continue
        key = None
        name, sep, value = raw.partition(":")
        if not sep or raw[:1] in (" ", "\t", "#"):
            continue
        name, value = name.strip(), value.strip()
        meta[name] = "" if value in (">", ">-", "|", "|-") else value
        if value in (">", ">-", "|", "|-", ""):
            key = name
    return meta, "\n".join(lines[end + 1 :])


def in_plugin(path: Path) -> bool:
    return any((p / ".claude-plugin" / "plugin.json").is_file() for p in path.resolve().parents[:4])


def lint_file(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    shown = path.as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = frontmatter(text)
    if meta is None:
        return [f"FA001 {shown}: no frontmatter, or the opening --- is not the first line"], []
    name = meta.get("name", "").strip("\"'")
    if not name:
        errors.append(
            f"FA002 {shown}: no name (plugin agents load under the file name, others are skipped)"
        )
    elif ":" in name or name.startswith("-") or len(name) > 256:
        errors.append(
            f"FA002 {shown}: name {name!r} may not contain ':', start with '-' or pass 256 chars"
        )
    elif not KEBAB.match(name):
        warnings.append(f"FA002 {shown}: name {name!r} is not kebab-case")
    desc = meta.get("description", "")
    head = text.split("\n---", 1)[0]
    if not desc:
        errors.append(f"FA003 {shown}: no description (the agent is skipped)")
    else:
        plain = re.search(r"^description:[ \t]*([^>|\s\"'].*)$", head, re.M)
        if plain and ": " in plain.group(1):
            errors.append(
                f"FA003 {shown}: plain description contains ': '; use a >- block or quote it"
            )
        if len(desc) > 1000:
            warnings.append(
                f"FA003 {shown}: description is {len(desc)} chars; every agent description"
                " loads in every session, keep it under 1000"
            )
    for key in meta:
        if key not in FIELDS:
            hint = f" (did you mean {LIKELY[key]}?)" if key in LIKELY else ""
            warnings.append(f"FA004 {shown}: unknown field {key!r} is ignored{hint}")
    if in_plugin(path):
        for key in sorted(PLUGIN_IGNORED & meta.keys()):
            warnings.append(
                f"FA005 {shown}: {key!r} is ignored in plugin agents; ship hooks in"
                " hooks/hooks.json and MCP servers in .mcp.json"
            )
    model = meta.get("model", "").strip("\"'")
    if model and model not in ALIASES and "claude" not in model and "anthropic" not in model:
        errors.append(
            f"FA006 {shown}: model {model!r} is not an alias ({', '.join(sorted(ALIASES))})"
            " or a model id"
        )
    checks = [
        ("effort", EFFORTS),
        ("color", COLORS),
        ("isolation", {"worktree"}),
        ("memory", MEMORY),
        ("background", BOOLS),
    ]
    for key, allowed in checks:
        value = meta.get(key, "").strip("\"'").lower()
        if value and value not in allowed:
            errors.append(
                f"FA007 {shown}: {key} {value!r} is not one of {', '.join(sorted(allowed))}"
            )
    if model and model != "inherit" and not meta.get("effort"):
        warnings.append(
            f"FA008 {shown}: model {model} set without effort; a subagent on another model"
            " does not inherit the session's effort"
        )
    if "<<fill" in text:
        warnings.append(f"FA009 {shown}: <<fill placeholder left")
    if not body.strip():
        warnings.append(f"FA010 {shown}: empty body; the body is the agent's system prompt")
    return errors, warnings


def fold(text: str) -> str:
    return "\n".join(
        textwrap.wrap(" ".join(text.split()), 76, initial_indent="  ", subsequent_indent="  ")
    )


def write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} exists; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    print(f"wrote {path.as_posix()}")


def render(asset: str, **values: str) -> str:
    return Template((ASSETS / asset).read_text(encoding="utf-8")).substitute(values)


def agent_text(
    name: str,
    kind: str,
    description: str,
    model: str | None,
    effort: str | None,
    color: str,
) -> str:
    routing = load_routing()
    route = routing["kinds"].get(kind)
    if route is None:
        raise SystemExit(f"unknown kind {kind!r}; known: {', '.join(routing['kinds'])}")
    writes = route["writes"]
    return render(
        "agent.md.tmpl",
        name=name,
        title=name.replace("-", " "),
        description=fold(
            description
            or f"<<fill: what {name} does, who calls it, and what it never"
            " does>>. Use when <<fill: the requests that should route here>>."
        ),
        model=model or route["model"],
        effort=effort or route["effort"],
        tools=routing["profiles"][route["profile"]],
        color=color,
        owns_line="the only paths you may change" if writes else "always none: you are read-only",
        must_not="Edit a path outside `owns`; commit or push."
        if writes
        else "Edit, create or delete files; commit or push.",
    )


def git_user() -> str:
    try:
        out = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True, check=False
        )
    except OSError:
        return "Your Name"
    return out.stdout.strip() or "Your Name"


def cmd_agent(args: argparse.Namespace) -> int:
    path = Path(args.dest) / f"{args.name}.md"
    write(
        path,
        agent_text(args.name, args.kind, args.description, args.model, args.effort, args.color),
        args.force,
    )
    return report_lint([path])


def cmd_plugin(args: argparse.Namespace) -> int:
    if not KEBAB.match(args.name):
        raise SystemExit(f"plugin name {args.name!r} must be kebab-case")
    root = Path(args.dest)
    author = args.author or git_user()
    description = args.description or f"<<fill: what the {args.name} plugin does>>"
    agents = []
    for spec in args.agent or []:
        agent, _, kind = spec.partition(":")
        agents.append((agent, kind or "implement"))
    routing = load_routing()
    manifest = {
        "name": args.name,
        "version": "0.1.0",
        "description": description,
        "author": {"name": author},
        "license": "MIT",
        "keywords": ["agents"],
    }
    market = {
        "name": args.name,
        "owner": {"name": author},
        "metadata": {"description": description},
        "plugins": [
            {
                "name": args.name,
                "source": "./",
                "description": description,
                "version": "0.1.0",
                "license": "MIT",
            }
        ],
    }
    write(
        root / ".claude-plugin" / "plugin.json",
        json.dumps(manifest, indent=2) + "\n",
        args.force,
    )
    write(
        root / ".claude-plugin" / "marketplace.json",
        json.dumps(market, indent=2) + "\n",
        args.force,
    )
    written = []
    rows, skill_rows = [], []
    for n, (agent, kind) in enumerate(agents):
        path = root / "agents" / f"{agent}.md"
        write(
            path,
            agent_text(agent, kind, "", None, None, PALETTE[n % len(PALETTE)]),
            args.force,
        )
        written.append(path)
        route = routing["kinds"][kind]
        rows.append(f"| {agent} | {route['model']} | {route['effort']} | <<fill: one line>> |")
        skill_rows.append(
            f"| {n + 1} | `{args.name}:{agent}` | {route['model']} | <<fill: goal, owns, verify>> |"
        )
    agent_rows = "\n".join(rows) or "| <<fill>> | | | |"
    write(
        root / "README.md",
        render(
            "plugin/README.md.tmpl",
            name=args.name,
            description=description,
            agent_rows=agent_rows,
        ),
        args.force,
    )
    today = datetime.date.today()
    write(
        root / "CHANGELOG.md",
        render(
            "plugin/CHANGELOG.md.tmpl",
            date=today.isoformat(),
            agent_list=", ".join(a for a, _ in agents) or "<<fill>>",
        ),
        args.force,
    )
    write(
        root / "LICENSE",
        render("plugin/LICENSE.tmpl", year=str(today.year), author=author),
        args.force,
    )
    write(root / ".gitignore", ".env\n.env.*\n__pycache__/\n.DS_Store\n", args.force)
    if args.skill:
        skill_desc = fold(
            f"<<fill: what the {args.name} skill does with its agents>>. Use when"
            " <<fill: the requests that should load it>>."
        )
        write(
            root / "skills" / args.name / "SKILL.md",
            render(
                "plugin/skill.md.tmpl",
                name=args.name,
                description=skill_desc,
                agent_rows="\n".join(skill_rows) or "| 1 | <<fill>> | | |",
            ),
            args.force,
        )
    print(f"next: fill every <<fill marker, then run: claude plugin validate {root.as_posix()}")
    return report_lint(written) if written else 0


def cmd_register(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if args.project else Path.cwd()
    path = project / ".claude" / "foreman" / "routing.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"kinds": {}}
    builtin = load_routing()["kinds"]
    entry = {**data.setdefault("kinds", {}).get(args.kind, {}), "agent": args.agent}
    for key in ("model", "effort", "what"):
        if getattr(args, key):
            entry[key] = getattr(args, key)
    if args.writes is not None:
        entry["writes"] = args.writes
    if args.kind not in builtin:
        if "what" not in entry or "writes" not in entry:
            raise SystemExit(
                f"new kind {args.kind!r} needs --what and one of --writes, --read-only"
            )
        entry.setdefault("model", "sonnet")
        entry.setdefault("effort", "medium")
        entry.setdefault("profile", "edit" if entry["writes"] else "read")
    data["kinds"][args.kind] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {path.as_posix()}: {args.kind} -> {json.dumps(entry)}")
    return 0


def report_lint(paths: list[Path]) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    for path in paths:
        e, w = lint_file(path)
        errors += e
        warnings += w
    for line in errors + warnings:
        print(line)
    print(f"{len(paths)} agent files linted, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


def cmd_lint(args: argparse.Namespace) -> int:
    paths: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        paths += sorted(p.rglob("*.md")) if p.is_dir() else [p]
    return report_lint(paths)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="foreman scaffold",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_agent = sub.add_parser("agent", help="write one agent file")
    p_agent.add_argument("name")
    p_agent.add_argument("--kind", required=True, help="a kind from plan.py routes")
    p_agent.add_argument(
        "--dest",
        required=True,
        help=".claude/agents, ~/.claude/agents or <plugin>/agents",
    )
    p_agent.add_argument("--description", default="")
    p_agent.add_argument("--model")
    p_agent.add_argument("--effort")
    p_agent.add_argument("--color", default="green", choices=sorted(COLORS))
    p_agent.add_argument("--force", action="store_true")
    p_plugin = sub.add_parser("plugin", help="write an agent plugin skeleton")
    p_plugin.add_argument("name")
    p_plugin.add_argument("--dest", required=True)
    p_plugin.add_argument("--agent", action="append", help="NAME:KIND, repeatable")
    p_plugin.add_argument(
        "--skill", action="store_true", help="add a skill that launches the agents"
    )
    p_plugin.add_argument("--description", default="")
    p_plugin.add_argument("--author")
    p_plugin.add_argument("--force", action="store_true")
    p_reg = sub.add_parser("register", help="route a kind to an agent in this project")
    p_reg.add_argument("agent", help="agent name as the session lists it, e.g. my-plugin:auditor")
    p_reg.add_argument("--kind", required=True)
    p_reg.add_argument("--project")
    p_reg.add_argument("--model")
    p_reg.add_argument("--effort")
    p_reg.add_argument("--what")
    mode = p_reg.add_mutually_exclusive_group()
    mode.add_argument("--writes", dest="writes", action="store_true", default=None)
    mode.add_argument("--read-only", dest="writes", action="store_false")
    p_lint = sub.add_parser("lint", help="lint agent files or folders of them")
    p_lint.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    return {
        "agent": cmd_agent,
        "plugin": cmd_plugin,
        "register": cmd_register,
        "lint": cmd_lint,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
