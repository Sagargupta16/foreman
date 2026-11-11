# Changelog

## [0.3.2] - 2026-11-11

- Docs: "How a task runs" in the README opens with an animated figure of one
  dispatch run: the request, the 6-subtask plan, the `plan.py check` gate,
  three waves on the model ladder (Haiku, Sonnet, Opus, Fable), a rerun at
  higher effort, verify once and the run log, with a caption for each beat.
  It plays `examples/feature-plan.json` as the checker routes it. Four
  self-contained SVGs (dark and light, desktop and phone, about 25 KB each,
  SMIL only, so it animates inside a README image) live in
  `docs/how-it-works/`; `scripts/how_it_works_svg.py` draws them.

## [0.3.1] - 2026-11-11

- Fix: dispatch now waits for its wave in `claude -p` and the Agent SDK.
  Agents start in the background unless the call asks to wait, there too. A
  0.3.0 run in `claude -p` (Claude Code 2.1.322) started all three agents in
  the background and finished on the session's model (Opus), though the docs
  said the turn waits. Step 6 now sets `run_in_background: false` on every
  Agent call when the tool has that parameter. Measured after the change on
  the same version: two waves ran in the foreground, the reports came back
  in the turn, and every turn ran on Sonnet (four Sonnet subtasks, 0.61 USD
  in total). The README table, the skill and the repo CLAUDE.md now say what
  was measured.
- Fix: dispatch sets `effort` on every Agent call, taken from the checked
  plan. It used to set it only when it differed from the agent's own, which
  the coordinator cannot see: with a project route such as
  `{"kinds": {"implement": {"effort": "high"}}}` the plan showed `high`
  while the builder's file says `medium`, and nothing said the two differ.
- Fix: a project `.claude/foreman/routing.json` whose `max_top` or
  `max_wave` is not a whole number (`"max_top": "2"`) crashed `plan.py check`
  with a `TypeError`. That, and a routing file that is not a JSON object, is
  now FM016 with the file and the key named, from every command that reads
  the routing.
- Docs: the repo is public since 2026-11-11 and is its own marketplace.
  `SECURITY.md` points at GitHub private vulnerability reporting beside the
  email and lists the specialist among the agents that can edit files.

## [0.3.0] - 2026-11-10

- Fable tier: the ladder is now haiku, sonnet, opus, fable. A tenth agent,
  `specialist` (fable, high effort), takes `solve` subtasks: one long,
  tangled unit done end to end in one context where splitting would lose the
  thread. A `design` or `debug` that was still wrong on Opus reruns on Fable.
  `references/routing.md` says what the top tier is for and what to keep off
  it (the coordinating turn, work a brief could spell out, getting past a
  refusal), with list prices read 2026-11-10.
- `plan.py check`: FM015 warns when more than `max_top` (2) subtasks sit on
  the top tier. FM012 no longer flags a single subtask that is on the top
  tier: sending one hard unit up is the point of delegating it.
- Failure ladder: effort before model. A subtask that stopped short
  (`partial`, below high effort) reruns once on the same model at `high`
  through the Agent tool's per-call `effort` (Claude Code 2.1.292 and
  later); one that tried and was wrong reruns once a tier up. Compiled
  Workflows apply the same rule and return `final_effort`.
- Run log and stats: each line records `effort` and `final_effort`. A new
  hint, raise a kind's effort, fires when over 30% of its subtasks needed a
  rerun at higher effort; those reruns no longer count toward raising the
  model.
- Fix: dispatch told the coordinator to launch waves in the foreground, which
  interactive terminal, VS Code and desktop sessions cannot do (subagents
  start in the background there by default). The skill now handles both
  cases and says which model integrates the results; the README has the
  table and the two ways to stay on Sonnet.
- Fix: a plan with `"owns": "src/x.ts"` (a string, not a list) was read as
  one path per character and reported a false overlap; `owns`, `reads` and
  `after` now take a lone string as one entry. A numeric `id` no longer
  crashes `plan.py check`, and a `kind` that is not text is FM003.
- Project routing can set `ladder` and `max_top` as well as `max_wave`, so a
  project with no Fable stops the ladder at opus.
- Compiled Workflows take the ladder from the routing table (it was a fixed
  haiku, sonnet, opus list).

## [0.2.0] - 2026-11-04

- Run log: `plan.py log` appends one line per finished subtask to
  `~/.claude/foreman/runs.jsonl` (or `$FOREMAN_LOG`); dispatch logs every run
  as its last step.
- `plan.py stats`: success, escalation and verification per kind x model,
  with tune hints (raise or lower a route) once a pairing has 5+ subtasks.
  Hints are never applied automatically.
- `plan.py workflow`: compiles a checked plan into a Workflow script (waves,
  `agentType` and model per subtask, structured return block, failure ladder
  in code, dependents of unfinished work skipped). New reference
  `references/workflow.md`; dispatch offers it for plans over 20 subtasks.
- Cheaper coordinator: the dispatch skill runs on Sonnet (`model: sonnet`);
  judgement still goes to the architect and debugger on Opus. Waves launch in
  the foreground, because a background wave's results arrive in a new turn on
  the session's model (measured: an Opus integration turn cost 0.71 of 1.49
  USD). The run log records the coordinator's actual model.
- Tests: pytest suite for plan.py and scaffold.py, and a Node harness that
  runs compiled Workflows against mock `agent()` and `parallel()`.
- Evals: `claude plugin eval` cases for dispatch and new-agent.
- Fix: `scaffold.py plugin` checks every `--agent` name and kind before
  writing, so a bad kind no longer leaves a half-written plugin.
- Compiled Workflows: `final_model` is the model of the last attempt (it
  named a model that never ran after two failures), an `agent()` call that
  throws counts as a failed attempt instead of ending the run, and plan text
  that looks like a template placeholder (`__TASK__`) stays text.
- Tune hints: the "lower" hint counts only first-try successes on the lower
  tier, and skipped subtasks no longer count against a model.
- `check.py` skips `.archify/` and eval `results/`; CI runs pytest.

## [0.1.0] - 2026-11-04

- `dispatch` skill: qualify, pick a template, plan, route, check, run in
  waves, integrate, verify once, report with the model mix.
- Nine agents with per-kind model and effort: scout and mechanic (haiku),
  researcher, builder, writer, reviewer and verifier (sonnet), architect and
  debugger (opus), all ending in one return block.
- `routing.json`: kind of work to agent, model, effort and tool profile;
  project overrides in `.claude/foreman/routing.json`.
- Seven task templates (feature, bugfix, refactor, migration, research,
  review, docs); project templates in `.claude/foreman/templates/`.
- `plan.py`: `templates`, `routes`, `new`, `check` with rules FM001 to
  FM014 (overlapping owns per wave, silent model changes, cycles, missing
  verify).
- `new-agent` skill and `scaffold.py`: write an agent or an agent plugin,
  register a route, lint agent files (FA001 to FA010).
- `scripts/check.py` repo gate and CI.
