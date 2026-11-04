# Agent file format

Source: code.claude.com docs `sub-agents.md` and `plugins/components.md`,
read 2026-11-04 (Claude Code 2.1.312). Re-check the docs when a field here
does not behave as described; the format still changes between releases.

## Where agent files live

| location | scope | priority when names collide |
| --- | --- | --- |
| managed settings | the organization | 1 (wins) |
| `claude --agents '<json>'` | this session only | 2 |
| `.claude/agents/` | this project (commit it to share) | 3 |
| `~/.claude/agents/` | every project of this user | 4 |
| a plugin's `agents/` | wherever the plugin is enabled | 5 |

Project and user folders are scanned recursively, and only the `name` field
gives the identity; when two files under one folder share a name, only one
loads, chosen by filesystem read order. Both folders are watched: a new or
edited file is picked up within seconds, unless the folder did not exist
when the session started (then restart). Plugin agents are named `<plugin>:<name>`, and a subfolder adds a
segment (`agents/review/security.md` in `my-plugin` is
`my-plugin:review:security`).

## Frontmatter fields

Names are camelCase and exact. An unknown field is dropped without a
warning, which is why the lint reports one (FA004).

| field | values | notes |
| --- | --- | --- |
| `name` | kebab-case, no `:`, at most 256 chars | required outside plugins; a bad name skips the file |
| `description` | text | required; when Claude should delegate to this agent |
| `tools` | comma list or YAML list | allowlist; omitted means every tool, including `Agent` |
| `disallowedTools` | same | removed first |
| `model` | `haiku`, `sonnet`, `opus`, `fable`, `inherit`, or a model id | omitted: the session's model |
| `effort` | `low`, `medium`, `high`, `xhigh`, `max` | set it whenever `model` differs from the session's |
| `maxTurns` | integer | stops a runaway agent; output is marked partial |
| `skills` | skill names | preloaded into the agent's context |
| `memory` | `user`, `project`, `local` | a persistent memory folder for this agent |
| `background` | boolean | always run in the background |
| `isolation` | `worktree` | run in a temporary git worktree |
| `omitClaudeMd` | boolean | skip CLAUDE.md files at startup |
| `autoCompactWindow` | 100000 to 1000000 | plain integer; `200k` reads as 200 |
| `color` | `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan` | display only |
| `permissionMode`, `hooks`, `mcpServers`, `initialPrompt` | | ignored in plugin agents; plugins ship hooks in `hooks/hooks.json` and servers in `.mcp.json` |

The model a subagent runs on is chosen in this order: the `model` the caller
passes on the Agent call (aliases only), then the file's `model`, then
`CLAUDE_CODE_SUBAGENT_MODEL`, then the session's model. So a file's `model`
is a default that foreman's dispatch can override per subtask.

## Writing the description

Every agent description loads in every session, and Claude reads it to
decide when to delegate. Keep it under about 1000 characters and make it
single out this agent:

1. What it does, as a role and an action ("Read-only reviewer for one diff").
2. Who calls it, and for what ("Called by foreman dispatch for review
   subtasks; also use it directly for ...").
3. What it never does ("Never edits, commits or comments on a PR").

Write it as a `>-` folded block. A plain value with `: ` inside breaks the
YAML, and the whole frontmatter is then ignored.

## Writing the body

The body is the agent's whole system prompt; it does not see the
conversation that launched it. Write in the second person.

- **Role**, two sentences: what you do and why the result matters to whoever
  acts on it next.
- **Brief you get**: the fields it should expect (`id`, `task`, `goal`,
  `owns`, `reads`, `inputs`, `verify`).
- **Procedure**: numbered steps; start with what to read, end with how to
  check the result.
- **Return**: the fixed block (`id`, `status`, `changed`, `result`,
  `verified`, `open`). Keep it even outside foreman: a caller that knows the
  shape can check the result without rereading the transcript.
- **Must not**: the two or three boundaries that matter for this job.

Keep it under about 10,000 characters. Give the agent the fewest tools that
do the job: read-only roles get `Read, Grep, Glob, Bash`, editing roles add
`Edit, Write`, research adds `WebFetch, WebSearch`. Leaving `Agent` out of
`tools` stops the agent from launching agents of its own.
