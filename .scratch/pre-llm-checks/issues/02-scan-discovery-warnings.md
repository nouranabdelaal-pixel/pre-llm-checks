# 02: Scan + project discovery + warnings + --dry-run

**What to build:** The script walks a target directory, discovers all Projects by matching build files to language rules from `languages.toml`, assigns source files to their nearest ancestor Project (with language-affinity enforcement), and produces all six warning types without executing any commands. `--dry-run` prints the planning table and warning list; with `--output` it writes the JSON report with `"mode": "dry-run"`. This ticket makes the full discovery path end-to-end verifiable — no runner needed.

**Blocked by:** 01 (CLI skeleton + languages.toml loading + --version).

**Status:** ready-for-agent

- [ ] Directory walk skips: `node_modules`, `.git`, `.next`, `target`, `build`, `dist`, `.venv`, `graphify-out`, `.ua`, `.pre-llm`.
- [ ] Build files are matched to language entries from `languages.toml`; each directory gets at most one Project per language.
- [ ] When multiple build files for the same language exist in one directory, the priority order defined in `languages.toml` governs; all matched files are recorded in `build_files`.
- [ ] The nearest ancestor Project wins for each source file; language affinity is enforced (e.g. `package.json` does not claim `.java` files).
- [ ] Root-level build files only claim files that have no closer ancestor Project for that language.
- [ ] For each Project, tool discovery runs: explicit script/task entries, built-in tasks, config-trigger files, and plugin configuration are all considered per `languages.toml` rules.
- [ ] `unsupported_extension` warning: one per unrecognised source-code extension (grouped, with count and up to 3 example paths); extensions on `ignore_extensions` never warn.
- [ ] `no_project` warning: one per extension + top-level folder for source files in a known language with no matching Project.
- [ ] `tool_not_installed` warning: emitted when a configured runner (e.g. `mvn`, `gradle`) is not found on PATH and no wrapper exists; stage is noted as skipped.
- [ ] `nothing_to_run` warning: emitted per Project when no stage has any runnable script or task.
- [ ] `gitignore_missing` warning: emitted when `.pre-llm/` is absent from `.gitignore`; includes the exact line to add.
- [ ] `--add-gitignore` appends `.pre-llm/` to `.gitignore` and suppresses the warning.
- [ ] Warning objects in the JSON are structured: `{ type, extension, folders, count, files (capped at 50), more, reason }`.
- [ ] `--dry-run` prints the terminal table with `PLANNED` in every stage cell, followed by the list of commands that would run per Project, plus the warnings section.
- [ ] `--dry-run --output <file>` writes `pre-llm-report.json` with `"mode": "dry-run"`, `summary.status = "planned"`, command entries with `"status": "planned"`, and no `output_tail` or `log_path`.
- [ ] With no `--dry-run`, discovery results are passed to the pipeline (ticket 04) without executing anything in this ticket.
- [ ] `tests/fixtures/` contains at least: a `monorepo` fixture (nested Projects of different languages) and a `missing-deps` fixture; `--dry-run` against these produces the expected warnings recorded in `tests/fixtures/EXPECTED.md`.
