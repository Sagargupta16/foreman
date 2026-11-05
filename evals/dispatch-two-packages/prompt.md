---
description: 'Two independent packages: dispatch plans, routes agents by model, edits only the five expected files and reports a model table.'
tags: [dispatch, scaffold]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, Write, Edit, Bash]
---

/foreman:dispatch Add a reverse(text) function to textkit and a multiply(a, b) function to mathkit, each with a pytest test in tests/, and add both to the README functions list. Use subagents for the parts.
