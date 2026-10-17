"""Tests for foreman's delegate.py, using fake_agent.py as a stand-in worker CLI.

Run from the repo root:  python -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins" / "foreman" / "skills" / "foreman"
SCRIPT = SKILL / "scripts" / "delegate.py"
FAKE = Path(__file__).resolve().parent / "fake_agent.py"

_spec = importlib.util.spec_from_file_location("delegate", SCRIPT)
delegate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(delegate)

GIT_ID = ["-c", "user.name=test", "-c", "user.email=test@example.com"]


def fake_backend(**overrides):
    spec = {
        "binary": sys.executable,
        "base": [str(FAKE), "--prompt", "{prompt}", "--model", "{model}"],
        "edit": [],
        "readonly": [],
        "readonly_enforced": True,
        "report_keys": ["response"],
        "session_keys": ["session_id"],
        "usage_keys": ["usage"],
        "models_args": [str(FAKE), "models"],
    }
    spec.update(overrides)
    return spec


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.config = self.tmp / "config.json"
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("# Task: write out.txt\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def write_config(self, routes, backends):
        self.config.write_text(json.dumps({"routes": routes, "backends": backends}), encoding="utf-8")

    def cli(self, *args, **env):
        identity = {"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
                    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com"}
        full_env = {**os.environ, **identity, "FOREMAN_CONFIG": str(self.config), "FOREMAN_GRACE_SECONDS": "1",
                    **{k: str(v) for k, v in env.items()}}
        full_env.pop("CLAUDECODE", None)
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              encoding="utf-8", env=full_env, timeout=120)
        try:
            return proc.returncode, json.loads(proc.stdout)
        except json.JSONDecodeError:
            self.fail(f"Non-JSON output (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}")

    def run_task(self, *extra, **env):
        return self.cli("run", "--brief", str(self.brief), "--cwd", str(self.work), *extra, **env)

    def make_repo(self):
        (self.work / "README.md").write_text("demo\n", encoding="utf-8")
        for cmd in (["init", "-q"], ["add", "-A"], [*GIT_ID, "commit", "-qm", "init"]):
            subprocess.run(["git", *cmd], cwd=self.work, check=True, capture_output=True)


class TestUnits(unittest.TestCase):
    rules = delegate.builtin_data()["_tier_rules"]

    def test_classify_vendor_names(self):
        cases = {
            "claude-haiku-4-5": "light", "claude-sonnet-4-6": "balanced", "claude-opus-4-6-thinking": "frontier",
            "gemini-3.5-flash-lite": "light", "gemini-3.8-flash-high": "balanced", "gemini-3.1-pro-preview": "frontier",
            "gemini-3.8-flash-low": "light", "gpt-5.4-nano": "light", "gpt-5.4-mini": "light", "gpt-6-astra": "frontier",
            "qwen3.8-max": "frontier", "minimax-m3": "balanced", "gpt-oss-120b-medium": "balanced",
        }
        for model, tier in cases.items():
            with self.subTest(model=model):
                self.assertEqual(delegate.classify(model, self.rules), tier)

    def test_missing_model_drops_flag(self):
        spec = {"base": ["exec", "-m", "{model}", "{prompt}"]}
        cmd, stdin = delegate.build_command(spec, "tool", None, "hi", False, 5, None)
        self.assertEqual(cmd, ["tool", "exec", "hi"])
        self.assertIsNone(stdin)

    def test_stdin_prompt_and_model(self):
        spec = {"base": ["-m", "{model}"], "prompt_via": "stdin", "edit": ["--edit"]}
        cmd, stdin = delegate.build_command(spec, "tool", "m1", "line1\nline2", False, 5, None)
        self.assertEqual(cmd, ["tool", "-m", "m1", "--edit"])
        self.assertEqual(stdin, "line1\nline2")

    def test_prompt_with_braces_is_kept_verbatim(self):
        spec = {"base": ["{prompt}"]}
        cmd, _ = delegate.build_command(spec, "tool", None, 'use {"a": 1} and {model}', False, 5, None)
        self.assertEqual(cmd[1], 'use {"a": 1} and {model}')

    def test_parse_worker_with_effort(self):
        self.assertEqual(delegate.parse_worker("agy:gemini-3.8-flash@high"), ("agy", "gemini-3.8-flash", "high"))
        self.assertEqual(delegate.parse_worker("codex@low"), ("codex", None, "low"))
        self.assertEqual(delegate.parse_worker("x:vertex/model@2024"), ("x", "vertex/model@2024", None))

    def test_clamp_effort(self):
        self.assertEqual(delegate.clamp_effort("max", ["low", "medium", "high"]), "high")
        self.assertEqual(delegate.clamp_effort("minimal", ["low", "medium", "high"]), "low")
        self.assertEqual(delegate.clamp_effort("medium", ["low", "high"]), "low")
        self.assertEqual(delegate.clamp_effort("high", []), "high")

    def test_choose_effort_priority(self):
        spec = {"effort_flag": ["--effort", "{effort}"], "efforts": ["low", "medium", "high"]}
        choose = delegate.choose_effort
        self.assertEqual(choose(spec, "m", "high", "low", "medium"), ("high", "m"))
        self.assertEqual(choose(spec, "m", None, "low", "medium"), ("low", "m"))
        self.assertEqual(choose(spec, "m", None, None, "medium"), ("medium", "m"))
        # Model name already carries an effort: the tier default must not override it.
        self.assertEqual(choose(spec, "gemini-3.8-flash-high", None, None, "medium"), (None, "gemini-3.8-flash-high"))
        # ...but an explicit request still applies.
        self.assertEqual(choose(spec, "gemini-3.8-flash-high", "low", None, "medium"), ("low", "gemini-3.8-flash-high"))
        # "max" in a model name is a tier, not an effort.
        self.assertEqual(choose(spec, "qwen3.8-max", None, None, "high"), ("high", "qwen3.8-max"))
        # Backends without an effort setting ignore it.
        self.assertEqual(choose({}, "m", "high", None, None), (None, "m"))

    def test_agy_effort_rules(self):
        # Verified live with agy 1.4.0: '--effort' conflicts with an effort-suffixed id, works with
        # the base id, and is rejected for the Claude models Antigravity hosts.
        agy = delegate.builtin_data()["agy"]
        choose = delegate.choose_effort
        self.assertEqual(choose(agy, "gemini-3.8-flash-medium", "high", None, None), ("high", "gemini-3.8-flash"))
        self.assertEqual(choose(agy, "gemini-3.8-flash-high", None, None, "medium"), (None, "gemini-3.8-flash-high"))
        self.assertEqual(choose(agy, "claude-opus-4-6-thinking", "low", None, "high"), (None, "claude-opus-4-6-thinking"))

    def test_effort_flag_and_tail_order(self):
        spec = delegate.builtin_data()["codex"]
        cmd, stdin = delegate.build_command(spec, "codex", "m1", "brief", False, 5, None, "high")
        self.assertEqual(cmd[-1], "-")
        self.assertIn("model_reasoning_effort=high", cmd)
        self.assertEqual(stdin, "brief")

    def test_find_key_prefers_latest_item(self):
        items = [{"text": "early"}, {"item": {"text": "final"}}]
        self.assertEqual(delegate.find_key(items, ["text"]), "final")

    def test_parse_output_json_lines(self):
        out = 'noise\n{"a": 1}\n{"b": 2}\n'
        self.assertEqual(delegate.parse_output(out), [{"a": 1}, {"b": 2}])

    @unittest.skipUnless(os.name == "nt", "npm .cmd shims exist only on Windows")
    def test_npm_shim_unwrapped(self):
        with tempfile.TemporaryDirectory() as d:
            exe_shim = Path(d) / "tool.cmd"
            exe_shim.write_text('@ECHO off\r\n"%dp0%\\node_modules\\tool\\bin\\tool.exe"   %*\r\n')
            self.assertTrue(delegate.launcher(str(exe_shim))[0].endswith("tool.exe"))
            js_shim = Path(d) / "js.cmd"
            js_shim.write_text('SET "_prog=node"\r\n"%_prog%"  "%dp0%\\node_modules\\js\\cli.js" %*\r\n')
            cmd = delegate.launcher(str(js_shim))
            if len(cmd) == 2:  # node is installed
                self.assertTrue(cmd[1].endswith("cli.js"))


class TestRun(CliTestCase):
    def test_success_reports_files_and_report(self):
        self.write_config({"balanced": ["fake:acme-1"]}, {"fake": fake_backend()})
        code, res = self.run_task()
        self.assertEqual(code, 0, res)
        self.assertEqual(res["status"], "done")
        self.assertEqual(res["files"]["created"], ["out.txt"])
        self.assertIn("SUMMARY", res["worker_report"])
        self.assertEqual(res["session_id"], "s-1")
        self.assertEqual(res["model"], "acme-1")

    def test_quota_falls_back_to_next_worker(self):
        self.write_config({"balanced": ["broke", "fake"]},
                          {"broke": fake_backend(env={"FAKE_MODE": "quota"}), "fake": fake_backend()})
        code, res = self.run_task()
        self.assertEqual(code, 0, res)
        self.assertEqual([a["status"] for a in res["attempts"]], ["quota", "done"])
        self.assertEqual(res["backend"], "fake")

    def test_missing_binary_falls_back(self):
        self.write_config({"balanced": ["ghost", "fake"]},
                          {"ghost": fake_backend(binary="definitely-not-installed-xyz"), "fake": fake_backend()})
        code, res = self.run_task()
        self.assertEqual(code, 0, res)
        self.assertEqual(res["attempts"][0]["status"], "unavailable")

    def test_failure_does_not_fall_back(self):
        self.write_config({"balanced": ["bad", "fake"]},
                          {"bad": fake_backend(env={"FAKE_MODE": "fail"}), "fake": fake_backend()})
        code, res = self.run_task()
        self.assertEqual(code, 1)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(len(res["attempts"]), 1)

    def test_all_unavailable(self):
        self.write_config({"balanced": ["broke"]}, {"broke": fake_backend(env={"FAKE_MODE": "quota"})})
        code, res = self.run_task()
        self.assertEqual(code, 3)
        self.assertEqual(res["status"], "all_unavailable")

    def test_no_output(self):
        self.write_config({"balanced": ["fake"]}, {"fake": fake_backend(env={"FAKE_MODE": "nothing"})})
        code, res = self.run_task()
        self.assertEqual(code, 1)
        self.assertEqual(res["status"], "no_output")

    def test_timeout(self):
        self.write_config({"balanced": ["fake"]}, {"fake": fake_backend(env={"FAKE_MODE": "slow"})})
        code, res = self.run_task("--timeout", "0.01")
        self.assertEqual(code, 4)
        self.assertEqual(res["status"], "timeout")

    def test_disabled_backend_is_skipped(self):
        self.write_config({"balanced": ["off", "fake"]}, {"off": fake_backend(enabled=False), "fake": fake_backend()})
        code, res = self.run_task()
        self.assertEqual(code, 0)
        self.assertEqual(res["attempts"][0]["error"], "disabled in config")

    def test_explicit_worker_and_tier(self):
        self.write_config({"light": ["fake:small-1"]}, {"fake": fake_backend()})
        code, res = self.run_task("--tier", "light")
        self.assertEqual((code, res["model"], res["tier"]), (0, "small-1", "light"))
        code, res = self.run_task("--worker", "fake:other-2")
        self.assertEqual((code, res["model"]), (0, "other-2"))

    def test_tier_effort_reaches_the_cli(self):
        log = self.tmp / "args.json"
        effortful = fake_backend(effort_flag=["--effort", "{effort}"], efforts=["low", "medium", "high"])
        self.config.write_text(json.dumps({"routes": {"frontier": ["fake:acme-1"], "light": ["fake:acme-1@medium"]},
                                           "tier_effort": {"frontier": "max"},
                                           "backends": {"fake": effortful}}), encoding="utf-8")
        code, res = self.run_task("--tier", "frontier", FAKE_ARGS_LOG=log)
        self.assertEqual((code, res["effort"]), (0, "high"))  # max clamped to the CLI's highest
        self.assertIn("--effort", json.loads(log.read_text())["args"])
        code, res = self.run_task("--tier", "light", FAKE_ARGS_LOG=log)
        self.assertEqual(res["effort"], "medium")  # worker@effort beats the default
        code, res = self.run_task("--tier", "light", "--effort", "low", FAKE_ARGS_LOG=log)
        self.assertEqual(res["effort"], "low")  # --effort beats both

    def test_missing_tier_route_is_a_usage_error(self):
        self.write_config({"balanced": ["fake"]}, {"fake": fake_backend()})
        code, res = self.run_task("--tier", "frontier")
        self.assertEqual(code, 2)

    def test_stdin_backend_receives_full_brief(self):
        log = self.tmp / "args.json"
        self.write_config({"balanced": ["fake"]},
                          {"fake": fake_backend(base=[str(FAKE), "--stdin"], prompt_via="stdin")})
        code, _ = self.run_task(FAKE_ARGS_LOG=log)
        self.assertEqual(code, 0)
        self.assertIn("# Task: write out.txt", json.loads(log.read_text())["prompt"])

    def test_worker_note_is_placed_before_brief(self):
        log = self.tmp / "args.json"
        self.write_config({"balanced": ["fake"]}, {"fake": fake_backend(worker_note="NO SHELL")})
        self.run_task(FAKE_ARGS_LOG=log)
        prompt = json.loads(log.read_text())["prompt"]
        self.assertLess(prompt.index("NO SHELL"), prompt.index("# Task"))


class TestGit(CliTestCase):
    def test_worktree_isolates_edits(self):
        self.make_repo()
        self.write_config({"balanced": ["fake"]}, {"fake": fake_backend()})
        code, res = self.run_task("--worktree")
        self.assertEqual(code, 0, res)
        self.assertFalse((self.work / "out.txt").exists(), "main checkout must stay untouched")
        self.assertTrue((Path(res["workdir"]) / "out.txt").exists())
        branches = subprocess.run(["git", "branch", "--list", res["worktree_branch"]], cwd=self.work,
                                  capture_output=True, text=True).stdout
        self.assertIn(res["worktree_branch"], branches)
        subprocess.run(["git", "worktree", "remove", "--force", res["workdir"]], cwd=self.work)

    def _run_in_worktree(self):
        self.make_repo()
        self.write_config({"balanced": ["fake"]}, {"fake": fake_backend()})
        code, res = self.run_task("--worktree")
        self.assertEqual(code, 0, res)
        return res

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.work, capture_output=True, text=True).stdout

    def test_land_leaves_uncommitted_changes_and_cleans_up(self):
        res = self._run_in_worktree()
        head = self._git("rev-parse", "HEAD")
        code, landed = self.cli("land", "--workdir", res["workdir"])
        self.assertEqual((code, landed["status"], landed["committed"]), (0, "landed", False))
        self.assertTrue((self.work / "out.txt").exists())
        self.assertEqual(self._git("rev-parse", "HEAD"), head, "land must not commit by default")
        self.assertFalse(Path(res["workdir"]).exists())
        self.assertEqual(self._git("branch", "--list", res["worktree_branch"]).strip(), "")

    def test_land_with_commit_merges(self):
        res = self._run_in_worktree()
        code, landed = self.cli("land", "--workdir", res["workdir"], "--commit", "-m", "add out")
        self.assertEqual((code, landed["committed"]), (0, True))
        self.assertIn("add out", self._git("log", "-1", "--format=%s"))
        self.assertEqual(self._git("status", "--porcelain").strip(), "")

    def test_land_commit_needs_message(self):
        res = self._run_in_worktree()
        code, out = self.cli("land", "--workdir", res["workdir"], "--commit")
        self.assertEqual(code, 2)
        self.assertTrue(Path(res["workdir"]).exists(), "worktree must be kept on error")
        self.cli("discard", "--workdir", res["workdir"])

    def test_land_refuses_conflicting_changes(self):
        res = self._run_in_worktree()
        (self.work / "out.txt").write_text("someone else's file\n")
        code, out = self.cli("land", "--workdir", res["workdir"])
        self.assertEqual(code, 2)
        self.assertEqual((self.work / "out.txt").read_text(), "someone else's file\n")
        self.assertTrue(Path(res["workdir"]).exists())
        self.cli("discard", "--workdir", res["workdir"])

    def test_discard_removes_worktree_and_branch(self):
        res = self._run_in_worktree()
        code, out = self.cli("discard", "--workdir", res["workdir"])
        self.assertEqual((code, out["status"]), (0, "discarded"))
        self.assertFalse(Path(res["workdir"]).exists())
        self.assertFalse((self.work / "out.txt").exists())
        self.assertEqual(self._git("branch", "--list", res["worktree_branch"]).strip(), "")

    def test_land_rejects_main_checkout(self):
        self.make_repo()
        code, out = self.cli("land", "--workdir", str(self.work))
        self.assertEqual(code, 2)
        self.assertIn("main checkout", out["error"])

    def test_unenforced_readonly_runs_in_throwaway_worktree(self):
        self.make_repo()
        self.write_config({"balanced": ["fake"]}, {"fake": fake_backend(readonly_enforced=False)})
        code, res = self.run_task("--readonly")
        self.assertEqual(code, 0, res)
        self.assertFalse((self.work / "out.txt").exists())
        self.assertIn("discarded", res.get("warning", ""))
        worktrees = subprocess.run(["git", "worktree", "list"], cwd=self.work, capture_output=True, text=True).stdout
        self.assertEqual(len(worktrees.strip().splitlines()), 1, "throwaway worktree must be removed")

    def test_unenforced_readonly_outside_git_is_skipped(self):
        self.write_config({"balanced": ["fake"]}, {"fake": fake_backend(readonly_enforced=False)})
        code, res = self.run_task("--readonly")
        self.assertEqual(code, 3)
        self.assertEqual(res["attempts"][0]["status"], "skipped")


class TestSetup(CliTestCase):
    def test_init_builds_tier_routes_from_model_list(self):
        # init uses only built-in backends, so point one at the fake agent through the config path
        # by checking the classification it would produce instead.
        models = delegate.list_models(fake_backend())
        self.assertEqual(models, ["acme-3-pro", "acme-3-flash", "acme-3-flash-lite", "acme-3-mini-high"])
        tiers = {m: delegate.classify(m, delegate.builtin_data()["_tier_rules"]) for m in models}
        self.assertEqual(tiers, {"acme-3-pro": "frontier", "acme-3-flash": "balanced",
                                 "acme-3-flash-lite": "light", "acme-3-mini-high": "light"})

    def test_doctor_and_models_run(self):
        self.write_config({"balanced": ["fake"]}, {"fake": fake_backend()})
        code, res = self.cli("doctor")
        self.assertEqual(code, 0)
        self.assertTrue(res["backends"]["fake"]["installed"])
        code, res = self.cli("models", "fake")
        self.assertEqual(res["fake"]["acme-3-pro"], "frontier")

    def test_init_refuses_to_overwrite(self):
        self.write_config({}, {})
        code, res = self.cli("init")
        self.assertEqual(code, 2)
        self.assertIn("already exists", res["error"])

    def test_init_skips_lead(self):
        code, res = self.cli("init", "--lead", "agy")
        self.assertEqual(code, 0, res)
        for workers in res["routes"].values():
            self.assertFalse(any(w.split(":")[0] == "agy" for w in workers))


class TestPackaging(unittest.TestCase):
    def frontmatter(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
        self.assertIsNotNone(m, "SKILL.md must start with YAML frontmatter")
        fields = dict(re.findall(r"^(\w[\w-]*): (.*)$", m.group(1), re.M))
        return fields, m.group(2)

    def test_skill_frontmatter_follows_spec(self):
        fields, body = self.frontmatter()
        self.assertRegex(fields["name"], r"^[a-z0-9-]{1,64}$")
        self.assertNotRegex(fields["name"], r"anthropic|claude")
        self.assertLessEqual(len(fields["description"]), 1024)
        self.assertNotRegex(fields["description"], r"<[^>]+>")
        self.assertLess(body.count("\n"), 500)

    def test_names_match_across_manifests(self):
        fields, _ = self.frontmatter()
        plugin = json.loads((ROOT / "plugins" / "foreman" / ".claude-plugin" / "plugin.json").read_text())
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(plugin["name"], fields["name"])
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])
        self.assertEqual(plugin["version"], delegate.VERSION)

    def test_references_exist(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for ref in re.findall(r"\]\((references/[^)]+)\)", text):
            self.assertTrue((SKILL / ref).is_file(), ref)

    def test_backends_are_well_formed(self):
        data = delegate.builtin_data()
        names = [k for k in data if not k.startswith("_")]
        self.assertEqual(sorted(names), sorted(data["_preference"]))
        for name in names:
            spec = data[name]
            with self.subTest(backend=name):
                self.assertTrue(spec.get("binary"))
                self.assertIsInstance(spec.get("base"), list)
                via_arg = spec.get("prompt_via", "arg") == "arg"
                self.assertEqual(via_arg, any("{prompt}" in t for t in spec["base"]))
                self.assertIn(spec.get("output", "json"), ("json", "text"))


if __name__ == "__main__":
    unittest.main()
