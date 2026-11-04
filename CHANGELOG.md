# Changelog

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
