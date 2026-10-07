# 04: Pipeline orchestration

**What to build:** The per-Project execution loop that sequences stages (build → lint → tests → coverage), enforces the build-fail gate, applies `--steps` filtering, deduplicates commands, records `skipped_scripts`, detects `dependencies_missing` before running, and wires discovery results (ticket 02) to the command runner (ticket 03). Projects are independent; a failure in one does not stop others. At the end of this ticket a full run produces raw per-project stage results ready for reporting (ticket 05).

**Blocked by:** 02 (Scan + project discovery + warnings + --dry-run), 03 (Command runner).

**Status:** ready-for-agent

- [ ] Stages run in order: build → lint → tests → coverage; only defined stages run (pipeline is opportunistic).
- [ ] If build is included in `--steps` and fails or times out: lint, tests, and coverage are skipped for that Project; their stage status is `skipped` with reason `"build failed"`.
- [ ] `--lint-anyway`: when set, lint runs even after a build failure or timeout; tests and coverage are still skipped.
- [ ] `--steps <list>` restricts which stages are attempted; excluded stages are recorded with reason `"excluded by --steps"`. If build is excluded, the build-fail gate is not applied; a note `"build not run (excluded by --steps)"` is added.
- [ ] Stage script matching: exact names and prefix patterns (e.g. `lint:*`) defined in `languages.toml`; matching is applied to the project's declared scripts/tasks.
- [ ] Exclude list applied before matching: scripts whose names match any exclude suffix (`:fix`, `:watch`, `:dev`, `:serve`, `:e2e`, `:docker`, `:deploy`) are added to `skipped_scripts` with reason `"excluded pattern"` and never run.
- [ ] The script never runs commands that include file-modifying flags (`--fix`, `--write`); such scripts are added to `skipped_scripts` with reason `"modifies files"`.
- [ ] Deduplication: within a stage, commands identical after trimming and collapsing whitespace run once; all matching script names are merged into `scripts`; different argument strings are treated as different commands.
- [ ] `skipped_scripts` array on each Project records `{ script, stage, reason }` for every script that was matched but not run.
- [ ] `nothing_to_run` warning is emitted when a Project has no runnable scripts or tasks across all stages after all filtering.
- [ ] Dependency detection runs before any stage for a Project: filesystem checks (where defined per language) and output-pattern matching (for Python and others) map to `dependencies_missing`; affected Projects have all stages skipped.
- [ ] Projects are run sequentially; a failure in one Project does not affect others.
- [ ] Zero tests executed (test runner exits 0 but reports 0 tests) → command status `warning`, not `pass`.
- [ ] `tests/fixtures/` contains: `risky-scripts` (scripts that should be excluded), `duplicate-scripts` (two scripts resolving to the same command), `missing-deps` (Node project with no `node_modules/`); each produces the expected stage results per `tests/fixtures/EXPECTED.md`.
