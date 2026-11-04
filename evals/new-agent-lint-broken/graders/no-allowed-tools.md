---
type: regex
pattern: '^allowed[-_]?tools[ \t]*:'
flags: im
match: not_contains
target:
  source: file
  path: .claude/agents/reviewer.md
---

No allowed-tools line is left: it is a skill field, and an agent file drops it without a warning.
