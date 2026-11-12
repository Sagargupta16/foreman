# CLAUDE.md

> This file stacks on top of the workspace root at `C:\Code\GitHub\`:
> - Root [`CLAUDE.md`](../../CLAUDE.md) -- voice, rules, routing map, references, skills, slash commands, conventions.
> - Root [`MEMORY.md`](../../MEMORY.md) -- live facts across repos.
> - Root [`STATUS.md`](../../STATUS.md) -- live PR/CI/security dashboard.
> - [`.claude/resources/`](../../.claude/resources/README.md) -- deep reference for collaboration, workflow, git, OSS, debugging, voice.
>
> Read those first. The guidance below only adds **repo-specific context** -- it does not override anything in the root.

## Project

Claude Code plugin (`foreman`) that splits a task into subtasks, routes each to a predefined agent type and picks the model (haiku, sonnet, opus, fable) by the kind of work, then runs the subtasks in dependency waves and verifies once. A second skill scaffolds new agents and agent plugins and lints agent files. Public since 2026-11-11; the repo is its own plugin marketplace.

Install: `/plugin marketplace add Sagargupta16/foreman` then `/plugin install foreman@foreman`, or `claude --plugin-dir .` from a clone.

## Stack

- **Language**: Python 3.12+ standard library (plan checker, scaffolder, repo gate)
- **Framework**: none at runtime; Markdown skills and agents, JSON routing and templates
- **Package manager**: none required; `pip install -r requirements-dev.txt` for ruff
- **Deploy target**: GitHub repo as its own plugin marketplace (`.claude-plugin/marketplace.json`, `source: "./"`)

## Run

```
python skills/dispatch/scripts/plan.py templates
python skills/dispatch/scripts/plan.py routes
python skills/dispatch/scripts/plan.py new feature --task "..."
python skills/dispatch/scripts/plan.py check examples/feature-plan.json
python skills/dispatch/scripts/plan.py workflow examples/feature-plan.json --out .scratch/feature.js
node tests/workflow_harness.mjs .scratch/feature.js build-api   # run it against mocks; build-api fails once
python skills/dispatch/scripts/plan.py log plan-with-results.json --log .scratch/runs.jsonl
python skills/dispatch/scripts/plan.py stats --log .scratch/runs.jsonl
python skills/new-agent/scripts/scaffold.py agent NAME --kind review --dest .scratch/agents
python skills/new-agent/scripts/scaffold.py plugin NAME --dest .scratch/NAME --agent a:implement --skill
python skills/new-agent/scripts/scaffold.py lint agents
python scripts/how_it_works_svg.py   # redraw the README figure in docs/how-it-works/
```

## Test

```
python scripts/check.py
python -m pytest -q
ruff check .
ruff format --check .
npx -y @sagargupta1610/skillcheck@0.2.5 lint skills
claude plugin validate .
claude plugin eval . --scaffold --allow-tools Bash Write Edit   # real models, costs tokens, run on request
```

## Entry points

- `skills/dispatch/SKILL.md` -- the foreman procedure (`/foreman:dispatch`)
- `skills/dispatch/routing.json` -- kind to agent, model, effort, tool profile; the one source of truth
- `skills/dispatch/templates/*.json` -- task templates
- `skills/dispatch/scripts/plan.py` -- plan checker (FM001-FM016), run log and stats with tune hints, plan-to-Workflow compiler
- `tests/workflow_harness.mjs` -- runs a compiled Workflow offline against mock `agent()`/`parallel()`; pytest drives it
- `skills/new-agent/SKILL.md` -- agent and plugin scaffolding (`/foreman:new-agent`)
- `skills/new-agent/scripts/scaffold.py` -- agent, plugin, register, lint (FA001-FA010)
- `agents/*.md` -- the ten agent types
- `hooks/hooks.json`, `hooks/capture.py` -- the optional SubagentStop hook that records agent runs (plugin option `capture_runs`, off by default)

## Gotchas

- The capture hook was built against real payloads on Claude Code 2.1.322 (2026-11-12): SubagentStop carries `agent_type`, `agent_transcript_path` and `effort.level`; the agent transcript writes one line per content block with the same `message.id` and `usage`, so usage is counted once per id; the `tokens` it stores equals the `totalTokens` the Agent tool reports. The subtask id comes from `agent-<id>.meta.json` beside the transcript (`description`, `requestShape`), a file seen on 2.1.322 and not documented, with the brief's `id:` line as fallback: coordinators write free-form briefs, so the brief alone gave no id in a live run. Replay a saved payload to test it: `CLAUDE_PLUGIN_OPTION_CAPTURE_RUNS=true FOREMAN_CAPTURE_LOG=<file> python hooks/capture.py < payload.json`. In a `claude -p --plugin-dir .` run, turn the option on with `--settings` holding `{"pluginConfigs": {"foreman@inline": {"options": {"capture_runs": true}}}}`.
- `rates` in routing.json are Anthropic list prices read on the date in `rates.read`. Re-read https://platform.claude.com/docs/en/about-claude/pricing before changing them, and bump the date.
- The README figure (`docs/how-it-works/*.svg`) is drawn from data written into `scripts/how_it_works_svg.py` (`SUBTASKS`, `TIMES`, the lane agent lists). A change to `routing.json`, the agent roster or `examples/feature-plan.json` needs the same change there and a rerun; never hand-edit the SVGs. Check them with svg-forge's `validate_svg.py --strict-contrast` (one `--theme` per half) and look at `frames.py` sheets: 0 errors and 0 warnings on all four files on 2026-11-11.
- An agent's `model`, `effort` and `tools` must equal its routing.json kind and profile; `scripts/check.py` (FC009) fails otherwise. Change routing.json and the agent file together.
- Plugin agents ignore `permissionMode`, `hooks`, `mcpServers` and `initialPrompt`; `claude plugin validate` does not warn about them (measured 2.1.312), `scaffold.py lint` does (FA005).
- The Agent tool's per-call `model` beats the agent file's `model`; dispatch relies on that to route per subtask.
- `claude plugin validate .` warns that this CLAUDE.md is not loaded as plugin context. Expected: it is for repo sessions, not plugin users. It also prints a plugin directory warning for the missing icon (ICON_MISSING), so `--strict` fails on those two; the plain run passing with exactly those two warnings is the gate (2026-11-10).
- Templates under `skills/new-agent/assets/` use `string.Template` (`${name}`); a literal `$` must be `$$`.
- The Workflow script template lives in a Python string in plan.py (`WORKFLOW_JS`): `\\n` there becomes `\n` in JS. Workflow scripts may not call `Date.now()`, `Math.random()` or argless `new Date()` (a test checks it).
- dispatch has `model: sonnet` in its frontmatter: the coordinator turn runs on Sonnet whatever the session model is. That holds for one turn only, and subagents start in the background everywhere unless the call asks to wait (sub-agents docs, read 2026-11-11). In `claude -p` and the Agent SDK the Agent tool has `run_in_background`, and dispatch sets it to `false` so the wave returns in the same turn: a 0.3.0 run in `claude -p` (2.1.322) left it unset, all three agents went to the background and the turns after the wave ran on Opus; the 0.3.1 run on the same version kept both waves in the foreground and every coordinator turn on Sonnet. Interactive terminal, VS Code and desktop sessions have no such parameter unless `CLAUDE_CODE_FORK_SUBAGENT=0`, so there wave results arrive in later turns on the session's model.
- Fable is the top of the ladder and the route for `solve` only (`foreman:specialist`). `max_top` in routing.json caps Fable subtasks per plan (FM015). Reruns go effort first (a `partial` below high reruns at high on the same model), then one tier up.
- Live test runs (`claude -p --plugin-dir .`) need the demo repo OUTSIDE this folder: files under a loaded plugin dir count as sensitive, so every agent edit there is denied in `-p` mode (2026-11-04). The 2026-11-04 run used a two-package demo repo at `C:/Code/worktrees/foreman-demo` (4 haiku subtasks, 4/4 verified, 0.92 USD, 0.90 of it the Opus main session). From the Desktop app, `claude -p` has to run in a terminal tab (Desktop-managed Bedrock credentials refuse a Bash child). With foreman also installed at user scope, pass `--settings` with `{"enabledPlugins": {"foreman@foreman": false}}` so the `--plugin-dir` copy is the only one loaded (the `init` event lists it by path). A task of a few small edits is done inline with no agents; end the prompt with "Use subagents for the parts." to exercise a wave.

## Repo-specific rules

- Written for public release: no personal names in skill or agent bodies ("the user"), no home paths. Author and owner fields are the exception.
- Skill frontmatter: `name` equals the folder, `description` is a `>-` block with "Use when" triggers and no unquoted `: `.
- Every PR updates CHANGELOG.md under a concrete version and bumps both manifests when it releases.
- No en or em dashes anywhere; `scripts/check.py` fails on them.
