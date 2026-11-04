---
type: tool_order
before:
  tool: Bash
  input_match: 'plan\.py\W{0,6}check\b'
after: Agent
arm: with-only
---

The plan check came before the first Agent call, because the skill checks a plan before any agent starts. with-only: the baseline has no plan checker.
