#!/usr/bin/env python3
"""Self-serve account signup (free during the beta).

Two steps, driven conversationally by the skill:

  signup.py request --email you@example.com            # emails a 6-digit code
  signup.py verify  --email you@example.com --code 123456

`verify` exchanges the code for an API token and saves it (mode 0600) to
~/.wemutate/credentials.json, where resolve_engine.py and the engine's
runtime licence check both look. One signup covers every project on this
machine.

Exit codes: 0 ok · 2 request/verify failed (details as JSON on stderr).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CREDENTIALS = Path.home() / ".wemutate" / "credentials.json"
DEFAULT_SERVER = "https://wemutate.dev"


def _post(server: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        server.rstrip("/") + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "wemutate-skill/0.1.0"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _fail(message: str, hint: str = "") -> int:
    out = {"error": message}
    if hint:
        out["hint"] = hint
    print(json.dumps(out), file=sys.stderr)
    return 2


def cmd_request(args) -> int:
    try:
        _post(args.server, "/v1/signup", {"email": args.email})
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        return _fail(f"signup request failed ({e.code})", detail)
    except (urllib.error.URLError, OSError) as e:
        return _fail(f"signup service unreachable: {e}")
    print(json.dumps({"sent": True, "email": args.email,
                      "next": "verify with the 6-digit code from the email"}))
    return 0


def cmd_verify(args) -> int:
    try:
        data = _post(args.server, "/v1/signup/verify",
                     {"email": args.email, "code": args.code})
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return _fail("invalid or expired code",
                         "request a fresh code with signup.py request")
        detail = e.read().decode(errors="replace")[:200]
        return _fail(f"verification failed ({e.code})", detail)
    except (urllib.error.URLError, OSError) as e:
        return _fail(f"signup service unreachable: {e}")

    CREDENTIALS.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS.write_text(json.dumps({
        "server": args.server.rstrip("/"), "email": args.email,
        "token": data["token"], "plan": data.get("plan", "beta-free")},
        indent=2))
    os.chmod(CREDENTIALS, 0o600)
    print(json.dumps({"registered": True, "email": args.email,
                      "plan": data.get("plan", "beta-free"),
                      "credentials": str(CREDENTIALS)}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_req = sub.add_parser("request")
    p_req.add_argument("--email", required=True)
    p_req.add_argument("--server", default=DEFAULT_SERVER)
    p_ver = sub.add_parser("verify")
    p_ver.add_argument("--email", required=True)
    p_ver.add_argument("--code", required=True)
    p_ver.add_argument("--server", default=DEFAULT_SERVER)
    args = ap.parse_args()
    return cmd_request(args) if args.cmd == "request" else cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
