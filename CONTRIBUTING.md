# Contributing to foreman

foreman is small on purpose: two skills, nine agents, seven templates, two
scripts. Changes that make plans safer to run or agents easier to route are
the most welcome.

## Setup

```bash
git clone https://github.com/Sagargupta16/foreman
cd foreman
pip install -r requirements-dev.txt
```

The scripts use the Python 3.12+ standard library only.

## Before you open a PR

```bash
python scripts/check.py
python skills/dispatch/scripts/plan.py check examples/feature-plan.json
ruff check .
ruff format --check .
npx -y @sagargupta1610/skillcheck@0.2.5 lint skills
claude plugin validate .
```

CI runs all but the last.

## Adding an agent

1. Add a kind to `skills/dispatch/routing.json` (agent, model, effort,
   profile, writes, what).
2. Write `agents/<name>.md` with `scaffold.py agent <name> --kind <kind>
   --dest agents`, then fill the body: role, brief, procedure, the standard
   return block, must not.
3. Add the agent to the README table and, if a template should use it, to
   that template.
4. `scripts/check.py` checks that the file's model, effort and tools match
   the route.

## Adding a template

Add `skills/dispatch/templates/<name>.json` with `name`, `summary`, `match`
and `steps` (each with `id`, `kind`, `goal`, `verify`, `after`, and
optionally `fan_out` or `skip_when`). Add it to the README table.

## Adding a check rule

Give it the next `FM0xx` (plan.py) or `FA0xx` (scaffold.py lint) id, a
one-line message that says how to fix it, and list it in the script's
docstring and in the reference page that describes the rules.

## Style

- No en or em dash characters anywhere (use `-` or `--`).
- Write "the user", not a person's name. No absolute home paths.
- Every external claim about Claude Code behavior links its docs page or
  says which version it was measured on.
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
  `chore:`.
- CHANGELOG entries go under a concrete version (`## [0.2.0] - YYYY-MM-DD`).
  Releases bump `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json` together.
