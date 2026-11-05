---
type: regex
pattern: '^name:[ \t]*["'']?[a-z0-9]+(?:-[a-z0-9]+)*["'']?[ \t]*$'
flags: m
target:
  source: file
  path: .claude/agents/reviewer.md
---

The name is plain kebab-case with no colon, the cause of the file being skipped.
