---
name: new-agent
description: >-
  Creates Claude Code subagents and agent plugins in foreman's format. Writes
  one agent file with the model, effort and tools its kind of work needs, or a
  whole plugin (manifest, marketplace entry, agents, an optional skill that
  launches them, README, changelog, license), lints agent files for fields
  Claude Code ignores without a warning, validates the plugin, and registers
  a new agent so foreman's dispatch routes work to it. Use when the user asks
  to create, add or write an agent or subagent, make or publish an agent
  plugin, turn a repeated job into an agent, check or fix an agent file, or
  teach foreman a new kind of work.
argument-hint: "[agent|plugin|register|lint] [name]"
---

# new-agent

An agent is a Markdown file: frontmatter that says when to use it and how it
runs, and a body that becomes its system prompt. Most agent files that
misbehave do so silently: an unknown field is dropped, a `:` in the name
skips the file, a plugin agent's `permissionMode` is ignored, a model other
than the session's runs at the default effort. This skill writes files that
avoid those traps and checks them with a linter that reports each one.

Request: $ARGUMENTS

The script is `${CLAUDE_SKILL_DIR}/scripts/scaffold.py` (Python 3.12+,
standard library). The commands below say `python3`; on Windows use `python`
or `py` when `python3` is not found.

## Read first

- [references/agent-format.md](references/agent-format.md): every
  frontmatter field, where agent files live and which wins, and how to write
  the description and the body
- [references/plugin-layout.md](references/plugin-layout.md): the plugin
  folder, both manifests, testing locally, and publishing

## Pick the mode

| the user wants | mode |
| --- | --- |
| one agent for this project or for every project | `agent` |
| a set of agents to share or publish | `plugin` |
| foreman to send a kind of work to their agent | `register` |
| to know why an agent file does not load or behave | `lint` |

## Procedure

1. **Pin the job** before writing anything. One sentence each: what the
   agent does, what it gets in its brief, what it returns, whether it edits
   files. A job that is really two jobs is two agents. Then pick the
   closest kind from `python3 "${CLAUDE_SKILL_DIR}/../dispatch/scripts/plan.py" routes`;
   the kind sets the default model, effort and tools.
2. **Name it** in kebab-case after the job, not the technique
   (`migration-auditor`, not `helper` or `sql-agent-v2`). No `:` in the
   name. Check it is not already taken: list `.claude/agents/`,
   `~/.claude/agents/` and the agents the session already shows.
3. **Write it.**

   One agent, with `--dest` set to `.claude/agents` (this project, shared
   through git), `~/.claude/agents` (every project, only this user), or a
   plugin's `agents` folder:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/scaffold.py" agent migration-auditor --kind review --dest .claude/agents --description "<what it does and when to use it>"
```

   A plugin, one `--agent NAME:KIND` per agent and `--skill` when the agents
   should run as a sequence the user can call by name:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/scaffold.py" plugin db-crew --dest ../db-crew --agent migration-writer:implement --agent migration-auditor:review --skill
```

4. **Fill every `<<fill` marker.** Follow
   [references/agent-format.md](references/agent-format.md): the description
   says what the agent does, who calls it, and what it never does; the body
   gives the role, the procedure, the return block and the boundaries. Keep
   the return block: foreman's dispatch integrates on it.
5. **Lint and validate** until both are clean:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/scaffold.py" lint .claude/agents
claude plugin validate <plugin folder>
```

   `claude plugin validate` checks manifests and paths; the lint checks the
   agent fields it lets through (a bad model, effort or color, a `:` in the
   name, misspelled fields, plugin-ignored fields).
6. **Register** the agent when foreman should route to it. An existing kind
   is overridden for this project; a new kind needs `--what` and `--writes`
   or `--read-only`:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/scaffold.py" register migration-auditor --kind review --model opus
```

   This writes `.claude/foreman/routing.json`. Commit it to share the route.
7. **Prove it loads and works.** Claude Code watches `.claude/agents/` and
   `~/.claude/agents/` and picks up a new or edited file within seconds,
   except when that `agents` folder did not exist when the session started
   (then restart). A plugin agent needs `/reload-plugins`, or a session
   started with `claude --plugin-dir <folder>`. Run the agent once through
   the Agent tool on a small real task and check that the reply ends in the
   return block.

## Output

```
mode: agent | wrote .claude/agents/migration-auditor.md (kind review: sonnet, high)
lint: 0 errors, 0 warnings | validate: passed
route: review -> migration-auditor (opus) in .claude/foreman/routing.json
proof: one Agent run as migration-auditor returned the block (status done)
```

## Must not

- Overwrite an existing agent or plugin file without the user's yes
  (`--force`).
- Give a read-only job Edit or Write, or leave `tools` open on an agent that
  only reads.
- Put a secret, token or personal path in an agent file or manifest.
- Publish, push, or add a marketplace for the user; hand them the commands
  in [references/plugin-layout.md](references/plugin-layout.md).
- Leave a `<<fill` marker or a lint error in a file you report as done.
