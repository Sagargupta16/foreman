---
type: llm
focus: last_message
---

PASS if the final report lists the changed paths and every one of them is among textkit/__init__.py, mathkit/__init__.py, tests/test_textkit.py, tests/test_mathkit.py and README.md, with no other path reported as edited, created or deleted.
FAIL if the report lists any other changed path (a new module, a config file, a changelog), or does not say which paths changed.
