# Routing: which agent, which model

`plan.py routes` prints the live table from [../routing.json](../routing.json)
merged with the project's `.claude/foreman/routing.json`. This page explains
how to read it and when to leave the default.

## The default rule

The kind of work picks the agent; the agent's file sets the default model and
effort. In one line: Haiku when the brief can spell out the exact steps,
Sonnet when the goal is specified and the agent chooses the steps, Opus when
the agent has to decide what the goal even means, Fable when one long chain
of hard reasoning has to stay in one head from the first read to the proof.

| tier | gets | kinds |
| --- | --- | --- |
| haiku | exact files, exact commands, a recipe; output a machine can check | locate, mechanical |
| sonnet | a clear goal and boundaries; it picks the steps | research, implement, document, review, verify |
| opus | an outcome and the constraints; it picks the approach | design, debug |
| fable | one tangled unit, start to proof; it investigates, decides, builds and checks | solve |

## Move a subtask up one tier when

- the goal is ambiguous, or the user described an outcome and not a change
- the stakes are high: authentication, payments, data migrations, deletes,
  security review, a public API
- the change crosses several modules, or its owns list is long and the parts
  interact
- the same subtask already failed once at this tier with the right inputs
  (the failure ladder)
- a review lens is security or concurrency (`review` to opus)

## Move a subtask down one tier when

- the brief contains the exact old and new text, or the exact commands
  (`implement` to mechanical on haiku)
- a pilot already proved the recipe and this subtask repeats it
- the result is checked mechanically right after (a count, a test, a grep)

Every move, up or down, gets a `why` in the subtask. The check fails a plan
that changes a model or agent silently, because "it felt hard" is how cost
runs away and "it felt easy" is how quality drops.

## The top tier

Fable is the exception in a plan, never the default. It costs twice what Opus
does per token, and Anthropic's guidance is to start with Opus and use Fable
for demanding reasoning and long-horizon work, or when Opus at higher effort
still falls short. Send a subtask to fable when:

- **the unit cannot be split.** Every step needs what the last one learned: a
  parser rewrite, a concurrency fix, an algorithm, a change whose order is
  tangled. Plan it as one `solve` subtask for the specialist, not as build
  lanes that each see a slice. Work that is one dependent chain does better
  in one context than fanned out.
- **opus already had its try.** A `design` or `debug` subtask ran on opus
  with the right inputs and was still wrong. The failure ladder moves it up.
- **the answer gates everything after it and cannot be undone.** A `design`
  that spans systems and locks in a schema or a public contract, or a
  `debug` for a failure nobody has reproduced. Move it up with a `why`.

Keep a subtask off fable when:

- the brief could spell out the steps. That is haiku or sonnet work at any
  size, and a larger model adds cost, not correctness.
- it is the coordinating turn. In Anthropic's measurements Fable as the
  orchestrator cost 19% more than Opus for about the same score.
- you hope a larger model will get past a refusal. Fable, Opus 5.5 and
  Sonnet 5.5 all run safety classifiers that most often flag cybersecurity
  and biology content, and a flagged request reruns on an older model
  (Opus 4.8 for cybersecurity from Fable and from Opus 5.5 alike). Moving
  exploit analysis or penetration-test work up a tier buys nothing.

`plan.py check` warns (FM015) when more than `max_top` subtasks (2 by
default) sit on the top tier of the ladder.

List prices per million tokens, input / output, read 2026-11-10 on
platform.claude.com `about-claude/pricing`: Haiku 5.5 $0.10 / $0.50 for
prompts up to 100,000 tokens, Sonnet 5.5 $2 / $10, Opus 5.5 $4 / $20,
Fable 5.2 $8 / $40. Opus costs twice Sonnet and Fable twice Opus.

## The failure ladder

A rerun has to change something. In Anthropic's measurements, rerunning a
failure on the same model at the same effort scored about the same for more
money, while rerunning only the failures at `high` effort beat running
everything at `high` for a little over half the cost.

1. A subtask returns `failed`, `partial` or `blocked`, or its claim does not
   survive your check: read why. A missing input or a wrong brief is your
   bug: fix the brief and rerun at the same tier and effort.
2. **It did not try hard enough.** It skipped a file, did not run the check,
   or stopped partway (`partial`), and it ran below `high` effort: rerun
   once on the same model with `effort` set to `high` on the Agent call.
3. **It did not know enough.** It had the right inputs, clearly tried, and
   was still wrong (`failed`, a confident claim your check refuted, or a
   `partial` that already ran at `high`): rerun once, one tier up, with the
   failure reason pasted into `inputs`.
4. Several subtasks fail with the same error: that is one shared cause (a
   broken build, a missing dependency, a wrong path in every brief). Fix it
   once in the main session and rerun only those subtasks.
5. A subtask fails at the top of the ladder, or fails twice in total: stop
   launching it. Do it inline when the second failure showed you what was
   missing; when the top tier itself could not do it, report it as open with
   what both attempts found. Never a third launch.

## Provider notes

The Agent tool takes a `model` alias per call (`haiku`, `sonnet`, `opus`,
`fable`) and, since Claude Code 2.1.292, an `effort` level per call; both
beat the agent file's own values. Each alias resolves per provider. On
Amazon Bedrock and Google Cloud's Agent Platform, `sonnet` and `haiku`
resolve to older models than on the Anthropic API unless
`ANTHROPIC_DEFAULT_SONNET_MODEL` and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are set;
the tiers then differ more than the names suggest.
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` makes one model override every per-call
choice; when a user sets it, foreman's routing has no effect and the report
should say so.

`fable` resolves to Fable 5.2 (Claude Code 2.1.321 and later), or to the
model named in `ANTHROPIC_DEFAULT_FABLE_MODEL`. Depending on the plan, Fable
can bill to usage credits, and `claude -p` bills it without asking. When an
organization's `availableModels` allowlist blocks the model a subagent asks
for, Claude Code runs that subagent on a fallback model and names both. A
project on a provider or plan with no Fable at all takes it out of the
ladder in `.claude/foreman/routing.json`, so the checker and the reruns stop
at opus:

```json
{
  "ladder": ["haiku", "sonnet", "opus"],
  "kinds": { "solve": { "model": "opus", "effort": "xhigh" } }
}
```

The specialist's own file still says fable; the `model` and `effort` on the
Agent call beat it, so the override is all a project needs.

A subagent on a different model from the session does not inherit the
session's effort level, which is why every foreman agent file sets `effort`.

## Cost estimates

`routing.json` carries `rates`: Anthropic's list prices per million tokens
for the four routed models, with the date they were read. `plan.py log`
uses them to estimate `cost_usd` for the subtasks the capture hook
recorded, and `plan.py stats` divides by verified results. It is an
estimate: a provider, a region surcharge or a plan can bill differently,
Haiku 5.5 is priced at its rate for prompts up to 100,000 tokens, and a
model with no entry gets no cost. A project adds or replaces a model under
`rates.models` in its own routing file; the key is matched inside the
model id (`sonnet-5-5` matches `claude-sonnet-5-5`).

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
same file can set `ladder`, `max_wave` and `max_top`; the two limits are
whole numbers, and anything else stops `plan.py` with FM016. The `new-agent`
skill writes routes for you (`scaffold.py register`).
