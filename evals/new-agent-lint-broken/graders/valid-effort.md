---
type: regex
pattern: '^effort:[ \t]*(?:low|medium|high|xhigh|max)[ \t]*$'
flags: m
target:
  source: file
  path: .claude/agents/reviewer.md
---

The effort is one of the five levels Claude Code accepts, and extreme is gone.
