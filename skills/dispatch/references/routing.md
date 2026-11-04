# Routing: which agent, which model

`plan.py routes` prints the live table from [../routing.json](../routing.json)
merged with the project's `.claude/foreman/routing.json`. This page explains
how to read it and when to leave the default.

## The default rule

The kind of work picks the agent; the agent's file sets the default model and
effort. In one line: Haiku when the brief can spell out the exact steps,
Sonnet when the goal is specified and the agent chooses the steps, Opus when
the agent has to decide what the goal even means.

| tier | gets | kinds |
| --- | --- | --- |
| haiku | exact files, exact commands, a recipe; output a machine can check | locate, mechanical |
| sonnet | a clear goal and boundaries; it picks the steps | research, implement, document, review, verify |
| opus | an outcome and the constraints; it picks the approach | design, debug |

`fable`, where the provider has it, sits above opus for the hardest long
runs. The ladder in `routing.json` stops at opus; use fable only with a `why`.

## Move a subtask up one tier when

- the goal is ambiguous, or the user described an outcome and not a change
- the stakes are high: authentication, payments, data migrations, deletes,
  security review, a public API
- the change crosses several modules, or its owns list is long and the parts
  interact
- the same subtask already failed once at this tier (the failure ladder)
- a review lens is security or concurrency (`review` to opus)

## Move a subtask down one tier when

- the brief contains the exact old and new text, or the exact commands
  (`implement` to mechanical on haiku)
- a pilot already proved the recipe and this subtask repeats it
- the result is checked mechanically right after (a count, a test, a grep)

Every move, up or down, gets a `why` in the subtask. The check fails a plan
that changes a model or agent silently, because "it felt hard" is how cost
runs away and "it felt easy" is how quality drops.

## The failure ladder

1. A subtask returns `failed` or `blocked`, or its claim does not survive
   your check: read why. A missing input or a wrong brief is your bug: fix
   the brief and rerun at the same tier.
2. A real attempt with the right inputs that still failed: rerun once, one
   tier up, with the failure reason pasted into `inputs`.
3. Several subtasks fail with the same error: that is one shared cause (a
   broken build, a missing dependency, a wrong path in every brief). Fix it
   once in the main session and rerun only those subtasks.
4. A subtask fails at opus, or fails twice in total: do it inline in the
   main session and say why. Never a third launch.

## Provider notes

The Agent tool's `model` parameter takes aliases only (`haiku`, `sonnet`,
`opus`, `fable`), and each alias resolves per provider. On Amazon Bedrock and
Google Cloud's Agent Platform, `sonnet` and `haiku` resolve to older models
than on the Anthropic API unless `ANTHROPIC_DEFAULT_SONNET_MODEL` and
`ANTHROPIC_DEFAULT_HAIKU_MODEL` are set; the tiers then differ more than the
names suggest. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` makes one model override
every per-call choice; when a user sets it, foreman's routing has no effect
and the report should say so.

A subagent on a different model from the session does not inherit the
session's effort level, which is why every foreman agent file sets `effort`.

## Adding or overriding a route

A project can route a kind to its own agent, or add a kind, in
`.claude/foreman/routing.json`:

```json
{
  "kinds": {
    "review": { "agent": "my-plugin:security-reviewer", "model": "opus" },
    "migrate-sql": { "agent": "db-migrator", "model": "sonnet", "effort": "high", "profile": "edit", "writes": true, "what": "write and dry-run a SQL migration" }
  }
}
```

Keys merge over the built-in route, so a partial entry keeps the rest. The
`new-agent` skill writes this file for you (`scaffold.py register`).
