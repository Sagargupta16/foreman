---
type: llm
focus: last_message
---

PASS if the final reply contains a Markdown table with one row per subtask and a column that names the model each subtask ran on (haiku, sonnet or opus).
FAIL if the reply has no table, or the table has no model column, or a row leaves the model blank.
