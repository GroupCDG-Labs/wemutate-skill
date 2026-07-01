# we-mutate mutation skill for Claude Code

Mutation testing for Java (Maven & Gradle), JavaScript/TypeScript, Python, and C/C++ projects — one skill, one vocabulary, driven from Claude Code. Ask Claude to "check my test quality" or "run mutation testing" and this skill takes over: it detects your language, resolves the right engine (PiTest, Stryker, mutmut, or Mull), runs mutation analysis on your git diff, and surfaces hidden mutants one at a time in plain English — with the missing assertion suggested as an inline edit.

No prior mutation-testing knowledge required. The skill explains what a "mutant" is the first time it matters and gets out of the way after that. Whatever the language, the results speak the same vocabulary: the same statuses (hidden / found / uncovered), the same score formulas, the same dashboard.

## About this repository (open source)

This repo is the **open skill shell** — SKILL.md, reference docs, and the
orchestration scripts (MIT, see `LICENSE`). It's here to be read and audited:
it's pure orchestration (detect language → resolve engine → run → render) and
contains **no mutation-testing engine logic**.

It is **not directly installable on its own** — the scripts call a we-mutate
engine, which is a separate proprietary component the skill downloads on first
run from the we-mutate registry (matched to your platform, checksum-verified).
So clone this to *understand* exactly what the skill does; to *use* it, install
the published plugin (which fetches its engine). The engines under the hood are
the open source projects [PiTest](https://pitest.org),
[Stryker](https://stryker-mutator.io), [mutmut](https://github.com/boxed/mutmut),
and [Mull](https://github.com/mull-project/mull).

## What it does

- **Language detection** — finds your build (pom.xml, build.gradle(.kts), package.json, pyproject.toml, CMakeLists.txt); monorepos get a menu of targets, never a guess.
- **One-command setup** — proposes the engine integration for your build file and applies it only after showing you the diff.
- **Diff-by-default** — mutation runs scope to your changed files. Whole-codebase runs are explicit opt-in, every time.
- **Plain-English mutants** — never surfaces raw mutator names. Quotes the actual line, names the test that should have caught the bug, suggests the smallest fix to close the gap.
- **One canonical model** — every engine's output is normalised to WM Report Format v1: stable mutant IDs that survive line-number changes, unified taxonomy, scores comparable across languages.
- **Persistent memory** — `.wemutate/state.json` tracks score history, trends, and triaged mutants across sessions; one-time migration from older `.pitest/` state included.
- **Shareable dashboard** — single-file HTML with score card, trend sparkline, bugs-prevented narrative, security panel, and per-file strength map.
- **PR comments** — one comment per PR, edited in place on reruns (via your existing `gh` auth).
- **ArcMutate-aware** — detects a licence on JVM projects and switches to native git-diff scoping.

## Requirements

| Language | Build | Test framework | Engine |
|---|---|---|---|
| Java 17+ | Maven (single-module) or Gradle | JUnit 5 | PiTest |
| JavaScript / TypeScript | npm, yarn, or pnpm | Jest, Vitest, Mocha, Jasmine, Karma | Stryker |
| Python 3.9+ | pyproject.toml | pytest | mutmut 3 |
| C / C++ | CMake | GoogleTest, Catch2, doctest | Mull (clang ≥ 14, matched to your Clang major) |

Plus Claude Code. For Rust, JUnit 4, TestNG, Make/Meson/Bazel, or Android: the skill politely refuses with a concrete next step.

## Install

The plugin is built from this repo, then installed from the build output:

```bash
python3 tools/build_plugin.py            # assembles dist/wemutate (self-contained)
```

Then in Claude Code:

1. Register the built plugin as a marketplace source:
   `/plugin marketplace add ./dist/wemutate`
2. Install the plugin from that source:
   `/plugin install wemutate@wemutate`

Once installed, the **wemutate** plugin contains the **wemutate** skill, which auto-activates whenever you ask Claude about mutation testing, test quality, or whether your tests would catch bugs. You can also invoke it manually with `/wemutate:wemutate`.

To update after repo changes: rebuild, then `/plugin marketplace update wemutate` and reinstall. To uninstall: `/plugin uninstall wemutate`.

## Usage

Open Claude Code in any supported project and ask any of:

- "Set up mutation testing"
- "Check the quality of my tests"
- "Are there any test gaps in the code I just changed?"
- "Would my tests actually catch bugs in Cart.java?"
- "Walk me through TDD with mutation feedback"
- "Show me the mutation dashboard"

The skill auto-invokes when these patterns appear; you don't need to call it by name.

## How it works

1. `detect.py` finds the build manifests and picks (or asks about) the target.
2. `resolve_engine.py` resolves the engine adapter for your language and prints what it resolved, with checksum.
3. The adapter's `doctor` reports project state (toolchain, test framework, existing config, licences). Unsupported setups are refused with a reason and a next step.
4. If integration is missing, `setup` proposes a build-file diff and waits for your approval.
5. `run --scope=diff` executes the engine against your changed files only.
6. `report --canonical` normalises the engine's output to WM Report Format v1; `state.py` records history and computes the trend.
7. The skill surfaces one hidden mutant at a time in plain English and offers the fix as an Edit; your triage decisions persist.

## Layout

```
.
├── .claude-plugin/
│   ├── plugin.json              # plugin manifest
│   └── marketplace.json         # marketplace manifest
├── README.md
└── skills/
    └── wemutate/                # the skill itself
        ├── SKILL.md             # operating rules + pipeline
        ├── reference/           # on-demand docs (setup, run, triage, tdd, …)
        └── scripts/             # detect.py, resolve_engine.py, state.py, dashboard.py

# vendored into the build by tools/build_plugin.py:
#   wm/ (canonical model library) · spec/ (schema + operator mappings)
#   adapters/*/wm-engine (uniform engine CLIs) · per-engine glue scripts
```

## Privacy

All analysis runs locally via your build tool and the bundled open source engines. The skill writes `.wemutate/state.json` in your project (add it to `.gitignore` if you want triage state local). Nothing leaves your machine unless you explicitly ask the skill to post a PR comment via your own `gh` auth.

## Licensing

The distribution is open-core, and the boundary is explicit:

- **Open (MIT):** the skill shell — `skills/wemutate/` (SKILL.md, reference docs, orchestration scripts). See `LICENSE-SKILL.md`.
- **Proprietary:** the canonical-model library, operator mapping tables, security rule packs, severity model, and engine adapters. Readable in the package, but licensed for use only — no redistribution or derivative works. See `LICENSE-PROPRIETARY.md`.
- **Open (CC0):** the WM Report Format v1 JSON schema — anyone may produce or consume conforming documents.
- **Third-party engines:** their own licences, unaffected; see `THIRD-PARTY.md`.

## Open source notice

The mutation engines are [PiTest](https://pitest.org), [Stryker](https://stryker-mutator.io), [mutmut](https://github.com/boxed/mutmut), and [Mull](https://github.com/mull-project/mull) (Apache-2.0 / BSD-3-Clause). Run `wm-engine licenses` on any adapter for the embedded notices. we-mutate is built on these projects and is not affiliated with or endorsed by them — and if one tool for one language is all you need, we encourage using them directly. For the commercial JVM layer (Kotlin support, Spring-aware operators, native git scoping), see [arcmutate.com](https://arcmutate.com).
