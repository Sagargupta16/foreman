# Changelog

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
