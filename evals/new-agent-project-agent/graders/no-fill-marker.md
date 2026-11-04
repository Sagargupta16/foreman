---
type: regex
pattern: '<<fill'
match: not_contains
target:
  source: file
  path: .claude/agents/migration-auditor.md
---

Every placeholder the scaffolder writes was filled in, since a file with a fill marker is not finished.
