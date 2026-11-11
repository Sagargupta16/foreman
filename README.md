# foreman

A Claude Code plugin that splits a task into subtasks, hands each one to a
predefined agent type, and picks Haiku, Sonnet, Opus or Fable for each by the
kind of work. The main session is the foreman: it plans, launches the agents in
dependency waves, reads every result and verifies once at the end. A plan
checker runs before any agent starts, and a scaffolder writes new agents and
whole agent plugins in the same format.

## Install

```text
/plugin marketplace add Sagargupta16/foreman
/plugin install foreman@foreman
```

Or try it from a clone without installing:

```bash
claude --plugin-dir ./foreman
```

## Use

```text
/foreman:dispatch add CSV export to the users API and a download button on the users page
/foreman:new-agent agent migration-auditor
```

Both skills also load on their own when a request matches: "split this up",
"use subagents", "which model should do which part" for `dispatch`; "create
an agent", "make an agent plugin", "why is my agent ignored" for `new-agent`.
A task that is one unit of work is done inline: delegation costs tokens.

## How a task runs

<picture>
  <source media="(prefers-color-scheme: dark) and (min-width: 1012px)" srcset="docs/how-it-works/how-it-works-dark.svg">
  <source media="(prefers-color-scheme: light) and (min-width: 1012px)" srcset="docs/how-it-works/how-it-works-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="docs/how-it-works/how-it-works-dark-mobile.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/how-it-works/how-it-works-light-mobile.svg">
  <img alt="One foreman run of the example feature plan, step by step: request, plan, check, waves, verify, log. The feature template splits the request into 6 subtasks, and plan.py check passes it with 3 waves before any agent starts. Wave 1 runs the scout on Haiku. Wave 2 runs two builders on Sonnet in parallel; build-ui stops short and reruns once on Sonnet at higher effort, while a subtask that is wrong after a real try would go one tier up to Opus. Wave 3 runs docs on Haiku and review and verify on Sonnet. Opus and Fable are not needed in this plan. The foreman checks file ownership, runs the tests once, reads the full diff, and writes each outcome to the run log for tune hints." src="docs/how-it-works/how-it-works-dark-mobile.svg" width="880">
</picture>

The figure plays [examples/feature-plan.json](examples/feature-plan.json)
as `plan.py check` routes it; the build-ui rerun is staged to show the
failure ladder. `python scripts/how_it_works_svg.py` redraws all four files.

1. **Qualify.** One file, a handful of tool calls, or parts that each need the
   previous part's full context: no agents.
2. **Template.** Pick the closest of seven task templates.
3. **Plan.** Fill subtasks: goal, the files each may write (`owns`), what it
   waits for (`after`), the one check that proves it (`verify`).
4. **Route.** Each kind of work has a default agent, model and effort. Any
   change needs a written reason, and the top tier is capped at two subtasks
   a plan.
5. **Check.** `plan.py check` rejects overlapping file ownership inside a
   wave, read-only agents that own files, writers that own nothing, cycles,
   missing checks and silent model changes, then prints the waves.
6. **Run.** Each wave goes out as parallel Agent calls with `model` set per
   subtask; results feed the next wave. A subtask that stopped short reruns
   once at higher effort; one that tried and was wrong reruns once a tier up.
7. **Verify once.** The project's own check runs one time, the foreman reads
   the full diff, and the report says how each result was checked.
8. **Log.** Each subtask's outcome goes to the run log, which `plan.py stats`
   turns into a success table and tune hints.

The dispatch turn itself runs on Sonnet (`model: sonnet` in the skill):
following a written procedure is Sonnet work by foreman's own rule, and the
judgement calls go to the architect and debugger on Opus. In the v0.1 demo
run, an Opus coordinator was 98% of the cost (0.90 of 0.92 USD) while the
Haiku agents did the edits.

A skill's model holds only for the turn it loads in, so where the agents'
reports come back decides which model integrates them:

| session | agents run | integration runs on |
| --- | --- | --- |
| `claude -p`, Agent SDK | in the background unless the call asks to wait; dispatch asks (`run_in_background: false`), so the turn waits | Sonnet |
| interactive terminal, VS Code, desktop app | in the background; reports arrive in later turns | the session's model |

Agents start in the background everywhere. In `claude -p` and the Agent SDK
the coordinator can wait for them, and since 0.3.1 dispatch asks it to. A
0.3.0 run in `claude -p` (Claude Code 2.1.322) did not ask: all three agents
started in the background and the turns after the wave ran on Opus. A 0.3.1
run on the same version kept both of its waves in the foreground and every
turn on Sonnet (four Sonnet subtasks, 0.61 USD in total).

For an interactive run on Sonnet end to end, switch the session with
`/model sonnet` first, or set `CLAUDE_CODE_FORK_SUBAGENT=0` so the turn can
wait for its agents ([sub-agents docs](https://code.claude.com/docs/en/sub-agents.md#run-subagents-in-foreground-or-background),
read 2026-11-11).

## Run log and tune hints

```bash
python skills/dispatch/scripts/plan.py stats          # this project
python skills/dispatch/scripts/plan.py stats --all    # every project
```

After each run the foreman appends one line per subtask to
`~/.claude/foreman/runs.jsonl` (or `$FOREMAN_LOG`): kind, agent, model, the
route's model, status, attempts, final model, whether it was verified,
tokens. `stats` groups them by kind and model. Once a pairing has five or
more subtasks it prints hints: raise a kind's effort when over 30% finished
only after a rerun at higher effort, raise it a tier when under 70% finish on
its route's model or over 30% escalate, lower it when 90% or more finish
verified one tier below. Hints are suggestions; applying one is your call
(`scaffold.py register`, or `.claude/foreman/routing.json`).

## Big plans as Workflows

```bash
python skills/dispatch/scripts/plan.py workflow plan.json --out /tmp/foreman-feature.js
```

A checked plan compiles into a Claude Code Workflow script: waves in order,
each wave's subtasks in parallel through `agent()` with the plan's agent type,
model and effort, a JSON schema for the return block, the failure ladder in
code (a subtask that stopped short reruns once at high effort, a failed one
once a tier up, a blocked one waits for you), and dependents of an
unfinished subtask marked skipped. dispatch offers this
for plans over 20 subtasks or when you ask for a workflow, and runs it only on
your yes.

## Agents

| agent | model | effort | job |
| --- | --- | --- | --- |
| `foreman:scout` | haiku | low | find files, call sites, counts (read-only) |
| `foreman:mechanic` | haiku | low | exact edits and commands the brief spells out |
| `foreman:researcher` | sonnet | medium | primary-source research with cited rows (read-only) |
| `foreman:builder` | sonnet | medium | a specified code change in the files it owns |
| `foreman:writer` | sonnet | medium | docs and changelogs checked against the code |
| `foreman:reviewer` | sonnet | high | findings with file:line and a trigger (read-only) |
| `foreman:verifier` | sonnet | medium | reproduce claims with its own commands (read-only) |
| `foreman:architect` | opus | high | approach, tradeoffs, lanes with disjoint files (read-only) |
| `foreman:debugger` | opus | high | reproduce, root cause, the fix and its files (read-only) |
| `foreman:specialist` | fable | high | one tangled unit end to end: investigate, decide, change, prove |

The rule behind the tiers: Haiku when the brief can spell out the exact
steps, Sonnet when the goal is clear and the agent picks the steps, Opus when
the agent has to work out what the goal means, Fable when one long chain of
hard reasoning has to stay in one head. A subtask moves up a tier for
ambiguity, high stakes or a failed attempt, and down when it repeats a proven
recipe. Every agent ends with the same return block (`id`, `status`,
`changed`, `result`, `verified`, `open`), so integration is mechanical.

### Where Fable fits

Fable is the exception in a plan. It reaches a subtask three ways: a `solve`
subtask (a unit that cannot be split, such as a parser rewrite or a
concurrency fix, goes to the specialist whole), the failure ladder (a
`design` or `debug` that was still wrong on Opus reruns on Fable), or a
route change with a written reason. The plan checker warns past two Fable
subtasks. It is never the coordinator: Anthropic measured Fable as an
orchestrator at 19% more cost than Opus for about the same score, and
advises starting with Opus and keeping Fable for demanding reasoning and
long-horizon work ([cost and intelligence guide](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence),
read 2026-11-10).

## Templates

| template | steps (`*` fans out, `?` skippable) |
| --- | --- |
| feature | map > design? > build* > docs? > review > verify |
| bugfix | map? > diagnose > fix > verify |
| refactor | map > design? > apply* > verify |
| migration | map > pilot > batch* > verify |
| research | lane* > verify |
| review | map > lens* > verify |
| docs | map > write* > verify |

[examples/feature-plan.json](examples/feature-plan.json) is a filled plan;
`python skills/dispatch/scripts/plan.py check examples/feature-plan.json`
prints its three waves.

## Extend it per project

- `.claude/foreman/routing.json` routes a kind to your own agent or adds a
  kind (`scaffold.py register` writes it).
- `.claude/foreman/templates/*.json` adds task templates; a name that matches
  a built-in one replaces it.

## Make your own agents

`/foreman:new-agent` writes an agent file (project, user or plugin scope) or a
plugin skeleton: manifest, marketplace entry, agents, an optional skill that
launches them, README, changelog and license. Its linter reports what Claude
Code drops without a warning. Measured on Claude Code 2.1.312:
`claude plugin validate` passed an agent file with a `:` in its name,
`model: gpt-5`, `effort: extreme`, `color: magenta`, an `allowed-tools` key
and `permissionMode` in a plugin agent. `scaffold.py lint` reports each one.

## Notes

- **Cost.** Anthropic measured multi-agent research runs at about 15 times
  the tokens of a chat. foreman spends them on the parts that need them:
  the coordinator, scouts and mechanics run below Opus, and the report shows
  the model mix.
- **Provider aliases.** The Agent tool takes `haiku`, `sonnet`, `opus` and
  `fable`. On Amazon Bedrock and Google Cloud's Agent Platform, `sonnet` and
  `haiku` resolve to older models than on the Anthropic API unless
  `ANTHROPIC_DEFAULT_SONNET_MODEL` and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are set.
- **Fable.** List price is $8 / $40 per million tokens against $4 / $20 for
  Opus 5.5 (read 2026-11-10). Depending on the plan it bills to usage
  credits, and `claude -p` bills it without asking. A request its safety
  classifiers flag (mostly cybersecurity and biology) reruns on an older
  Opus model, as it does from Opus 5.5, so a larger model does not get past
  a refusal. No Fable on your provider or plan: set
  `"ladder": ["haiku", "sonnet", "opus"]` and route `solve` to opus in
  `.claude/foreman/routing.json`.
- **Effort.** A subagent on a different model from the session does not
  inherit the session's effort, so every agent file sets `effort`. The
  Agent tool also takes `effort` per call (Claude Code 2.1.292 and later),
  which is how a rerun at higher effort is launched.
- **Forced model.** With `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`, one model runs
  every subagent and foreman's routing has no effect.

## Layout

```text
.claude-plugin/        plugin.json and marketplace.json (versions must match)
agents/                the ten agent types
skills/dispatch/       SKILL.md, routing.json, templates/, references/, scripts/plan.py
skills/new-agent/      SKILL.md, assets/ (agent and plugin skeletons), references/, scripts/scaffold.py
examples/              a filled plan the checker passes
tests/                 pytest suite, plus a Node harness that runs compiled Workflows against mocks
evals/                 claude plugin eval cases for dispatch and new-agent
docs/how-it-works/     the animated README figure, dark and light, desktop and phone
scripts/check.py       repo gate: dashes, secrets, links, manifests, agents vs routing, templates
scripts/how_it_works_svg.py  draws docs/how-it-works/ (standard library, deterministic)
```

## Develop

```bash
python scripts/check.py
python -m pytest -q
ruff check .
ruff format --check .
npx -y @sagargupta1610/skillcheck@0.2.5 lint skills
claude plugin validate .
```

The eval suite runs real models and costs tokens, so it runs on request:
`claude plugin eval . --scaffold --allow-tools Bash Write Edit`. Its Bash
graders need Linux, macOS or WSL2.

Python 3.12+ standard library only. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
