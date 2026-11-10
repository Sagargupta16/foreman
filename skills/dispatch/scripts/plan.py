#!/usr/bin/env python3
"""foreman plan tool: templates and routes, start and check a plan, log runs, compile Workflows.

  plan.py templates [--project DIR]
  plan.py routes [--project DIR]
  plan.py new TEMPLATE --task "the user's words" [--project DIR]
  plan.py check PLAN.json|- [--project DIR] [--json]
  plan.py log PLAN.json|- [--log FILE]          plan with results -> one line per subtask
  plan.py stats [--log FILE] [--all]            success per kind x model, with tune hints
  plan.py workflow PLAN.json|- [--out FILE]     checked plan -> Workflow script

The run log defaults to $FOREMAN_LOG, else ~/.claude/foreman/runs.jsonl. For `log`, each
subtask carries its outcome: status (done, partial, blocked, failed, skipped, inline),
attempts (default 1), final_model (default: model), final_effort (default: effort), verified
(true when the foreman checked it), and optional tokens and duration_ms.

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
  FM012 W one subtask below the top tier: do it inline
  FM013 W agent is neither a foreman agent nor named in a route
  FM014 W template hint (fan_out, skip_when) left in the plan
  FM015 W more than max_top subtasks on the top tier of the ladder

An "after" entry matches a subtask id, or every id that starts with it plus "-"
(after: ["build"] waits for build-api and build-ui). "owns", "reads" and "after" take a
list; a lone string counts as one entry.

Project extensions: <project>/.claude/foreman/routing.json ("kinds" merged over the
defaults, "ladder", "max_wave", "max_top") and <project>/.claude/foreman/templates/*.json
(same name replaces).
"""

from __future__ import annotations

import argparse
import datetime
import fnmatch
import json
import os
import re
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
PLUGIN = SKILL.parent.parent
GLOB = "*?["
STATUSES = ("done", "partial", "blocked", "failed", "skipped", "inline")
MIN_SAMPLES = 5  # stats gives no tune hint for a kind x model with fewer logged subtasks
PLACEHOLDER = re.compile(r"__(?:META|TASK|SUBTASKS|WAVES|LADDER)__")


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
        routing["ladder"] = over.get("ladder") or routing["ladder"]  # an empty ladder is no ladder
        for key in ("max_wave", "max_top"):
            routing[key] = over.get(key, routing[key])
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


def as_list(value) -> list[str]:
    """A plan field that takes a list: a lone string is one entry, not its characters."""
    if value is None:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


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
        for entry in as_list(s.get("after")):
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
        "owns": [norm(p) for p in as_list(sub.get("owns"))],
        "reads": as_list(sub.get("reads")),
        "after": as_list(sub.get("after")),
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
        sid = str(raw.get("id") or f"#{n}")
        for key in ("id", "kind", "goal"):
            if not raw.get(key):
                errors.append(f"FM002 {sid}: missing {key}")
        if sid in seen:
            errors.append(f"FM002 {sid}: duplicate id")
        seen.add(sid)
        kind = raw.get("kind")
        if kind and (not isinstance(kind, str) or kind not in kinds):
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
    top = routing["ladder"][-1]
    on_top = [s["id"] for s in items if s["model"] == top]
    # one unit sent up to the top tier is the point of delegating it; anything else stays inline
    if len(items) == 1 and not on_top:
        warnings.append("FM012 one subtask: do it inline instead of delegating")
    if len(on_top) > routing["max_top"]:
        warnings.append(
            f"FM015 {len(on_top)} on {top}, max_top is {routing['max_top']}:"
            f" {', '.join(on_top)}; keep {top} for work that beat the tier below or cannot"
            " be split, and move the rest down"
        )
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
    return "-" if value in (None, "") else str(value).replace("|", "/")


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


def read_plan(source: str):
    if source == "-":
        return json.loads(sys.stdin.buffer.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def log_file(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("FOREMAN_LOG")
    return Path(env) if env else Path.home() / ".claude" / "foreman" / "runs.jsonl"


def log_lines(plan: dict, routing: dict, project: Path, stamp: str, run: str) -> list[dict]:
    """One record per subtask; raises ValueError when a subtask has no valid status."""
    lines = []
    for raw in plan.get("subtasks", []):
        status = raw.get("status")
        if status not in STATUSES:
            raise ValueError(f"{raw.get('id')}: status {status!r} is not one of {STATUSES}")
        sub = resolve(raw, routing)
        route = routing["kinds"].get(sub.get("kind"), {})
        line = {
            "ts": stamp,
            "run": run,
            "project": project.as_posix(),
            "template": plan.get("template", "custom"),
            "id": sub["id"],
            "kind": sub.get("kind"),
            "agent": sub["agent"],
            "model": sub["model"],
            "route_model": route.get("model"),
            "final_model": raw.get("final_model") or sub["model"],
            "effort": sub["effort"],
            "final_effort": raw.get("final_effort") or sub["effort"],
            "status": status,
            "attempts": int(raw.get("attempts", 1)),
            "verified": bool(raw.get("verified", False)),
        }
        line.update({k: raw[k] for k in ("tokens", "duration_ms") if isinstance(raw.get(k), int)})
        if plan.get("coordinator"):
            line["coordinator"] = plan["coordinator"]
        lines.append(line)
    return lines


def cmd_log(project: Path, source: str, log_arg: str | None) -> int:
    try:
        plan = read_plan(source)
        stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        run = f"{stamp[:10]}-{uuid.uuid4().hex[:8]}"
        lines = log_lines(plan, load_routing(project), project, stamp, run)
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError) as exc:
        print(f"cannot log plan: {exc}")
        return 1
    path = log_file(log_arg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.writelines(json.dumps(line) + "\n" for line in lines)
    print(f"logged run {run}: {len(lines)} subtasks -> {path.as_posix()}")
    return 0


def load_log(path: Path, project: Path | None) -> tuple[list[dict], int]:
    """Records from the log (only this project's unless project is None) and a bad-line count."""
    records, bad = [], 0
    if not path.is_file():
        return records, bad
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            bad += 1
            continue
        if project is None or rec.get("project") == project.as_posix():
            records.append(rec)
    return records, bad


def effort_only(rec: dict) -> bool:
    """True when the rerun stayed on the model and only raised the effort level."""
    same_model = rec["final_model"] == rec["model"]
    return same_model and rec.get("final_effort", rec.get("effort")) != rec.get("effort")


def tune_hints(groups: dict, routing: dict) -> list[str]:
    """Suggest a route change only from MIN_SAMPLES or more logged subtasks; never apply one."""
    ladder = routing["ladder"]
    hints = []
    for kind, route in routing["kinds"].items():
        model = route.get("model")
        if model not in ladder:
            continue
        tier = ladder.index(model)
        # a skipped subtask never ran, so it says nothing about the model
        here = [r for r in groups.get((kind, model), []) if r["status"] != "skipped"]
        if len(here) >= MIN_SAMPLES:
            # a rerun that only raised effort argues for more effort, not for a larger model
            pushed = sum(effort_only(r) for r in here)
            if pushed / len(here) > 0.3:
                hints.append(
                    f"raise {kind} effort above {route.get('effort')}: on {model} {pushed} of"
                    f" {len(here)} needed a rerun at higher effort"
                )
        if len(here) >= MIN_SAMPLES and tier + 1 < len(ladder):
            done = sum(r["status"] == "done" for r in here)
            moved = sum(
                (r["final_model"] != r["model"] or r["attempts"] > 1) and not effort_only(r)
                for r in here
            )
            if done / len(here) < 0.7 or moved / len(here) > 0.3:
                hints.append(
                    f"raise {kind} to {ladder[tier + 1]}: on {model} {done} of {len(here)} done,"
                    f" {moved} escalated"
                )
                continue
        if tier > 0:
            lower = ladder[tier - 1]
            below = [r for r in groups.get((kind, lower), []) if r["status"] != "skipped"]
            # only first-try successes on the lower tier argue for it, not ones that escalated
            good = sum(
                r["status"] == "done"
                and r["verified"]
                and r["attempts"] == 1
                and r["final_model"] == r["model"]
                for r in below
            )
            if len(below) >= MIN_SAMPLES and good / len(below) >= 0.9:
                hints.append(
                    f"lower {kind} to {lower}: {good} of {len(below)} done and verified on {lower}"
                )
    return hints


def cmd_stats(project: Path, log_arg: str | None, all_projects: bool) -> int:
    path = log_file(log_arg)
    records, bad = load_log(path, None if all_projects else project)
    scope = "all projects" if all_projects else project.as_posix()
    if not records:
        print(f"no logged subtasks for {scope} in {path.as_posix()}")
        return 0
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for rec in records:
        groups[(rec.get("kind"), rec.get("model"))].append(rec)
    rows = []
    for (kind, model), recs in sorted(
        groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))
    ):
        done = sum(r["status"] == "done" for r in recs)
        moved = sum(r["final_model"] != r["model"] or r["attempts"] > 1 for r in recs)
        verified = sum(bool(r["verified"]) for r in recs)
        tokens = [r["tokens"] for r in recs if isinstance(r.get("tokens"), int)]
        median = f"{statistics.median(tokens) / 1000:.1f}k" if tokens else "-"
        pct = round(100 * done / len(recs))
        rows.append([kind, model, len(recs), f"{done} ({pct}%)", moved, verified, median])
    runs = len({r["run"] for r in records})
    note = f", {bad} unreadable lines skipped" if bad else ""
    print(f"runs: {runs} | subtasks: {len(records)} | {scope} | log: {path.as_posix()}{note}")
    head = ["kind", "model", "subtasks", "done", "escalated", "verified", "median tokens"]
    print(table(rows, head))
    hints = tune_hints(groups, load_routing(project))
    print(
        "tune hints (apply by hand, e.g. scaffold.py register <agent> --kind <kind> --model <m>):"
    )
    print(
        "\n".join(f"  {h}" for h in hints) or f"  none yet (a hint needs {MIN_SAMPLES}+ subtasks)"
    )
    return 0


WORKFLOW_JS = """export const meta = __META__

// Generated by foreman plan.py from a checked plan. Change the plan and regenerate.
const TASK = __TASK__
const SUBTASKS = __SUBTASKS__
const WAVES = __WAVES__
const LADDER = __LADDER__
const LIMIT = 2000
const RETURN = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['done', 'partial', 'blocked', 'failed'] },
    changed: { type: 'array', items: { type: 'string' } },
    result: { type: 'string' },
    verified: { type: 'string' },
    open: { type: 'string' },
  },
  required: ['id', 'status', 'changed', 'result', 'verified', 'open'],
}
const results = {}

function inputsFor(s) {
  const parts = s.deps.map(d => {
    const text = JSON.stringify(results[d])
    if (text.length > LIMIT) log(`${s.id}: input from ${d} cut to ${LIMIT} characters`)
    return `${d}: ${text.slice(0, LIMIT)}`
  })
  return parts.join('\\n') || 'none'
}

function brief(s, note) {
  return [
    `id:      ${s.id}`,
    `task:    ${TASK}`,
    `goal:    ${s.goal}`,
    `owns:    ${s.owns.length ? s.owns.join(', ') : 'none (read-only)'}`,
    `reads:   ${s.reads.join(', ') || '-'}`,
    `inputs:  ${inputsFor(s)}`,
    `verify:  ${s.verify}`,
    'limits:  no commit or push; no edits outside owns; no new dependencies unless the goal'
      + ' names one; no secret values in any file; no full test, lint or build run unless'
      + ' verify names it',
    note ? `retry:   ${note}` : '',
    'return:  the structured fields id, status, changed, result, verified, open',
  ].filter(Boolean).join('\\n')
}

function up(model) {
  const i = LADDER.indexOf(model)
  return i >= 0 && i < LADDER.length - 1 ? LADDER[i + 1] : null
}

// failure ladder, one rerun: a partial result below high effort stopped short, so it reruns on
// the same model at high effort (on any tier); a failed one, or a partial one already at high
// effort, had its try and goes one model tier up, and has no rerun on the top tier
function rerunWith(r, model, effort) {
  if (r && r.status === 'partial' && ['low', 'medium'].includes(effort)) {
    return { model, effort: 'high' }
  }
  const higher = up(model)
  return higher ? { model: higher, effort } : null
}

async function run(s, wave) {
  const waiting = s.deps.filter(d => results[d].status !== 'done')
  if (waiting.length) {
    results[s.id] = { id: s.id, status: 'skipped', changed: [], verified: 'not run',
      result: `waits on ${waiting.join(', ')}, which did not finish`,
      open: 'rerun after its dependencies', attempts: 0, final_model: s.model,
      final_effort: s.effort }
    return
  }
  let now = { model: s.model, effort: s.effort }
  let note = ''
  let attempts = 0
  let r = null
  while (attempts < 2) {
    attempts++
    const tag = now.effort === s.effort ? now.model : `${now.model}, ${now.effort}`
    const opts = { label: attempts > 1 ? `${s.id} (${tag})` : s.id, phase: `Wave ${wave}`,
      model: now.model, schema: RETURN }
    if (s.agent) opts.agentType = s.agent
    if (now.effort) opts.effort = now.effort
    try {
      r = await agent(brief(s, note), opts)
    } catch (e) {
      // agent() throws when the return never matches the schema; treat it as a failed attempt
      r = null
      log(`${s.id}: agent call failed on ${now.model}: ${String(e).slice(0, 200)}`)
    }
    // blocked needs the foreman, so it is not rerun
    if (r && !['failed', 'partial'].includes(r.status)) break
    const rerun = attempts < 2 ? rerunWith(r, now.model, now.effort) : null
    if (!rerun) break
    const why = r ? `${r.status}, ${r.result.slice(0, 500)}` : 'no result'
    note = `attempt ${attempts} on ${now.model}: ${why}`
    now = rerun
    log(`${s.id}: retrying on ${now.model} at ${now.effort || 'default'} effort`)
  }
  const fallback = { id: s.id, status: 'failed', changed: [], result: 'no result',
    verified: 'not run', open: 'do it in the main session' }
  results[s.id] = { ...(r || fallback), attempts, final_model: now.model,
    final_effort: now.effort }
}

for (let w = 0; w < WAVES.length; w++) {
  phase(`Wave ${w + 1}`)
  await parallel(WAVES[w].map(id => () => run(SUBTASKS[id], w + 1)))
  log(`wave ${w + 1}: ${WAVES[w].map(id => id + ' ' + results[id].status).join(', ')}`)
}
return results
"""


def compile_workflow(plan: dict, report: dict, routing: dict) -> str:
    """JS for the Workflow tool: waves run in order, subtasks in a wave run in parallel."""
    ids = [s["id"] for s in report["subtasks"]]
    subtasks = {}
    for s in report["subtasks"]:
        deps = sorted({d for e in s.get("after", []) for d in resolve_after(e, ids)} - {s["id"]})
        subtasks[s["id"]] = {
            "id": s["id"],
            "agent": s["agent"],
            "model": s["model"],
            "effort": s["effort"],
            "goal": s["goal"],
            "owns": s["owns"],
            "reads": s.get("reads", []),
            "verify": s["verify"],
            "deps": deps,
        }
    task = str(plan.get("task", ""))
    meta = {
        "name": f"foreman-{plan.get('template', 'custom')}",
        "description": f"foreman plan: {task[:100]}" if task else "foreman plan",
        "phases": [{"title": f"Wave {w}"} for w in range(1, len(report["waves"]) + 1)],
    }
    values = {
        "__META__": json.dumps(meta, indent=2),
        "__TASK__": json.dumps(task),
        "__SUBTASKS__": json.dumps(subtasks, indent=2),
        "__WAVES__": json.dumps(report["waves"]),
        "__LADDER__": json.dumps(routing["ladder"]),
    }
    # one pass over the template only, so placeholder-like text inside the plan stays text
    return PLACEHOLDER.sub(lambda m: values[m.group(0)], WORKFLOW_JS)


def cmd_workflow(project: Path, source: str, out: str | None) -> int:
    try:
        plan = read_plan(source)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FM001 cannot read plan: {exc}", file=sys.stderr)
        return 1
    routing = load_routing(project)
    report = check_plan(plan, routing)
    if report["errors"]:
        print("plan has errors; run plan.py check and fix them first:", file=sys.stderr)
        print("\n".join(f"  {e}" for e in report["errors"]), file=sys.stderr)
        return 1
    script = compile_workflow(plan, report, routing)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(script.encode("utf-8"))
        n_waves = len(report["waves"])
        print(f"wrote {Path(out).as_posix()}: {len(report['subtasks'])} subtasks, {n_waves} waves")
    else:
        print(script, end="")
    return 0


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
    p_log = sub.add_parser("log", help="append a finished plan's outcomes to the run log")
    p_log.add_argument("plan", help="plan JSON with per-subtask status, or - for stdin")
    p_log.add_argument("--log", help="log file (default: $FOREMAN_LOG or ~/.claude/foreman)")
    p_stats = sub.add_parser("stats", help="success per kind x model from the run log")
    p_stats.add_argument("--log", help="log file (default: $FOREMAN_LOG or ~/.claude/foreman)")
    p_stats.add_argument("--all", action="store_true", help="every project, not just --project")
    p_wf = sub.add_parser("workflow", help="compile a checked plan into a Workflow script")
    p_wf.add_argument("plan", help="plan JSON file, or - for stdin")
    p_wf.add_argument("--out", help="write the script here instead of stdout")
    args = parser.parse_args(argv)
    project = Path(args.project).resolve() if args.project else Path.cwd()
    if args.cmd == "templates":
        return cmd_templates(project)
    if args.cmd == "routes":
        return cmd_routes(project)
    if args.cmd == "new":
        return cmd_new(project, args.template, args.task)
    if args.cmd == "log":
        return cmd_log(project, args.plan, args.log)
    if args.cmd == "stats":
        return cmd_stats(project, args.log, args.all)
    if args.cmd == "workflow":
        return cmd_workflow(project, args.plan, args.out)
    return cmd_check(project, args.plan, args.json)


if __name__ == "__main__":
    sys.exit(main())
