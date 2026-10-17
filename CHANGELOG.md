# Changelog

## 0.4.1

- Logo (`assets/logo.svg`, `assets/logo.png`): a foreman's hard hat leading a crew of three.
- Rewritten README with a how-it-works diagram, a real session, tier and CLI tables, a command
  reference and an FAQ. New CONTRIBUTING.md and SECURITY.md.
- Plugin README lists exactly what Foreman runs, sends and writes, for Anthropic's directory.
- Author shown as Muhammad Ahsan.

## 0.4.0

Changes from the first end-to-end tests (a lead delegating real tasks to Antigravity workers):

- New `land` command: brings accepted worktree changes into the user's checkout as uncommitted
  changes (or commits with `--commit -m`), then removes the worktree and branch. New `discard`
  command for rejected work. The lead no longer commits unless the user wants that.
- Worker preamble now asks for the simplest code that meets the brief, without speculative
  fallbacks; review notes list "speculative code" as a failure mode.
- Leads check their gate commands before putting them in a brief.
- The keep-it-yourself rule names payment processing, not anything payment-related.

## 0.3.0

- Reasoning effort: each tier has a default effort (`tier_effort`), workers can carry one
  (`backend:model@high`), and `run --effort` overrides both. Mapped to each CLI's own flag for
  Antigravity, Claude Code and Codex, clamped to the levels a CLI supports, and skipped when the
  model id already names an effort.
- Backends can declare `tail` arguments that must come last (Codex's stdin marker).

## 0.2.0

- Renamed to **foreman** and packaged as a Claude Code plugin marketplace; the skill folder also
  works on its own in any agent that supports Agent Skills.
- Model tiers: routes are now `light`, `balanced` and `frontier`, with a guide for matching tasks
  to tiers across vendors (`references/model-tiers.md`).
- New `models` command lists a CLI's models with a suggested tier; `init` builds tier routes from
  those lists and leaves out the lead agent's own CLI.
- New backends: GitHub Copilot CLI, Qwen Code, Factory Droid, Amp, Aider, Goose, Crush, Continue.
- Read-only runs on CLIs that cannot enforce read-only happen in a throwaway git worktree.
- Windows npm launchers are unwrapped so multi-line briefs arrive intact.
- Test suite and CI on Linux, macOS and Windows.

## 0.1.0

- First version: `doctor`, `init`, `run`; fallback when a worker is missing or out of quota; git
  worktree isolation; before/after file change detection.
