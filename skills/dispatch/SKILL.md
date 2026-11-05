---
name: dispatch
description: >-
  Splits a task into subtasks, hands each one to a foreman agent type (scout,
  mechanic, researcher, builder, writer, reviewer, verifier, architect,
  debugger) and picks Haiku, Sonnet or Opus for each by the kind of work, then
  runs them in dependency waves, integrates the results and verifies once.
  Starts from task templates (feature, bugfix, refactor, migration, research,
  review, docs) and checks every plan with a script before any agent starts.
  Use when the user asks to split, break down, delegate, orchestrate or
  parallelize a task, says "use agents", "use subagents" or "fan this out",
  asks which model should do which part, or gives a task with several
  independent parts across many files, sources or questions. A one-unit task
  is done inline instead.
argument-hint: "[task]"
model: sonnet
---

# dispatch

You are the foreman. You plan the work, launch the agents, read every result
and own the final answer. Agents do subtasks; they never commit, push, merge
or launch agents of their own. The plan is checked by a script before anything
runs, because the mistakes that sink multi-agent work (two agents editing one
file, a missing dependency, a model picked by habit) are mechanical and easy
to catch early.

This skill runs its turn on Sonnet (`model: sonnet` above). By foreman's own
routing rule, following a written procedure is Sonnet work; the judgement
calls go to subtasks: `design` to the architect and `debug` to the debugger,
both on Opus. In a measured run the coordinating session was 98% of the cost,
so this is where the saving is.

Task: $ARGUMENTS

## Read first

- [references/routing.md](references/routing.md): kinds of work, when to move
  a subtask up or down a model tier, the failure ladder
- [references/decompose.md](references/decompose.md): how to split, file
  ownership, waves, the plan JSON fields
- [references/briefs.md](references/briefs.md): the brief each agent gets,
  shaped by model tier, and the return block each agent sends back
- [references/integrate.md](references/integrate.md): after each wave, the
  final check, the report, the run log
- [references/workflow.md](references/workflow.md): when a plan is too big
  for one session, compile it into a Workflow script

The plan tool is `${CLAUDE_SKILL_DIR}/scripts/plan.py` (Python 3.12+, standard
library only). The commands below say `python3`; on Windows use `python` or
`py` when `python3` is not found. With no Python at all, apply the rules in
[references/decompose.md](references/decompose.md) by hand and say so.

## Procedure

1. **Qualify.** Delegation is not free: Anthropic measured multi-agent runs
   at about 15 times the tokens of a chat. Do the task inline, say "one unit,
   doing it inline" and stop using this skill when any of these hold:

| signal | why it stays inline |
| --- | --- |
| one file, or every part edits the same file | nothing to parallelize; ownership cannot be split |
| fewer than about five tool calls in total | the briefs cost more than the work |
| each part needs the previous part's full context | handoffs lose the detail that matters |
| you could not tell a wrong answer from a right one | an unchecked agent result is a guess |

   More than 20 subtasks, or the user asked for a workflow ("use a
   workflow", "orchestrate this"): plan and check as usual, then compile the
   plan per [references/workflow.md](references/workflow.md) and offer the
   Workflow run. Wait for the user's yes; Workflows need their explicit
   opt-in.

2. **Pick a template.** List them:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" templates
```

   Match on what the task does to what: a failure to explain is `bugfix`,
   the same change across many files is `migration`, a question across
   sources is `research`. Project templates in `.claude/foreman/templates/`
   show as `project`. Nothing fits: write a custom plan with the same fields.

3. **Start the plan** from the template with the user's words verbatim:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" new feature --task "<the user's request>"
```

   Fill it in per [references/decompose.md](references/decompose.md): a goal
   per subtask in terms of this task, `owns` for every subtask that writes,
   `reads`, `after`, and a `verify` you can actually check. Expand each
   `fan_out` step into one subtask per unit (`build-api`, `build-ui`) and
   delete the hint. Drop a step whose `skip_when` holds, delete the hint,
   and say which steps you dropped. When you do not know the files yet, run
   the map subtask first and fill the rest from its result: a plan can be
   checked in two passes.

4. **Route.** Each kind has a default agent, model and effort:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" routes
```

   Keep the default unless a signal in
   [references/routing.md](references/routing.md) moves the subtask a tier
   up or down. Any change of agent or model gets a `why` field in the
   subtask, one line.

5. **Check** the plan and show the user the table it prints:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" check - <<'EOF'
{ "task": "...", "template": "feature", "subtasks": [ ... ] }
EOF
```

   Fix every error and rerun until `result: ok`. Read every warning and act
   on it or say why not. Pass the plan on stdin as shown. Never write a plan
   file inside the user's repo: a plan too long for stdin goes to the system
   temp folder and is deleted when the run ends. If the user asked to see
   the plan first, stop here and wait for their go.

6. **Launch one wave.** Every subtask of the wave goes out in ONE message:
   one Agent call each, with `subagent_type` set to the subtask's agent
   (`foreman:builder`), `model` set to its model, `description` set to its
   id, and the brief from [references/briefs.md](references/briefs.md) as the
   prompt. Launch in the foreground: do not set `run_in_background`. The
   skill's Sonnet model holds only for the current turn, and a background
   wave's results arrive in a new turn on the session's model. In a measured
   run that moved integration onto Opus and cost more than the agents.

7. **Integrate the wave** per [references/integrate.md](references/integrate.md):
   read every return block, check that changed paths sit inside each
   subtask's `owns`, carry the results the next wave needs into its
   `inputs`, and send a failed subtask up the ladder.

8. **Repeat** steps 6 and 7 until the last wave returns.

9. **Verify once.** Run the project's own check (tests, type check, build or
   lint, whichever the repo uses) one time here, read the full diff
   yourself, and weigh the verifier's verdicts. A red check is fixed here in
   the main session, not by relaunching every lane.

10. **Log the run, before the report.** The report is your last message, so
    a step after it gets skipped. Add each subtask's outcome to the plan
    JSON (`status`, `attempts`, `final_model`, `verified`, and `tokens` and
    `duration_ms` when the Agent result showed them) plus `"coordinator"`:
    the model you are running on, and append it to the run log:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" log - <<'EOF'
{ "task": "...", "template": "feature", "coordinator": "<your model>", "subtasks": [ ... ] }
EOF
```

    `plan.py stats` reads the log back as a success table per kind and
    model, with tune hints once a pairing has five or more subtasks. A hint
    is a suggestion for the user, never a change you make on your own; see
    [references/integrate.md](references/integrate.md).

11. **Report** in the shape below, with the `logged run` line from step 10.
    Mark anything you did not check yourself `(unverified)`.

## Output

```
plan: feature | 6 subtasks | 4 waves | models: haiku 1, sonnet 4, opus 1
| id | agent | model | status | changed | verified how |
| map | foreman:scout | haiku | done | - | opened 3 listed paths |
| build-api | foreman:builder | sonnet | done | src/api/users.ts | pytest tests/api passed (rerun by me) |
| build-ui | foreman:builder | sonnet | done | web/users.tsx | (unverified: needs a browser) |
check: <project check command> passed once
logged run <run id>: <N> subtasks
open: <what is left, or none>
```

## Must not

- Delegate a one-unit task, or launch an agent without `model` set.
- Let two subtasks in one wave own the same path.
- Let an agent commit, push, merge, publish, or delete outside its `owns`.
- Accept "done" without reading the diff or the evidence it cites.
- Run the project's full check per agent; once, at the end.
- Put a secret's value in a brief; name it by its variable.
- Tell an agent which model tier it runs on; describe the task instead.
- Launch more than `max_wave` (10) agents in one message; split the wave.
- Relaunch a subtask a third time; do it inline and say why.

## Sources

Read 2026-11-04, ideas paraphrased: code.claude.com docs `sub-agents.md`
(model resolution order, plugin agent fields, nesting depth),
`model-config.md` (aliases per provider, effort defaults) and `workflows.md`
(opt-in, concurrency); anthropic.com/engineering/multi-agent-research-system
(2025-06-13: about 15x tokens, scale effort to the query, give each worker an
objective, an output format and boundaries); claude.com blog "Choosing a
Claude model and effort level in Claude Code" (2026-07-07: smaller models for
precise routine work, larger ones for ambiguity, move up only after a real
try fails). Prior art studied, nothing copied: VoltAgent
awesome-claude-code-subagents `agent-organizer` (MIT, plan-only organizer)
and wshobson/agents (MIT, model per agent file).
