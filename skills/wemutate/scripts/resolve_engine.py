#!/usr/bin/env python3
"""Engine resolution + download (we-mutate registry client, spec §11).

Resolution order:
  1. a locally present engine — the monorepo, or an engine vendored into the
     plugin (bundled-install case);
  2. a previously downloaded engine cached under ~/.wemutate/engines/<version>/;
  3. otherwise, download from the registry: GET <server>/v1/resolve for this
     platform+python (token-gated), verify the SHA-256, extract to the cache,
     and use that.

So a *thin* skill (no engine shipped) fetches its engine on first run and
reuses it thereafter (works offline once cached). A bundled install just uses
its vendored engine and never calls the registry.

Registry config comes from (in order): --server/--token flags, the
WEMUTATE_REGISTRY / WEMUTATE_TOKEN env vars, or the project's
.wemutate/sync.json (written by sync.py enable).

Usage:
  resolve_engine.py ADAPTER [--platform P] [--python X.Y]
                    [--project-root DIR] [--server URL] [--token T] [--refresh]
Exit codes: 0 resolved · 2 unavailable (unknown adapter / no engine + no registry)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as _platform
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ADAPTERS = {"jvm-maven", "jvm-gradle", "js-ts", "c-cpp", "python"}
PLANNED = {"rust"}
CACHE = Path.home() / ".wemutate" / "engines"


def _has_engine(p: Path) -> bool:
    """A directory is an engine home if it has adapters/ and a wm module
    (source dir or compiled wm.* native module)."""
    return (p / "adapters").is_dir() and (
        (p / "wm").is_dir() or any(p.glob("wm.*.so")) or (p / "wm.pyd").is_file())


def local_home(start: Path) -> Path | None:
    env = os.environ.get("WEMUTATE_HOME")
    if env and _has_engine(Path(env)):
        return Path(env).resolve()
    p = start.resolve()
    for _ in range(10):
        if _has_engine(p):
            return p
        if p.parent == p:
            break
        p = p.parent
    return None


def cached_home() -> Path | None:
    if not CACHE.is_dir():
        return None
    cands = [d for d in CACHE.iterdir() if d.is_dir() and _has_engine(d)]
    return sorted(cands, key=lambda d: d.name)[-1] if cands else None


def registry_config(project_root: Path, server_arg, token_arg):
    server = server_arg or os.environ.get("WEMUTATE_REGISTRY")
    token = token_arg or os.environ.get("WEMUTATE_TOKEN")
    cfg = project_root / ".wemutate" / "sync.json"
    if cfg.is_file():
        data = json.loads(cfg.read_text())
        server = server or data.get("server")
        token = token or data.get("token")
    return server, token


def _get(url: str, token: str, timeout: int) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(server: str, token: str, plat: str, py: str) -> tuple[Path, dict]:
    server = server.rstrip("/")
    meta = json.loads(_get(f"{server}/v1/resolve?platform={plat}&python={py}",
                           token, 30))
    dl = meta["url"]
    if dl.startswith("/"):
        dl = server + dl
    blob = _get(dl, token, 180)
    got = hashlib.sha256(blob).hexdigest()
    if got != meta["sha256"]:
        raise SystemExit(f"checksum mismatch (expected {meta['sha256']}, got {got}) "
                         "— refusing to install")
    dest = CACHE / meta["version"]
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp:
        tmp.write(blob)
        tmp.flush()
        with tarfile.open(tmp.name) as tf:
            try:
                tf.extractall(dest, filter="data")   # py3.12+ safe extraction
            except TypeError:
                tf.extractall(dest)
    return dest, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("adapter")
    ap.add_argument("--platform",
                    default=f"{_platform.system().lower()}-{_platform.machine()}")
    ap.add_argument("--python", default=".".join(map(str, sys.version_info[:2])))
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--server")
    ap.add_argument("--token")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore cache/local and re-download from the registry")
    args = ap.parse_args()

    if args.adapter in PLANNED:
        print(json.dumps({"error": f"adapter {args.adapter!r} is planned but "
                          "not yet available"}), file=sys.stderr)
        return 2
    if args.adapter not in ADAPTERS:
        print(json.dumps({"error": f"unknown adapter {args.adapter!r}",
                          "available": sorted(ADAPTERS)}), file=sys.stderr)
        return 2

    version, source = None, None
    home = None
    if not args.refresh:
        home = local_home(Path(__file__).parent)
        source = "local" if home else None
        if home is None:
            home = cached_home()
            source = "cache" if home else None

    if home is None:
        server, token = registry_config(Path(args.project_root), args.server, args.token)
        if not (server and token):
            print(json.dumps({
                "error": "no engine available locally and the registry is not "
                         "configured. Provide --server/--token, set "
                         "WEMUTATE_REGISTRY/WEMUTATE_TOKEN, or run "
                         "sync.py enable --token …."}), file=sys.stderr)
            return 2
        try:
            home, meta = download(server, token, args.platform, args.python)
        except urllib.error.HTTPError as e:
            print(json.dumps({"error": f"registry {e.code}: {e.reason}"}),
                  file=sys.stderr)
            return 2
        except urllib.error.URLError as e:
            print(json.dumps({"error": f"registry unreachable: {e.reason}"}),
                  file=sys.stderr)
            return 2
        version, source = meta["version"], "registry"

    engine = home / "adapters" / args.adapter / "wm-engine"
    if not engine.is_file():
        print(json.dumps({"error": f"engine binary missing at {engine}"}),
              file=sys.stderr)
        return 2
    out = {
        "adapter": args.adapter,
        "platform": args.platform,
        "python": args.python,
        "source": source,                       # local | cache | registry
        "path": str(engine),
        "sha256": hashlib.sha256(engine.read_bytes()).hexdigest(),
        "licenses_via": f"{engine} licenses",
    }
    if version:
        out["version"] = version
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
