---
type: regex
pattern: '\btotal\b'
match: not_contains
target:
  source: file
  path: calc.py
---

No total is left in calc.py, so the function was renamed and not copied.
