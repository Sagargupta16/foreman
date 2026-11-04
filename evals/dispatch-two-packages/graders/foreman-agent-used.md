---
type: tool_used
tool: Agent
input_match: '"subagent_type"\s*:\s*"foreman:[a-z-]+"'
arm: with-only
---

At least one Agent call used a foreman: subagent_type, so the work went to the plugin's own agent types and not a generic agent. with-only: the baseline has no foreman agents.
