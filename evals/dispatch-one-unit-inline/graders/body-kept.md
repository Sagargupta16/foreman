---
type: regex
pattern: 'def sum_all\(xs\):\s*return sum\(xs\)'
target:
  source: file
  path: calc.py
---

The function body is unchanged: a rename must not touch behavior.
