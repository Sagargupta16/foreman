# Briefs and returns

An agent starts with nothing but its own system prompt and your brief. Vague
briefs are the main way multi-agent work fails: agents duplicate each other,
leave gaps, or solve a different problem. Every brief carries an objective,
an output format, the boundaries and the check.

## Brief skeleton

Same fields for every agent, in this order:

```
id:      build-api
task:    <the user's request, verbatim>
goal:    <what this subtask must produce, in this task's terms>
owns:    <paths it may write, or "none (read-only)">
reads:   <paths and inputs to start from>
inputs:  <results from earlier subtasks: pasted text, or file paths>
verify:  <the one check that proves it worked>
limits:  no commit or push; no edits outside owns; no new dependencies
         unless the goal names one; no secret values in any file; no full
         test, lint or build run unless verify names it; no test or check
         deleted, skipped or loosened to pass verify unless the goal names it
return:  the return block from your instructions
```

## Shape it for the model

Describe the task, never the model tier ("you are the fast one" changes
nothing useful and costs words).

| tier | what to put in `goal` and `inputs` |
| --- | --- |
| fable | the same as opus, plus everything a failed earlier attempt found and the reason the unit was not split; no steps at all |
| opus | the outcome in the user's words, why it matters, what a good result looks like, the constraints; leave the route to the agent |
| sonnet | the goal plus the steps that are already decided, the interfaces to keep, the files that matter, the edge cases you know |
| haiku | exact paths, exact old and new text or the exact commands, the expected output; nothing to decide |

## Inputs between waves

- Paste a short result (under about 40 lines) into `inputs`.
- A long one (a full findings table, a log) goes to a file the next agent
  can read, and `inputs` names the path. Prefer the repo's ignored scratch
  folder when it has one; otherwise the system temp folder.
- Pass the parts the next subtask needs, not the whole return block.

## Return block

Every foreman agent ends with the same block, so integration is mechanical:

```
id:       <id from the brief>
status:   done | partial | blocked | failed
changed:  <paths, or none>
result:   <the answer: table, plan, summary of the change>
verified: <command and decisive output, or "not verified: <why>">
open:     <what is left for the foreman, or none>
```

A return without this block, or one that ends in "next I would...", has
stalled. Send that agent a message asking for the block; do not count it as
done.

## Custom agents

A project or plugin agent that is not a foreman agent may not know the
return block. Add the block to the end of its brief.
