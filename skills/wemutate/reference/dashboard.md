# Dashboard — stakeholder-facing artifact

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/wemutate/scripts/dashboard.py \
    --run /tmp/wm-run.json [--project-root .] [--out PATH]
```

Self-contained HTML at `.wemutate/dashboard.html` (no network, no JS deps —
safe to email or attach). Sections, identical for every adapter:

1. Score card — mutation score · test strength · coverage signal
2. Trend sparkline over recorded runs (needs ≥ 2 runs)
3. **What if?** — one counterfactual per closed gap: *without test T, flaw F
   at file:line would still be shipping as <damage>*. Built from triage
   entries (real_bug, or test_gap with the fix applied) joined to the run
   doc's mutants for the code line, the killing test name, and the
   severity/security tag that sizes the damage phrase. Triage notes are
   quoted as the story — this is why notes matter. This is the section that
   sells mutation testing to someone who has never read a diff.
4. Security panel — untested security-relevant paths (wording rule: never
   "vulnerability")
5. Per-file strength map + top hidden untriaged mutants
6. **All projects on this machine** — the zoom-out: every project ever
   recorded (machine-level registry at `~/.wemutate/projects.json`, written
   by `state.py record-run`/`triage`). Live-reloads each project's state
   when the directory exists; deleted projects stay listed with last-seen
   data. The current project is highlighted. The cross-*machine* equivalent
   is the portal (`/portal`, sync opt-in).
7. Methodology footer — formulas, subsumption/incremental status, and the
   explicit "score is a signal, not a target" statement

Offer it after a run when (a) history has ≥ 2 entries, (b) the user mentions
reporting/leadership/teams, or (c) a milestone (score crossed a threshold).
One line: "Want the shareable dashboard? One file, no dependencies."
