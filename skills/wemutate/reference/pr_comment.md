# PR comment — one per PR, edited in place

Field-validated flow (M0.3): find-or-create by hidden marker, then edit.

- Offer **once per branch** (tracked in state `pr_comment_branches`); never
  re-offer after a no.
- Marker: `<!-- wemutate-report -->` as the first line of the body.
- Find: `gh api repos/{owner}/{repo}/issues/{pr}/comments --jq '.[] |
  select(.body | startswith("<!-- wemutate-report -->")) | .id'`
- Absent → `gh pr comment N --body-file body.md`.
  Present → `gh api -X PATCH repos/{owner}/{repo}/issues/comments/{id} -F body=@body.md`.
- Body: score card with delta vs previous run, counts table
  (found/hidden/uncovered using WM vocabulary), top hidden mutants
  (max 5, four-step framing condensed to one line each), methodology
  footer line.
- Requires `gh` authenticated; if not, say what's missing
  (`gh auth login`) rather than failing silently.

The legacy per-plugin `pr_comment.py` scripts still generate engine-specific
bodies; until the WM-v1 renderer ships (M4), generate the body from the
canonical run document inline using the same structure.
