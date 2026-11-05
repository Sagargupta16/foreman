---
type: regex
pattern: '^def reverse\(text\b'
flags: m
target:
  source: file
  path: textkit/__init__.py
---

textkit gained reverse(text) at module level, as the user asked.
