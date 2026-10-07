# 03: Command runner

**What to build:** A self-contained command execution layer that runs a single command safely and returns a structured result. It handles: selecting the correct native runner (npm, mvnw/mvn, gradlew/gradle, or language-defined), launching via argument list with `shell=False`, enforcing per-stage timeouts with full process-tree kill (cross-platform, including Windows), buffering output with a live progress line, streaming in `--verbose` mode, writing full output to a log file under `.pre-llm/logs/`, capturing the last N lines as `output_tail`, and masking secret patterns before any output leaves the runner. The pipeline (ticket 04) calls this layer; this ticket does not wire up the pipeline itself.

**Blocked by:** 01 (CLI skeleton + languages.toml loading + --version).

**Status:** ready-for-agent

- [ ] Commands are launched as argument lists; `shell=False` is enforced — no shell injection is possible.
- [ ] Working directory is always the directory containing the Project's build file.
- [ ] Runner selection: Node → `npm run <script>`; Maven → `mvnw` / `mvnw.cmd` if present, else `mvn`; Gradle → `gradlew` / `gradlew.bat` if present, else `gradle`; others use the command defined in `languages.toml`.
- [ ] If neither wrapper nor global runner is found on PATH, the runner returns a `tool_not_installed` signal (not a failed command result) so the pipeline can emit the warning and skip the stage.
- [ ] Per-stage timeouts are enforced (defaults: build 10m, lint 5m, tests 15m, coverage 15m); CLI `--timeout-*` flags override defaults.
- [ ] On timeout, the entire process tree is killed (including grandchildren); the result status is `timeout`, not `fail`.
- [ ] Full stdout+stderr is written to `.pre-llm/logs/<rel-path-slug>--<stage>--<script-slug>.log`; the log path in the result is relative to the repo root.
- [ ] `output_tail` contains the last N lines of combined output (default 50, overridden by `--tail-lines`).
- [ ] Secret patterns (tokens, API keys, passwords, connection strings) are masked with `***` in `output_tail` and in any terminal output; the full unmasked content is written to the log file only.
- [ ] Secret pattern list is defined in one maintainable place (config or script constant), not scattered inline.
- [ ] Default (buffered) mode: a single progress line is printed and updated in place while the command runs, showing project, stage, script name, and elapsed time; on completion it is replaced with the final status line.
- [ ] `--verbose` mode: stdout+stderr is streamed live to the terminal instead of buffered.
- [ ] The runner result carries: `command`, `scripts` (merged names), `source`, `status` (`pass`/`fail`/`timeout`), `duration_s`, `output_tail`, `log_path`.
- [ ] A command that exits non-zero is `fail`; exit zero is `pass`.
- [ ] `tests/fixtures/hang/` contains a Project with a script that sleeps indefinitely; running it with a short `--timeout-build` produces status `timeout` in the result within that timeout period.
