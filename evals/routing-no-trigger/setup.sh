#!/usr/bin/env bash
# Writes the one file the question is about into the empty run workspace. Runs only with --scaffold.
set -euo pipefail
mkdir -p textkit

cat > textkit/__init__.py <<'EOF'
def shout(text: str) -> str:
    return text.upper() + "!"
EOF
