#!/usr/bin/env python3
"""Opt-in sync of run summaries to the we-mutate portal (spec §9.3/§10.3).

What leaves the machine: project name, adapter, run id/timestamp, commit,
branch, scope, the metric block, the security counts, and the impact
counters. Never source code, file paths, or mutant fragments — enforced
here by constructing the payload from scratch rather than forwarding the
run document.

Subcommands:
  enable --token T [--server URL] [--project NAME]    store config in .wemutate/
  disable
  push --run PATH                                     sync one run document
  badge                                               request the Well Tested Code badge

Exit codes: 0 ok · 2 not configured / invalid input · 4 server rejected
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Production portal by default so `sync.py enable --token …` reaches the real
# service without an explicit --server (override with --server for local dev).
DEFAULT_SERVER = "https://wemutate.dev"


def _cfg_path(root: Path) -> Path:
    return root / ".wemutate" / "sync.json"


def _load_cfg(root: Path) -> dict | None:
    p = _cfg_path(root)
    return json.loads(p.read_text()) if p.is_file() else None


def _git(args: list[str]) -> str | None:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (subprocess.CalledProcessError, OSError):
        return None


def _post(url: str, token: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"detail": str(e)}
    except urllib.error.URLError as e:
        return 0, {"detail": f"server unreachable: {e.reason}"}


def cmd_enable(root: Path, args) -> int:
    project = args.project or root.resolve().name
    cfg = {"server": args.server.rstrip("/"), "token": args.token,
           "project": project}
    p = _cfg_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    try:
        p.chmod(0o600)
    except OSError:
        pass
    print(json.dumps({"enabled": True, "server": cfg["server"], "project": project}))
    return 0


def cmd_disable(root: Path, _args) -> int:
    p = _cfg_path(root)
    if p.is_file():
        p.unlink()
    print(json.dumps({"enabled": False}))
    return 0


def _impact(root: Path) -> dict | None:
    state_file = root / ".wemutate" / "state.json"
    if not state_file.is_file():
        return None
    state = json.loads(state_file.read_text())
    triage = list(state.get("triage", {}).values())
    dead = [e for e in triage if e.get("resolution") == "dead_code"]
    return {
        "bugs_found": sum(e.get("resolution") == "real_bug" for e in triage),
        "test_gaps_closed": sum(e.get("resolution") == "test_gap"
                                and e.get("fix_applied") for e in triage),
        "dead_code_lines_removed": sum(e.get("lines_removed") or 0 for e in dead),
    }


def cmd_push(root: Path, args) -> int:
    cfg = _load_cfg(root)
    if not cfg:
        print("sync not enabled (run sync.py enable --token …)", file=sys.stderr)
        return 2
    run_doc = json.loads(Path(args.run).read_text())
    if run_doc.get("wm_version") != "1":
        print("not a WM v1 run document", file=sys.stderr)
        return 2
    totals = dict(run_doc["totals"])
    security = totals.pop("security", None)
    totals.pop("by_kind", None)  # keep the wire payload to plain counters
    payload = {
        "project": cfg["project"],
        "adapter": run_doc["run"]["engine"]["adapter"],
        "run_id": run_doc["run"]["id"],
        "timestamp": run_doc["run"]["timestamp"],
        "commit_sha": _git(["rev-parse", "--short", "HEAD"]),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "scope": run_doc["run"]["scope"]["mode"],
        "totals": totals,
        "security": security,
        "impact": _impact(root),
    }
    status, body = _post(f"{cfg['server']}/v1/runs", cfg["token"], payload)
    print(json.dumps({"status": status, **body}))
    return 0 if status == 200 else 4


def cmd_badge(root: Path, _args) -> int:
    cfg = _load_cfg(root)
    if not cfg:
        print("sync not enabled", file=sys.stderr)
        return 2
    status, body = _post(f"{cfg['server']}/v1/badges", cfg["token"],
                         {"project": cfg["project"],
                          "commit_sha": _git(["rev-parse", "--short", "HEAD"])})
    if status == 200:
        body["badge_url"] = cfg["server"] + body["badge_url"]
        body["verify_url"] = cfg["server"] + body["verify_url"]
        body["markdown"] = (f"[![WeMutate Well Tested Code]({body['badge_url']})]"
                            f"({body['verify_url']})")
    print(json.dumps({"status": status, **body}, indent=2))
    return 0 if status == 200 else 4


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("enable")
    p.add_argument("--token", required=True)
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--project")
    sub.add_parser("disable")
    p = sub.add_parser("push")
    p.add_argument("--run", required=True)
    sub.add_parser("badge")
    args = ap.parse_args()
    root = Path(args.project_root)
    return {"enable": cmd_enable, "disable": cmd_disable,
            "push": cmd_push, "badge": cmd_badge}[args.cmd](root, args)


if __name__ == "__main__":
    sys.exit(main())
