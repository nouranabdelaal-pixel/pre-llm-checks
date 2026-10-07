# 05: Report JSON + terminal table + exit codes

**What to build:** Everything the user sees and everything a downstream consumer reads. After the pipeline completes, this ticket produces: the terminal summary table (one row per Project, worst-status rollup per stage cell, detail lines only for non-passing commands, warnings section, overall summary line), the `pre-llm-report.json` file at the configured path, and the correct process exit code. The report is always written — even on script error (exit code 2).

**Blocked by:** 04 (Pipeline orchestration).

**Status:** ready-for-agent

- [ ] Terminal table: one row per Project; columns: Project, Language (`[untested]` when `verification = "untested"`), Build, Lint, Tests, Coverage.
- [ ] Stage cell shows the worst status among that stage's commands: `fail` > `timeout` > `warning` > `pass`; `SKIP` when the stage was not run.
- [ ] Coverage cell shows the lowest line-coverage percentage across all coverage results with a source count (e.g. `64% (2)`); `—` when no coverage data is available.
- [ ] Below the table: detail lines for every non-passing command — `project › stage › command`, status, duration, last output lines, log path. Passing commands produce no detail lines.
- [ ] Below the detail lines: a warnings section listing all structured warnings.
- [ ] Final line: overall status, project count, per-status counts, report path.
- [ ] `--verbose` mode prints a row for every command regardless of status.
- [ ] Plain text output (no ANSI colour required); optional colour when the terminal reports colour support.
- [ ] `pre-llm-report.json` written to `--output` path (default `pre-llm-report.json`), always, even on error.
- [ ] Report conforms to the schema: `schema_version`, `mode`, `generated_at`, `summary` (with `status`, `project_count`, `counts`, `warning_count`), `projects` (each with `name`, `language`, `verification`, `build_files`, `skipped_scripts`, `stages`), `warnings`.
- [ ] Summary `status` enum: `pass`, `fail`, `warning`, `error`, `planned` (dry-run only). Any `timeout` command makes summary `fail`. Warnings alone → summary `pass`.
- [ ] Command entries include: `command`, `scripts`, `source`, `status`, `duration_s`, `output_tail`, `log_path`.
- [ ] All paths in the report are relative to the repo root.
- [ ] On script error (exit 2): report is written with `summary.status = "error"` and a top-level `"error"` field containing the message.
- [ ] Exit codes: 0 = all pass or warnings only; 1 = any `fail` or `timeout`; 2 = script error; 3 = no supported Project found.
- [ ] `tests/fixtures/EXPECTED.md` entries for at least one `ok` fixture and one `build-fail` fixture verify the correct exit code, table content, and JSON shape.
