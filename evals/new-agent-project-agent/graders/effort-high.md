---
type: regex
pattern: '^effort:[ \t]*high[ \t]*$'
flags: m
target:
  source: file
  path: .claude/agents/migration-auditor.md
---

The effort is high, set explicitly because a subagent on another model does not inherit the session's effort.
