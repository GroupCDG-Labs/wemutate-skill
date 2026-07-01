#!/usr/bin/env python3
"""Inline terminal scorebox — the always-visible dashboard for skill sessions.

Renders a fixed-width box from a WM v1 run document, with bar gauges for
test strength and mutation score, the count line, and (when history allows)
the trend vs the previous recorded run.

Usage:
  term_dashboard.py --run PATH [--label TEXT] [--project-root .] [--width 56]

The skill prints this verbatim (inside a code block) after every run and
after each fix→rerun cycle, so scores stay visible throughout the session.

Exit codes: 0 ok · 2 bad input
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BAR_CELLS = 20


def _bar(ratio: float | None) -> str:
    if ratio is None:
        return "·" * BAR_CELLS + "    n/a"
    filled = round(max(0.0, min(1.0, ratio)) * BAR_CELLS)
    return "█" * filled + "░" * (BAR_CELLS - filled) + f"  {ratio * 100:5.1f}%"


def _series(project_root: Path, target: str | None) -> list[dict]:
    """History entries for one target (like-with-like trends). When target is
    None, use the most recent entry's target so a multi-module project doesn't
    cross-compare a :core run against a :web run."""
    state_file = project_root / ".wemutate" / "state.json"
    if not state_file.is_file():
        return []
    history = json.loads(state_file.read_text()).get("score_history", [])
    if not history:
        return []
    if target is None:
        target = history[-1].get("target", ".")
    return [h for h in history if h.get("target", ".") == target]


def _trend(project_root: Path, target: str | None) -> str | None:
    series = _series(project_root, target)
    if len(series) < 2:
        return None
    last = series[-1]["totals"].get("mutation_score")
    prev = series[-2]["totals"].get("mutation_score")
    if last is None or prev is None:
        return None
    delta = (last - prev) * 100
    # Two diff-scoped runs usually cover *different* changed lines, so a points
    # delta between them compares different mutant populations — honest only as
    # an indicative signal, not a like-for-like score change (fitness review M2).
    diff_scoped = (series[-1].get("scope") in ("diff", "staged")
                   and series[-2].get("scope") in ("diff", "staged"))
    qualifier = " · diff (indicative)" if diff_scoped else ""
    if abs(delta) < 0.05:
        return "→ unchanged since last run" + qualifier
    arrow = "▲" if delta > 0 else "▼"
    return f"{arrow} {delta:+.1f} pts since last run{qualifier}"


def _impact_lines(project_root: Path, target: str | None) -> list[str]:
    """Improvement story since the first recorded run — only lines with
    something real to say. Sourced from state history + triage, never estimated.

    The score/LOC story is per-target (like-with-like); bugs-found, gaps-closed
    and dead-code counts are repo-wide (triage isn't target-tagged, and these
    are genuine whole-repo value)."""
    state_file = project_root / ".wemutate" / "state.json"
    if not state_file.is_file():
        return []
    state = json.loads(state_file.read_text())
    triage = list(state.get("triage", {}).values())
    series = _series(project_root, target)
    lines: list[str] = []

    if len(series) >= 2:
        first = series[0]["totals"].get("mutation_score")
        last = series[-1]["totals"].get("mutation_score")
        if first is not None and last is not None and abs(last - first) >= 0.0005:
            lines.append(f"Score {first * 100:.1f}% → {last * 100:.1f}%"
                         f"   ({(last - first) * 100:+.1f} pts)")

    bugs = sum(e.get("resolution") == "real_bug" for e in triage)
    gaps = sum(e.get("resolution") == "test_gap" and e.get("fix_applied")
               for e in triage)
    if bugs or gaps:
        parts = []
        if bugs:
            parts.append(f"Bugs found: {bugs}")
        if gaps:
            parts.append(f"Test gaps closed: {gaps}")
        lines.append("   ".join(parts))

    dead = [e for e in triage if e.get("resolution") == "dead_code"]
    removed = sum(e.get("lines_removed") or 0 for e in dead)
    if dead:
        msg = f"Dead code removed: {removed} lines" if removed else \
              f"Dead code found: {len(dead)} spots"
        loc_first = series[0].get("loc") if series else None
        loc_last = series[-1].get("loc") if series else None
        if removed and loc_first and loc_last is not None and loc_last < loc_first:
            msg += f"  (code {(loc_first - loc_last) / loc_first * 100:.1f}% shorter)"
        lines.append(msg)

    return lines


def render(run_doc: dict, label: str | None, project_root: Path,
           width: int = 56, target: str | None = None) -> str:
    t = run_doc["totals"]
    if target is None:
        target = run_doc["run"]["scope"].get("target")
    inner = width - 4  # between "║  " and trailing "║"

    def line(text: str = "") -> str:
        if len(text) > inner:  # never break the box border
            text = text[:inner - 1] + "…"
        return f"║  {text:<{inner}}║"

    title = "Test Strength" + (f"  ({label})" if label else "")
    counts = (f"Found: {t['found']}  Hidden: {t['hidden']}  "
              f"No coverage: {t['uncovered']}")
    if t.get("equivalent") or t.get("suppressed"):
        counts += f"  ({t.get('equivalent', 0) + t.get('suppressed', 0)} excluded)"

    rows = [
        "╔" + "═" * (width - 2) + "╗",
        line(title),
        line(_bar(t.get("test_strength"))),
        line(),
        line("Mutation Score"),
        line(_bar(t.get("mutation_score"))),
        line(),
        line(counts),
    ]
    trend = _trend(project_root, target)
    if trend:
        rows.append(line(trend))
    impact = _impact_lines(project_root, target)
    if impact:
        rows.append("╟" + "─" * (width - 2) + "╢")
        rows.append(line("Impact since first run"))
        rows.extend(line(text) for text in impact)
    rows.append("╚" + "═" * (width - 2) + "╝")
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--label", default=None)
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--width", type=int, default=56)
    ap.add_argument("--target", default=None,
                    help="sub-project/module for the trend (default: from the run doc)")
    args = ap.parse_args()
    try:
        run_doc = json.loads(Path(args.run).read_text(encoding="utf-8"))
        assert run_doc.get("wm_version") == "1"
    except Exception as e:
        print(f"bad run document: {e}", file=sys.stderr)
        return 2
    print(render(run_doc, args.label, Path(args.project_root), args.width,
                 target=args.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
