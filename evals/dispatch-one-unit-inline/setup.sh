#!/usr/bin/env bash
# Builds a one-file git repo in the empty run workspace. Runs only with --scaffold.
set -euo pipefail

cat > calc.py <<'EOF'
def total(xs): return sum(xs)
EOF

git init -q -b main
git add calc.py
git -c user.name=eval -c user.email=eval@example.invalid commit -q -m "init"
