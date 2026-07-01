#!/usr/bin/env python3
"""we-mutate dashboard — self-contained HTML from .wemutate/state.json plus
the latest WM v1 run document (spec §9.1). Engine-agnostic: the same six
sections render for any adapter because everything reads the canonical model.

Sections: 1 score card · 2 trend · 3 bugs prevented · 4 security panel
          5 per-file strength + top hidden mutants · 6 methodology footer

Usage: dashboard.py --run PATH [--project-root .] [--out .wemutate/dashboard.html]
Exit codes: 0 written · 2 bad input
"""

from __future__ import annotations

import argparse
import html
import json
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


def _sparkline(history: list[dict]) -> str:
    scores = [h["totals"].get("mutation_score") for h in history
              if h["totals"].get("mutation_score") is not None]
    if len(scores) < 2:
        return "<p class='muted'>Trend appears after two runs.</p>"
    w, h_px, n = 360, 60, len(scores)
    pts = []
    for i, s in enumerate(scores):
        x = 5 + i * (w - 10) / (n - 1)
        y = 5 + (1 - s) * (h_px - 10)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f"<svg width='{w}' height='{h_px}' role='img' "
            f"aria-label='mutation score trend'>"
            f"<polyline fill='none' stroke='#2563eb' stroke-width='2' "
            f"points='{' '.join(pts)}'/></svg>"
            f"<p class='muted'>{n} runs · {_pct(scores[0])} → {_pct(scores[-1])}</p>")


def build_html(state: dict, run_doc: dict) -> str:
    totals = run_doc["totals"]
    engine = run_doc["run"]["engine"]
    mutants = run_doc.get("mutants", [])
    triage = state.get("triage", {})

    # 3. Bugs prevented — narrative straight from triage notes.
    prevented = [(wid, e) for wid, e in triage.items()
                 if e.get("resolution") == "real_bug"
                 or (e.get("resolution") == "test_gap" and e.get("fix_applied"))]
    prevented_html = "".join(
        f"<li><code>{html.escape(w)}</code> — {html.escape(e.get('notes') or e['resolution'])}</li>"
        for w, e in prevented) or "<li class='muted'>None recorded yet — triage notes feed this section.</li>"

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

<h2>3 · Bugs prevented</h2>
<ul>{prevented_html}</ul>

<h2>4 · Security — untested security-relevant paths</h2>
<ul>{sec_html}</ul>

<h2>5 · Per-file test strength &amp; top hidden mutants</h2>
<table><tr><th>file</th><th>found/total</th><th>strength</th></tr>{file_rows}</table>
<ul>{top_html}</ul>

<footer>
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
    out = Path(args.out) if args.out else root / ".wemutate" / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(state, run_doc), encoding="utf-8")
    print(json.dumps({"written": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
