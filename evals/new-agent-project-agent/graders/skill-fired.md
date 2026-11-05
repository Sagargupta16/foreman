---
type: regex
pattern: '\\?"skill\\?"\s*:\s*\\?"(?:foreman:)?new-agent\\?"|skills[/\\]+new-agent[/\\]'
target: trace
arm: with-only
---

The new-agent skill ran. A slash prompt loads the skill without a Skill tool call (seen in a claude -p run), so this looks in the trace for that call or for any call into skills/new-agent/. A plugin-fired indicator: with-only, since the baseline has no skill.
