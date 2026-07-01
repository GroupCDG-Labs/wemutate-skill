# Dashboard — stakeholder-facing artifact

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/wemutate/scripts/dashboard.py \
    --run /tmp/wm-run.json [--project-root .] [--out PATH]
```

Self-contained HTML at `.wemutate/dashboard.html` (no network, no JS deps —
safe to email or attach). Six sections, identical for every adapter:

1. Score card — mutation score · test strength · coverage signal
2. Trend sparkline over recorded runs (needs ≥ 2 runs)
3. **Bugs prevented** — quotes triage notes verbatim (this is why notes
   matter)
4. Security panel — untested security-relevant paths (populated once the M2
   overlay ships; honest placeholder until then)
5. Per-file strength map + top hidden untriaged mutants
6. Methodology footer — formulas, subsumption/incremental status, and the
   explicit "score is a signal, not a target" statement

Offer it after a run when (a) history has ≥ 2 entries, (b) the user mentions
reporting/leadership/teams, or (c) a milestone (score crossed a threshold).
One line: "Want the shareable dashboard? One file, no dependencies."
