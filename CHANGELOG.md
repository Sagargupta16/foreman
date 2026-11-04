# Changelog

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
