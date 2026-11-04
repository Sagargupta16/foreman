---
type: regex
pattern: '^(?=[\s\S]*^[-*][ \t].*\breverse\b)(?=[\s\S]*^[-*][ \t].*\bmultiply\b)'
flags: m
target:
  source: file
  path: README.md
---

The README functions list has a bullet for each new function, next to the existing shout and add bullets.
