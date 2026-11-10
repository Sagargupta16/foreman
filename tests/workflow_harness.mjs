// Runs a script from `plan.py workflow` against mock Workflow globals, offline.
// usage: node workflow_harness.mjs <script.js> [fails-once] [blocks] [fails-always] [throws] [partial-once]
// each argument after the script is a subtask id ('' for none).
// prints JSON: every agent() call, the log lines, each subtask's final status, attempts and model,
// and its final effort.
import { readFileSync } from 'node:fs'

const [file, failOnce, blocks, failAlways, throws, partialOnce] = process.argv.slice(2)
const body = readFileSync(file, 'utf8').replace('export const meta', 'const meta')
const AsyncFunction = (async () => {}).constructor

const calls = []
const logs = []
const seen = {}

async function agent(prompt, opts) {
  const id = prompt.split('\n')[0].replace('id:', '').trim()
  seen[id] = (seen[id] || 0) + 1
  calls.push({
    id,
    label: opts.label,
    agentType: opts.agentType,
    model: opts.model,
    effort: opts.effort,
    phase: opts.phase,
    hasSchema: Boolean(opts.schema),
    retry: prompt.includes('\nretry:'),
  })
  if (id === throws) throw new Error('mock API error')
  let status = 'done'
  if (id === failOnce && seen[id] === 1) status = 'failed'
  if (id === partialOnce && seen[id] === 1) status = 'partial'
  if (id === failAlways) status = 'failed'
  if (id === blocks) status = 'blocked'
  return { id, status, changed: [], result: `mock ${status}`, verified: 'mock', open: 'none' }
}

async function parallel(thunks) {
  return Promise.all(thunks.map(t => t().catch(() => null)))
}

const run = new AsyncFunction('agent', 'parallel', 'phase', 'log', body)
const result = await run(agent, parallel, () => {}, m => logs.push(m))
const statuses = {}
const efforts = {}
for (const [id, r] of Object.entries(result)) {
  statuses[id] = { status: r.status, attempts: r.attempts, final_model: r.final_model }
  efforts[id] = r.final_effort
}
console.log(JSON.stringify({ calls, logs, statuses, efforts }))
