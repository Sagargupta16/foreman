# Decompose: splitting a task into a plan

## Find the unit

Split along the unit the work naturally repeats over, not along steps of one
person's process: a page, a route group, a package, a doc surface, a
question, a batch of files. One subtask per unit, each with its own files.

Good splits have three properties:

- **Disjoint writes.** No path is owned by two subtasks in the same wave.
- **Small briefs.** An agent can start from the brief and a few files, not
  from the whole conversation.
- **Checkable results.** Each subtask returns something you can verify in
  under a minute: a test, a count, a citation, a rendered page.

A unit that fails the second or third test stays in the main session.

How many lanes: two to four for a comparison or a change across a few
packages, more than ten only for a wide sweep of independent units. In
Anthropic's measurements delegation paid off in two cases, routine work with
a long cost tail and work larger than one context window; a dependent chain
that fits in one context did better undivided.

## The unit that cannot be split

Some work is one chain: each step needs everything the last one learned, and
lanes that each see a slice would make choices that do not fit together (a
parser rewrite, a concurrency fix, an algorithm). Do not cut it into build
lanes. When it is routine, do it inline. When it is hard, make it one
`solve` subtask: the specialist gets the outcome, owns the files, and does
the investigation, the change and the proof in one context. A plan can hold
a `solve` subtask beside ordinary lanes, as long as their `owns` are
disjoint.

## Ownership

- `owns` lists the paths a subtask may write: files, folders or globs
  (`src/api/**`). Read-only kinds (locate, research, review, verify, design,
  debug) own nothing. The writing kinds are mechanical, implement, document
  and solve.
- A file several subtasks need to change (a shared type, a barrel export, a
  config, a lockfile) gets its own subtask in an earlier wave, or one subtask
  owns it while the rest read it.
- A subtask that deletes or renames a shared name runs after every subtask
  that still uses it. Disjoint files do not protect a shared name.
- Lockfiles and manifests (`package.json`, `pyproject.toml`) belong to one
  subtask or to the main session.
- When two subtasks truly must edit the same file in parallel, launch them
  with `isolation: "worktree"` and merge in the main session; this is the
  exception.

## Waves

`after` lists what a subtask waits for. The check groups subtasks into waves:
every subtask in a wave has all its `after` done, and a wave's subtasks run
in parallel. An `after` entry matches an id exactly, or every id that starts
with it plus `-`, so `"after": ["build"]` waits for `build-api` and
`build-ui`.

Keep waves at or under `max_wave` (10 by default). A fan-out of 30 files is
three waves of 10 batches, or 10 batches of 3 files each.

## Plan fields

```json
{
  "task": "the user's request, verbatim",
  "template": "feature",
  "subtasks": [
    {
      "id": "build-api",
      "kind": "implement",
      "agent": "foreman:builder",
      "model": "sonnet",
      "effort": "medium",
      "goal": "Add GET /users/:id/export returning CSV",
      "owns": ["src/api/users.ts", "tests/api/users.test.ts"],
      "reads": ["src/api/index.ts", "src/db/users.ts"],
      "after": ["design"],
      "verify": "npm test -- tests/api/users.test.ts passes",
      "why": "only when agent or model differs from the kind's route"
    }
  ]
}
```

| field | required | notes |
| --- | --- | --- |
| `id` | yes | short, unique; fan-out ids share a prefix (`build-api`) |
| `kind` | yes | a kind from `plan.py routes` |
| `goal` | yes | what this subtask produces, in this task's terms |
| `verify` | yes | the one check that proves it; for read-only kinds, how you will check the answer |
| `owns` | writing kinds | paths it may write; a list, or one string for one path |
| `reads` | no | where it starts reading |
| `after` | no | ids or id prefixes it waits for |
| `agent`, `model`, `effort` | no | default from the route; a changed agent or model needs `why`; a changed `effort` goes on the Agent call |
| `writes` | no | override the kind's read-only flag (rare) |

## Checks the script runs

Errors fail the plan: missing fields (FM002), unknown kind (FM003), a model
or effort the Agent tool does not take (FM004), a changed agent or model
without `why` (FM005), unknown `after` or a cycle (FM006), a read-only
subtask that owns paths (FM007), a writing subtask that owns nothing
(FM008), two subtasks in one wave owning the same path (FM009), no verify
(FM010). Warnings: a wave wider than `max_wave` (FM011), a one-subtask plan
below the top tier (FM012), an agent no route names (FM013), a template hint
left in (FM014), more than `max_top` subtasks on the top tier (FM015), two
globs that may overlap (FM009).

Without Python, check the same rules by hand before launching: unique ids,
disjoint `owns` per wave, every writer owns something, every subtask has a
verify, no cycles.
