# Big plans as Workflow scripts

A Claude Code Workflow is a script the runtime executes: it holds the plan,
the loops and the intermediate results, so the coordinating session's
context holds only the final answer. Use it when a checked plan is larger
than one session should run turn by turn.

## When

- More than 20 subtasks, or more than 3 waves of 10.
- The user asked for a workflow ("use a workflow", "orchestrate this",
  "fan out"), or ultracode is on for the session.

Otherwise run the waves yourself with Agent calls: you can check ownership
between waves, which a script cannot.

A Workflow runs only with the user's explicit opt-in. Show the plan table and
the agent count, say it will run as a Workflow, and wait for their yes. A
plan you compiled is not their opt-in.

## Compile

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" workflow <plan.json> --out <temp folder>/foreman-<template>.js
```

The plan must pass `plan.py check`; `workflow` refuses one with errors. Keep
the plan file and the script in the system temp folder, not the repo.

The script it writes:

- runs the waves in order and every subtask of a wave in parallel
- launches each subtask with `agentType` set to its agent (`foreman:builder`),
  `model` and `effort` set from the plan, and a JSON schema for the return
  block (`id`, `status`, `changed`, `result`, `verified`, `open`)
- passes each subtask the results of the subtasks it waits for, cut to 2,000
  characters each (it logs every cut)
- applies the failure ladder in code, one rerun per subtask with the reason
  in the brief: a `partial` result below `high` effort reruns on the same
  model at `high`; a `failed` one, or a `partial` one already at `high`,
  reruns one tier up the project's ladder (opus to fable by default); on
  the top tier there is no tier to move to, so that result stands; `blocked`
  is never rerun, because it needs you
- marks every subtask that waits on an unfinished one `skipped`
- returns one result per subtask with `attempts`, `final_model` and
  `final_effort`

## Run

Call the Workflow tool with `scriptPath` set to the compiled file. Watch it
in `/workflows`. When it returns:

1. Run the ownership check from [integrate.md](integrate.md) once over the
   whole run (`git status --porcelain` against every `owns`); the script
   cannot.
2. Rerun the `skipped` and `failed` subtasks yourself, or fix the plan and
   compile again. A relaunch with the same script returns finished agents
   from cache.
3. Verify once, report, and log the run with the returned `attempts`,
   `final_model`, `final_effort` and `status` per subtask.

## Limits

The runtime runs up to 16 agents at once by default, fewer on a machine with
few CPUs (`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` changes it, 1 to 256),
and at most 1,000 agents per run. A script cannot read files or run commands; only
its agents can. `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` (Claude Code 2.1.296
and later) runs every workflow agent on one model; when a user sets it, the
plan's per-subtask models have no effect and the report should say so.
Source: code.claude.com docs `workflows.md`, read 2026-11-04, and the Claude
Code changelog, read 2026-11-10.
