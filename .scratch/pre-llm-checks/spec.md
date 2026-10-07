# Spec: pre-llm-checks

Status: ready-for-agent

---

## Problem Statement

Before handing a repository to an LLM code reviewer, developers need to know whether the code actually builds, passes lints, and has passing tests. Running checks manually across a polyglot monorepo is tedious and error-prone: different languages use different tools, different project structures, and different conventions. There is no standard way to discover what checks exist, run only the project-defined ones, and produce a structured summary that an LLM can consume without noise.

---

## Solution

A local, cross-platform (Windows/macOS/Linux) Python script — `pre-llm-checks` — that scans a repository, discovers projects by their build files, runs build → lint → tests → coverage using only tools the project itself defines, and produces both a human-readable terminal table and a machine-readable `pre-llm-report.json`. The script is strictly read-only: it never modifies files, never installs dependencies, and never runs formatters or fixers. Requires Python 3.11+ (uses `tomllib` from the standard library).

---

## User Stories

1. As a developer, I want the script to discover all projects in a repo automatically, so that I don't have to list them manually.
2. As a developer, I want projects identified by their build files (package.json, pom.xml, pyproject.toml, etc.), so that the script works without any per-repo configuration.
3. As a developer, I want each build file to only match files of the language it builds, so that a root package.json does not claim Java files.
4. As a developer, I want the nearest ancestor build file to win, so that monorepo sub-packages are matched correctly.
5. As a developer, I want the script to only run tools that the project itself defines (explicit scripts, built-in tasks, or configured plugins), so that I get no false results from globally-installed tools.
6. As a developer, I want Maven/Gradle built-in lifecycle phases to count as project-defined, so that Java projects work without explicit script entries.
7. As a developer, I want tools configured via project config files (tsconfig.json, ESLint config, Checkstyle config, etc.) to count as project-defined, so that common tooling patterns are discovered automatically.
8. As a developer, I want dependency-only devDependencies with no script entry and no config file to be ignored, so that the script doesn't try to run tools that have no defined invocation.
9. As a developer, I want the pipeline to run build → lint → tests → coverage opportunistically (skipping stages not defined for a project), so that Python projects without a build step still get linted and tested.
10. As a developer, I want a build failure to stop the remaining stages of that project by default, so that lint and test results against broken code are not reported as meaningful.
11. As a developer, I want a `--lint-anyway` flag to run lint even when build fails, so that I can diagnose lint issues independently.
12. As a developer, I want every script whose name matches a stage's exact names or prefixes (e.g. `lint:*`) to be run for that stage, so that all configured checks are exercised.
13. As a developer, I want scripts matching an exclude list (`:fix`, `:watch`, `:dev`, `:serve`, `:e2e`, `:docker`, `:deploy`) to be skipped, so that the script never triggers file-modifying or long-running processes.
14. As a developer, I want skipped scripts recorded in the report with their reason, so that the LLM and human reviewer can see what was intentionally excluded.
15. As a developer, I want commands that are identical after whitespace normalization to run only once, with all matching script names recorded together, so that duplicate checks don't waste time.
16. As a developer, I want different arguments to count as different commands (e.g. `jest` vs `jest --ci`), so that variant invocations are not silently merged.
17. As a developer, I want all commands run from the directory containing the project's build file, so that relative paths in configs resolve correctly.
18. As a developer, I want the script to prefer project wrappers (mvnw, gradlew, mvnw.cmd, gradlew.bat) over globally-installed tools, so that the project's pinned tool version is always used.
19. As a developer, I want a warning when a required runner is not installed and the stage to be skipped (not failed), so that missing global tools don't produce false failures.
20. As a developer, I want commands launched as argument lists without shell=True, so that there is no risk of command injection.
21. As a developer, I want per-stage timeouts (build 10m, lint 5m, tests 15m, coverage 15m) with CLI overrides, so that hung processes don't block the run indefinitely.
22. As a developer, I want the entire process tree killed on timeout, so that child processes don't linger on any platform.
23. As a developer, I want timeout to be a distinct status (not "fail"), recorded in the report, and to count toward exit code 1.
24. As a developer, I want a build timeout to stop that project's remaining stages, like a build failure.
25. As a developer, I want projects to be independent — a failure in one does not stop others — so that I get a complete picture of the repo in one run.
26. As a developer, I want command output buffered by default with a live progress line showing elapsed time, so that the terminal is readable during a long run.
27. As a developer, I want full command output saved to `.pre-llm/logs/<slug>.log`, so that I can inspect failures in detail.
28. As a developer, I want `.pre-llm/` to be gitignored; if it is not, I want a structured `gitignore_missing` warning with the exact line to add, so that logs are never accidentally committed.
29. As a developer, I want a `--add-gitignore` flag that lets the script add `.pre-llm/` to `.gitignore` itself, so that I can opt in to that one write operation explicitly.
30. As a developer, I want a `--verbose` flag to stream command output live, so that I can debug a failing tool interactively.
31. As a developer, I want the last N lines (default 50, overridable via `--tail-lines <N>`) of each command's output included in the JSON report, so that the LLM can see the failure context without reading log files.
32. As a developer, I want common secret patterns (tokens, API keys, passwords, connection strings) masked in `output_tail` and terminal output, so that credentials are never written into the report.
33. As a developer, I want full unmasked logs kept only in the local, gitignored `.pre-llm/` directory.
34. As a developer, I want the script to detect missing dependencies before running each project, warn with type `dependencies_missing`, and skip that project's stages without failing.
35. As a developer, I want the script to never install dependencies, so that it has no side effects on the project.
36. As a developer, I want zero tests executed to produce status "warning" (not "pass"), so that an empty test suite is not silently treated as green.
37. As a developer, I want a terminal summary table with one row per project showing Project | Language | Build | Lint | Tests | Coverage, so that I can assess the repo at a glance.
38. As a developer, I want each stage cell to show the worst status among that stage's tools (fail > timeout > warning > pass; SKIP if not run), so that no failure is hidden by an aggregate.
39. As a developer, I want the coverage cell to show the lowest coverage percentage across tools with a count (e.g. "64% (2)"), so that the worst case is always visible.
40. As a developer, I want detail lines below the table only for non-passing commands (project › stage › command, status, duration, last output lines, log path), so that passing runs produce no noise.
41. As a developer, I want a warnings section and an overall summary line below the table.
42. As a developer, I want `--verbose` to print a row for every command, not just failures.
43. As a developer, I want the table in plain text (no colour required) so that it works on all terminals; optional colour if the terminal supports it.
44. As a developer, I want `pre-llm-report.json` with a versioned schema (starting at "1.0"), a summary block, typed warnings, relative paths, and fixed status enum values, so that the report is stable and machine-parseable.
45. As a developer, I want each command entry in the report to include: command, scripts (merged names), source (script name or config file), status, duration_s, output_tail, and log_path.
46. As a developer, I want all paths in the report relative to the repo root, so that the report is portable across machines.
47. As a developer, I want coverage extracted from report files first (timestamp-checked to ensure freshness), falling back to stdout regex, so that stale coverage results are never reported.
48. As a developer, I want built-in readers for JaCoCo XML, Cobertura XML, Istanbul json-summary, and lcov formats.
49. As a developer, I want line coverage as the primary metric with branch coverage included in the JSON when available.
50. As a developer, I want multiple coverage tools kept separately in the JSON (never averaged), so that the LLM sees the full picture.
51. As a developer, I want a missing or unreadable coverage report to produce a "warning" status (not "fail"), with the reason recorded.
52. As a developer, I want files in ignored directories (node_modules, .git, .next, target, build, dist, .venv, graphify-out, .ua, .pre-llm) excluded from scanning entirely.
53. As a developer, I want files with extensions on the `ignore_extensions` list (docs, images, configs, lock files, etc.) to produce no warnings.
54. As a developer, I want files with a source-code extension that has no rule in languages.toml to produce one warning per extension (grouped, with file count and example paths).
55. As a developer, I want files in a supported language with no matching project file to produce one warning per extension + top-level folder.
56. As a developer, I want warnings structured as typed objects (type, extension, folders, count, files capped at 50, "more" count, reason) in the JSON.
57. As a developer, I want the six warning types — `unsupported_extension`, `no_project`, `tool_not_installed`, `nothing_to_run`, `dependencies_missing`, `gitignore_missing` — to be the complete set in v1.
58. As a developer, I want a `nothing_to_run` warning emitted when a project is discovered but has no runnable scripts or tasks in any stage, so that I know the project was seen but produced no checks.
59. As a developer, I want language rules (extensions, project files, stage commands, config triggers, coverage report paths, output patterns, dependency checks) maintained in a `languages.toml` config file, so that adding a language requires no code change.
60. As a developer, I want the initial languages.toml to include: Java (Maven, Gradle), Kotlin (Gradle), JS/TS (package.json), Python (pyproject.toml/requirements.txt), Go (go.mod), C#/.NET (.csproj/.sln), Rust (Cargo.toml), PHP (composer.json), Ruby (Gemfile), Swift (Package.swift), C/C++ (CMakeLists.txt/Makefile).
61. As a developer, I want each language in languages.toml tagged as "tested" or "untested", so that I know which languages have been validated against real projects.
62. As a developer, I want exit code 0 when all commands pass or only warnings are present, 1 for any tool failure or timeout, 2 for script error, and 3 for no supported project found — so that warnings alone do not cause a non-zero exit.
63. As a developer, I want a `--dry-run` flag that detects projects, tools, and warnings and prints the same summary table with status PLANNED per stage plus the list of commands that would run, without executing anything.
64. As a developer, I want `--dry-run` with `--output` to write the JSON report with `"mode": "dry-run"` so that the plan is machine-readable.
65. As a developer, I want `--path <folder>` to target a specific subdirectory instead of the current directory.
66. As a developer, I want `--output <file>` to change the report path from the default `pre-llm-report.json`.
67. As a developer, I want `--steps <list>` to run a subset of build,lint,tests,coverage; stages excluded by `--steps` do not trigger the build-fail gate, and each skipped stage is noted in the report as "excluded by --steps".
68. As a developer, I want `--config <file>` to use an alternative languages.toml.
69. As a developer, I want `--version` to print the script version.
70. As a developer, I want Language rows in the terminal table tagged with `[untested]` when the language is not yet verified, so that I can trust the results appropriately.
71. As a developer, I want `--timeout-*` flags to accept duration formats `90s`, `30m`, `1h`, `1h30m`, or a plain integer (treated as seconds), so that I can express durations naturally.
71b. As a developer, I want `--tail-lines <N>` to accept a plain integer line count only, so that the interface is unambiguous.
72. As a developer, I want the report always written, even on script error (exit code 2), with `summary.status = "error"` and a top-level `"error"` field containing the message, so that consumers never encounter a missing report file.
73. As a developer, I want a project with multiple build files of the same language in one directory resolved by a priority list (Python: pyproject.toml > requirements.txt; .NET: .sln > .csproj), with all matched files recorded in `build_files`, so that there is always exactly one project per directory per language.

---

## Implementation Decisions

### Architecture

- Single cross-platform Python script; minimum Python 3.11 (uses `tomllib` from the standard library — no third-party TOML dependency).
- No compiled or third-party dependencies required to run the script itself.
- Configuration split into two layers: `languages.toml` (language registry, never hardcoded in code) and CLI flags (per-run overrides).
- All file I/O uses `pathlib.Path`; all subprocess calls use argument lists with `shell=False`.

### Project Discovery

- Walk the target directory recursively, skipping: `node_modules`, `.git`, `.next`, `target`, `build`, `dist`, `.venv`, `graphify-out`, `.ua`, `.pre-llm`.
- A **Project** is identified by a build file present in a directory. One project per directory per language.
- When multiple build files for the same language exist in one directory, a priority list in `languages.toml` selects which one governs; all matched files are recorded in `build_files`.
  - Python priority: `pyproject.toml` > `requirements.txt`
  - .NET priority: `.sln` > `.csproj`
- A source file is assigned to the nearest ancestor directory containing a build file for its language. Language affinity is enforced: `package.json` does not claim `.java` files.
- Root-level build files match only files that have no closer ancestor build file for that language.

### Tool Discovery (per Project)

A tool is **project-defined** if any of the following is true:
1. There is an explicit script/task entry in the build file (e.g. `"lint"` in `package.json` scripts).
2. The project file itself configures the tool (e.g. `<plugin>` in `pom.xml`, `plugins {}` in `build.gradle`).
3. A config file for the tool exists alongside the project file (e.g. `.eslintrc`, `tsconfig.json`), as declared in `languages.toml`.
4. The tool is a Maven/Gradle built-in lifecycle phase (e.g. `compile`, `test`).

Dependency-only entries in devDependencies with no script and no config file are not project-defined.

### Stage Matching

- Each stage (build, lint, tests, coverage) defines in `languages.toml`: exact script names and name prefixes (e.g. `lint:*`).
- Scripts matching an exclude list (`:fix`, `:watch`, `:dev`, `:serve`, `:e2e`, `:docker`, `:deploy`) are skipped regardless; the reason is recorded in `skipped_scripts`.
- The script never runs commands that modify files (`--fix`, `--write`, formatters).
- Deduplication: commands identical after trimming and collapsing whitespace run once; all matching script names are recorded together. Different arguments = different runs.
- A stage with no matching scripts gets a `skipped` status with a note; it does not emit a `nothing_to_run` warning. `nothing_to_run` is emitted only when a project has no runnable scripts across all stages.

### `--steps` and Build Gating

- `--steps <list>` restricts which stages are attempted. Excluded stages are recorded with reason `"excluded by --steps"`.
- If `build` is excluded by `--steps`, the build-fail gate does not apply; the requested stages run unconditionally with a note `"build not run (excluded by --steps)"`.
- If `build` is included and fails or times out: remaining stages are skipped, unless `--lint-anyway` is set (lint still runs).

### Execution

- Working directory: always the directory containing the project's build file.
- Runner selection: Node → `npm run <script>`; Maven → `./mvnw` (or `mvnw.cmd` on Windows) if present, else `mvn`; Gradle → `./gradlew` (or `gradlew.bat` on Windows) if present, else `gradle`; others as defined in `languages.toml`.
- If neither wrapper nor global runner is found → warning `tool_not_installed`, stage skipped (not failed).
- All commands launched as argument lists (`subprocess` with `shell=False`).

### Dependency Detection (per Project, before execution)

Each language entry in `languages.toml` may define an optional `dependency_check`:
- **Filesystem check**: presence/absence of a directory or file (e.g. `node_modules/` for Node). If the check fails → warning `dependencies_missing`, project stages skipped. Not used for Python (projects may use global, conda, or any non-`.venv` environment).
- **Output pattern**: the tool is run normally; if its output matches a known dependency-error pattern (defined per language in `languages.toml`), the command result is mapped to `dependencies_missing` instead of `fail`. Used as the sole dependency detection mechanism for Python (e.g. matching `ModuleNotFoundError`, `No module named`).
- The script never installs dependencies.

### Timeouts

- Default per stage: build 10m, lint 5m, tests 15m, coverage 15m.
- Overridable via CLI (`--timeout-build`, `--timeout-lint`, `--timeout-tests`, `--timeout-coverage`) and per language in `languages.toml`.
- Duration format: `90s`, `30m`, `1h`, `1h30m`, or plain integer (seconds).
- On timeout: kill the entire process tree (platform-aware, including Windows); status = `timeout`; last output lines and the limit are recorded.
- A timeout at build stage stops remaining stages, like a build failure.
- Timeout counts toward exit code 1; summary `status` treats any `timeout` as `fail`. Warnings alone never cause exit code 1.

### Output

- **Terminal**: buffered by default; one live progress line per command with elapsed time, replaced on completion. `--verbose` streams live.
- **Logs**: full output → `.pre-llm/logs/<rel-path-slug>--<stage>--<script-slug>.log` (e.g. `packages-api--lint--lint-types.log`). Gitignored.
- **output_tail**: last N lines per command (default 50, overridable via `--tail-lines <N>`); secret patterns masked before writing to report or terminal.
- **Table**: one row per project; columns: Project, Language (`[untested]` tag), Build, Lint, Tests, Coverage. Stage cell = worst status. Coverage cell = lowest % with source count.
- **Detail section**: non-passing commands only (project › stage › command, status, duration, last output, log path).
- **Warnings section** + overall summary line.
- `--verbose`: prints a row per command.
- Colour: optional if terminal supports it; not required.
- **`.pre-llm/` gitignore check**: if `.pre-llm/` is not in `.gitignore`, emit a `gitignore_missing` warning with the exact line to add. `--add-gitignore` flag opts in to having the script add it automatically (the only write the script ever performs outside its own output files).

### `--dry-run`

- Detects projects, matches tools, collects warnings — does not execute any commands.
- Prints the same terminal table with `PLANNED` in every stage cell, followed by the list of commands that would run per project.
- With `--output`: writes `pre-llm-report.json` with `"mode": "dry-run"` at the top level; command entries have `"status": "planned"` and no `output_tail` or `log_path`.

### Report Schema (pre-llm-report.json)

```
{
  "schema_version": "1.0",
  "mode": "run | dry-run",
  "generated_at": "<ISO8601>",
  "summary": {
    "status": "pass | fail | warning | error | planned",
    "project_count": N,
    "counts": { "pass": N, "fail": N, "timeout": N, "skipped": N, "warning": N, "planned": N },
    "warning_count": N
  },
  "error": "<message, present only when status=error>",
  "projects": [
    {
      "name": "<relative path>",
      "language": "<language>",
      "verification": "tested | untested",
      "build_files": ["relative/path/to/pom.xml"],
      "skipped_scripts": [
        { "script": "lint:fix", "stage": "lint", "reason": "modifies files" }
      ],
      "stages": {
        "build": { "status": "...", "commands": [...] },
        "lint":  { "status": "...", "commands": [...] },
        "tests": { "status": "...", "commands": [...] },
        "coverage": { "status": "...", "commands": [...], "results": [...] }
      }
    }
  ],
  "warnings": [
    {
      "type": "unsupported_extension | no_project | tool_not_installed | nothing_to_run | dependencies_missing | gitignore_missing",
      "extension": "...",
      "folders": [...],
      "count": N,
      "files": ["...", "..."],
      "more": N,
      "reason": "..."
    }
  ]
}
```

Each command entry:
```
{
  "command": "npm run test",
  "scripts": ["test", "test:unit"],
  "source": "package.json script | .eslintrc",
  "status": "pass | fail | timeout | skipped | warning | planned",
  "duration_s": 12.4,
  "output_tail": ["..."],
  "log_path": "relative/path/to/.pre-llm/logs/packages-api--tests--test.log"
}
```

**Status enums:**
- Summary-level: `pass`, `fail`, `warning`, `error`, `planned` (dry-run only). A `timeout` on any command makes summary `fail`. Warnings alone → `pass` (exit code 0).
- Command-level: `pass`, `fail`, `timeout`, `skipped`, `warning`, `planned` (dry-run only).
- All paths relative to repo root.
- Report is always written, even on script error (exit code 2); in that case `summary.status = "error"` and `"error"` field is populated.
- Zero tests executed → command status `warning`.

### Coverage Extraction

1. Read a coverage report file defined in `languages.toml` (path + format), checking file modification timestamp to confirm freshness (modified during this run).
2. Fall back to regex on stdout (pattern defined in `languages.toml`).
3. Built-in readers: JaCoCo XML, Cobertura XML, Istanbul json-summary, lcov.
4. Primary metric: line coverage. Branch coverage included in JSON when available.
5. Multiple coverage tools: kept separately (never averaged); table shows lowest %.
6. No coverage threshold enforcement in v1.

### Language Registry (languages.toml)

Read with `tomllib` (Python 3.11+ stdlib). No third-party TOML library required.

Each language entry defines:
- `extensions`: list of file extensions claimed by this language.
- `project_files`: build files that identify a project, in priority order.
- `stages`: per stage — `exact` names, `prefixes`, `excludes`, built-in tasks.
- `config_triggers`: config files whose presence enables a tool for a stage.
- `dependency_check`: optional — `filesystem` (path that must exist, used for languages like Node where the absence of `node_modules/` is unambiguous) and/or `error_patterns` (output substrings that map to `dependencies_missing`; used as the sole mechanism for Python and other languages with flexible environment layouts).
- `coverage`: `report_files` (path + format) and `output_pattern`.
- `verification`: `"tested"` or `"untested"`.
- `ignore_extensions`: global list of extensions that never produce warnings (shared across all language entries, defined once at the top level).

Initial languages (v1): Java (Maven, Gradle), Kotlin (Gradle), JS/TS (package.json), Python (pyproject.toml/requirements.txt), Go (go.mod), C#/.NET (.csproj/.sln), Rust (Cargo.toml), PHP (composer.json), Ruby (Gemfile), Swift (Package.swift), C/C++ (CMakeLists.txt/Makefile).

---

## Testing Decisions

### What makes a good test

Tests verify observable behaviour at the boundary of the script: what it prints to stdout, what it writes to `pre-llm-report.json`, and its exit code. Tests do not assert on internal data structures, module internals, or implementation details.

### Fixture-based integration tests

- Test fixtures live under `tests/fixtures/`.
- Per-language fixtures: `ok`, `build-fail`, `test-fail`, `lint-fail`, `no-tests`.
- Shared edge-case fixtures: `risky-scripts`, `duplicate-scripts`, `hang`, `monorepo`, `missing-deps`.
- `tests/fixtures/EXPECTED.md` records the expected status per stage for each fixture.
- A language's verification tag moves from `untested` to `tested` in `languages.toml` only when all its fixtures produce output matching `EXPECTED.md`.
- v1 targets tested status for: Java, JS/TS, Python.

### Seam

The single test seam is the script's CLI: invoke `pre-llm-checks --path <fixture> --output <tmp>` and assert on exit code, the terminal table (captured stdout), and the JSON report. No internal mocking required; fixture projects provide deterministic inputs.

### `--dry-run` aids test coverage

`--dry-run` produces the detection plan without executing tools, enabling fast tests of project discovery, tool matching, and warning generation independent of installed toolchains.

---

## Out of Scope (v1)

- `--parallel-projects` (reserved for v2).
- `--only-language` filter.
- `--changed-only` / blast-radius integration (v2 candidate).
- Coverage thresholds or pass/fail gates on coverage percentage.
- Dependency installation.
- File modification of any kind except: writing `pre-llm-report.json` and `.pre-llm/` logs (always), and optionally appending to `.gitignore` when `--add-gitignore` is passed.
- Remote execution or CI-specific integration.

---

## Further Notes

- The script itself must print its version (`--version`) to aid bug reports.
- Secret masking patterns (tokens, API keys, passwords, connection strings) should be defined in a maintainable list within the script or config, not as scattered one-off regexes.
- The `[untested]` tag in the terminal table and `"verification": "untested"` in the JSON are the mechanism by which the team tracks confidence in language support over time.
- The `languages.toml` config file is the sole extension point: adding support for a new language or tool requires only a new TOML entry, no code change.
