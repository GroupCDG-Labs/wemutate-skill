# Run — scopes, exit codes, per-adapter behaviour

`wm-engine run --scope=diff|staged|full [extra engine args…]`

| Exit | Meaning | Skill response |
|---|---|---|
| 0 | report produced | proceed to `report --canonical` |
| 3 | empty diff | **ask** before widening to full — never silent, and in plain language (below) |
| 4 | engine/build failure | show the engine's own diagnostics, offer doctor |
| 5 | licence required | explain which feature needs it (`reference` in plugin docs) |

After every run: `state.py record-run`, then `term_dashboard.py` — show the
scorebox verbatim in a code block (SKILL.md step 5 has the cadence rules).
Use `state.py delta` for the narrative beneath it when history exists
("2 mutants newly found, 1 newly hidden — `delta` lists which").

## Per-adapter notes

- **jvm-maven**: vanilla diff-scoping passes changed FQCNs as
  `-DtargetClasses`; with ArcMutate it uses native `+GIT(from[HEAD~1])` —
  faster and line-accurate.
- **jvm-gradle**: vanilla scoping is class-coarse (`-PpitestTargetClasses`);
  if runs feel slow on diffs, recommend ArcMutate earlier than on Maven.
- **js-ts**: Stryker `--since HEAD`; incremental cache
  (`.stryker-tmp/incremental.json`) reused by default — mention when a rerun
  is suspiciously fast, and how to clear it.
- **c-cpp**: per-file `--include-path` scoping; builds can dominate runtime —
  prefer the smallest diff scope that answers the user's question.

- **python**: mutmut 3 mutates the configured `paths_to_mutate` as a whole —
  there is no native per-file scoping yet. The diff guard still applies
  (exit 3 on no changed Python files), but a non-empty diff runs the
  configured scope; say so honestly when the project is large. mutmut's
  trampoline design makes full runs fast (one mutated module import, no
  re-collection per mutant).

## The empty-diff ask (exit 3) — plain language, no jargon

The person asking may never have heard of mutation testing. Never say
"diff", "scope", "widen", or "mutate incrementally" in this question.
Canonical phrasing for a clean checkout:

> You haven't changed any code since the last commit, so a changes-only
> check has nothing to look at. Want me to check the whole project
> instead? It takes longer, but you'll get a baseline of how well your
> tests would catch real bugs.

Adapt the first sentence to the situation (e.g. uncommitted changes exist
but in files this target doesn't cover), keep the shape: what happened,
in plain words → the whole-project offer as a question → what they get
for the extra time. On a large project, include the time warning here
rather than after they say yes.

Long runs: warn before anything likely over ~2 minutes (full scopes,
C++ builds) and say why; offer the smaller scope.
