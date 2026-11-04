---
description: 'Create a read-only project agent: the file lands in .claude/agents with the review kind defaults, filled in and linted.'
tags: [new-agent, scaffold]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

/foreman:new-agent create a read-only project agent named migration-auditor that reviews SQL migration files for unsafe operations
