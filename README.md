# foreman

A Claude Code plugin that splits a task into subtasks, hands each one to a
predefined agent type, and picks Haiku, Sonnet or Opus for each by the kind
of work. The main session is the foreman: it plans, launches the agents in
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

1. **Qualify.** One file, a handful of tool calls, or parts that each need the
   previous part's full context: no agents.
2. **Template.** Pick the closest of seven task templates.
3. **Plan.** Fill subtasks: goal, the files each may write (`owns`), what it
   waits for (`after`), the one check that proves it (`verify`).
4. **Route.** Each kind of work has a default agent, model and effort. Any
   change needs a written reason.
5. **Check.** `plan.py check` rejects overlapping file ownership inside a
   wave, read-only agents that own files, writers that own nothing, cycles,
   missing checks and silent model changes, then prints the waves.
6. **Run.** Each wave goes out as parallel Agent calls with `model` set per
   subtask; results feed the next wave.
7. **Verify once.** The project's own check runs one time, the foreman reads
   the full diff, and the report says how each result was checked.

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

The rule behind the tiers: Haiku when the brief can spell out the exact
steps, Sonnet when the goal is clear and the agent picks the steps, Opus when
the agent has to work out what the goal means. A subtask moves up a tier for
ambiguity, high stakes or a failed attempt, and down when it repeats a proven
recipe. Every agent ends with the same return block (`id`, `status`,
`changed`, `result`, `verified`, `open`), so integration is mechanical.

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
  scouts and mechanics run on Haiku, and the report shows the model mix.
- **Provider aliases.** The Agent tool takes `haiku`, `sonnet`, `opus` and
  `fable`. On Amazon Bedrock and Google Cloud's Agent Platform, `sonnet` and
  `haiku` resolve to older models than on the Anthropic API unless
  `ANTHROPIC_DEFAULT_SONNET_MODEL` and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are set.
- **Effort.** A subagent on a different model from the session does not
  inherit the session's effort, so every agent file sets `effort`.
- **Forced model.** With `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`, one model runs
  every subagent and foreman's routing has no effect.

## Layout

```text
.claude-plugin/        plugin.json and marketplace.json (versions must match)
agents/                the nine agent types
skills/dispatch/       SKILL.md, routing.json, templates/, references/, scripts/plan.py
skills/new-agent/      SKILL.md, assets/ (agent and plugin skeletons), references/, scripts/scaffold.py
examples/              a filled plan the checker passes
scripts/check.py       repo gate: dashes, secrets, links, manifests, agents vs routing, templates
```

## Develop

```bash
python scripts/check.py
ruff check .
ruff format --check .
npx -y @sagargupta1610/skillcheck@0.2.5 lint skills
claude plugin validate .
```

Python 3.12+ standard library only. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
