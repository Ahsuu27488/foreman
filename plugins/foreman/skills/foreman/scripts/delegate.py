#!/usr/bin/env python3
"""foreman: hand one task to a worker CLI agent (Antigravity, Codex, Cursor, Copilot, Gemini CLI,
Qwen Code, Aider, OpenCode, Claude Code...) and report exactly what it changed, so the lead agent
can review it.

Commands:
  delegate.py doctor                    installed CLIs, their status, and how routes resolve
  delegate.py models [BACKEND]          a CLI's models with a suggested tier (light/balanced/frontier)
  delegate.py init [--lead BACKEND] [--force]
                                        write the user config: one route per tier, built from the
                                        installed CLIs and their model lists
  delegate.py run --brief FILE --cwd DIR [--tier TIER | --worker BACKEND[:MODEL][@EFFORT]]
                  [--effort LEVEL] [--readonly] [--worktree] [--timeout MIN]
                  [--continue SESSION_ID]
  delegate.py land --workdir DIR [--commit -m MESSAGE]
                                        bring accepted worktree changes into the user's checkout
                                        (uncommitted unless --commit), then remove the worktree
  delegate.py discard --workdir DIR     remove a worktree and its branch without landing anything

Backends are data, not code: built-ins live in backends.json next to this script, and the user
config can override any field or add backends without touching the skill.

Standard library only. Exit codes: 0 done, 1 worker failed or produced nothing, 2 usage or config
error, 3 every worker on the route was unavailable or out of quota, 4 timeout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

SKILL_NAME = "foreman"
VERSION = "0.4.0"
SCRIPT_DIR = Path(__file__).resolve().parent
BACKENDS_FILE = SCRIPT_DIR / "backends.json"
# Kept outside the skill folder so updating or reinstalling the skill never overwrites it.
CONFIG_PATH = Path(os.environ.get("FOREMAN_CONFIG")
                   or Path.home() / ".config" / SKILL_NAME / "config.json")
RUNS_DIR = Path(tempfile.gettempdir()) / f"{SKILL_NAME}-runs"
TIERS = ("light", "balanced", "frontier")
# Reasoning effort levels, lowest to highest. Backends list the subset they accept in "efforts".
EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")
DEFAULT_TIER_EFFORT = {"light": "low", "balanced": "medium", "frontier": "high"}
# A model id that already ends in an effort level (gemini-3.8-flash-high) has its effort chosen.
# "max" is left out on purpose: in names like qwen3.8-max it is a tier, not an effort.
NAMED_EFFORT_RE = re.compile(r"[-_](minimal|low|medium|high|xhigh)$", re.I)

# Windows caps a whole command line at 32,767 characters; leave room for the other arguments.
MAX_ARG_PROMPT = 30_000
# Seconds a CLI gets to exit on its own after its timeout before it is killed.
GRACE_SECONDS = float(os.environ.get("FOREMAN_GRACE_SECONDS", "60"))
# Generated, vendored or huge folders. Workers should not edit them, and walking them is slow.
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build",
             ".mypy_cache", ".pytest_cache", "target", ".gradle", ".tox"}
# Hashing very large files is slow and they are rarely hand-edited; size + mtime is enough there.
HASH_LIMIT = 5 * 1024 * 1024
# Phrases the supported CLIs print when a plan or API quota is exhausted.
QUOTA_RE = re.compile(r"quota|rate.?limit|resource.?exhausted|usage limit|\b429\b", re.I)
REPORT_TAIL = 4000

PREAMBLE_EDIT = """You are a worker agent. A lead engineer wrote the brief below and will review every
change you make before accepting it, so aim for work that needs no corrections.

Rules:
- Work only inside the current folder, and only on the files the brief allows.
- Do not commit, push, or change git branches.
- Read existing code before using it; do not invent APIs, files or dependencies.
- Write the simplest code that meets the brief. No aliases, fallbacks or extra code paths for
  situations the brief does not describe: the lead judges your code by reading it, not by hidden
  tests you need to anticipate, and speculative code is sent back.
- If the brief is ambiguous, make the most reasonable choice and list it under ASSUMPTIONS.

Finish with this report:
SUMMARY: what you did, in 2-4 lines
FILES: each file created or changed, with one line on why
ASSUMPTIONS: choices you made that the brief did not settle (or "none")
OPEN QUESTIONS: anything the lead should decide (or "none")

--- BRIEF ---
"""

PREAMBLE_READONLY = """You are a research worker. A lead engineer wrote the brief below and will act on
your answer, so be precise, cite file paths and line numbers, and say when you are unsure.
Do not create, modify or delete any files.

--- BRIEF ---
"""


# ---------------------------------------------------------------- config

def fail(msg: str, code: int = 2):
    print(json.dumps({"status": "error", "error": msg}, indent=2))
    sys.exit(code)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        fail(f"{path} is not valid JSON: {e}")


def builtin_data() -> dict:
    return load_json(BACKENDS_FILE)


def load_backends(config: dict) -> dict:
    """Built-in backends, with per-field overrides and extra backends from the user config."""
    backends = {k: v for k, v in builtin_data().items() if not k.startswith("_")}
    for name, override in config.get("backends", {}).items():
        backends[name] = {**backends.get(name, {}), **override}
    return backends


def tier_rules(config: dict) -> dict:
    return {**builtin_data().get("_tier_rules", {}), **config.get("tier_rules", {})}


def parse_worker(text: str) -> tuple[str, str | None, str | None]:
    """'backend[:model][@effort]' -> (backend, model, effort)."""
    effort = None
    head, sep, tail = text.rpartition("@")
    if sep and tail.lower() in EFFORTS:
        text, effort = head, tail.lower()
    backend, _, model = text.partition(":")
    return backend, (model or None), effort


def clamp_effort(effort: str, supported: list[str]) -> str:
    """Nearest level the backend accepts; on a tie, the lower one (cheaper, and review catches it)."""
    if not supported or effort in supported:
        return effort
    want = EFFORTS.index(effort)
    ranked = sorted((s for s in supported if s in EFFORTS), key=lambda s: (abs(EFFORTS.index(s) - want), EFFORTS.index(s)))
    return ranked[0] if ranked else effort


def choose_effort(spec: dict, model: str | None, explicit: str | None, worker_effort: str | None,
                  tier_effort: str | None) -> tuple[str | None, str | None]:
    """Returns (effort to send, model id to send).

    --effort beats worker@effort beats the tier default. The tier default is skipped when the
    model name already carries an effort level, so 'flash-high' is not quietly turned down.
    Backends can limit effort to some models ('effort_models', a regex) and can require the
    effort suffix to be removed from the id when a flag is sent ('strip_named_effort')."""
    if not spec.get("effort_flag"):
        return None, model
    if (pattern := spec.get("effort_models")) and not (model and re.search(pattern, model)):
        return None, model
    named = bool(model and NAMED_EFFORT_RE.search(model))
    effort = explicit or worker_effort
    if effort is None and tier_effort and not named:
        effort = tier_effort
    if effort is None:
        return None, model
    if named and spec.get("strip_named_effort"):
        model = NAMED_EFFORT_RE.sub("", model)
    return clamp_effort(effort, spec.get("efforts", [])), model


# ---------------------------------------------------------------- binaries

def resolve_binary(spec: dict) -> str | None:
    for candidate in [spec.get("binary")] + spec.get("binary_alternatives", []):
        if candidate and (path := shutil.which(candidate)):
            return path
    return None


def launcher(binary: str) -> list[str]:
    """On Windows, npm installs .cmd shims that run through cmd.exe, which mangles multi-line
    arguments. Run the real target (a native .exe, or node + script) directly instead."""
    if os.name != "nt" or not binary.lower().endswith((".cmd", ".bat")):
        return [binary]
    try:
        text = Path(binary).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [binary]
    m = re.search(r'"%dp0%\\([^"]+)"\s+%\*', text, re.I)
    if not m:
        return [binary]
    target = Path(binary).parent / m.group(1)
    if target.suffix.lower() == ".exe":
        return [str(target)]
    if re.search(r"_prog=.*node", text, re.I):
        local_node = Path(binary).parent / "node.exe"
        node = str(local_node) if local_node.exists() else shutil.which("node")
        if node:
            return [node, str(target)]
    return [binary]


# ---------------------------------------------------------------- models and tiers

def classify(model_id: str, rules: dict) -> str:
    """Guess a model's tier from the words in its name. A hint for init, never the final word:
    families reuse names differently, so the user or lead should confirm the result."""
    tokens = set(re.split(r"[^a-z0-9]+", model_id.lower()))
    if tokens & set(rules.get("light", [])):
        return "light"
    if tokens & set(rules.get("frontier", [])):
        return "frontier"
    return "balanced"


def list_models(spec: dict) -> list[str] | None:
    """Ask the CLI for its models. None when the CLI has no listing command or it failed."""
    args = spec.get("models_args")
    binary = resolve_binary(spec)
    if not args or not binary:
        return None
    try:
        out = subprocess.run([*launcher(binary), *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    models: list[str] = []
    for line in out.stdout.splitlines():
        m = re.match(r"\s*([A-Za-z0-9][\w.\-/:@]*)", line)
        # Model ids contain a digit, hyphen or slash; this skips headings like "Fetching...".
        if m and re.search(r"[\d\-/]", m.group(1)) and m.group(1) not in models:
            models.append(m.group(1))
    return models or None


def cmd_models(args) -> int:
    config = load_json(CONFIG_PATH)
    backends = load_backends(config)
    rules = tier_rules(config)
    names = [args.backend] if args.backend else list(backends)
    report = {}
    for name in names:
        spec = backends.get(name)
        if spec is None:
            fail(f"Unknown backend '{name}'. Known: {', '.join(backends)}")
        if not resolve_binary(spec):
            if args.backend:
                report[name] = {"installed": False}
            continue
        models = list_models(spec)
        if models:
            report[name] = {m: classify(m, rules) for m in models}
        else:
            report[name] = {"listing": "not available from this CLI",
                            "tier_hints": spec.get("tiers", {}),
                            "note": "Set models per tier in the user config (see references/model-tiers.md)."}
    print(json.dumps(report, indent=2))
    return 0


# ---------------------------------------------------------------- doctor / init

def detect_lead() -> str | None:
    """Which agent is running this script, from environment variables those agents set."""
    if os.environ.get("CLAUDECODE"):
        return "claude"
    if any(k.startswith("CODEX_") for k in os.environ):
        return "codex"
    if os.environ.get("GEMINI_CLI"):
        return "gemini"
    return None


def cmd_doctor(_args) -> int:
    config = load_json(CONFIG_PATH)
    backends = load_backends(config)
    report = {"version": VERSION, "config": str(CONFIG_PATH), "config_exists": CONFIG_PATH.exists(),
              "lead": config.get("lead") or detect_lead(), "backends": {}}
    for name, spec in backends.items():
        path = resolve_binary(spec)
        entry = {"label": spec.get("label", name), "installed": bool(path),
                 "enabled": spec.get("enabled", True), "verified": spec.get("verified", "no")}
        if path:
            entry["path"] = path
            try:
                out = subprocess.run([*launcher(path), "--version"], capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=20)
                lines = (out.stdout or out.stderr).strip().splitlines()
                entry["version"] = lines[0][:80] if lines else "unknown"
            except (subprocess.TimeoutExpired, OSError):
                entry["version"] = "unknown"
        report["backends"][name] = entry
    report["routes"] = {
        tier: [{"worker": w, "ready": report["backends"].get(parse_worker(w)[0], {}).get("installed", False)}
               for w in workers]
        for tier, workers in config.get("routes", {}).items()}
    if not CONFIG_PATH.exists():
        report["hint"] = "No user config yet. Run: delegate.py init"
    print(json.dumps(report, indent=2))
    return 0


def cmd_init(args) -> int:
    if CONFIG_PATH.exists() and not args.force:
        fail(f"{CONFIG_PATH} already exists. Edit it, or re-run with --force to replace it.")
    backends = load_backends({})
    rules = tier_rules({})
    lead = args.lead or detect_lead()
    order = builtin_data().get("_preference", list(backends))
    routes: dict[str, list[str]] = {t: [] for t in TIERS}
    picks: dict[str, dict] = {}
    for name in order:
        spec = backends.get(name)
        # The lead's own CLI is skipped: delegating to it spends the same plan you want to save.
        if (not spec or name == lead or not spec.get("enabled", True)
                or not spec.get("auto_route", True) or not resolve_binary(spec)):
            continue
        chosen: dict[str, str | None] = {}
        for model in list_models(spec) or []:
            chosen.setdefault(classify(model, rules), model)
        for tier in TIERS:
            chosen.setdefault(tier, (spec.get("tiers") or {}).get(tier))
        picks[name] = chosen
        for tier in TIERS:
            if chosen[tier]:
                routes[tier].append(f"{name}:{chosen[tier]}")
            elif tier == "balanced":
                # A CLI's default model is usually its mid tier; unknown for light and frontier.
                routes[tier].append(name)
    config = {
        "_comment": "Each tier is a route: workers are tried in order, and the next one is used "
                    "only if one is missing or out of quota. Edit freely. 'backends' overrides "
                    "fields from backends.json; 'tier_rules' tunes model-name classification.",
        "lead": lead,
        "routes": routes,
        "tier_effort": dict(DEFAULT_TIER_EFFORT),
        "backends": {},
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(json.dumps({"status": "written", "config": str(CONFIG_PATH), "lead": lead,
                      "routes": routes, "tier_picks": picks,
                      "next": "Show these routes to the user and confirm the tier picks; model "
                              "names alone can mislead. Empty tiers need models set by hand."},
                     indent=2))
    return 0


# ---------------------------------------------------------------- snapshots

def snapshot(root: Path) -> dict[str, str]:
    state = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            try:
                st = p.stat()
                key = p.relative_to(root).as_posix()
                if st.st_size <= HASH_LIMIT:
                    state[key] = hashlib.sha1(p.read_bytes()).hexdigest()
                else:
                    state[key] = f"{st.st_size}:{st.st_mtime_ns}"
            except OSError:
                continue
    return state


def diff_snapshots(before: dict, after: dict) -> dict[str, list[str]]:
    return {
        "created": sorted(set(after) - set(before)),
        "modified": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
        "deleted": sorted(set(before) - set(after)),
    }


# ---------------------------------------------------------------- git worktrees

def git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def git_root(cwd: Path) -> Path | None:
    out = git("rev-parse", "--show-toplevel", cwd=cwd)
    return Path(out.stdout.strip()) if out.returncode == 0 else None


def make_worktree(cwd: Path, run_id: str, detached: bool = False) -> tuple[Path, Path, str | None, list[str]]:
    """Returns (workdir inside the worktree, worktree root, branch, warnings)."""
    root = git_root(cwd)
    if root is None:
        fail(f"A worktree needs a git repository, and {cwd} is not inside one.")
    warnings = []
    if git("status", "--porcelain", cwd=root).stdout.strip():
        warnings.append("Uncommitted changes in the main checkout are NOT in the worker's worktree.")
    suffix = "readonly" if detached else "delegate"
    path = root.parent / f"{root.name}.{suffix}-{run_id}"
    branch = None if detached else f"{SKILL_NAME}/{run_id}"
    cmd = ["worktree", "add", "--detach", str(path), "HEAD"] if detached else \
          ["worktree", "add", "-b", branch, str(path), "HEAD"]
    added = git(*cmd, cwd=root)
    if added.returncode != 0:
        fail(f"git worktree add failed: {added.stderr.strip()}")
    # Keep the worker in the same subfolder the caller pointed at.
    return path / cwd.resolve().relative_to(root.resolve()), path, branch, warnings


def remove_worktree(path: Path, cwd: Path):
    if (root := git_root(cwd)) is not None:
        git("worktree", "remove", "--force", str(path), cwd=root)


def worktree_info(workdir: Path) -> tuple[Path, Path, str | None]:
    """(worktree root, main checkout root, branch) for a linked worktree, or fail."""
    top = git_root(workdir)
    if top is None:
        fail(f"{workdir} is not inside a git worktree.")
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=top).stdout.strip()
    own = git("rev-parse", "--path-format=absolute", "--git-dir", cwd=top).stdout.strip()
    if not common or Path(common).resolve() == Path(own).resolve():
        fail(f"{top} is the main checkout, not a worktree made by 'run --worktree'.")
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=top).stdout.strip() or None
    return top, Path(common).parent, branch


def finish_worktree(top: Path, main: Path, branch: str | None) -> bool:
    """Remove the worktree, and its branch if foreman created it. Returns whether a branch went."""
    git("worktree", "remove", "--force", str(top), cwd=main)
    if branch and branch.startswith(f"{SKILL_NAME}/"):
        return git("branch", "-D", branch, cwd=main).returncode == 0
    return False


def cmd_land(args) -> int:
    top, main, branch = worktree_info(Path(args.workdir).resolve())
    git("add", "-A", cwd=top)
    changes = [line for line in git("diff", "--cached", "--name-status", "HEAD", cwd=top).stdout.splitlines() if line]
    if not changes:
        finish_worktree(top, main, branch)
        print(json.dumps({"status": "nothing_to_land", "worktree_removed": str(top)}, indent=2))
        return 0
    if args.commit:
        if not args.message:
            fail("--commit needs -m MESSAGE.")
        done = git("commit", "-q", "-m", args.message, cwd=top)
        if done.returncode != 0:
            fail(f"Commit failed in the worktree (kept at {top}): {done.stderr.strip()}")
        merged = git("merge", "--ff-only", "-q", branch, cwd=main)
        if merged.returncode != 0:
            merged = git("merge", "--no-edit", "-q", branch, cwd=main)
        if merged.returncode != 0:
            git("merge", "--abort", cwd=main)
            fail(f"Merging {branch} into {main} conflicts. Nothing was changed there; the worktree is "
                 f"kept at {top}. Resolve by hand or rerun after updating the checkout.")
    else:
        # Bytes, not text: the patch may contain binary hunks or non-UTF-8 files.
        patch = subprocess.run(["git", "diff", "--cached", "--binary", "HEAD"], cwd=top,
                               capture_output=True).stdout
        applied = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], cwd=main,
                                 input=patch, capture_output=True)
        if applied.returncode != 0:
            # Line-ending or drift mismatches: fall back to a three-way apply using the shared
            # object store. This also stages the changes, which is still uncommitted.
            applied = subprocess.run(["git", "apply", "--3way", "--whitespace=nowarn", "-"], cwd=main,
                                     input=patch, capture_output=True)
        if applied.returncode != 0:
            fail(f"The changes do not apply cleanly to {main} (the checkout moved on since the worker "
                 f"started). Nothing was changed there; the worktree is kept at {top}. "
                 f"{applied.stderr.decode(errors='replace').strip()}")
    branch_removed = finish_worktree(top, main, branch)
    print(json.dumps({"status": "landed", "into": str(main), "committed": bool(args.commit),
                      "changes": changes, "worktree_removed": str(top),
                      "branch_removed": branch if branch_removed else None}, indent=2))
    return 0


def cmd_discard(args) -> int:
    top, main, branch = worktree_info(Path(args.workdir).resolve())
    branch_removed = finish_worktree(top, main, branch)
    print(json.dumps({"status": "discarded", "worktree_removed": str(top),
                      "branch_removed": branch if branch_removed else None}, indent=2))
    return 0


# ---------------------------------------------------------------- running a worker

def build_command(spec: dict, binary: str, model: str | None, prompt: str, readonly: bool,
                  timeout_min: float, session: str | None,
                  effort: str | None = None) -> tuple[list[str], str | None]:
    values = {"model": model or "", "timeout": str(max(1, round(timeout_min))),
              "session": session or "", "effort": effort or ""}
    groups = [spec.get("base", []), spec.get("readonly" if readonly else "edit", []),
              spec.get("timeout_flag", [])]
    if effort and spec.get("effort_flag"):
        groups.append(spec["effort_flag"])
    if session:
        if not spec.get("continue"):
            fail("This backend has no 'continue' support. Send a fresh, self-contained brief instead.")
        groups.append(spec["continue"])
    # 'tail' holds positional arguments that must come last, such as codex's "-" (read stdin).
    groups.append(spec.get("tail", []))
    args: list[str] = []
    for group in groups:
        for token in group:
            if "{model}" in token and not model:
                # No model chosen: drop the placeholder and the flag before it, use the CLI default.
                if args and args[-1].startswith("-"):
                    args.pop()
                continue
            for key, value in values.items():
                token = token.replace("{" + key + "}", value)
            # The prompt goes in last so braces inside the brief are never treated as placeholders.
            args.append(token.replace("{prompt}", prompt))
    stdin = None
    exe = launcher(binary)
    if spec.get("prompt_via", "arg") == "stdin":
        stdin = prompt
    else:
        if len(prompt) > MAX_ARG_PROMPT:
            fail(f"Brief is too long to pass as an argument ({len(prompt)} chars, limit "
                 f"{MAX_ARG_PROMPT}). Shorten it, point the worker at files, or use a backend "
                 f"with prompt_via 'stdin'.")
        if exe[0].lower().endswith((".cmd", ".bat")) and "\n" in prompt:
            fail(f"{binary} is a cmd.exe launcher that cannot take a multi-line prompt. Point the "
                 f"backend's 'binary' at the real executable in the user config.")
    return [*exe, *args], stdin


def find_key(obj, keys: list[str]):
    """Depth-first search for the first non-empty value under any of `keys`, latest items first."""
    if isinstance(obj, dict):
        for k in keys:
            if obj.get(k) not in (None, "", [], {}):
                return obj[k]
        for v in obj.values():
            if (found := find_key(v, keys)) is not None:
                return found
    elif isinstance(obj, list):
        for v in reversed(obj):
            if (found := find_key(v, keys)) is not None:
                return found
    return None


def parse_output(stdout: str) -> list:
    """Accept a single JSON document or JSON Lines; ignore non-JSON chatter."""
    try:
        return [json.loads(stdout)]
    except json.JSONDecodeError:
        pass
    items = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def run_once(spec: dict, model: str | None, prompt: str, workdir: Path, args,
             worker_effort: str | None = None, tier_effort: str | None = None) -> dict:
    binary = resolve_binary(spec)
    if not binary:
        return {"status": "unavailable", "error": f"'{spec.get('binary')}' is not on PATH"}
    model = model or spec.get("default_model")
    effort, model = choose_effort(spec, model, args.effort, worker_effort, tier_effort)
    if note := spec.get("worker_note"):
        # Backend-specific limits go above the brief so the worker reads them before planning.
        prompt = prompt.replace("--- BRIEF ---", f"Important: {note}\n\n--- BRIEF ---", 1)
    cmd, stdin = build_command(spec, binary, model, prompt, args.readonly, args.timeout,
                               args.continue_session, effort)
    env = {**os.environ, **spec.get("env", {})}
    before = snapshot(workdir)
    started = datetime.now()
    try:
        proc = subprocess.run(cmd, cwd=workdir, input=stdin, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env,
                              timeout=args.timeout * 60 + GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "model": model, "files": diff_snapshots(before, snapshot(workdir)),
                "error": f"Worker exceeded {args.timeout} minutes and was stopped."}
    except OSError as e:
        return {"status": "unavailable", "error": str(e)}
    elapsed = (datetime.now() - started).total_seconds()
    files = diff_snapshots(before, snapshot(workdir))
    combined = f"{proc.stdout}\n{proc.stderr}"
    if spec.get("output", "json") == "text":
        items, report = [], proc.stdout.strip()[-REPORT_TAIL:] or None
    else:
        items = parse_output(proc.stdout)
        report = find_key(items, spec.get("report_keys", ["response", "result", "text"]))
    result = {
        "model": model,
        "effort": effort,
        "exit_code": proc.returncode,
        "duration_seconds": round(elapsed, 1),
        "session_id": find_key(items, spec.get("session_keys", ["session_id"])),
        "usage": find_key(items, spec.get("usage_keys", ["usage"])),
        "denied_actions": find_key(items, ["denied_actions"]),
        "files": files,
        "worker_report": report if isinstance(report, str) or report is None else json.dumps(report),
    }
    changed = any(files.values())
    if not report and not changed and QUOTA_RE.search(combined):
        result["status"] = "quota"
    elif proc.returncode != 0 and not changed:
        result["status"] = "failed"
    elif not report and not changed:
        result["status"] = "no_output"
    else:
        result["status"] = "done"
    if result["status"] != "done" or not report:
        result["output_tail"] = combined.strip()[-REPORT_TAIL:]
    return result


def cmd_run(args) -> int:
    brief_path = Path(args.brief)
    if not brief_path.is_file():
        fail(f"Brief file not found: {brief_path}")
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        fail(f"--cwd is not a folder: {cwd}")
    if args.timeout <= 0:
        fail("--timeout must be positive (minutes).")
    config = load_json(CONFIG_PATH)
    backends = load_backends(config)

    tier_effort = None
    if args.worker:
        candidates, tier = [args.worker], None
    else:
        tier = args.tier or "balanced"
        candidates = config.get("routes", {}).get(tier)
        if not candidates:
            fail(f"No route for tier '{tier}' in {CONFIG_PATH}. Run 'delegate.py init', add the "
                 f"tier to the config, or pass --worker.")
        tier_effort = config.get("tier_effort", DEFAULT_TIER_EFFORT).get(tier)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    brief = brief_path.read_text(encoding="utf-8-sig")
    (run_dir / "brief.md").write_text(brief, encoding="utf-8")
    prompt = (PREAMBLE_READONLY if args.readonly else PREAMBLE_EDIT) + brief

    workdir, branch, warnings = cwd, None, []
    if args.worktree and not args.readonly and not args.continue_session:
        workdir, _, branch, warnings = make_worktree(cwd, run_id)

    attempts: list[dict] = []
    final = None
    for worker in candidates:
        name, model, worker_effort = parse_worker(worker)
        spec = backends.get(name)
        if spec is None or not spec.get("enabled", True):
            reason = "unknown backend" if spec is None else "disabled in config"
            attempts.append({"worker": worker, "status": "unavailable", "error": reason})
            continue
        run_dir_for_worker, isolation = workdir, None
        if args.readonly and not spec.get("readonly_enforced", False):
            # This CLI cannot promise not to write, so give it a throwaway copy of the repo.
            if git_root(cwd) is None:
                attempts.append({"worker": worker, "status": "skipped",
                                 "error": "read-only is not enforced by this CLI and the folder is "
                                          "not a git repo, so it cannot be isolated"})
                continue
            run_dir_for_worker, isolation, _, _ = make_worktree(cwd, f"{run_id}-{len(attempts)}", detached=True)
        try:
            outcome = run_once(spec, model, prompt, run_dir_for_worker, args, worker_effort, tier_effort)
        finally:
            if isolation is not None:
                remove_worktree(isolation, cwd)
        if args.readonly and any(outcome.get("files", {}).values()):
            outcome["warning"] = ("Read-only run changed files." if isolation is None else
                                  "Worker tried to change files; they were discarded with its throwaway worktree.")
        attempts.append({"worker": worker, "status": outcome["status"], "error": outcome.get("error")})
        final = {"backend": name, **outcome}
        # Fall through to the next worker only for infrastructure problems. Poor quality is the
        # lead's call to make after review, not something to retry blindly.
        if outcome["status"] not in ("unavailable", "quota"):
            break

    result = {
        "schema": f"{SKILL_NAME}-result.v1",
        "run_id": run_id,
        "tier": tier,
        "mode": "readonly" if args.readonly else "edit",
        "workdir": str(workdir),
        "worktree_branch": branch,
        "warnings": warnings,
        "attempts": attempts,
        **(final or {"status": "unavailable"}),
    }
    if attempts and all(a["status"] in ("unavailable", "quota", "skipped") for a in attempts):
        result["status"] = "all_unavailable"
    (run_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["result_file"] = str(run_dir / "result.json")
    print(json.dumps(result, indent=2))
    return {"done": 0, "timeout": 4, "all_unavailable": 3}.get(result["status"], 1)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="delegate.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"{SKILL_NAME} {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="detect installed agent CLIs").set_defaults(func=cmd_doctor)
    models = sub.add_parser("models", help="list a CLI's models with suggested tiers")
    models.add_argument("backend", nargs="?")
    models.set_defaults(func=cmd_models)
    init = sub.add_parser("init", help="write the user config")
    init.add_argument("--lead", help="backend the lead agent itself runs on (excluded from routes)")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)
    run = sub.add_parser("run", help="delegate one task")
    run.add_argument("--brief", required=True, help="markdown file with the task brief")
    run.add_argument("--cwd", required=True, help="project folder the worker operates in")
    who = run.add_mutually_exclusive_group()
    who.add_argument("--tier", choices=TIERS, help="route to use (default: balanced)")
    who.add_argument("--worker", help="explicit BACKEND or BACKEND:MODEL, e.g. agy:gemini-3.8-flash-high")
    run.add_argument("--effort", choices=EFFORTS,
                     help="reasoning effort for this run; overrides the tier default and worker@effort")
    run.add_argument("--readonly", action="store_true", help="research only; no file changes")
    run.add_argument("--worktree", action="store_true", help="isolate edits in a new git worktree")
    # Most delegated tasks finish in 3-10 minutes; 20 leaves headroom for large refactors.
    run.add_argument("--timeout", type=float, default=20, help="minutes before the worker is stopped")
    run.add_argument("--continue", dest="continue_session", metavar="SESSION_ID",
                     help="send this brief as a follow-up in an earlier worker session")
    run.set_defaults(func=cmd_run)
    land = sub.add_parser("land", help="bring accepted worktree changes into the user's checkout")
    land.add_argument("--workdir", required=True, help="the workdir from the run result")
    land.add_argument("--commit", action="store_true",
                      help="commit and merge instead of leaving uncommitted changes")
    land.add_argument("-m", "--message", help="commit message (with --commit)")
    land.set_defaults(func=cmd_land)
    discard = sub.add_parser("discard", help="remove a worktree without landing it")
    discard.add_argument("--workdir", required=True)
    discard.set_defaults(func=cmd_discard)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
