---
name: wemutate
description: >
  Multi-language mutation testing. Use when the user asks to assess test
  quality, check mutation score, find gaps in their tests, run mutation
  testing, or wants to know whether their tests would actually catch bugs —
  in Java (Maven or Gradle), JavaScript/TypeScript, Python, or C/C++.
  Detects the language, resolves the right engine (PiTest, Stryker, mutmut,
  Mull), runs
  diff-scoped by default, and explains surviving mutants in plain English
  with suggested fixes.
---

# wemutate — one skill, one vocabulary

This skill drives mutation testing across languages through a uniform
pipeline. Engine differences live in adapters; everything the user sees uses
the same canonical vocabulary (WM Report Format v1).

```
detect → resolve engine (signup on first run) → doctor → (setup) → run
       → report --canonical → record state → triage loop
       → offers (dashboard · PR comment · badge)
```

## Hard rules

1. **Never show raw mutator names** (`NegateConditionalsMutator`,
   `cxx_lt_to_le`). Always translate via the canonical kind and the
   plain-English phrasing in `reference/triage.md`.
2. **Four-step framing** for every surviving ("hidden") mutant, in order:
   ① quote the actual code line → ② name a test that covered it (or say "no
   test executes this line") → ③ explain the mutation in plain English →
   ④ offer the smallest fix as an Edit suggestion.
3. **Progressive disclosure**: one hidden mutant at a time. Hold the rest
   until the user asks.
4. **Diff-by-default**: never run `--scope=full` without explicit user
   opt-in, every time. Exit code 3 (empty diff) means *ask* — never silently
   widen scope.
5. **Build-file edits need approval**: run `setup` (plan mode), show the
   diff, apply only after an explicit yes.
6. **Tests must be green before mutating.** A red build makes mutation
   results meaningless; refuse with the phrasing in `reference/refusals.md`.
7. **Status vocabulary**: hidden / found / uncovered — never "survived" /
   "killed" in user-facing text.
8. **No emojis, no raw stack traces, never "run this command"** — the skill
   executes; the user converses.

## Step 1 — Detect

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/wemutate/scripts/detect.py [ROOT]
```

- Exactly one supported target → proceed with it, say which.
- Multiple targets (monorepo / multi-language) → present the list as a menu
  with path + language + hints; remember the choice in state
  (`project.target_path`). Ask — don't guess.
- A directory matching two rules → ask.
- Nothing detected, or only unsupported adapters (rust) → refuse with
  next steps (`reference/refusals.md`).

## Step 2 — Resolve engine

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/wemutate/scripts/resolve_engine.py <adapter>
```

Print what was resolved (source, path, sha256). On a thin install (no
bundled engine) this downloads the engine from the production registry,
SHA-256-verified, cached in `~/.wemutate/engines/` — needs the account from
Step 2a. The resolved `wm-engine` executable is used for every following
step. All adapters share one CLI:
`doctor` · `setup [--apply]` · `run --scope=…` · `report --canonical` ·
`version` · `licenses` (exit codes: 0 ok, 2 setup required, 3 empty diff,
4 engine failure, 5 licence required).

## Step 2a — Account (first run on a machine only)

Triggered lazily — only when `resolve_engine.py` or a `wm-engine` step
reports it (`"action": "signup"` on stderr, or exit code 5):

1. Explain in one line: a free beta account links the engine to the user;
   nothing about their code is ever sent.
2. Ask for their email, then:
   `python3 .../scripts/signup.py request --email <email>`
3. Say a 6-digit code is in their inbox (expires in 10 minutes) and ask for
   it, then: `signup.py verify --email <email> --code <code>`
4. On success the token is saved to `~/.wemutate/credentials.json` — retry
   the step that asked for it and carry on. Never store or echo the code
   anywhere else; never ask for a password (there are none).

Exit code 5 on a machine that already has an account means the token was
revoked or the licence could not be validated — relay the engine's message
(phrasing in `reference/refusals.md`) and offer to re-run the signup flow.

## Step 3 — Doctor, then setup if needed

Always run `wm-engine doctor` first; branch on its JSON (per-adapter details
in `reference/setup.md`). If the build isn't integrated yet: `setup` (plan),
show diff, get approval, `setup --apply`.

## Step 4 — Run

`wm-engine run --scope=diff` (default) · `staged` · `full` (opt-in only).
On exit 3, ask whether to widen. On exit 4, surface the engine diagnostics
honestly. Guidance per adapter in `reference/run.md`.

## Step 5 — Canonical report + state + scorebox

```
wm-engine report --canonical > /tmp/wm-run.json
python3 .../scripts/state.py record-run --run /tmp/wm-run.json [--target <module>]
python3 .../scripts/state.py delta [--target <module>]   # trend vs previous run of same target
python3 .../scripts/term_dashboard.py --run /tmp/wm-run.json --label <scope> [--target <module>]
```

**The scorebox stays visible.** Print `term_dashboard.py` output verbatim in
a code block (it is box-drawing art — never paraphrase it into prose):
- immediately after every run,
- again after each fix → rerun cycle (the before/after bars are the payoff),
- and at session end as the closing summary.
`--label` is the focus of the run (class, file, or module name) when there
is one; omit it for whole-diff runs. **For a monorepo / multi-module run,
pass `--target <module>`** (e.g. `:core`, a workspace package) to `record-run`,
`delta`, and `term_dashboard` so trends compare that module against its own
history, not against other modules. Omit `--target` for single-project repos
(it defaults to `.`). The box includes the trend line
automatically once two runs are recorded. **A trend between two diff-scoped runs
is indicative only** — consecutive diff runs usually cover different changed
lines, so the box marks it `· diff (indicative)`; describe it as a signal, not a
like-for-like score change (reserve "your score went up/down" for full-scope
runs). The box also shows an "Impact since first run"
section (score first→last, bugs found, gaps closed, dead code removed)
as soon as triage has produced any of those — `state.py impact` gives the
same data as JSON for prose summaries. When a mutant proves code is useless
(`dead_code` resolution, see triage.md), record the deleted line count so
the impact line can say "40 lines of bloat removed, code 5% shorter".

Open the triage loop on the `hidden` then `uncovered` mutants,
**severity-ordered** (every mutant carries `severity.score` and explainable
`factors`). Security-tagged mutants therefore surface first — introduce them
as what they are: "this is an untested *validation path*" (use the tag's
`rationale`), never as a confirmed vulnerability. If the user says a tag is
wrong, clear it permanently: `state.py clear-tag <wmid> <tag>` — it will not
be shown again for that mutant. Record every user decision:

```
python3 .../scripts/state.py triage <wmid> --resolution test_gap|real_bug|equivalent|suppressed|deferred [--notes "…"] [--fix-applied]
```

`suppressed` and `equivalent` both require notes — they remove the mutant from
the score denominator, so a reason is mandatory and auditable. Triage notes are
load-bearing: the dashboard's "bugs prevented" section quotes them verbatim.

**Legacy projects:** if `.pitest/state.json` (or `.stryker/`, `.mull/`)
exists and `.wemutate/state.json` doesn't, offer the one-time migration
(`state.py migrate …`, PiTest variant available now). Unresolvable entries
are preserved, never dropped.

## Step 6 — Offers (never push, always one line)

- **Dashboard**: `scripts/dashboard.py --run /tmp/wm-run.json` → self-contained
  HTML at `.wemutate/dashboard.html`.
- **PR comment**: once per branch, idempotent edit-in-place
  (`reference/pr_comment.md`).
- **TDD micro-loop** when the user is mid red→green cycle
  (`reference/tdd.md`).
- **Portal sync** (opt-in, once per project): if `.wemutate/sync.json`
  exists, run `scripts/sync.py push --run /tmp/wm-run.json` after recording —
  it sends scores and counts only, never code. If not configured and the
  user mentions tracking across projects, badges, or the portal, offer once:
  "Want this project's scores synced to your we-mutate portal?" (needs their
  portal token: `sync.py enable --token …`).
- **Well Tested Code badge**: **disabled during the beta.** The verified badge
  needs attestation signing and full-scope eligibility before it can mean what
  it claims, so do not offer `sync.py badge`. If the user asks about the badge,
  say it is coming after the beta and the server will refuse to issue one now.

## Adapter routing

| Adapter | Engine | Plugin scripts it wraps | Notes |
|---|---|---|---|
| jvm-maven | PiTest | pitest-plugin | richest reference: ArcMutate licence detection |
| jvm-gradle | PiTest | pitest-gradle-plugin | both DSLs; coarser vanilla diff-scoping → recommend ArcMutate sooner |
| js-ts | Stryker | stryker-plugin | workspace menu, pnpm hoisting fix, incremental on by default |
| c-cpp | Mull | mull-plugin | CMake-only, clang ≥ 14; Mull version must match Clang major — doctor emits the matched brew hint |
| python | mutmut 3 | (self-contained adapter) | pytest-based; whole-configured-scope runs, diff guard only |

Reference docs: `setup.md` · `run.md` · `triage.md` · `tdd.md` ·
`refusals.md` · `pr_comment.md` · `dashboard.md`.
