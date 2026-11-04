---
type: tool_used
tool: Agent
input_match: '^(?![\s\S]*"model"\s*:\s*")'
min: 0
max: 0
arm: with-only
---

No Agent call left out its model: the pattern matches only a call with no "model" value, and the skill forbids launching an agent that way. with-only: the baseline does not route by model.
