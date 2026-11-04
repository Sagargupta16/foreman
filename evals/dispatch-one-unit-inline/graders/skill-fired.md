---
type: regex
pattern: '\\?"skill\\?"\s*:\s*\\?"(?:foreman:)?dispatch\\?"|skills[/\\]+dispatch[/\\]'
target: trace
arm: with-only
---

The dispatch skill ran, so the inline answer is its qualify step and not a run that never loaded it. A slash prompt loads the skill without a Skill tool call (seen in a claude -p run), so this looks in the trace for that call or for any call into skills/dispatch/. A plugin-fired indicator: with-only, since the baseline has no skill.
