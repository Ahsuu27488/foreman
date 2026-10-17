# Contributing to Foreman

Thanks for helping. The most valuable contributions are **verified backends**: a real run of a
worker CLI that Foreman so far only knows from documentation.

## Verifying a backend

1. Install the CLI and sign in.
2. Run `python3 plugins/foreman/skills/foreman/scripts/delegate.py doctor` and check it shows as
   installed.
3. In a throwaway git repository, run a small read-only task, then a small edit task:

   ```bash
   python3 delegate.py run --readonly --worker <backend> --brief brief.md --cwd <repo>
   python3 delegate.py run --worktree --worker <backend> --brief brief.md --cwd <repo>
   ```

4. Check the JSON result: `status` is `done`, `files` lists what changed, and `worker_report` holds
   the worker's answer. For a read-only run, confirm no files changed.
5. If flags were wrong, fix them in `scripts/backends.json`.
6. Open a pull request that sets the backend's `verified` field to something like
   `"codex-cli 0.160.0, macOS 15, 2026-11-02 (edit and read-only runs)"`.

## Adding a new CLI

Add an entry to `plugins/foreman/skills/foreman/scripts/backends.json` and to `_preference`. The
fields are documented in `references/backends.md`. A CLI qualifies when it has a non-interactive
mode, can edit files without prompting (ideally sandboxed without shell access), and prints JSON,
JSON Lines or plain text. Mark it `"verified": "no"` until someone has run it.

## Changing the skill or script

- Keep `SKILL.md` short: it is loaded into the lead agent's context every time.
- `delegate.py` uses the Python standard library only and must run on Windows, macOS and Linux.
- Add or update tests in `tests/`. `tests/fake_agent.py` stands in for a worker CLI.
- Run the checks before opening a pull request:

  ```bash
  python -m unittest discover -s tests
  claude plugin validate --strict ./plugins/foreman
  ```

## Releasing

Raise the version in all three places together, or installed copies will not update:
`plugins/foreman/.claude-plugin/plugin.json`, `VERSION` in `scripts/delegate.py`, and `metadata.version`
in `SKILL.md`. Add a `CHANGELOG.md` entry. The tests check that the versions match.
