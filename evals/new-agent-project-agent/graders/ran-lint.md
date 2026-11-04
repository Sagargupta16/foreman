---
type: tool_used
tool: Bash
input_match: 'scaffold\.py\W{0,6}lint\b'
arm: with-only
---

The finished agent file was checked with scaffold.py lint, the skill's step for fields Claude Code drops without a warning. Needs a Bash grant (WSL2 or Linux/macOS; native Windows has no sandbox backend). with-only: the baseline has no linter.
