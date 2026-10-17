# foreman

**Make your best model the lead engineer, and let the CLI agents you already pay for do the typing.**

foreman is an [Agent Skill](https://agentskills.io) for Claude Code and other skill-aware agents.
When a task is clear, checkable and big enough to be worth it, the lead agent writes a brief, hands
it to a worker CLI (Antigravity, Codex, Cursor, Copilot, Gemini CLI, Qwen Code, Droid, Amp,
OpenCode, Aider and more), then **reviews, tests and fixes the result before accepting it**. The
lead's usage limits go to judgment; the workers' quotas go to volume.

## How it works

1. **Decide.** The lead keeps tiny edits, design calls, subtle debugging and anything with secrets.
   Clear, verifiable, larger tasks get delegated.
2. **Pick a tier.** `light` for mechanical work, `balanced` for normal engineering from a spec,
   `frontier` for hard reasoning. Each tier maps to a route of workers you choose.
3. **Brief.** A self-contained brief: goal, scope, requirements, edge cases, how it will be checked.
4. **Dispatch.** `delegate.py` runs the worker headless, sandboxed and edit-only, in its own git
   worktree, and measures exactly which files changed.
5. **Review.** The lead runs your tests and reads the whole diff. It accepts, sends the work back
   with precise fixes, or escalates a tier. After two failed rounds it does the work itself.
6. **Land.** `delegate.py land` brings the accepted changes into your checkout as uncommitted
   changes (or commits them, if you want that) and cleans up. Workers never commit. The lead tells
   you what it fixed in review.

## Install

**Claude Code plugin:**

```
/plugin marketplace add Ahsuu27488/foreman
/plugin install foreman@foreman
```

**Any agent with Agent Skills support:** copy `plugins/foreman/skills/foreman/` into that agent's
skills folder (for Claude Code: `~/.claude/skills/foreman/`).

**Then, once per machine:**

```bash
python3 <skill-folder>/scripts/delegate.py doctor   # which worker CLIs you have
python3 <skill-folder>/scripts/delegate.py init     # build light/balanced/frontier routes
```

`init` writes `~/.config/foreman/config.json`. Edit it to reorder workers, disable some, or add
new CLIs. Use `python` instead of `python3` on Windows.

## Example config

A Claude Code lead with a Google AI Pro plan (Antigravity):

```json
{
  "lead": "claude",
  "routes": {
    "light": ["agy:gemini-3.8-flash-low"],
    "balanced": ["agy:gemini-3.8-flash-high"],
    "frontier": ["agy:claude-opus-4-6-thinking"]
  }
}
```

A Codex lead with Antigravity on the side works the same way; `init` leaves the lead's own CLI out
of the routes, because delegating to it would spend the same plan.

## Supported worker CLIs

| CLI | Status |
|---|---|
| Google Antigravity (`agy`) | Verified end to end |
| Gemini CLI, OpenCode | Flags checked against the installed CLI |
| OpenAI Codex, Cursor Agent, GitHub Copilot CLI, Qwen Code, Factory Droid, Amp, Aider, Goose, Crush, Continue, Claude Code | From official docs; please report results |

Any other headless agent CLI can be added in the config without code changes. See
[references/backends.md](plugins/foreman/skills/foreman/references/backends.md).

## Requirements

- Python 3.10+ (standard library only) and git.
- At least one worker CLI, installed and signed in.

## Privacy and safety

- Briefs, and the files a worker reads, go to that worker's vendor. Some free tiers train on
  prompts. Keep secrets out of briefs.
- Workers run in each CLI's sandboxed edit mode. foreman never enables "skip all permissions" modes.
- Edits happen in a separate git worktree; your checkout changes only when the lead merges.

## Contributing

Verified a backend on your machine, or added a new CLI? Open a pull request updating
`plugins/foreman/skills/foreman/scripts/backends.json` with a `verified` note (CLI version, OS,
date). Run the tests with `python -m unittest discover -s tests`.

## License

MIT
