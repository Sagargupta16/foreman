---
type: regex
pattern: '^def multiply\(a\b[^)]*\bb\b'
flags: m
target:
  source: file
  path: mathkit/__init__.py
---

mathkit gained multiply(a, b) at module level, as the user asked.
