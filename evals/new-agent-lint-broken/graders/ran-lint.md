---
type: tool_used
tool: Bash
input_match: 'scaffold\.py\W{0,6}lint\b'
arm: with-only
---

The skill's linter was run on the agent file, the check that names each of the three planted faults. Needs a Bash grant (WSL2 or Linux/macOS; native Windows has no sandbox backend). with-only: the baseline has no linter.
