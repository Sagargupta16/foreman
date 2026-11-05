---
type: regex
pattern: '\breverse\('
target:
  source: file
  path: tests/test_textkit.py
---

The textkit test file calls reverse, so the new function has a pytest test in the existing file (a call, since the import line has no parenthesis).
