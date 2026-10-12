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

Note: `ok` runs `node --test test.mjs` (real test) → PASS (not WARN).
Note: `test-fail` has no `lint` script so Lint=SKIP; run with `--steps build,tests`.
Note: `config-trigger` has `.eslintrc.json` but no `lint` npm script. Config triggers
  no longer generate synthetic commands → Lint=SKIP (not an unrunnable fail).

| config-trigger | PASS | SKIP | SKIP | 0 | has .eslintrc but no lint script |

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

Note: `ok` runs `python -m unittest discover` (real test) → PASS (not WARN).
Note: `missing-deps` maps `ModuleNotFoundError` output to `dependencies_missing` warning
  AND now emits a structured Warning entry in the report (type=dependencies_missing).
Note: `entry-points` has only `[project.scripts]` PEP 621 entry points which are NOT
  shell commands → no runnable scripts found → nothing_to_run warning, all stages SKIP.

| entry-points | SKIP | SKIP | 0 | [project.scripts] entry points ignored |

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

| Fixture      | Purpose                                                     |
|--------------|-------------------------------------------------------------|
| monorepo     | Two projects (node + python) in one tree                    |
| missing-deps | Node project with no `node_modules/` — dependencies_missing Warning emitted |

---

## Spec compliance notes (fixes applied)

| # | Issue | Fix |
|---|-------|-----|
| 1 | Unexpected exception wrote no report | `main()` now catches all non-SystemExit exceptions, writes `summary.status="error"` report, exits 2 |
| 2 | `summary.status="warning"` when only stage-warnings | Status is now always `"pass"` unless there is a hard fail or timeout; warnings alone → pass + exit 0 |
| 3 | `tool_not_installed` / `dependencies_missing` not in warnings list | Both now emit structured `Warning` entries visible in the JSON `warnings` array |
| 4 | Config-trigger path generated unrunnable `[eslint via .eslintrc]` commands | Removed; config triggers are detection-only; runnable commands must come from declared scripts or builtin_triggers |
| 5 | `[project.scripts]` PEP 621 entry points treated as shell commands | `_read_declared_scripts` no longer reads `[project.scripts]`; only `[tool.taskipy.tasks]` |
| 6 | Long identifiers and git SHAs masked by `{32,}` patterns | Hex pattern raised to `{64,}`; base64 pattern now requires `+` or `/` in the match |
| 7 | `ok` fixtures showed Tests=WARN due to false-positive in `_zero_tests_detected` | Fixed in previous session; `ok` now shows Tests=PASS |
