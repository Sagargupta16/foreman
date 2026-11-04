#!/usr/bin/env bash
# Builds an empty git repo in the empty run workspace. Runs only with --scaffold.
set -euo pipefail

git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid commit -q --allow-empty -m "init"
