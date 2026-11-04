#!/usr/bin/env bash
# Writes a broken agent file into the empty run workspace. Runs only with --scaffold.
# Planted faults: a ':' in name (Claude Code skips the file), allowed-tools instead of tools
# (a skill field, dropped silently) and an effort that is not a level.
set -euo pipefail
mkdir -p .claude/agents

cat > .claude/agents/reviewer.md <<'EOF'
---
name: code:reviewer
description: >-
  Reviews a diff for bugs and risky changes before a commit. Use when the user
  asks for a code review.
allowed-tools: Read
effort: extreme
---

You are a careful code reviewer. Read the changed files and report each
problem with its file and line.
EOF
