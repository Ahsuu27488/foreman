<img src="assets/logo.svg" alt="Foreman logo" width="96" height="96">

# Foreman

Foreman makes your Claude Code session the lead engineer on a team of other AI coding agents you
already pay for. When a task is clear, checkable and big enough to be worth it, Claude writes a
brief, hands it to a worker CLI such as Google Antigravity, OpenAI Codex, Cursor Agent, GitHub
Copilot CLI or Gemini CLI, then runs your tests, reads every changed line, and accepts the work,
sends it back with precise fixes, or does it itself. Your Claude usage goes to judgment and review;
the workers' quotas go to the typing.

It picks a light, balanced or frontier model and a reasoning effort for each task, falls back to
the next worker when one is missing or out of quota, and isolates edits in a separate git worktree
until Claude lands them in your checkout as uncommitted changes.

## Requirements

- **Claude Code** on your own machine (desktop app or CLI). Foreman runs local programs, so it
  does nothing on claude.ai or in Cowork.
- Python 3.10+ and git.
- At least one worker CLI installed and signed in. Antigravity is verified end to end; the others
  are implemented from their documentation.

## Setup

In a Claude Code session, ask: "run foreman doctor and init". Claude runs
`scripts/delegate.py doctor` to find your worker CLIs and `init` to write your routes to
`~/.config/foreman/config.json`, then shows them to you to confirm.

## What foreman runs, sends and writes

- **Runs** the worker CLIs you have installed (for example `agy`, `codex`, `cursor-agent`,
  `gemini`), headless, in their sandboxed edit-only or read-only modes. It never enables "skip all
  permissions" modes. It also runs `git` to create and remove worktrees, and each CLI's own
  `--version` and model-listing commands.
- **Sends** each task brief, and whatever files the worker chooses to read in your project, to
  that worker's vendor (Google, OpenAI, Cursor, GitHub and so on) through the vendor's own CLI.
  Foreman itself makes no network requests and collects no telemetry. Some free model tiers train
  on prompts, so keep secrets out of briefs and pick workers whose data policy fits your code.
- **Writes** your settings to `~/.config/foreman/config.json`, run records (brief and result) to
  `<temp>/foreman-runs/`, and git worktrees next to your repository named `<repo>.delegate-<id>`
  on branches `foreman/<id>`, which are removed when work is landed or discarded.

## Learn more

Full documentation, configuration and the list of supported CLIs:
https://github.com/Ahsuu27488/foreman

## License

MIT
