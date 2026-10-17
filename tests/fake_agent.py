"""A stand-in worker CLI for tests. Behaviour is chosen with `--mode X` (or FAKE_MODE):

ok       write the file named by FAKE_FILE (default out.txt) and print a JSON report
quota    print a quota error and exit 1
fail     print an error and exit 3
nothing  print an empty JSON response
slow     sleep longer than any test timeout
models   print a model list (used as the 'models' subcommand)
"""
import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
if args[:1] == ["models"]:
    print("Fetching available models...")
    for m in ("acme-3-pro", "acme-3-flash", "acme-3-flash-lite", "acme-3-mini-high"):
        print(f"{m}\t{m.title()}")
    sys.exit(0)

mode = args[args.index("--mode") + 1] if "--mode" in args else os.environ.get("FAKE_MODE", "ok")
prompt = sys.stdin.read() if "--stdin" in args else (args[args.index("--prompt") + 1] if "--prompt" in args else "")
Path(os.environ.get("FAKE_ARGS_LOG", os.devnull)).write_text(json.dumps({"args": args, "prompt": prompt}))

if mode == "quota":
    print("Error: You exceeded your current quota (429).", file=sys.stderr)
    sys.exit(1)
if mode == "fail":
    print("Error: model crashed", file=sys.stderr)
    sys.exit(3)
if mode == "nothing":
    print(json.dumps({"response": "", "session_id": "s-0"}))
    sys.exit(0)
if mode == "slow":
    time.sleep(30)
    sys.exit(0)

Path(os.environ.get("FAKE_FILE", "out.txt")).write_text("written by fake agent\n")
print(json.dumps({"response": "SUMMARY: wrote the file", "session_id": "s-1",
                  "usage": {"total_tokens": 42}}))
