#!/usr/bin/env python3
"""foreman plan tool: list templates and routes, start a plan from a template, check a plan.

  plan.py templates [--project DIR]
  plan.py routes [--project DIR]
  plan.py new TEMPLATE --task "the user's words" [--project DIR]
  plan.py check PLAN.json|- [--project DIR] [--json]

check rules (E = error, exit 1; W = warning):
  FM001 E plan is not a JSON object with a non-empty subtasks list
  FM002 E subtask missing id, kind or goal, or a duplicate id
  FM003 E unknown kind
  FM004 E model is not an Agent tool alias, or effort is not a level
  FM005 E agent or model differs from the kind's route and the subtask has no "why"
  FM006 E "after" names no subtask, or the subtasks form a cycle
  FM007 E read-only subtask owns paths
  FM008 E writing subtask owns nothing
  FM009 E two subtasks in one wave own the same path (W when two globs only may overlap)
  FM010 E subtask has no verify
  FM011 W wave wider than max_wave
  FM012 W one subtask: do it inline
  FM013 W agent is neither a foreman agent nor named in a route
  FM014 W template hint (fan_out, skip_when) left in the plan

An "after" entry matches a subtask id, or every id that starts with it plus "-"
(after: ["build"] waits for build-api and build-ui).

Project extensions: <project>/.claude/foreman/routing.json ("kinds" merged over the
defaults, "max_wave") and <project>/.claude/foreman/templates/*.json (same name replaces).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from collections import Counter
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
PLUGIN = SKILL.parent.parent
GLOB = "*?["


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def ext_dir(project: Path) -> Path:
    return project / ".claude" / "foreman"


def load_routing(project: Path) -> dict:
    routing = load_json(SKILL / "routing.json")
    extra = ext_dir(project) / "routing.json"
    if extra.is_file():
        over = load_json(extra)
        for kind, route in over.get("kinds", {}).items():
            routing["kinds"][kind] = {**routing["kinds"].get(kind, {}), **route}
        routing["max_wave"] = over.get("max_wave", routing["max_wave"])
    return routing


def load_templates(project: Path) -> dict[str, tuple[dict, str]]:
    found: dict[str, tuple[dict, str]] = {}
    for folder, origin in (
        (SKILL / "templates", "built-in"),
        (ext_dir(project) / "templates", "project"),
    ):
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            template = load_json(path)
            found[template.get("name", path.stem)] = (template, origin)
    return found


def roster() -> set[str]:
    return {f"foreman:{p.stem}" for p in (PLUGIN / "agents").glob("*.md")}


def resolve_after(entry: str, ids: list[str]) -> list[str]:
    if entry in ids:
        return [entry]
    return [i for i in ids if i.startswith(entry + "-")]


def waves_of(items: list[dict]) -> tuple[list[list[str]], list[str]]:
    """Kahn layering on resolved "after" edges; returns (waves, problems)."""
    ids = [s["id"] for s in items]
    deps: dict[str, set[str]] = {}
    problems = []
    for s in items:
        deps[s["id"]] = set()
        for entry in s.get("after", []):
            hits = resolve_after(entry, ids)
            if not hits:
                problems.append(f"FM006 {s['id']}: after {entry!r} names no subtask")
            deps[s["id"]].update(h for h in hits if h != s["id"])
    waves, done = [], set()
    while len(done) < len(ids):
        ready = [i for i in ids if i not in done and deps[i] <= done]
        if not ready:
            stuck = sorted(set(ids) - done)
            problems.append(f"FM006 cycle among {', '.join(stuck)}")
            break
        waves.append(ready)
        done.update(ready)
    return waves, problems


def norm(path: str) -> str:
    path = path.replace("\\", "/").strip()
    while path.startswith("./"):
        path = path[2:]
    return path.rstrip("/") or "."


def prefix(path: str) -> str:
    cut = [path.index(c) for c in GLOB if c in path]
    return path[: min(cut)] if cut else path


def inside(path: str, folder: str) -> bool:
    return folder == "." or path == folder or path.startswith(folder + "/")


def overlap(a: str, b: str) -> str | None:
    """'same' when the two owns entries certainly share a path, 'maybe' for two loose globs."""
    a, b = norm(a), norm(b)
    ga, gb = any(c in a for c in GLOB), any(c in b for c in GLOB)
    if a == b:
        return "same"
    if not ga and not gb:
        return "same" if inside(a, b) or inside(b, a) else None
    if ga != gb:
        glob, lit = (a, b) if ga else (b, a)
        if fnmatch.fnmatchcase(lit, glob) or inside(prefix(glob).rstrip("/"), lit):
            return "same"
        return None
    pa, pb = prefix(a), prefix(b)
    for glob, other in ((a, pb), (b, pa)):
        # dir/** holds every path under dir, whatever the other glob's tail is
        if glob.endswith("/**") and inside(other.rstrip("/"), glob[:-3]):
            return "same"
    return "maybe" if pa.startswith(pb) or pb.startswith(pa) else None


def resolve(sub: dict, routing: dict) -> dict:
    route = routing["kinds"].get(sub.get("kind"), {})
    return {
        **sub,
        "agent": sub.get("agent") or route.get("agent", ""),
        "model": sub.get("model") or route.get("model", ""),
        "effort": sub.get("effort") or route.get("effort", ""),
        "writes": sub.get("writes", route.get("writes", False)),
        "owns": [norm(p) for p in sub.get("owns", [])],
    }


def check_plan(plan, routing: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if (
        not isinstance(plan, dict)
        or not isinstance(plan.get("subtasks"), list)
        or not plan["subtasks"]
    ):
        return {
            "errors": ["FM001 plan must be a JSON object with a non-empty subtasks list"],
            "warnings": [],
            "waves": [],
            "subtasks": [],
        }
    kinds = routing["kinds"]
    known_agents = roster() | {r.get("agent") for r in kinds.values()}
    seen: set[str] = set()
    items = []
    for n, raw in enumerate(plan["subtasks"], 1):
        if not isinstance(raw, dict):
            errors.append(f"FM002 subtask {n} is not an object")
            continue
        sid = raw.get("id") or f"#{n}"
        for key in ("id", "kind", "goal"):
            if not raw.get(key):
                errors.append(f"FM002 {sid}: missing {key}")
        if sid in seen:
            errors.append(f"FM002 {sid}: duplicate id")
        seen.add(sid)
        kind = raw.get("kind")
        if kind and kind not in kinds:
            errors.append(f"FM003 {sid}: unknown kind {kind!r} (known: {', '.join(sorted(kinds))})")
            continue
        sub = resolve({**raw, "id": sid}, routing)
        route = kinds.get(kind, {})
        if sub["model"] not in routing["models"]:
            errors.append(f"FM004 {sid}: model {sub['model']!r} is not one of {routing['models']}")
        if sub["effort"] and sub["effort"] not in routing["efforts"]:
            errors.append(
                f"FM004 {sid}: effort {sub['effort']!r} is not one of {routing['efforts']}"
            )
        moved = [k for k in ("agent", "model") if route and sub[k] != route.get(k)]
        if moved and not raw.get("why"):
            what = ", ".join(f"{k} {sub[k]} (route: {route.get(k)})" for k in moved)
            errors.append(f'FM005 {sid}: {what} needs a "why"')
        if not sub["writes"] and sub["owns"]:
            errors.append(f"FM007 {sid}: {kind} is read-only but owns {sub['owns']}")
        if sub["writes"] and not sub["owns"]:
            errors.append(f"FM008 {sid}: {kind} writes files but owns nothing")
        if not str(raw.get("verify", "")).strip():
            errors.append(f"FM010 {sid}: no verify")
        if sub["agent"] and sub["agent"] not in known_agents:
            warnings.append(
                f"FM013 {sid}: agent {sub['agent']!r} is not a foreman agent or route;"
                " confirm the session lists it"
            )
        hints = [k for k in ("fan_out", "skip_when") if k in raw]
        if hints:
            warnings.append(
                f"FM014 {sid}: template hint {', '.join(hints)} left in the plan;"
                " apply it and delete the key"
            )
        items.append(sub)
    waves, problems = waves_of(items)
    errors += problems
    by_id = {s["id"]: s for s in items}
    for w, wave in enumerate(waves, 1):
        if len(wave) > routing["max_wave"]:
            warnings.append(
                f"FM011 wave {w} has {len(wave)} subtasks (max_wave {routing['max_wave']});"
                " split it"
            )
        for i, a in enumerate(wave):
            for b in wave[i + 1 :]:
                for pa in by_id[a]["owns"]:
                    for pb in by_id[b]["owns"]:
                        hit = overlap(pa, pb)
                        msg = f"FM009 wave {w}: {a} owns {pa!r} and {b} owns {pb!r}"
                        if hit == "same":
                            errors.append(msg)
                        elif hit == "maybe":
                            warnings.append(msg + " (globs may overlap; list files to be sure)")
    if len(items) == 1:
        warnings.append("FM012 one subtask: do it inline instead of delegating")
    return {"errors": errors, "warnings": warnings, "waves": waves, "subtasks": items}


def validate_template(template: dict, kinds: dict) -> list[str]:
    """Problems with a template file; check.py runs this on every shipped template."""
    problems = [f"missing {k}" for k in ("name", "summary", "steps") if not template.get(k)]
    steps = template.get("steps") or []
    for step in steps:
        sid = step.get("id", "?")
        problems += [
            f"step {sid}: missing {k}" for k in ("id", "kind", "goal", "verify") if not step.get(k)
        ]
        if step.get("kind") and step["kind"] not in kinds:
            problems.append(f"step {sid}: unknown kind {step['kind']!r}")
    _, wave_problems = waves_of([s for s in steps if s.get("id")])
    return problems + wave_problems


def new_plan(template: dict, task: str, routing: dict) -> dict:
    subtasks = []
    for step in template["steps"]:
        route = routing["kinds"][step["kind"]]
        sub = {
            "id": step["id"],
            "kind": step["kind"],
            "agent": route["agent"],
            "model": route["model"],
            "goal": step["goal"],
            "owns": [],
            "reads": [],
            "after": step.get("after", []),
            "verify": step["verify"],
        }
        sub.update({k: step[k] for k in ("fan_out", "skip_when") if k in step})
        subtasks.append(sub)
    return {"task": task, "template": template["name"], "subtasks": subtasks}


def chain(template: dict) -> str:
    marks = []
    for step in template.get("steps", []):
        mark = "*" if "fan_out" in step else "?" if "skip_when" in step else ""
        marks.append(step["id"] + mark)
    return " > ".join(marks)


def cell(value) -> str:
    if isinstance(value, list):
        value = ", ".join(value)
    return str(value or "-").replace("|", "/")


def table(rows: list[list], head: list[str]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def cmd_templates(project: Path) -> int:
    rows = [
        [name, origin, chain(t), t.get("summary")]
        for name, (t, origin) in load_templates(project).items()
    ]
    print(table(rows, ["template", "origin", "steps (* fans out, ? skippable)", "summary"]))
    return 0


def cmd_routes(project: Path) -> int:
    kinds = load_routing(project)["kinds"]
    rows = [
        [
            k,
            r.get("agent"),
            r.get("model"),
            r.get("effort"),
            "yes" if r.get("writes") else "no",
            r.get("what"),
        ]
        for k, r in kinds.items()
    ]
    print(table(rows, ["kind", "agent", "model", "effort", "writes", "what"]))
    return 0


def cmd_new(project: Path, name: str, task: str) -> int:
    templates = load_templates(project)
    if name not in templates:
        print(f"unknown template {name!r}; known: {', '.join(templates)}", file=sys.stderr)
        return 2
    print(json.dumps(new_plan(templates[name][0], task, load_routing(project)), indent=2))
    return 0


def cmd_check(project: Path, source: str, as_json: bool) -> int:
    try:
        text = (
            sys.stdin.buffer.read().decode("utf-8")
            if source == "-"
            else Path(source).read_text(encoding="utf-8")
        )
        plan = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FM001 cannot read plan: {exc}")
        return 1
    report = check_plan(plan, load_routing(project))
    if as_json:
        print(json.dumps(report, indent=2))
        return 1 if report["errors"] else 0
    subs = {s["id"]: s for s in report["subtasks"]}
    rows = [
        [
            w,
            sid,
            subs[sid]["kind"],
            subs[sid]["agent"],
            subs[sid]["model"],
            subs[sid]["owns"],
            subs[sid].get("after"),
            subs[sid].get("verify"),
        ]
        for w, wave in enumerate(report["waves"], 1)
        for sid in wave
    ]
    mix = Counter(s["model"] for s in report["subtasks"])
    models = ", ".join(f"{m} {mix[m]}" for m in ("haiku", "sonnet", "opus", "fable") if mix[m])
    print(
        f"plan: {plan.get('template', 'custom')} | {len(subs)} subtasks"
        f" | {len(report['waves'])} waves | models: {models or '-'}"
    )
    if rows:
        print(
            table(
                rows,
                ["wave", "id", "kind", "agent", "model", "owns", "after", "verify"],
            )
        )
    for label, found in (
        ("errors", report["errors"]),
        ("warnings", report["warnings"]),
    ):
        if found:
            print(f"{label}:")
            print("\n".join(f"  {line}" for line in found))
    n_err = len(report["errors"])
    print(f"result: {'ok' if not n_err else f'{n_err} error' + 's' * (n_err > 1)}")
    return 1 if n_err else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="foreman plan tool",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--project", help="project root for .claude/foreman extensions (default: cwd)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("templates", help="list task templates")
    sub.add_parser("routes", help="list kinds with their agent, model and effort")
    p_new = sub.add_parser("new", help="print a plan skeleton from a template")
    p_new.add_argument("template")
    p_new.add_argument("--task", required=True, help="the user's request, verbatim")
    p_check = sub.add_parser("check", help="validate a plan and print its waves")
    p_check.add_argument("plan", help="plan JSON file, or - for stdin")
    p_check.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    project = Path(args.project).resolve() if args.project else Path.cwd()
    if args.cmd == "templates":
        return cmd_templates(project)
    if args.cmd == "routes":
        return cmd_routes(project)
    if args.cmd == "new":
        return cmd_new(project, args.template, args.task)
    return cmd_check(project, args.plan, args.json)


if __name__ == "__main__":
    sys.exit(main())
