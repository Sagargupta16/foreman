---
description: 'A one-file rename is one unit: dispatch must do it inline and launch no agent.'
tags: [dispatch, routing, scaffold]
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Agent, Write, Edit, Bash]
---

/foreman:dispatch rename the function total to sum_all in calc.py
