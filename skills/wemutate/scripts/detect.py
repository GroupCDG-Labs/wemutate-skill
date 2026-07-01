#!/usr/bin/env python3
"""Language/build detection for the wemutate skill (spec §2.2).

Walks the project tree for build manifests and emits a JSON list of mutation
targets — one per detected (directory, adapter) pair. Detection never writes
anything and never guesses: ambiguity is surfaced for the skill to ask about.

Usage: detect.py [ROOT] [--max-depth N]

Output: {"targets": [{path, adapter, language, build_file, hints{}}], "notes": []}
Exit codes: 0 targets found · 2 nothing detected
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "target", "build", "dist", "out",
             ".gradle", ".idea", "vendor", "venv", ".venv", "__pycache__",
             "archive"}

# Detection rules in precedence order within a directory (spec §2.2).
RULES = (
    ("pom.xml", "jvm-maven", "java"),
    ("build.gradle", "jvm-gradle", "java"),
    ("build.gradle.kts", "jvm-gradle", "kotlin"),
    ("package.json", "js-ts", "javascript"),
    ("CMakeLists.txt", "c-cpp", "c-cpp"),
    ("pyproject.toml", "python", "python"),
    ("Cargo.toml", "rust", "rust"),
)

SUPPORTED = {"jvm-maven", "jvm-gradle", "js-ts", "c-cpp", "python"}

_JS_TEST_RUNNERS = ("jest", "vitest", "mocha", "jasmine", "karma")


def _js_hints(pkg_path: Path) -> dict:
    hints: dict = {}
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except Exception:
        return {"warning": "unparseable package.json"}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    hints["test_runners"] = [r for r in _JS_TEST_RUNNERS
                             if any(r in d for d in deps)]
    hints["typescript"] = "typescript" in deps
    hints["workspaces"] = bool(pkg.get("workspaces"))
    if (pkg_path.parent / "pnpm-workspace.yaml").is_file():
        hints["workspaces"] = True
        hints["package_manager"] = "pnpm"
    return hints


def _cpp_hints(cmake_path: Path) -> dict:
    sources = []
    for ext in ("*.c", "*.cc", "*.cpp", "*.cxx"):
        sources += list(cmake_path.parent.glob(f"**/{ext}"))
        if sources:
            break
    return {"has_cpp_sources": bool(sources)}


def detect(root: Path, max_depth: int = 4) -> dict:
    targets, notes = [], []
    root = root.resolve()

    def walk(directory: Path, depth: int):
        if depth > max_depth or directory.name in SKIP_DIRS:
            return
        matched_here = []
        for build_file, adapter, language in RULES:
            candidate = directory / build_file
            if not candidate.is_file():
                continue
            # Gradle: both DSLs may coexist in detection rules; dedupe adapter.
            if any(t["adapter"] == adapter for t in matched_here):
                continue
            hints: dict = {}
            if adapter == "js-ts":
                hints = _js_hints(candidate)
                if not hints.get("test_runners"):
                    notes.append(f"{candidate}: package.json without a known "
                                 "test runner — may not be a testable target")
            elif adapter == "c-cpp":
                hints = _cpp_hints(candidate)
                if not hints["has_cpp_sources"]:
                    continue
            entry = {
                "path": str(directory.relative_to(root)) or ".",
                "adapter": adapter,
                "language": language,
                "build_file": build_file,
                "supported": adapter in SUPPORTED,
                "hints": hints,
            }
            matched_here.append(entry)
        targets.extend(matched_here)
        if len(matched_here) > 1:
            notes.append(f"{directory}: multiple build systems detected "
                         f"({', '.join(t['adapter'] for t in matched_here)}) — ask, don't guess")
        # Recurse: nested modules/workspaces are separate candidate targets.
        for child in sorted(p for p in directory.iterdir() if p.is_dir()):
            walk(child, depth + 1)

    walk(root, 0)
    return {"targets": targets, "notes": notes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--max-depth", type=int, default=4)
    args = ap.parse_args()
    result = detect(Path(args.root), args.max_depth)
    json.dump(result, sys.stdout, indent=2)
    print()
    return 0 if result["targets"] else 2


if __name__ == "__main__":
    sys.exit(main())
