---
type: regex
pattern: '(?:^|/|\\)(?:tests|textkit|mathkit)(?:/|\\)(?!.*(?:__pycache__|\.pytest_cache))[^\n]*\.(?:py|md)$'
flags: m
match: not_contains
target: files
---

No agent created a new module or test file under tests/, textkit/ or mathkit/ (caches aside): the new code belongs in the five files that already exist.
