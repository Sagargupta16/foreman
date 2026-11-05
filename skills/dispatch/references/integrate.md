# Integrate, verify, report

## After every wave

1. **Read each return block.** Status, changed paths, the verified line. A
   summary describes intent; the diff and the evidence are what happened.
2. **Check ownership.** Run `git status --porcelain` and map every changed
   path to exactly one subtask's `owns`. A path outside every `owns` is
   reverted (`git checkout -- <path>` for a tracked file the user did not
   change before the run) and that subtask is rerun with a tighter brief.
   Never revert a path the user changed before the run.
3. **Spot-check claims.** For each `verified:` line, rerun the command or
   open the cited file when it is cheap. What you did not check stays
   `(unverified)` in the report.
4. **Carry results forward.** Put what the next wave needs into its
   `inputs`: the architect's lanes become builder briefs, the debugger's
   `fix owns` becomes the builder's `owns`, the scout's map becomes `reads`.
   When a result changes the plan (the design has four lanes, not two),
   update the plan and run `plan.py check` again before the next wave.
5. **Handle failures** with the ladder in [routing.md](routing.md).

## Verify once at the end

- Run the project's own check one time: the test command, type check, build
  or linter the repo uses (its README, CONTRIBUTING or CI file says which).
- Read the full diff (`git diff`) yourself.
- Weigh the verifier subtask's verdicts. A refuted claim reopens the
  subtask that made it.
- A red check is fixed here, in the main session. Relaunching every lane for
  one shared error wastes the whole run.

## Report

Lead with the outcome in one line, then the table, then what is open. One
row per subtask: id, agent, model, status, changed paths, and how YOU
verified it. Add the model mix (`haiku 2, sonnet 4, opus 1`), because the
user chose foreman partly to spend less on the parts that do not need the
largest model.

Commit, push or open a PR only when the user asked, and only after the final
check passes. One commit or PR for the whole run, never one per subtask.

## Log the run

Every finished run goes to the run log, including runs where subtasks
failed: the failures are what the stats are for. Per subtask, record:

| field | value |
| --- | --- |
| `status` | `done`, `partial`, `blocked`, `failed`, `skipped`, or `inline` when you did it yourself after the ladder |
| `attempts` | launches of this subtask, 1 when it ran once |
| `final_model` | the model of the last attempt, when the ladder moved it |
| `verified` | `true` only when you checked the result yourself |
| `tokens`, `duration_ms` | from the Agent result's usage, when it shows them |

The log lives at `~/.claude/foreman/runs.jsonl` (or `$FOREMAN_LOG`), one
JSON line per subtask with the project path, so one file serves every
project. It holds subtask ids and kinds, not the task's content beyond the
template name.

## Read the stats

`plan.py stats` groups the log for this project (`--all` for every project)
by kind and model: subtasks, done, escalated, verified, median tokens. Below
the table it prints tune hints:

- **raise** a kind one tier when, on its route's model, fewer than 70% of its
  subtasks finished or more than 30% escalated
- **lower** a kind one tier when, one tier below its route, 90% or more
  finished and were verified

A hint needs five or more subtasks for that pairing. Show hints to the user
with their numbers; applying one is their decision (`scaffold.py register`
or an edit to `.claude/foreman/routing.json`). Never change a route because
of a hint on your own.
