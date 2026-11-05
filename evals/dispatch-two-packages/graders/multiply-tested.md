---
type: regex
pattern: '\bmultiply\('
target:
  source: file
  path: tests/test_mathkit.py
---

The mathkit test file calls multiply, so the new function has a pytest test in the existing file (a call, since the import line has no parenthesis).
