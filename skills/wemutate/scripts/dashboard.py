#!/usr/bin/env python3
"""we-mutate dashboard — self-contained HTML from .wemutate/state.json plus
the latest WM v1 run document (spec §9.1). Engine-agnostic: the same
sections render for any adapter because everything reads the canonical model.

Sections: 1 score card · 2 trend · 3 what if? (bugs these tests now prevent)
          4 security panel · 5 per-file strength + top hidden mutants
          6 all projects on this machine · methodology footer

--share writes a snapshot safe to send to someone else: identical except
section 6 is omitted (it lists every project on this machine — private to
the machine, not this project). The file stays local either way; sharing
is the user handing the file over, never an upload.

Usage: dashboard.py --run PATH [--project-root .] [--out .wemutate/dashboard.html]
       dashboard.py --run PATH --share [--out .wemutate/dashboard-share.html]
Exit codes: 0 written · 2 bad input
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

KIND_LABELS = {
    "boundary": "comparison boundary moved",
    "negate_conditional": "condition flipped",
    "remove_conditional": "branch forced on/off",
    "arithmetic": "arithmetic operator changed",
    "logical": "logical operator changed",
    "unary": "sign/increment changed",
    "constant": "literal value changed",
    "return_value": "return value replaced",
    "null_handling": "value replaced with null",
    "remove_call": "call removed or defaulted",
    "exception_handling": "error handling weakened",
    "string": "string literal mutated",
    "collection": "collection emptied",
    "async": "async behaviour mutated",
    "regex": "regular expression mutated",
    "extreme": "entire body removed",
    "other": "engine-specific mutation",
}


def _pct(x) -> str:
    return f"{x * 100:.1f}%" if isinstance(x, (int, float)) else "—"


def _spark_svg(values: list[float], w: int = 360, h_px: int = 60,
               label: str = "trend") -> str:
    n = len(values)
    pts = []
    for i, s in enumerate(values):
        x = 5 + i * (w - 10) / (n - 1)
        y = 5 + (1 - s) * (h_px - 10)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f"<svg width='{w}' height='{h_px}' role='img' "
            f"aria-label='{html.escape(label)}'>"
            f"<polyline fill='none' stroke='#2563eb' stroke-width='2' "
            f"points='{' '.join(pts)}'/></svg>")


def _sparkline(history: list[dict]) -> str:
    scores = [h["totals"].get("mutation_score") for h in history
              if h["totals"].get("mutation_score") is not None]
    if len(scores) < 2:
        return "<p class='muted'>Trend appears after two runs.</p>"
    return (_spark_svg(scores, label="mutation score trend")
            + f"<p class='muted'>{len(scores)} runs · {_pct(scores[0])} → {_pct(scores[-1])}</p>")


def user_dir() -> Path:
    """Same resolution as state.py: ~/.wemutate, WEMUTATE_USER_DIR overrides."""
    return Path(os.environ.get("WEMUTATE_USER_DIR") or Path.home() / ".wemutate")


def _pretty_test(raw: str) -> str:
    """Human name from an engine test id. JUnit 5 ids look like
    'pkg.Cls.[engine:junit-jupiter]/[class:pkg.Cls]/[test-template:method(...)'];
    Stryker/mutmut report plain names, which pass through untouched."""
    m = re.search(r"\[(?:test-template|method|test-factory):([^(\]]+)", raw)
    cls = re.search(r"\[class:([^\]]+)\]", raw)
    if m:
        method = m.group(1).strip()
        if cls:
            return f"{cls.group(1).rsplit('.', 1)[-1]}.{method}"
        return method
    return raw.split("[")[0].rstrip("./ ") or raw


def _damage_phrase(mutant: dict | None, entry: dict) -> str:
    """The honest 'so what': sized by severity + security tag, never claiming
    a confirmed vulnerability (wording rules, SKILL.md)."""
    if entry.get("resolution") == "real_bug":
        return "a live bug"
    tags = (mutant or {}).get("security_tags") or []
    level = ((mutant or {}).get("severity") or {}).get("level")
    if tags:
        return (f"a defect on a security-relevant path "
                f"({html.escape(tags[0]['tag'])})")
    if level == "high":
        return "a high-severity defect"
    return "a silent defect"


def build_whatif(triage: dict, mutants: list[dict]) -> str:
    """Section 3 — the counterfactual: for every closed gap, the bug that
    would have shipped and the test that now stops it. This is the section
    that sells mutation testing to someone who has never read a diff."""
    by_wmid = {m["wmid"]: m for m in mutants}
    entries = []
    for wid, e in triage.items():
        if e.get("resolution") == "real_bug" or (
                e.get("resolution") == "test_gap" and e.get("fix_applied")):
            m = by_wmid.get(wid)
            sev = ((m or {}).get("severity") or {}).get("score", 0)
            entries.append((sev, wid, e, m))
    entries.sort(key=lambda t: -t[0])

    items = []
    for _sev, wid, e, m in entries:
        note = html.escape(e.get("notes") or "")
        when = html.escape((e.get("noted_at") or "")[:10])
        if m:
            killing = (m.get("tests") or {}).get("killing") or []
            guard = (f"<code>{html.escape(_pretty_test(killing[0]))}</code>"
                     if killing else "the test added for it")
            loc = f"{m['location']['file']}:{m['location']['line']}"
            items.append(
                f"<li><strong>Without {guard}</strong>, "
                f"{KIND_LABELS.get(m['kind'], m['kind'])} at "
                f"<code>{html.escape(loc)}</code> — "
                f"<code>{html.escape(m['code']['original'][:80])}</code> — "
                f"would still be shipping as {_damage_phrase(m, e)}."
                + (f"<br><span class='muted'>{note}</span>" if note else "")
                + (f" <span class='muted'>(closed {when})</span>" if when else "")
                + "</li>")
        else:
            # fixed long ago / outside this run's scope — the note is the story
            items.append(f"<li><strong>Closed gap</strong> <code>{html.escape(wid)}</code>"
                         f" — {note or 'no note recorded'}"
                         + (f" <span class='muted'>(closed {when})</span>" if when else "")
                         + "</li>")
    return "".join(items) or (
        "<li class='muted'>Nothing here yet. Every gap you close in triage "
        "becomes a story on this list: the bug that would have shipped, and "
        "the test that now stops it.</li>")


def build_all_projects(current_root: Path) -> str:
    """Section 6 — the zoom-out: every project this machine has run
    mutation testing on, live-reloaded when the directory still exists,
    last-seen snapshot when it doesn't."""
    reg_path = user_dir() / "projects.json"
    try:
        projects = json.loads(reg_path.read_text(encoding="utf-8"))["projects"]
    except (OSError, ValueError, KeyError):
        projects = {}
    if not projects:
        return ("<p class='muted'>Only this project so far. Every project you "
                "run we-mutate in appears here automatically.</p>")

    rows = []
    for path, snap in sorted(projects.items(),
                             key=lambda kv: kv[1].get("last_run_at") or "",
                             reverse=True):
        root = Path(path)
        state_file = root / ".wemutate" / "state.json"
        gone = not state_file.is_file()
        strengths = []
        if not gone:
            try:
                live = json.loads(state_file.read_text(encoding="utf-8"))
                hist = live.get("score_history", [])
                snap = dict(snap)
                if hist:
                    t = hist[-1]["totals"]
                    snap["last_totals"] = {k: t.get(k) for k in snap["last_totals"]}
                    snap["runs"] = len(hist)
                    snap["last_run_at"] = hist[-1].get("timestamp")
                strengths = [h["totals"].get("test_strength") for h in hist
                             if h["totals"].get("test_strength") is not None]
            except (OSError, ValueError, KeyError):
                pass
        totals = snap.get("last_totals", {})
        impact = snap.get("impact", {})
        here = root.resolve() == current_root.resolve()
        spark = (_spark_svg(strengths, w=120, h_px=24, label="strength trend")
                 if len(strengths) >= 2 else "")
        marker = " <strong>← this project</strong>" if here else (
            " <span class='muted'>(directory gone — last seen data)</span>" if gone else "")
        rows.append(
            f"<tr{' class=cur' if here else ''}>"
            f"<td title='{html.escape(path)}'><code>{html.escape(snap.get('name') or root.name)}</code>{marker}</td>"
            f"<td>{html.escape(snap.get('adapter') or '—')}</td>"
            f"<td class='num'>{snap.get('runs', 0)}</td>"
            f"<td class='num'>{_pct(totals.get('test_strength'))}</td>"
            f"<td class='num'>{_pct(totals.get('mutation_score'))}</td>"
            f"<td class='num'>{impact.get('test_gaps_closed', 0) + impact.get('bugs_found', 0)}</td>"
            f"<td>{spark}</td>"
            f"<td class='muted'>{html.escape((snap.get('last_run_at') or '')[:10])}</td></tr>")
    return ("<table><tr><th>project</th><th>language</th><th>runs</th>"
            "<th>strength</th><th>score</th><th>gaps closed</th>"
            "<th>trend</th><th>last run</th></tr>" + "".join(rows) + "</table>")


def build_html(state: dict, run_doc: dict, root: Path = Path("."),
               share: bool = False) -> str:
    totals = run_doc["totals"]
    engine = run_doc["run"]["engine"]
    mutants = run_doc.get("mutants", [])
    triage = state.get("triage", {})

    # 3. What if? — counterfactual per closed gap (upgrades bugs-prevented).
    whatif_html = build_whatif(triage, mutants)

    # 4. Security panel.
    sec_open = [m for m in mutants if m.get("security_tags")
                and m["status"] in ("hidden", "uncovered")
                and (triage.get(m["wmid"], {}).get("resolution")
                     not in ("equivalent", "suppressed"))]
    sec_html = "".join(
        f"<li><strong>{html.escape(m['security_tags'][0]['tag'])}</strong> "
        f"<code>{html.escape(m['location']['file'])}:{m['location']['line']}</code> — "
        f"{html.escape(m['code']['original'][:90])}</li>"
        for m in sec_open[:10]) or \
        "<li class='muted'>No security-tagged untested paths in this run. " \
        "(Tagging ships with the M2 security overlay.)</li>"

    # 5. Per-file strength + top hidden.
    per_file: dict[str, dict] = defaultdict(lambda: {"total": 0, "found": 0})
    for m in mutants:
        if m["status"] == "error":
            continue
        f = per_file[m["location"]["file"]]
        f["total"] += 1
        f["found"] += m["status"] == "found"
    file_rows = "".join(
        f"<tr><td><code>{html.escape(p)}</code></td><td>{v['found']}/{v['total']}</td>"
        f"<td>{_pct(v['found'] / v['total']) if v['total'] else '—'}</td></tr>"
        for p, v in sorted(per_file.items(),
                           key=lambda kv: kv[1]["found"] / kv[1]["total"] if kv[1]["total"] else 1))
    untriaged = [m for m in mutants if m["status"] in ("hidden", "uncovered")
                 and m["wmid"] not in triage]
    untriaged.sort(key=lambda m: -(m.get("severity") or {}).get("score", 0))
    top_html = "".join(
        f"<li><code>{html.escape(m['location']['file'])}:{m['location']['line']}</code> — "
        f"{KIND_LABELS.get(m['kind'], m['kind'])}: "
        f"<code>{html.escape(m['code']['original'][:90])}</code></li>"
        for m in untriaged[:10]) or "<li class='muted'>Nothing hidden and untriaged. Good.</li>"

    subsumption = run_doc["run"].get("subsumption", "none")
    inc = run_doc["run"].get("incremental") or {}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>we-mutate — {html.escape(state.get('project', {}).get('name') or 'project')}</title>
<style>
 body{{font:15px/1.5 -apple-system,Segoe UI,sans-serif;margin:2rem auto;max-width:780px;color:#111}}
 h1{{font-size:1.4rem}} h2{{font-size:1.05rem;margin-top:2rem;border-bottom:1px solid #e5e7eb;padding-bottom:.3rem}}
 .cards{{display:flex;gap:1rem}} .card{{flex:1;border:1px solid #e5e7eb;border-radius:8px;padding:1rem;text-align:center}}
 .card .n{{font-size:1.8rem;font-weight:700}} .muted{{color:#6b7280}}
 table{{border-collapse:collapse;width:100%}} td,th{{padding:.3rem .6rem;border-bottom:1px solid #f3f4f6;text-align:left}}
 code{{background:#f6f8fa;padding:.1rem .3rem;border-radius:4px;font-size:.85em}}
 td.num{{text-align:right}} tr.cur{{background:#f0f7ff}}
 footer{{margin-top:2.5rem;font-size:.8rem;color:#6b7280;border-top:1px solid #e5e7eb;padding-top:1rem}}
</style></head><body>
<h1>we-mutate dashboard</h1>
<p class="muted">{html.escape(engine['adapter'])} · {html.escape(engine['core'])} · run {html.escape(run_doc['run']['id'])} · {html.escape(run_doc['run']['timestamp'])}</p>

<h2>1 · Scores</h2>
<div class="cards">
 <div class="card"><div class="n">{_pct(totals.get('mutation_score'))}</div>mutation score</div>
 <div class="card"><div class="n">{_pct(totals.get('test_strength'))}</div>test strength</div>
 <div class="card"><div class="n">{_pct(totals.get('coverage_signal'))}</div>coverage signal</div>
</div>
<p class="muted">{totals['found']} found · {totals['hidden']} hidden · {totals['uncovered']} uncovered
 · {totals.get('equivalent', 0)} equivalent · {totals.get('suppressed', 0)} suppressed</p>

<h2>2 · Trend</h2>
{_sparkline(state.get('score_history', []))}

<h2>3 · What if? — bugs these tests now prevent</h2>
<ul>{whatif_html}</ul>

<h2>4 · Security — untested security-relevant paths</h2>
<ul>{sec_html}</ul>

<h2>5 · Per-file test strength &amp; top hidden mutants</h2>
<table><tr><th>file</th><th>found/total</th><th>strength</th></tr>{file_rows}</table>
<ul>{top_html}</ul>

{"" if share else f'''<h2>6 · All projects on this machine</h2>
{build_all_projects(root)}
'''}
<footer>
{"<p>Shared snapshot — covers this project only.</p>" if share else ""}
<strong>Methodology.</strong> mutation score = found / (total − equivalent − suppressed);
test strength = found / covered; timeouts count as found. Subsumption: {subsumption}.
Incremental: {"yes — " + str(inc.get('reused_results', 0)) + " reused / " + str(inc.get('executed', 0)) + " executed" if inc.get("used") else "no"}.
A mutation score is a signal for finding untested behaviour, not a target to chase.
Security items are untested security-<em>relevant</em> paths, not confirmed vulnerabilities.
Generated by we-mutate, built on {html.escape(engine['core'])} (open source).
</footer>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--out", default=None)
    ap.add_argument("--share", action="store_true",
                    help="share-safe snapshot: omit the all-projects section")
    args = ap.parse_args()
    root = Path(args.project_root)
    try:
        run_doc = json.loads(Path(args.run).read_text(encoding="utf-8"))
        assert run_doc.get("wm_version") == "1"
    except Exception as e:
        print(f"bad run document: {e}", file=sys.stderr)
        return 2
    state_file = root / ".wemutate" / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
    default_name = "dashboard-share.html" if args.share else "dashboard.html"
    out = Path(args.out) if args.out else root / ".wemutate" / default_name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(state, run_doc, root, share=args.share),
                   encoding="utf-8")
    print(json.dumps({"written": str(out), "share": args.share}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
