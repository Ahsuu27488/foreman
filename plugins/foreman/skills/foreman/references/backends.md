# Backends, routes and configuration

## Contents
- How routing works
- The user config
- Built-in backends
- Adding a new CLI
- Troubleshooting

## How routing works

A **backend** is one CLI (agy, codex, ...). A **worker** is `backend:model`, or just `backend` to
use that CLI's default model. Each **tier** (`light`, `balanced`, `frontier`) has a **route**: an
ordered list of workers.

The script tries the first worker on the route. It moves to the next one only when a worker is not
installed, disabled, out of quota, or (for read-only runs) cannot be isolated. A worker that runs
but does poor work is not retried automatically: judging quality is the lead's job.

## The user config

Path: `~/.config/foreman/config.json` (override with the `FOREMAN_CONFIG` environment variable).
It lives outside the skill folder, so updating the skill never overwrites it. `delegate.py init`
creates it from the installed CLIs and their model lists.

A Claude Code lead with an Antigravity subscription:

```json
{
  "lead": "claude",
  "routes": {
    "light": ["agy:gemini-3.8-flash-low"],
    "balanced": ["agy:gemini-3.8-flash-high"],
    "frontier": ["agy:claude-opus-4-6-thinking", "gemini:gemini-3.1-pro-preview"]
  },
  "backends": {"opencode": {"enabled": false}}
}
```

A Codex lead that also has Antigravity:

```json
{
  "lead": "codex",
  "routes": {
    "light": ["agy:gemini-3.8-flash-low"],
    "balanced": ["agy:gemini-3.8-flash-high"],
    "frontier": ["agy:claude-opus-4-6-thinking"]
  }
}
```

(Model names are examples; use what `delegate.py models` shows on your machine.)

`backends` entries merge field by field over the built-ins, so a single field can be fixed, for
example a renamed flag after a CLI update, without copying the whole definition. `tier_rules`
replaces the word lists used to classify model names. `tier_effort` sets the default reasoning
effort per tier, for example `{"light": "low", "balanced": "medium", "frontier": "high"}`; a route
entry can carry its own effort as `backend:model@high`.

## Built-in backends

`delegate.py doctor` shows which are installed and whether each definition has been verified end to
end. Unverified definitions come from each tool's documentation: run a small `--readonly` task
first and fix flags in the user config if needed.

Effort flags are built in for `agy` (`--effort`), `claude` (`--effort`) and `codex`
(`-c model_reasoning_effort=`). Other CLIs pick effort through model names or not at all.

| Backend | CLI | Edit mode | Read-only | Model list | Notes |
|---|---|---|---|---|---|
| `agy` | Google Antigravity | `--mode accept-edits --sandbox` | enforced (`--mode plan`) | yes | Verified. Headless runs cannot use the shell. |
| `codex` | OpenAI Codex | `--sandbox workspace-write` | enforced (`--sandbox read-only`) | no | Prompt via stdin. No follow-up support; send fresh briefs. |
| `cursor` | Cursor Agent | `--force` | isolated in a worktree | no | |
| `copilot` | GitHub Copilot CLI | `--allow-tool write` | isolated | no | Plain-text output. |
| `gemini` | Gemini CLI | `--approval-mode auto_edit` | enforced (`plan`) | no | Sign in with the subscription account. |
| `qwen` | Qwen Code | `--approval-mode auto-edit` | isolated | no | |
| `droid` | Factory Droid | `--auto low` | isolated | no | `exec` defaults to read-only. |
| `amp` | Amp | default | isolated | no | Chooses models itself. Paid credits needed. |
| `opencode` | OpenCode | `--agent build` | isolated | yes | Free models may train on prompts. |
| `aider` | Aider | default | isolated (`--dry-run`) | no | Your own API keys. |
| `goose` | Goose | default | isolated | no | |
| `crush` | Crush | default | isolated | no | |
| `continue` | Continue CLI (`cn`) | `--auto` | isolated | no | |
| `claude` | Claude Code | `--permission-mode acceptEdits` | enforced (`plan`) | no | Not routed automatically. Tiers use the stable aliases `haiku`, `sonnet`, `opus`. |

"Isolated" means the CLI cannot promise not to write, so read-only runs happen in a throwaway git
worktree that is deleted afterwards. Outside a git repo those backends are skipped for read-only
work.

## Adding a new CLI

Add an entry under `backends` in the user config. All fields:

```json
{
  "backends": {
    "mycli": {
      "label": "My CLI",
      "binary": "mycli",
      "base": ["run", "--json", "--model", "{model}", "{prompt}"],
      "edit": ["--allow-edits"],
      "readonly": ["--plan"],
      "readonly_enforced": false,
      "continue": null,
      "prompt_via": "arg",
      "output": "json",
      "report_keys": ["result", "response", "text"],
      "session_keys": ["session_id"],
      "usage_keys": ["usage"],
      "models_args": ["models"],
      "tiers": {"light": null, "balanced": null, "frontier": null},
      "effort_flag": ["--effort", "{effort}"],
      "efforts": ["low", "medium", "high"],
      "tail": [],
      "worker_note": null
    }
  }
}
```

The flags above are placeholders; take the real ones from that CLI's `--help`. A CLI can be a
backend when:

- It has a non-interactive mode that runs one prompt and exits.
- It can edit files in its working directory without asking, ideally sandboxed without shell access.
- Its output is JSON, JSON Lines (`"output": "json"`) or plain text (`"output": "text"`).

Field notes:

- `prompt_via: "stdin"` when the CLI reads the prompt from standard input. It avoids command-line
  length limits.
- `models_args`: arguments that print one model id per line, used by `models` and `init`.
- `tiers`: fallback model per tier when the CLI cannot list models.
- `effort_flag` and `efforts`: how the CLI takes a reasoning effort, and which levels it accepts.
  Leave `effort_flag` out if the CLI has no such setting.
- `tail`: arguments that must come last, such as a `-` meaning "read the prompt from stdin".
- `worker_note`: an extra instruction placed above the brief, for CLI-specific limits.
- `readonly_enforced: true` only if the CLI really refuses to write in read-only mode.

Then add the worker to a route and run a small task to verify it. To share it, open a pull request
adding it to `scripts/backends.json` with a `verified` note (CLI version, OS, date).

## Troubleshooting

- **`unavailable`**: the binary is not on PATH. Run `doctor`.
- **`quota`**: the plan or API limit is used up. The route moves on; check the CLI's usage page.
- **`no_output` with denied actions**: the worker tried a tool it is not allowed to use and gave up.
  Add or strengthen the backend's `worker_note`.
- **Worktree errors**: the folder must be inside a git repo with at least one commit.
- **Windows `.cmd` launchers**: npm shims are unwrapped automatically so multi-line briefs reach the
  real program. If a CLI uses another kind of launcher, point `binary` at the real executable.
