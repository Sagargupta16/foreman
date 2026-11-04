#!/usr/bin/env bash
# Builds a tiny two-package git repo in the empty run workspace. Runs only with --scaffold.
set -euo pipefail
mkdir -p textkit mathkit tests

cat > textkit/__init__.py <<'EOF'
def shout(text: str) -> str:
    return text.upper() + "!"
EOF

cat > mathkit/__init__.py <<'EOF'
def add(a: int, b: int) -> int:
    return a + b
EOF

cat > tests/test_textkit.py <<'EOF'
from textkit import shout


def test_shout():
    assert shout("hi") == "HI!"
EOF

cat > tests/test_mathkit.py <<'EOF'
from mathkit import add


def test_add():
    assert add(2, 3) == 5
EOF

cat > README.md <<'EOF'
# demo

Two tiny packages: textkit and mathkit. Run the tests with `python -m pytest`.

## Functions

- `textkit.shout(text)`: upper-case and add "!"
- `mathkit.add(a, b)`: sum
EOF

cat > .gitignore <<'EOF'
__pycache__/
.pytest_cache/
EOF

git init -q -b main
git add .
git -c user.name=eval -c user.email=eval@example.invalid commit -q -m "init"
