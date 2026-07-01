# Setup — per-adapter doctor branching and build integration

Always `wm-engine doctor` first. Shared rules: never edit a build file
without showing the plan diff and getting a yes; tests must be green before
any run; pinned tool versions come from each plugin's `versions.json`, never
hard-coded.

## jvm-maven (PiTest)

- Doctor reports JDK, JUnit 5 presence, existing pitest config, ArcMutate
  licence (env `ARCMUTATE_LICENSE` → `~/.arcmutate/` → project root).
- Setup = `pom.xml` plugin block via the plan/apply editor.
- JUnit 4-only or missing surefire → refuse with upgrade path.

## jvm-gradle (PiTest via info.solidsoft.pitest)

- Doctor detects DSL (Groovy vs Kotlin) — frequent regression surface; both
  must work.
- Setup injects the plugin block **and** the one-line
  `pitestTargetClasses` property bridge (vanilla diff-scoping needs it).
- Multi-module: doctor enumerates modules; ask which (`--module`).
- Kotlin sources present → mention ArcMutate's Kotlin filtering early.

## js-ts (Stryker)

- Doctor detects package manager (npm/yarn/pnpm), test runner (jest, vitest,
  mocha, jasmine, karma), workspaces.
- Workspaces/monorepo → present the sub-package menu (with runner hints);
  remember choice.
- pnpm → setup writes the `.npmrc` public-hoist workaround.
- TypeScript → add `@stryker-mutator/typescript-checker` + `checkers` config.

## c-cpp (Mull)

- Requirements doctor enforces: CMake (only), clang ≥ 14, macOS/Linux,
  GTest/Catch2/doctest.
- **Mull is strictly tied to the Clang major version** (Clang 18 needs
  `mull@18`). The doctor detects the project's Clang and emits a
  version-matched `install_hint` (e.g. `brew tap mull-project/mull && brew
  install mull-project/mull/mull@18`) — relay it verbatim, and explain the
  matching rule in one line so the user understands *why* the version is
  pinned. If Mull is installed but built for a different LLVM major, the
  doctor warns with the same matched hint; treat that as "reinstall the
  matching version", not as ok.
- `mull-runner` missing → *offer* to install (system-level: explicit yes
  required; see mull-plugin `reference/install.md`). Known issue: upstream
  Homebrew downloads have been failing intermittently (Cloudsmith 402) — if
  the install fails that way, say so and offer the source-build link
  (https://mull.readthedocs.io/en/latest/Installation.html) rather than
  retrying.
- Setup writes self-contained `cmake/MullIntegration.cmake` + a single
  `include()` line — keep CMakeLists edits minimal.

## python (mutmut 3)

- Doctor checks Python, pytest, mutmut importability (`pip install mutmut`
  hint when missing), and `[tool.mutmut]` in pyproject.toml.
- Setup proposes the `[tool.mutmut]` block (paths_to_mutate/tests_dir guessed
  from src/ and tests/ layout) as a diff; apply on approval.
- mutmut runs tests via pytest; pytest must be importable from the same
  Python. If imports fail under mutation, check `pythonpath` in
  `[tool.pytest.ini_options]`.

Deep details live in each plugin's own `reference/setup.md`; consult them
when an edge case appears rather than improvising.
