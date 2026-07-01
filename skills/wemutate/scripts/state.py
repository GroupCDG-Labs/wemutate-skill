#!/usr/bin/env python3
""".wemutate/state.json management (spec §4.7). Atomic writes, append-only
history, triage keyed by wmid, one-time legacy migration.

Subcommands:
  show                          print current state (creates nothing)
  record-run --run PATH         append a score_history entry from a WM v1 run doc
  delta                         last-vs-previous score/strength deltas (JSON)
  triage WMID --resolution R [--notes TEXT] [--fix-applied]
  migrate --legacy PATH --mutations-xml PATH --source-root PATH
                                migrate a pre-WM .pitest/state.json (PiTest only;
                                unresolvable keys preserved under legacy_triage)

State lives at <project>/.wemutate/state.json (override: --project-root).
Exit codes: 0 ok · 2 invalid input · 4 internal failure
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

def _find_home(start: Path) -> Path:
    """Env override, else nearest ancestor holding wm/ and adapters/ —
    works in the monorepo (repo root) and the packaged plugin (skills/wemutate/)."""
    env = os.environ.get("WEMUTATE_HOME")
    if env and ((Path(env) / "wm").is_dir() or any(Path(env).glob("wm.*"))):
        return Path(env).resolve()
    p = start.resolve()
    for _ in range(10):
        # wm/ is a source dir in development and a compiled native module
        # (wm.cpython-*.so / wm.pyd) in --compiled distributions.
        has_wm = (p / "wm").is_dir() or any(p.glob("wm.*.so")) or (p / "wm.pyd").is_file()
        if has_wm and (p / "adapters").is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    raise SystemExit(f"wemutate home not found above {start}; set WEMUTATE_HOME")


REPO_ROOT = _find_home(Path(__file__).parent)
sys.path.insert(0, str(REPO_ROOT))

from wm.migrate import migrate_triage, pitest_resolver  # noqa: E402
from wm.overlay import apply_state  # noqa: E402

RESOLUTIONS = {"test_gap", "real_bug", "dead_code", "equivalent", "suppressed", "deferred"}

# Production-source extensions per adapter, for the LOC snapshot recorded
# with every run (feeds the impact report's "code N% shorter" line).
_LOC_EXTENSIONS = {
    "jvm-maven": (".java", ".kt"),
    "jvm-gradle": (".java", ".kt"),
    "js-ts": (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"),
    "c-cpp": (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"),
    "python": (".py",),
}
_LOC_SKIP_DIRS = {".git", "node_modules", "target", "build", "dist", "out",
                  ".gradle", "__pycache__", ".wemutate", ".stryker-tmp", "reports"}
_LOC_TEST_MARKERS = ("/src/test/", "/tests/", "/__tests__/", "/__mocks__/",
                     ".test.", ".spec.", "Test.java", "Tests.java", "IT.java")


def project_loc(root: Path, adapter: str) -> int | None:
    """Count production source lines for the adapter's language. Honest
    approximation: git-style tree walk, test files excluded by convention."""
    exts = _LOC_EXTENSIONS.get(adapter)
    if not exts:
        return None
    total = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in exts:
            continue
        rel = "/" + str(path.relative_to(root))
        if any(part in _LOC_SKIP_DIRS for part in path.parts):
            continue
        if any(marker in rel for marker in _LOC_TEST_MARKERS):
            continue
        try:
            total += sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return total

EMPTY_STATE = {
    "wm_version": "1",
    "project": {},
    "score_history": [],
    "triage": {},
    "legacy_triage": {},
    "pr_comment_branches": [],
    "badge": {},
    "sync": {},
}


def state_path(project_root: Path) -> Path:
    return project_root / ".wemutate" / "state.json"


def load(project_root: Path) -> dict:
    path = state_path(project_root)
    if not path.is_file():
        return json.loads(json.dumps(EMPTY_STATE))
    return json.loads(path.read_text(encoding="utf-8"))


def save(project_root: Path, state: dict) -> None:
    """Atomic write: temp file in the same directory, then rename."""
    path = state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def cmd_show(root: Path, _args) -> int:
    json.dump(load(root), sys.stdout, indent=2)
    print()
    return 0


def cmd_record_run(root: Path, args) -> int:
    run_doc = json.loads(Path(args.run).read_text(encoding="utf-8"))
    if run_doc.get("wm_version") != "1":
        print("not a WM v1 run document", file=sys.stderr)
        return 2
    state = load(root)
    # Fold triage resolutions + cleared security tags into the doc so the
    # recorded scores reflect them (spec §4.5), then write the overlaid doc
    # back so every later consumer (scorebox, dashboard) sees the same data.
    run_doc = apply_state(run_doc, state)
    Path(args.run).write_text(json.dumps(run_doc, indent=2) + "\n",
                              encoding="utf-8")
    # The sub-project this run covered. Generic across build systems
    # (Gradle `:core`, a pnpm workspace package, a Maven module, a Cargo
    # crate); "." for a single-project / whole-repo run. Trends compare
    # like-with-like by grouping on this. See GAPS.md decision 2026-06-13.
    target = (getattr(args, "target", None)
              or run_doc["run"]["scope"].get("target") or ".")
    entry = {
        "timestamp": run_doc["run"]["timestamp"],
        "run_id": run_doc["run"]["id"],
        "adapter": run_doc["run"]["engine"]["adapter"],
        "scope": run_doc["run"]["scope"]["mode"],
        "target": target,
        "totals": run_doc["totals"],
        "hidden_wmids": sorted(m["wmid"] for m in run_doc.get("mutants", [])
                               if m["status"] in ("hidden", "uncovered")),
        "loc": project_loc(root, run_doc["run"]["engine"]["adapter"]),
    }
    state["score_history"].append(entry)
    state.setdefault("project", {}).setdefault("adapter",
                                               run_doc["run"]["engine"]["adapter"])
    save(root, state)
    print(json.dumps({"recorded": entry["run_id"],
                      "history_length": len(state["score_history"])}))
    return 0


def cmd_delta(root: Path, args) -> int:
    history = load(root)["score_history"]
    # Compare within one target so a :core run isn't "trended" against a :web
    # run. Default to the target of the most recent run.
    target = getattr(args, "target", None)
    if target is None and history:
        target = history[-1].get("target", ".")
    series = [h for h in history if h.get("target", ".") == target]
    if len(series) < 2:
        print(json.dumps({"delta": None, "target": target,
                          "reason": "fewer than two recorded runs for this target"}))
        return 0
    last, prev = series[-1]["totals"], series[-2]["totals"]
    newly_hidden = sorted(set(series[-1].get("hidden_wmids", []))
                          - set(series[-2].get("hidden_wmids", [])))
    newly_resolved = sorted(set(series[-2].get("hidden_wmids", []))
                            - set(series[-1].get("hidden_wmids", [])))
    def d(key):
        a, b = last.get(key), prev.get(key)
        return round(a - b, 4) if a is not None and b is not None else None
    print(json.dumps({
        "mutation_score_delta": d("mutation_score"),
        "test_strength_delta": d("test_strength"),
        "target": target,
        "newly_hidden": newly_hidden,
        "newly_resolved": newly_resolved,
    }, indent=2))
    return 0


def cmd_triage(root: Path, args) -> int:
    if args.resolution not in RESOLUTIONS:
        print(f"resolution must be one of {sorted(RESOLUTIONS)}", file=sys.stderr)
        return 2
    if args.resolution in ("suppressed", "equivalent") and not args.notes:
        # Both resolutions remove the mutant from the score denominator, so a
        # score can be lifted by labelling survivors away. A reason is therefore
        # mandatory and auditable for each (spec §4.6; fitness review M3).
        print(f"{args.resolution} requires --notes — it excludes the mutant from "
              "the score, so a reason is mandatory and auditable", file=sys.stderr)
        return 2
    state = load(root)
    entry = {
        "resolution": args.resolution,
        "fix_applied": bool(args.fix_applied),
        "noted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "notes": args.notes or "",
    }
    if args.lines_removed is not None:
        entry["lines_removed"] = args.lines_removed
    state["triage"][args.wmid] = entry
    save(root, state)
    print(json.dumps({"triaged": args.wmid, "resolution": args.resolution}))
    return 0


def cmd_clear_tag(root: Path, args) -> int:
    """User says a security tag is a false positive: remember per wmid so it
    is removed on every future run (spec §5.2 feedback loop)."""
    state = load(root)
    cleared = state.setdefault("cleared_tags", {})
    tags = cleared.setdefault(args.wmid, [])
    if args.tag not in tags:
        tags.append(args.tag)
    save(root, state)
    print(json.dumps({"cleared": args.tag, "wmid": args.wmid}))
    return 0


def cmd_impact(root: Path, _args) -> int:
    """Aggregate the improvement story: first→last scores, bugs found, gaps
    closed, dead code removed, LOC delta. Everything sourced from recorded
    history and triage — nothing estimated."""
    state = load(root)
    history = state["score_history"]
    triage = state["triage"].values()
    dead = [e for e in triage if e.get("resolution") == "dead_code"]
    lines_removed = sum(e.get("lines_removed") or 0 for e in dead)

    impact = {
        "runs": len(history),
        "bugs_found": sum(e.get("resolution") == "real_bug" for e in triage),
        "test_gaps_closed": sum(e.get("resolution") == "test_gap"
                                and e.get("fix_applied") for e in triage),
        "equivalents_identified": sum(e.get("resolution") == "equivalent"
                                      for e in triage),
        "dead_code_instances": len(dead),
        "dead_code_lines_removed": lines_removed,
    }
    if history:
        first, last = history[0], history[-1]
        impact["mutation_score_first"] = first["totals"].get("mutation_score")
        impact["mutation_score_last"] = last["totals"].get("mutation_score")
        impact["test_strength_first"] = first["totals"].get("test_strength")
        impact["test_strength_last"] = last["totals"].get("test_strength")
        loc_first, loc_last = first.get("loc"), last.get("loc")
        impact["loc_first"], impact["loc_last"] = loc_first, loc_last
        if loc_first and loc_last is not None and loc_first > 0:
            impact["loc_delta_pct"] = round((loc_last - loc_first) / loc_first * 100, 1)
    json.dump(impact, sys.stdout, indent=2)
    print()
    return 0


def cmd_migrate(root: Path, args) -> int:
    legacy = json.loads(Path(args.legacy).read_text(encoding="utf-8"))
    resolve = pitest_resolver(args.mutations_xml, args.source_root)
    migrated = migrate_triage(legacy, resolve)
    state = load(root)
    state["triage"].update(migrated["triage"])
    state["legacy_triage"].update(migrated["legacy_triage"])
    # Carry over legacy score history verbatim under a marked key — old
    # entries lack WM totals and must not silently mix into trend math.
    if legacy.get("score_history"):
        state.setdefault("pre_wm_history", legacy["score_history"])
    save(root, state)
    print(json.dumps({
        "migrated": len(migrated["triage"]),
        "preserved_unresolved": len(migrated["legacy_triage"]),
    }))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    p = sub.add_parser("record-run")
    p.add_argument("--run", required=True)
    p.add_argument("--target", help="sub-project/module this run covered "
                                     "(e.g. ':core'); '.' for whole-repo")
    p = sub.add_parser("delta")
    p.add_argument("--target", help="restrict the trend to one target "
                                    "(default: the most recent run's target)")
    p = sub.add_parser("triage")
    p.add_argument("wmid")
    p.add_argument("--resolution", required=True)
    p.add_argument("--notes")
    p.add_argument("--fix-applied", action="store_true")
    p.add_argument("--lines-removed", type=int)
    p = sub.add_parser("clear-tag")
    p.add_argument("wmid")
    p.add_argument("tag")
    sub.add_parser("impact")
    p = sub.add_parser("migrate")
    p.add_argument("--legacy", required=True)
    p.add_argument("--mutations-xml", required=True)
    p.add_argument("--source-root", required=True)
    args = ap.parse_args()
    root = Path(args.project_root)
    try:
        return {"show": cmd_show, "record-run": cmd_record_run,
                "delta": cmd_delta, "triage": cmd_triage,
                "clear-tag": cmd_clear_tag, "impact": cmd_impact,
                "migrate": cmd_migrate}[args.cmd](root, args)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"state error: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
