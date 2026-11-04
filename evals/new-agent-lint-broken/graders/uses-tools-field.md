---
type: regex
pattern: '^tools:[^\n]*\bRead\b'
flags: m
target:
  source: file
  path: .claude/agents/reviewer.md
---

The grant moved to tools and still includes Read, the one tool the author gave the agent.
