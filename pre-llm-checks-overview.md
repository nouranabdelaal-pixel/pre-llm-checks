# Pre-LLM Checks: Overview

> A read-only Python script that checks whether a repo **builds, passes lint and passes tests** before an AI reviews it, and writes the results in a form the AI can read.

Full specification: `.scratch/pre-llm-checks/spec.md`

---

## 1. Problem

Before an AI reviews code, we need to know whether the code works at all. In a repo with several languages, running each language's tools by hand is slow and easy to get wrong, and there's no standard way to collect the results.

## 2. Solution

A cross-platform Python script (**Windows / macOS / Linux**, Python **3.11+**, **no third-party packages**) that:

1. finds the projects in a repo
2. runs **build → lint → tests → coverage** using **only the project's own tools**
3. produces:
   - a **summary table** in the terminal (for people)
   - **`pre-llm-report.json`** (for the AI)

**Golden rule:** it never changes your code, never installs anything and never runs fixers or formatters.

---

## 3. How it works

### Step 1: Find projects

- It scans **the folder you run it in and everything inside it**. Use `--path <folder>` to scan a different folder.
- Run it on **one repository**, not on your home folder. Otherwise it scans every project on your machine.
- It skips: `node_modules`, `.git`, `.next`, `target`, `build`, `dist`, `.venv`, `graphify-out`, `.ua`, `.pre-llm`.
- A **project** is a folder that contains a build file, such as `package.json`, `pom.xml` or `pyproject.toml`.
- A build file only owns files in **its own language**, so `package.json` never claims `.java` files.
- Each file belongs to the **nearest** build file above it. In a monorepo, the sub-project wins over the root.

**Two build files for the same language in one folder:** there is only one project per folder per language. A priority list decides which file is in charge:

| Language | Wins | Over |
|---|---|---|
| Python | `pyproject.toml` | `requirements.txt` |
| .NET | `.sln` | `.csproj` |

Both files are still listed in `build_files` in the report.

### Step 2: Find the tools

A tool only counts if **the project itself defines it**:

- a script in the build file (e.g. `"lint"` in `package.json`)
- a plugin in the build file (e.g. Checkstyle in `pom.xml`)
- a config file next to it (e.g. `.eslintrc`, `tsconfig.json`)
- a built-in Maven/Gradle phase (e.g. `compile`, `test`)

A package that's **only listed in `devDependencies`**, with no script and no config, is **ignored**. Being installed doesn't tell the script *how* to run it, and guessing could produce false failures.

### Step 3: Match scripts to stages

- It matches exact names and prefixes, so `lint` and `lint:types` both count as lint.
- It **skips** names ending in `:fix`, `:watch`, `:dev`, `:serve`, `:e2e`, `:docker` or `:deploy`, and anything using `--fix` / `--write`. The reason is recorded in `skipped_scripts`.
- It runs identical commands **once**. Different arguments count as different commands, so `jest` and `jest --ci` both run.

### Step 4: Check dependencies first

Missing packages are a **setup problem**, not a code bug, so they're reported as a **warning**, not a failure. The script **never installs** anything.

| | Node | Python |
|---|---|---|
| When it checks | Before running | After running |
| How | Does `node_modules/` exist? | Does the output contain `ModuleNotFoundError` / `No module named`? |
| Result | `dependencies_missing` warning, project skipped | `dependencies_missing` instead of fail |

Python has no folder check because its packages can be installed in many places (global, `.venv`, virtualenv, conda).

### Step 5: Run safely

- Commands run from the **project's folder**.
- Wrappers are preferred: `mvnw` / `gradlew` over a global `mvn` / `gradle`.
- If no tool is installed, it gives a `tool_not_installed` warning and skips the stage. It doesn't fail.
- Commands run as argument lists (`shell=False`), so nothing can be injected.

### Step 6: Build gate

- If the build **fails or times out**, the other stages for that project are skipped.
- `--lint-anyway` still runs lint.
- If `--steps` excludes build, the gate is turned off.
- Each project is independent. A failure in one doesn't stop the others.

### Step 7: Timeouts

| Stage | Default |
|---|---|
| Build | 10m |
| Lint | 5m |
| Tests | 15m |
| Coverage | 15m |

- Override with `--timeout-build`, `--timeout-lint`, etc. Formats: `90s`, `30m`, `1h`, `1h30m`, or seconds.
- On a timeout it kills the **whole process tree**.
- `timeout` is its own status, but it counts as a failure for the exit code.

### Step 8: Coverage

- Reads report files: **JaCoCo XML, Cobertura XML, Istanbul json-summary, lcov**.
- A file is only used if it was **written during this run**, so old results are never reported.
- If there's no file, it tries to read the percentage from the command output.
- Line coverage is the main number. Branch coverage is included in the JSON when available.
- Each tool's result is kept separately and never averaged. The table shows the **lowest**.
- No minimum coverage threshold in v1.
- No coverage data → `warning`, not fail.

---

## 4. What you get

### Terminal table

One row per project:

```
Project    Language   Build  Lint   Tests  Coverage
todo-app   JS/TS      PASS   FAIL   PASS   78% (1)
```

- Each cell shows the **worst** result: `fail > timeout > warning > pass`. `SKIP` means the stage didn't run.
- Languages not yet verified show `[untested]`.
- Detail lines appear **only** for things that didn't pass, followed by warnings and a summary line.
- `--verbose` streams output live and prints a row for every command.

### JSON report: `pre-llm-report.json`

- Versioned schema (`"schema_version": "1.0"`) with a summary at the top.
- Each command includes: `command`, `scripts`, `source`, `status`, `duration_s`, `output_tail` (last 50 lines, `--tail-lines` to change) and `log_path`.
- **Secrets are masked** (tokens, API keys, passwords, connection strings).
- All paths are relative to the repo root.
- **Always written**, even if the script itself crashes (`summary.status = "error"`).

### Logs

- The full output goes to `.pre-llm/logs/`, which **should be gitignored**.
- If it isn't, you get a `gitignore_missing` warning. `--add-gitignore` adds it for you. That's the only change the script ever makes to your files.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | All passed, or only warnings |
| 1 | Something failed or timed out |
| 2 | The script itself had an error |
| 3 | No supported project found |

### Warning types

| Type | When |
|---|---|
| `unsupported_extension` | Source files in a language with no rule |
| `no_project` | Source files in a known language with no build file |
| `tool_not_installed` | The required runner isn't installed |
| `nothing_to_run` | A project was found but has nothing to run |
| `dependencies_missing` | Packages aren't installed |
| `gitignore_missing` | `.pre-llm/` isn't in `.gitignore` |

---

## 5. `languages.toml`: the rulebook

All language rules live in one file: extensions, build files, stage names, config files, dependency checks, coverage paths, and `tested` / `untested`.

**Adding a language means adding a TOML entry. No code changes.**

v1 languages: Java (Maven, Gradle), Kotlin (Gradle), JS/TS, Python, Go, C#/.NET, Rust, PHP, Ruby, Swift, C/C++.

---

## 6. CLI flags

| Flag | Purpose |
|---|---|
| `--path <folder>` | Scan a specific folder |
| `--output <file>` | Change the report path |
| `--dry-run` | Show the plan without running anything |
| `--steps <list>` | Run only some of `build,lint,tests,coverage` |
| `--lint-anyway` | Run lint even if the build fails |
| `--verbose` | Stream output live |
| `--timeout-*` | Override stage timeouts |
| `--tail-lines <N>` | Lines of output kept in the report |
| `--config <file>` | Use a different `languages.toml` |
| `--add-gitignore` | Add `.pre-llm/` to `.gitignore` |
| `--version` | Print the version |

---

## 7. Testing

- Tests only check what's visible from outside: **exit code, terminal table and JSON report**. They don't check internal code.
- Fixtures are small fake projects in `tests/fixtures/`. `EXPECTED.md` lists the result each one should give.
- Per-language fixtures: `ok`, `build-fail`, `test-fail`, `lint-fail`, `no-tests`. Not every fixture applies to every language (Python has no `build-fail`).
- Shared fixtures: `risky-scripts`, `duplicate-scripts`, `hang`, `monorepo`, `missing-deps`.
- Fixtures use **real runners** and are dependency-free where possible.
- A language is promoted to `tested` only when **all of its applicable fixtures** match `EXPECTED.md`.
- v1 target: **Java, JS/TS and Python** marked `tested`.

---

## 8. Not in v1

- Running projects in parallel
- Filtering by language
- Checking only changed files (blast-radius integration)
- Coverage thresholds
- Installing dependencies
- CI / remote integration

---

## 9. Quick start

```powershell
cd <your-repo>
python <path-to>/pre_llm_checks.py --dry-run   # see the plan
python <path-to>/pre_llm_checks.py             # run the checks
```
