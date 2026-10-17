# Model tiers across vendors

## Contents
- The three tiers
- How vendors name their tiers
- Effort and thinking settings
- Quotas and plans
- Checking what a CLI offers

## The three tiers

| Tier | Strength | Cost and speed | Delegate |
|---|---|---|---|
| light | Follows clear patterns; weak at multi-step reasoning | Cheapest and fastest | Mechanical edits, search, extraction, summaries |
| balanced | Solid engineering from a good spec | Moderate | Most implementation, tests, focused refactors |
| frontier | Deep reasoning, long-horizon changes | Most expensive and slowest | Hard problems and escalations |

The tier describes how hard the task is to get right. A huge but mechanical rename is `light`; a
twenty-line concurrency fix is `frontier`.

## How vendors name their tiers

Names change with every release, so treat these as patterns, not a list of current models. Run
`delegate.py models <backend>` to see what a CLI offers today.

| Vendor family | light | balanced | frontier |
|---|---|---|---|
| Anthropic Claude | Haiku | Sonnet | Opus (and any tier above it) |
| Google Gemini | Flash-Lite | Flash | Pro |
| OpenAI GPT | nano, mini | the standard model, Codex variants | Pro, Max, or the family's top name |
| xAI Grok | "fast" or mini variants | the numbered model | "heavy" variants |
| Alibaba Qwen | Flash, Turbo | Plus | Max |
| DeepSeek, GLM, Kimi, MiniMax | Flash and small variants | the main model | Pro, Max, or reasoning variants |

Watch for families that reuse a word at different tiers. For example, one generation may call its
mid model "Sol" and the next generation its top model "Sol". When names are ambiguous, compare
prices: within one vendor, price tracks tier closely.

`init` classifies names with simple word rules (`_tier_rules` in `scripts/backends.json`,
overridable with `tier_rules` in the user config). Always confirm its picks with the user.

## Effort and thinking settings

CLIs expose effort in one of two ways: a flag (`agy --effort`, `claude --effort`, Codex's
`model_reasoning_effort`) or separate model ids (`gemini-3.8-flash-low/-medium/-high`). More effort
moves a model up within its family, roughly half a tier:

- A balanced model on high effort is often enough for work you would otherwise send to frontier.
  It is the cheaper first escalation.
- A frontier model on low effort is rarely worth it; pick a balanced model instead.
- For light work, use the lowest effort available; thinking time is wasted on mechanical edits.
- Effort costs time and tokens on every run. Raise it per task, not as a habit.

How foreman applies effort, highest priority first:

1. `--effort LEVEL` on the `run` command.
2. `@LEVEL` on a worker, such as `agy:gemini-3.8-flash@high` in a route or `--worker`.
3. The tier default from `tier_effort` in the user config (light `low`, balanced `medium`,
   frontier `high`). It is skipped when the model id already ends in an effort level, so a route
   entry like `gemini-3.8-flash-high` keeps its high effort.

Levels are `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. When a CLI does not support the
requested level, the nearest supported one is used (the lower one on a tie). CLIs without an
effort setting ignore it, and the result's `effort` field shows what was actually sent.

## Quotas and plans

- Delegation only saves money when the worker draws on a different budget than the lead: another
  vendor's subscription, a separate quota pool, or free credits. `init` therefore leaves the lead's
  own CLI out of the routes.
- Some CLIs meter model families separately (Antigravity, for instance, has one quota for Gemini
  models and another for Claude and GPT models). Spread tiers across pools when you can.
- Free tiers often use prompts for training. Check before sending private code.

## Checking what a CLI offers

```bash
python3 delegate.py models            # every installed CLI that can list models
python3 delegate.py models agy        # one CLI
```

CLIs without a listing command report `tier_hints` instead. Set their models by hand in the user
config, for example `"frontier": ["codex:<top model>", "agy:<frontier model>"]`.
