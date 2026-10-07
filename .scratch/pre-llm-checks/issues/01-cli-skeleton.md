# 01: CLI skeleton + languages.toml loading + --version

**What to build:** A runnable `pre-llm-checks` script that accepts all specified CLI flags, loads and validates `languages.toml` using `tomllib` (Python 3.11+ stdlib), and exits cleanly with helpful errors on bad input. Running `--version` prints the version. Running with no arguments (or `--dry-run`) on an empty directory exits with code 3. All other flags parse and pass through without error. This is the foundation every other ticket builds on.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Script entry point exists and is executable on Windows, macOS, and Linux (Python 3.11+).
- [ ] `--version` prints the script version and exits 0.
- [ ] `--help` prints a useful usage summary.
- [ ] All CLI flags parse without error: `--path`, `--output`, `--dry-run`, `--steps`, `--lint-anyway`, `--verbose`, `--timeout-build`, `--timeout-lint`, `--timeout-tests`, `--timeout-coverage`, `--tail-lines`, `--config`, `--add-gitignore`.
- [ ] `--timeout-*` flags accept `90s`, `30m`, `1h`, `1h30m`, or a plain integer (seconds); invalid formats produce a clear error and exit 2.
- [ ] `--tail-lines` accepts a plain positive integer; non-integer input produces a clear error and exit 2.
- [ ] `--steps` accepts a comma-separated subset of `build,lint,tests,coverage`; unknown values produce a clear error and exit 2.
- [ ] `languages.toml` is loaded from the script's own directory by default, or from `--config <file>` when specified.
- [ ] If `languages.toml` is missing or invalid TOML, the script exits 2 with a clear message.
- [ ] The loaded language registry is validated: each entry must have at minimum `extensions`, `project_files`, and `verification` fields; missing required fields produce a clear error and exit 2.
- [ ] `ignore_extensions` global list is parsed from the top level of `languages.toml`.
- [ ] A minimal `languages.toml` stub (with at least one language entry) ships alongside the script and is loadable.
- [ ] Running against a directory with no recognised projects exits with code 3.
