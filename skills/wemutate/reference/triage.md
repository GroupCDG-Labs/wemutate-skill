# Triage — explaining hidden mutants

Every hidden/uncovered mutant gets the four-step framing (SKILL.md hard rule
2). Step ③ uses the canonical kind's plain-English template — never the
engine operator name.

## Kind → plain English

| Kind | Say |
|---|---|
| boundary | "A comparison boundary was moved (`<` became `<=`). Your tests pass either way — the exact boundary is never asserted. Off-by-one territory." |
| negate_conditional | "This condition was flipped entirely and no test noticed — the branch's behaviour is never pinned down." |
| remove_conditional | "This check was forced to always-true/always-false and every test still passed — the guard is effectively untested." |
| arithmetic | "An arithmetic operator was swapped (`+` → `-`). No test asserts the computed value." |
| logical | "An `and` became an `or` (or vice versa) and nothing failed — the combination of conditions isn't tested." |
| unary | "A sign or increment direction was reversed without any test noticing." |
| constant | "A literal value was changed and no assertion pinned the original." |
| return_value | "The return value was replaced and every caller's test still passed — the result is never actually checked." |
| null_handling | "A value was replaced with null (or a null-check removed) and no test caught it." |
| remove_call | "This call was deleted entirely and the tests still passed — its effect is never verified." |
| exception_handling | "Error handling was weakened (a throw removed or a catch silenced) without a test failing — the failure path is untested." |
| string | "A string literal was changed; nothing asserts its content." |
| collection | "The result was emptied and no test noticed the missing elements." |
| async | "Async behaviour was altered (an await/scheduling change) and tests didn't catch it." |
| regex | "The regular expression was mutated and still matches/passes everything the tests try." |
| extreme | "The entire body of this function was removed and every test still passed — nothing observes what it does." |
| other | Translate honestly from the engine description; quote the engine operator only if the user asks. |

## Resolutions

- `test_gap` — missing assertion; offer the smallest killing test as an Edit
  (step ④), set `--fix-applied` once accepted.
- `real_bug` — the mutant exposed an actual defect. Celebrate plainly; this
  feeds "bugs prevented".
- `dead_code` — the mutant proved the code has no observable effect (classic
  tells: an `extreme` mutant that removes a whole body and nothing fails, or
  a branch that can never matter). Offer the *deletion* as the fix. After the
  user accepts, count the removed lines from the diff you applied and record
  them: `state.py triage <wmid> --resolution dead_code --lines-removed N
  --notes "…"`. This feeds the impact report ("40 lines of bloat removed,
  code 5% shorter") — only record lines actually deleted, never estimates.
- `equivalent` — semantically identical mutation; remove from the
  denominator.
- `suppressed` — deliberately out of scope. **Notes are mandatory** (state.py
  enforces this).
- `deferred` — parked; it ages visibly on the dashboard.

Write notes the user would be happy to see quoted on a leadership dashboard
— they are rendered verbatim.

## Security tags

Mutants may carry `security_tags` (validation, error_path, auth_check,
bounds_check, null_guard, crypto, injection_guard, resource_limit), each with
confidence and a one-line rationale. Wording rules are binding (spec §5.2):

- Say "untested security-relevant path", **never** "vulnerability" or
  "security hole in your code". The hole is in the *tests*.
- Use the rationale: "a size comparison was mutated — off-by-one territory —
  and no test noticed."
- An `uncovered` + security-tagged mutant is the worst case ("no test even
  executes this auth check") — its severity is floored high; lead with it.
- False positive? `state.py clear-tag <wmid> <tag>` — cleared tags never
  return for that mutant, and severity is re-scored without the bonus.

## Uncovered (NoCoverage) phase

After hidden mutants are triaged, offer the uncovered group once:
"N mutants sit on lines no test executes — want me to draft coverage for the
highest-value ones?" Draft tests one file at a time; don't dump.
