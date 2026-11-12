# Security Policy

## What this plugin is

foreman ships Markdown skills, ten agent definitions, JSON routing and
templates, and Python scripts (standard library only) that check plans,
write agent files and record agent runs. It has no server and no network
calls of its own.
One hook ships and is off by default: with the `capture_runs` option on, it
appends the token counts and timings of finished foreman agents to a local
file, reading nothing but the agent's own transcript.

Realistic concerns:

1. **Skill and agent content** instructs Claude to run commands and launch
   agents. A bad or injected body could steer agents toward harmful actions.
2. **Agents edit files.** builder, mechanic, writer and specialist have Edit
   and Write; their briefs limit them to their `owns` paths, and the foreman
   checks `git status` after each wave, but the boundary is an instruction,
   not a sandbox.
3. **Project extensions** (`.claude/foreman/routing.json`) can route work to
   any agent name, including one from another plugin.
4. **Manifests** could declare unexpected components if the repo were
   compromised.

## Reporting a vulnerability

Do not open a public Issue or PR. Report it privately through
[GitHub private vulnerability reporting](https://github.com/Sagargupta16/foreman/security/advisories/new),
or email **sg85207@gmail.com** with the subject `[foreman security]`: what
you found, how to reproduce it, the impact, and any suggested fix. Expect a
first response within 7 days.

## In scope

- A skill or agent body that reliably steers Claude past the user's
  permission checks or outside the `owns` boundary.
- A plan the checker passes that lets two agents write the same file in one
  wave.
- `scaffold.py` writing outside the destination it was given.
- The capture hook storing prompt or result text, or writing outside its
  log file.
- Secrets committed to the repo.
