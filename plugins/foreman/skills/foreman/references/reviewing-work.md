# Reviewing delegated work

You are accountable for what you accept. Review as if a colleague's pull request would ship under
your name.

## Checklist

```
Review:
- [ ] Result status is "done" and the worker report makes sense
- [ ] Every file in files.created / modified / deleted was expected by the brief
- [ ] Gates run by me: tests, type check, build, lint (whatever the project uses)
- [ ] Each requirement in the brief is met, checked against the code, not the report
- [ ] Edge cases from the brief are handled and tested
- [ ] No weakened, skipped or deleted tests; no assertions loosened to pass
- [ ] No invented APIs, imports or dependencies; new dependencies were allowed
- [ ] No hard-coded values that only fit the examples
- [ ] Style matches the surrounding code
- [ ] Nothing outside scope changed (formatting sweeps, renamed symbols, config)
```

## Reading the result

- `status`: `done`, `failed`, `no_output`, `timeout`, `all_unavailable`. Anything but `done` means
  read `output_tail` and `attempts` before deciding what to do.
- `files`: computed by comparing the folder before and after, so it is accurate even when the
  worker's report is not. An empty list with a confident report means the worker described work it
  did not do.
- `denied_actions`: tools the CLI blocked (often shell commands). Expected for sandboxed runs.
- `warnings`: for example, uncommitted changes that the worktree does not contain.

For worktree runs, inspect with:

```bash
git -C <workdir> status --short
git -C <workdir> diff
```

New files show as untracked there; read them directly.

## Common worker failure modes

- **Plausible but wrong edge cases**: off-by-one, empty input, negative numbers, unicode, time zones.
- **Overfitting**: code that passes the examples in the brief and nothing else.
- **Test tampering**: making a failing test pass by editing the test.
- **Scope creep**: unrelated refactors that make the diff hard to review.
- **Hallucinated APIs**: methods that do not exist in the library version in use.
- **Silent behaviour change**: a default value, error type or return shape quietly altered.
- **Speculative code**: aliases, fallbacks and type juggling for situations the brief never
  mentions, often added to satisfy tests the worker imagined. The tests still pass, which is why
  only reading the code catches it. Send it back with the exact lines to remove.

## Deciding

- **Accept** if you would have written it, or it is at least as good. Then `delegate.py land`.
- **Fix it yourself** if the remaining problems take fewer tokens to fix than to describe.
- **Send back** otherwise, with a delta brief (see writing-briefs.md) via `--continue`.
- **Escalate** after two failed rounds: raise the effort or move up one tier, then do it yourself.
- **Reject** with `delegate.py discard` when the approach is wrong and a fresh brief is better.

When you report to the user, say what you changed during review. If the worker's output was poor
and you replaced most of it, say so too: that information decides what to delegate next time.
