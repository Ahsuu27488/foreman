# Privacy policy

_Last updated: 17 October 2026_

Foreman is an open-source plugin that runs entirely on your own computer. This policy explains
what it does with data.

## What Foreman collects

Nothing. Foreman has no servers, no accounts, no analytics and no telemetry. Its code makes no
network requests of its own.

## Where your data goes

When the lead agent delegates a task, Foreman starts a worker CLI that you installed and signed in
to, such as Google Antigravity, OpenAI Codex, Cursor Agent, GitHub Copilot CLI or Gemini CLI. That
CLI sends the task brief, and any project files it chooses to read, to its own vendor under that
vendor's terms and privacy policy. Foreman does not choose or change where that data goes; your
choice of worker does. Some free model tiers use prompts for training, so pick workers whose data
policy fits your code, and keep secrets out of briefs.

## What Foreman stores on your computer

- Your settings, in `~/.config/foreman/config.json`.
- A record of each run (the brief and the result), in `foreman-runs` inside your system's
  temporary folder.
- Temporary git worktrees next to your repository, named `<repo>.delegate-<id>`, on branches named
  `foreman/<id>`. They are removed when work is landed or discarded.

You can delete any of these at any time.

## Contact

Questions about this policy: open an issue at https://github.com/Ahsuu27488/foreman/issues.
