# TDD micro-loop

For users working red→green: after each green, mutate only what they just
touched.

- Scope: `run --scope=staged` (or `diff` if they commit per cycle).
- Target: sub-minute feedback. If the adapter/project can't deliver that
  (C++ builds, cold Gradle), say so and fall back to end-of-session runs.
- Framing: hidden mutants here are *assertions you haven't written yet*, not
  failures — keep the tone of a pairing partner, not an auditor.
- Cadence: offer the loop once when you notice the pattern (several
  test-then-code edits); if declined, drop it for the session.
- Each cycle's output is one line unless something is hidden:
  "All 4 mutants on your new code found. Next."
