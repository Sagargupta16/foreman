# Agent plugin layout

Source: code.claude.com docs `plugins-reference.md`, `plugins/components.md`
and `workflows.md`, read 2026-11-04 (Claude Code 2.1.312).

## Folder

```text
my-plugin/
  .claude-plugin/
    plugin.json          manifest: name (required), version, description, author, license
    marketplace.json     lets the repo itself be a marketplace (source "./")
  agents/
    my-agent.md          one file per agent; subfolders become name segments
  skills/
    my-plugin/SKILL.md   optional: a skill that launches the agents in order
  hooks/hooks.json       optional: hooks (agent files cannot carry their own)
  .mcp.json              optional: MCP servers (agent files cannot carry their own)
  workflows/*.js         optional: Workflow scripts, run as /my-plugin:<name>
  README.md
  CHANGELOG.md
  LICENSE
```

Only `plugin.json` goes inside `.claude-plugin/`; every other folder sits at
the plugin root. A `CLAUDE.md` at the plugin root is not loaded as context
(`claude plugin validate` warns about it); instructions that must reach
Claude go in a skill.

## Manifest rules

- `name` is kebab-case and namespaces everything: agent `my-agent` in
  `my-plugin` is `my-plugin:my-agent`, skill `review` is `/my-plugin:review`.
- `claude plugin validate` rejects names that pass for Anthropic's own: a
  `claude-` or `anthropic-` prefix, or exactly `claude` or `claude-code`.
- `version` pins users to that version until it changes; bump it in
  `plugin.json` and the marketplace entry together.
- Component paths in the manifest start with `./` and stay inside the
  plugin. Setting `agents` in the manifest replaces the `agents/` scan.
- `${CLAUDE_PLUGIN_ROOT}` in skill and agent bodies resolves to the
  installed plugin folder; `${CLAUDE_PLUGIN_DATA}` is a folder that survives
  updates. Neither is set in the environment of Bash commands.

## Test locally

```bash
claude plugin validate ./my-plugin
claude --plugin-dir ./my-plugin
```

Inside the session, `/reload-plugins` reloads after an edit and
`@agent-my-plugin:my-agent` runs one agent explicitly.
`claude plugin details my-plugin` shows the component list and the token
cost the descriptions add to every session.

`claude plugin eval` runs eval cases (`evals/**/case.yaml` or `prompt.md`
plus `graders/*.md`) against a real model. It costs tokens; run it when the
plugin's behavior matters enough to measure.

## Publish

The plugin's own repo can be its marketplace (`marketplace.json` with
`"source": "./"`). After pushing the repo, users run:

```text
/plugin marketplace add <owner>/<repo>
/plugin install my-plugin@<marketplace name>
```

`claude plugin validate --profile directory` adds the checks Anthropic's
plugin directory runs on a submission (README, license, icon).
