# Fixture Expected Results

Each fixture is run with `python pre_llm_checks.py --path <fixture> --steps <stages>`.
A language is promoted to `verification = "tested"` when all applicable fixtures match.

## Node/TS (`tests/fixtures/node/`)

| Fixture    | Stages         | Build | Lint | Tests | Coverage | Exit |
|------------|----------------|-------|------|-------|----------|------|
| ok         | build,lint,tests | PASS | PASS | WARN  | SKIP     | 0    |
| build-fail | build,lint,tests | FAIL | SKIP | SKIP  | SKIP     | 1    |
| test-fail  | build,tests    | PASS  | SKIP | FAIL  | SKIP     | 1    |
| lint-fail  | build,lint,tests | PASS | FAIL | PASS  | SKIP     | 1    |
| no-tests   | build,lint,tests | PASS | SKIP | SKIP  | SKIP     | 0    |

Note: Tests shows WARN (not PASS) for `ok` because `node -e "process.exit(0)"` produces
no test output, triggering the zero-tests heuristic. This is correct per spec.

## Python (`tests/fixtures/python/`)

No `build` stage (Python has no compile step). Run with `--steps lint,tests`.

| Fixture      | Lint | Tests | Exit |
|--------------|------|-------|------|
| ok           | PASS | WARN  | 0    |
| test-fail    | PASS | FAIL  | 1    |
| lint-fail    | FAIL | SKIP  | 1    |
| no-tests     | PASS | SKIP  | 0    |
| missing-deps | SKIP | WARN  | 0    |

Note: missing-deps maps `ModuleNotFoundError` output to `dependencies_missing` warning status.

## Java Maven (`tests/fixtures/java-maven/`)

Requires `mvn` on PATH. Run with `--steps build,tests`.

| Fixture    | Build | Tests | Exit |
|------------|-------|-------|------|
| ok         | PASS  | PASS  | 0    |
| build-fail | FAIL  | SKIP  | 1    |
| test-fail  | PASS  | FAIL  | 1    |

## Shared edge-case fixtures

| Fixture         | Purpose                                      |
|-----------------|----------------------------------------------|
| monorepo        | Two projects (node + python) in one tree     |
| missing-deps    | Node project with no node_modules/ (deps check) |
