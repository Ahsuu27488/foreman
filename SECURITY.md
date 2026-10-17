# Security policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/Ahsuu27488/foreman/security/advisories/new)
rather than in a public issue. Include the Foreman version, your operating system, the worker CLI
involved, and steps to reproduce. You can expect a first response within a week.

## Security model

Foreman is a local dispatcher. Knowing its boundaries helps you judge reports and use it safely.

- **No network access of its own.** `delegate.py` uses only the Python standard library and makes
  no network requests. Briefs reach a worker vendor only through that vendor's own CLI, which you
  installed and signed in to.
- **Sandboxed workers.** Each backend runs in its CLI's edit-only or read-only mode. Foreman never
  passes "skip all permissions" or full-access flags. How strong that sandbox is depends on each
  CLI.
- **Isolation.** Edit tasks run in a separate git worktree. Read-only tasks on CLIs that cannot
  enforce read-only run in a throwaway worktree that is deleted afterwards.
- **Change detection.** Every run compares the working folder before and after, so the lead sees
  what changed on disk regardless of what the worker reports.
- **The lead reviews everything.** Worker output is untrusted until the lead agent has run the
  project's tests and read the diff.

## What is in scope

- Foreman running a command, or passing a flag, that the backend definition does not describe.
- Read-only runs that can change the user's checkout.
- `land` or `discard` touching files outside the worktree and the user's checkout.
- Anything that sends data somewhere other than the selected worker CLI.

Vulnerabilities in the worker CLIs themselves should be reported to their vendors.
