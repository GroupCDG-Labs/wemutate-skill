# Refusals — always a reason plus a next step

Refuse honestly and offer the closest path forward. Never a dead end.

- **Unsupported language detected (rust)**: "we-mutate doesn't ship a Rust
  engine yet (it's on the roadmap). If you want, I can point you at
  cargo-mutants, which covers the basics today."
- **No build manifest found**: name what was looked for (pom.xml,
  build.gradle, package.json, CMakeLists.txt) and ask where the project
  root is.
- **Tests are red**: "Mutation testing on a failing build can't tell you
  anything — every mutant would 'fail' for the wrong reason. Want me to look
  at the failing tests first?"
- **JUnit 4 only (jvm)**: PiTest needs JUnit 5 here; offer the migration or
  a pointer.
- **Non-CMake C/C++ build** (Make/Meson/Bazel): Mull integration is
  CMake-only today; say so, don't attempt a hack.
- **GCC-only toolchain**: Mull requires clang ≥ 14; offer to check for an
  installable clang.
- **Mull not installed**: offer the install (explicit yes, it's
  system-level). Currently also disclose: upstream Homebrew packages are
  failing to download (their hosting quota); source build is the workaround.
- **`--scope=full` requested implicitly** ("just run everything"): confirm
  once with an estimate ("full scope on this project mutates ~N classes and
  can take a while — go ahead?").
- **User asks to skip approval on build edits**: still show the diff; apply
  immediately after, but never invisibly.
