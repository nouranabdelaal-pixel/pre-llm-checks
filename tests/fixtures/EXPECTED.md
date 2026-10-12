# Fixture Expected Results

Each fixture is run with `python pre_llm_checks.py --path <fixture> --steps <stages>`.
A language is promoted to `verification = "tested"` when all applicable fixtures match.

---

## Node/TS (`tests/fixtures/node/`)

Run with `--steps build,lint,tests`.

| Fixture    | Build | Lint | Tests | Exit |
|------------|-------|------|-------|------|
| ok         | PASS  | PASS | PASS  | 0    |
| build-fail | FAIL  | SKIP | SKIP  | 1    |
| test-fail  | PASS  | SKIP | FAIL  | 1    |
| lint-fail  | PASS  | FAIL | PASS  | 1    |
| no-tests   | PASS  | SKIP | SKIP  | 0    |

Note: `ok` runs `node --test test.mjs` (real test) → PASS.
Note: `test-fail` has no `lint` script so Lint=SKIP; run with `--steps build,tests`.

---

## Python (`tests/fixtures/python/`)

No `build` stage. Run with `--steps lint,tests`.

| Fixture      | Lint | Tests | Exit |
|--------------|------|-------|------|
| ok           | PASS | PASS  | 0    |
| test-fail    | PASS | FAIL  | 1    |
| lint-fail    | FAIL | PASS  | 1    |
| no-tests     | PASS | SKIP  | 0    |
| missing-deps | SKIP | WARN  | 0    |

Note: `ok` runs `python -m unittest discover` (real test) → PASS.
Note: `missing-deps` maps `ModuleNotFoundError` output to `dependencies_missing` warning.

---

## Java Maven (`tests/fixtures/java-maven/`)

Requires `mvn` on PATH. Run with `--steps build,lint,tests`.

| Fixture    | Build | Lint | Tests | Exit |
|------------|-------|------|-------|------|
| ok         | PASS  | SKIP | WARN  | 0    |
| build-fail | FAIL  | SKIP | SKIP  | 1    |
| test-fail  | PASS  | SKIP | FAIL  | 1    |
| lint-fail  | PASS  | FAIL | WARN  | 1    |
| no-tests   | PASS  | SKIP | WARN  | 0    |

Note: Lint builtins (`checkstyle:check` etc.) require `builtin_requires_trigger=true`;
  they only run when a config trigger file (checkstyle.xml etc.) is present.
  `ok`, `build-fail`, `test-fail`, `no-tests` have no trigger files → Lint=SKIP.
Note: `lint-fail` has `checkstyle.xml` → Checkstyle runs and fails.
  After lint fails, tests still run (lint failure does not gate tests).
  Tests has no test sources → "No tests to run." → WARN.
Note: Tests=WARN because `mvn test` with no test sources outputs "No tests to run."
  triggering the zero-tests heuristic. This is correct per spec (US-36).

---

## Java Gradle (`tests/fixtures/java-gradle/`)

**Cannot run on this machine** — `gradle` is not on PATH and no `gradlew` wrapper present.
Fixture `java-gradle/ok` exists with a stub `build.gradle` but cannot be executed.
`java_gradle` and `kotlin` remain `verification = "untested"` in `languages.toml`.

---

## Shared edge-case fixtures (ticket 04)

Run with `--steps build,lint,tests` unless noted.

| Fixture           | Build | Lint | Tests   | Exit | Notes                                              |
|-------------------|-------|------|---------|------|----------------------------------------------------|
| risky-scripts     | PASS  | PASS | PASS    | 0    | lint:fix, lint:watch, test:e2e, test:docker skipped|
| duplicate-scripts | PASS  | SKIP | PASS    | 0    | test + test:unit deduplicated to one command run   |
| hang              | PASS  | SKIP | TIMEOUT | 1    | run with `--timeout-tests 3s`                      |

Note: `risky-scripts` keeps `lint` and `test` (both pass); variants with bad suffixes are skipped.
Note: `duplicate-scripts` `test` and `test:unit` both resolve to `node --test test.mjs` → run once.
Note: `hang` must be tested with `--timeout-tests 3s` to avoid blocking the suite.

---

## Coverage fixtures (ticket 09)

Run with `--steps tests,coverage`. The `coverage` script writes a fresh report file.

| Fixture            | Tests | Coverage | Exit | Expected %          |
|--------------------|-------|----------|------|---------------------|
| coverage-istanbul  | PASS  | PASS     | 0    | 85.0% (istanbul)    |
| coverage-jacoco    | PASS  | PASS     | 0    | 85.0% (jacoco-xml)  |
| coverage-cobertura | PASS  | PASS     | 0    | 72.0% (cobertura)   |
| coverage-lcov      | PASS  | PASS     | 0    | 80.0% (lcov)        |
| coverage-stale     | PASS  | WARN     | 0    | — (stale file)      |

Note: `coverage-stale` has a pre-committed `coverage/coverage-summary.json`.
  The freshness check (mtime < run_start) rejects it. No stdout regex match either → WARN.

---

## Other shared fixtures

| Fixture      | Purpose                                              |
|--------------|------------------------------------------------------|
| monorepo     | Two projects (node + python) in one tree             |
| missing-deps | Node project with no `node_modules/` — deps warning  |
