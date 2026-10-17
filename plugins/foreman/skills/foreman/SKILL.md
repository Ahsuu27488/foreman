---
name: foreman
description: Lets the lead agent delegate well-scoped, verifiable coding and research tasks to other CLI coding agents the user already has (Google Antigravity, OpenAI Codex, Cursor, GitHub Copilot, Gemini CLI, Qwen Code, Factory Droid, Amp, OpenCode, Aider and more), picking a light, balanced or frontier model to fit the task, then reviewing, verifying and correcting the work before accepting it, so the lead's own usage limits last longer. Use when a task is clearly specified and checkable but big enough that doing it inline would burn many tokens, such as tests, boilerplate, mechanical refactors, renames across files, scaffolding, docs, codebase mapping, or log and file analysis. Also use when the user says delegate, offload, hand this off, use a worker or sub-agent, use Gemini or Codex, save tokens, or save my limit. Skip it for tiny edits, design decisions, subtle debugging, security-sensitive work, or anything involving secrets.
license: MIT
compatibility: Python 3.10+ and git. Needs at least one worker CLI installed and signed in. Written for any agent that supports Agent Skills (Claude Code, Codex, Gemini CLI, Antigravity and others).
metadata:
  version: 0.4.0
---

# Foreman

You are the lead engineer. Worker agents do the typing; you own the result. Anything a worker
produces becomes your work the moment you accept it, so the user never receives something you have
not reviewed and would not have signed off on had you written it yourself. The bar is the quality
you would deliver alone, not "good enough for a cheaper model".

Spend your tokens on judgment (deciding, briefing, reviewing) and the workers' tokens on volume
(reading, writing, iterating). If you end up redoing the work, the delegation was a loss.

The script is `scripts/delegate.py` inside this skill's folder; in Claude Code that path is
`${CLAUDE_SKILL_DIR}/scripts/delegate.py`. Commands below write `delegate.py` for that full path,
since you run them from the user's project, not from the skill folder. Use `python3`, or `python`
on Windows.

Worker runs take minutes (often 5 to 10). If your shell tool times out sooner, run `delegate.py run`
in the background or raise the tool's timeout, and keep working while it runs.

## First use on a machine

```bash
python3 delegate.py doctor     # which worker CLIs are installed
python3 delegate.py init       # write routes for the light, balanced and frontier tiers
```

`init` reads each CLI's model list where it has one, sorts models into tiers, and skips the CLI you
yourself run on (delegating to it spends the same plan). Show the user the resulting routes and
confirm the tier picks before relying on them; their preferences win. Details:
[references/backends.md](references/backends.md).

## When to delegate

Delegate when **all** of these hold:

- The task can be stated completely in a brief, without this conversation's history.
- Success is checkable: tests, a build, a linter, a grep, or a spec you can compare against.
- Doing it yourself would take many tool calls or a lot of reading or writing (several files, or
  roughly 15+ minutes of work).

Keep it yourself when:

- It is a few-line edit: briefing and reviewing cost more than doing it.
- It needs judgment you cannot hand over: architecture, API design, tradeoffs the user must weigh.
- It is subtle debugging where the hard part is understanding, not typing.
- It touches secrets, credentials, authentication, payment processing or production data.
- The user wants you to do it personally, or the code must not leave the machine for another
  vendor's servers.

When unsure, delegate the reading and keep the deciding: a `--readonly` worker can map a codebase
or summarise logs while you make the call. When the user explicitly asks you to delegate, do so
even for smaller tasks, unless it would put secrets or private data at risk; then say why not.

## Pick the tier

Almost every vendor ships a light, a balanced and a frontier model (for example Haiku, Sonnet and
Opus, or Flash-Lite, Flash and Pro). Match the tier to how hard the task is to get right, not to
how big it is:

| Tier | Use for | Typical models |
|---|---|---|
| `light` | Mechanical work with one obvious answer: renames, formatting, docstrings, simple boilerplate from a pattern, file search and summaries, data extraction | Haiku, Flash-Lite, mini, nano, low-effort settings |
| `balanced` | Normal engineering from a clear spec: a feature or function, unit tests, a bug fix with a known cause, a refactor inside one module, docs pages | Sonnet, Flash, standard GPT, Qwen Plus, medium or high effort |
| `frontier` | Hard reasoning: changes spanning many modules, tricky algorithms, concurrency, performance work, migrations, and every escalation | Opus, Pro, Max, top GPT tier, high thinking budgets |

Start one tier lower when you are unsure; escalation is cheap and your review catches the
difference. If a worker model is stronger than you, lean on objective checks (tests, builds,
specs) rather than your own judgment of its reasoning. Vendor families and naming quirks:
[references/model-tiers.md](references/model-tiers.md).

### Effort

Many CLIs also take a reasoning effort (`low`, `medium`, `high`, and on some `xhigh`, `max`).
Each tier runs at a default effort (light `low`, balanced `medium`, frontier `high`; set in the
user config as `tier_effort`). Change it only when the task calls for it:

- `--effort high` on a balanced worker is the cheap first escalation, before moving up a tier.
  Use it when the task is well understood but has many edge cases.
- `--effort low` on a balanced worker suits long but simple edits where light models stumble.
- More effort does not fix a vague brief; rewrite the brief first.

The script maps the level to each CLI's own flag and picks the nearest level a CLI supports. The
tier default never overrides a model name that already includes an effort (such as `flash-high`);
an explicit `--effort` or `@effort` does. The result's `effort` field shows what was sent.

## Workflow

Copy this checklist and track it:

```
Delegation:
- [ ] 1. Decide: delegate or keep it
- [ ] 2. Pick the tier
- [ ] 3. Write the brief
- [ ] 4. Dispatch
- [ ] 5. Review: re-run the gates, read the whole diff
- [ ] 6. Accept, send back with fixes, or escalate
- [ ] 7. Land it and report to the user
```

### 3. Write the brief

The worker sees only the brief and the files in its folder. Write it for a capable contractor on
day one: goal, context, exact scope (files it may and may not touch), acceptance criteria, known
edge cases, and how to verify. Run the gate command (tests, build) once yourself before putting it
in the brief, so you never hand over a command that does not work. Template and examples:
[references/writing-briefs.md](references/writing-briefs.md). Save it to a file, one task per brief.
Never put secrets in a brief.

### 4. Dispatch

```bash
python3 delegate.py run --tier balanced --brief <brief.md> --cwd <project-dir> --worktree
```

- `--tier light|balanced|frontier` picks the route. `--worker BACKEND:MODEL[@EFFORT]` picks one
  worker explicitly, for example `agy:gemini-3.8-flash-high` or `codex:<model>@high`.
- `--effort LEVEL` overrides the effort for this run.
- `--worktree` (git projects) runs the worker in a new worktree on branch `foreman/<id>`, so the
  user's checkout stays untouched until you merge. Use it for every edit task in a repo.
- `--readonly` for research and second opinions. CLIs that cannot guarantee read-only get a
  throwaway worktree automatically.
- `--continue <session_id> --cwd <previous workdir>` sends a follow-up to the same worker session.

If a worker is missing or out of quota, the script moves to the next one on the route and lists
every attempt. It prints one JSON result: `status`, `files` (created, modified, deleted, measured
on disk), `worker_report`, `workdir`, `worktree_branch`, `session_id`, `usage`. Runs take minutes,
so run long ones in the background and keep working.

### 5. Review

Do not trust the worker's report; verify. Full checklist:
[references/reviewing-work.md](references/reviewing-work.md). The essentials:

1. Run the project's real gates yourself: tests, type check, build, lint. Most workers run
   sandboxed without shell access, so assume nothing has been executed.
2. Read every changed file against the brief: missing pieces, scope creep, invented APIs, deleted
   or weakened tests, silent behaviour changes, values hard-coded to fit the examples.
3. Ask: would I have written this? If not, name exactly what is wrong.

### 6. Accept, send back, or escalate

- **Accept** when it meets the bar you hold your own work to. Small fixes (a name, a missing guard)
  are cheaper to make yourself than to brief.
- **Send back** with a delta brief via `--continue`: each defect with file, line, what is wrong and
  what correct looks like. Review again afterwards.
- **Escalate** after two failed rounds on the same task: raise the effort or move up one tier,
  and after a failed frontier round, do it yourself. Past two rounds, more briefing usually costs
  more than it saves.

### 7. Land and report

The worker never commits, and you commit only if the user asked you to or that is clearly how
they work. For a worktree run:

```bash
python3 delegate.py land --workdir <workdir>                       # uncommitted changes in the user's checkout
python3 delegate.py land --workdir <workdir> --commit -m "<msg>"   # only when committing is wanted
python3 delegate.py discard --workdir <workdir>                    # rejected work
```

`land` applies the worktree's changes to the user's checkout, then removes the worktree and its
branch. If the checkout moved on and the changes no longer apply, nothing is touched and the
worktree is kept so you can resolve it.

Tell the user briefly what was delegated, to which worker and tier, how many rounds it took, and
what you fixed in review. You shipped it, so you vouch for it: report problems you caught rather
than hiding them.

## Safety

- Workers run in each CLI's sandboxed, edit-only mode where the CLI has one. Do not switch a
  backend to a "skip all permissions" or full-access mode.
- One worker per set of files at a time; parallel tasks get separate worktrees.
- A brief is sent to the worker vendor's servers. Leave out keys, customer data and anything the
  user has marked private.
