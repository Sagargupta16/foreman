---
type: regex
pattern: '^tools:[ \t]*Read, Grep, Glob, Bash[ \t]*$'
flags: m
target:
  source: file
  path: .claude/agents/migration-auditor.md
---

The tools are the read profile (Read, Grep, Glob, Bash) with no Edit or Write, because the user asked for a read-only agent.
