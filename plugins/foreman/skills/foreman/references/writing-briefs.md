# Writing briefs

The brief is the only thing the worker knows about the task. A vague brief produces work you will
redo; a precise one usually lands in a single round. The script adds a short preamble (rules and a
report format), so the brief only needs the task itself.

## Template

```markdown
# Task: <one line>

## Goal
What should exist or be true when this is done, and why it matters (one short paragraph).

## Context
- Language, framework and versions that matter.
- Existing code to read first and follow: `path/to/similar_module.py` (pattern to copy).
- Conventions: naming, error handling, test style, formatting.

## Scope
- May create or edit: `src/feature/*.py`, `tests/test_feature.py`
- Must not touch: public APIs in `src/api/`, migrations, config, lockfiles.

## Requirements
1. Concrete, testable requirement.
2. ...

## Edge cases
- Inputs and situations you already know are tricky, with the expected behaviour.

## Done when
- `pytest tests/test_feature.py` passes (the lead will run it).
- No other files change.
```

## What makes a brief work

- **Concrete beats clever.** "Return `None` for an empty list" beats "handle edge cases".
- **Point at examples in the repo.** Workers copy local patterns well and invent badly.
- **State the gates, and check them first.** Name the exact commands you will run, even though the
  worker likely cannot run them; it then writes code aimed at passing them. Run each command once
  yourself before writing it down: a wrong flag in the brief misleads the worker and wastes a round.
- **Bound the scope.** List allowed files. Unbounded briefs invite drive-by refactors.
- **Put the hard part first.** If one requirement is subtle, say so and explain it.
- **Leave out history.** No "as we discussed": the worker was not there.

## Example: good

```markdown
# Task: add retry with backoff to the HTTP client

## Goal
Transient failures in `fetch_json` currently crash the sync job. Retry them.

## Context
- Python 3.12, `httpx` 0.28. Read `src/sync/client.py` (current code) and
  `src/sync/storage.py` (how we log with `log = logging.getLogger(__name__)`).

## Scope
- Edit only `src/sync/client.py` and add `tests/test_client_retry.py`.

## Requirements
1. Retry on `httpx.TransportError` and on status 429, 502, 503, 504. Never on other 4xx.
2. At most 4 attempts in total; delays 0.5 s, 1 s, 2 s (no jitter needed).
3. Respect a `Retry-After` header in seconds when present, capped at 30 s.
4. Make the sleep function injectable so tests do not actually sleep.

## Edge cases
- `Retry-After` may be an HTTP date; treat that like a missing header.

## Done when
- `pytest tests/test_client_retry.py` passes and covers each requirement.
```

## Example: too vague

```markdown
Make the HTTP client more robust and add some tests.
```

This one leaves every decision to the worker, so you end up reviewing guesses.

## Delta briefs (send-back rounds)

Keep them short and specific, and send them with `--continue` so the worker keeps its context:

```markdown
Review found 2 problems. Fix only these:
1. `src/sync/client.py:48` retries on 404. Requirement 1 says never retry other 4xx.
2. `tests/test_client_retry.py` never tests `Retry-After` as an HTTP date (edge case 1).
```
