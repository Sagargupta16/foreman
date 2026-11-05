---
type: tool_used
tool: Agent
input_match: '"model"\s*:\s*"(?:haiku|sonnet|opus|fable)"'
arm: with-only
---

At least one Agent call set a model, the per-subtask routing the skill exists for (the call's model beats the agent file's). with-only: the baseline does not route by model.
