# 09: Coverage readers (JaCoCo, Cobertura, Istanbul, lcov)

**What to build:** The coverage extraction layer that reads structured report files and produces `{ line_pct, branch_pct, tool, source }` results. Four built-in format readers are implemented and wired into the pipeline. Coverage report files are freshness-checked (modification timestamp during the current run) before reading. A stdout regex fallback is used when no report file is found or readable. Multiple coverage results per Project are kept separately in the JSON; the terminal table shows the lowest line percentage with a source count. Missing or stale coverage → `warning` status, not `fail`.

**Blocked by:** 05 (Report JSON + terminal table + exit codes).

**Status:** ready-for-agent

- [ ] **JaCoCo XML reader**: parses `target/site/jacoco/jacoco.xml` (or the path configured in `languages.toml`); extracts `LINE` and `BRANCH` counters; computes covered/total percentages.
- [ ] **Cobertura XML reader**: parses `coverage.xml` or `target/site/cobertura/coverage.xml`; extracts `line-rate` and `branch-rate` attributes.
- [ ] **Istanbul json-summary reader**: parses `coverage/coverage-summary.json`; reads `total.lines.pct` and `total.branches.pct`.
- [ ] **lcov reader**: parses `lcov.info` or `coverage/lcov.info`; accumulates `LH`/`LF` (lines hit/found) and `BRH`/`BRF` (branches hit/found) across all records.
- [ ] Freshness check: a report file is only accepted if its modification time is within the current run's start time; stale files are skipped and a `warning` is emitted with reason `"stale coverage report"`.
- [ ] Stdout regex fallback: if no valid report file is found, a language-defined regex pattern is applied to the command's stdout to extract a line coverage percentage.
- [ ] If neither report file nor regex yields a result → coverage stage status `warning` with reason `"coverage data not found"`, not `fail`.
- [ ] Line coverage is the primary metric; branch coverage is included in the JSON `results` entry when available.
- [ ] Multiple coverage tools for the same Project are stored as separate entries in `coverage.results`; they are never averaged.
- [ ] Terminal table coverage cell: lowest line percentage across all results with count, e.g. `64% (2)`; `—` when no data.
- [ ] `languages.toml` coverage section for each language defines `report_files` (list of `{ path, format }`) and `output_pattern`.
- [ ] `tests/fixtures/` includes at least one fixture per format (can be synthetic) with a pre-written report file; the reader extracts the expected percentage matching `tests/fixtures/EXPECTED.md`.
- [ ] A fixture with a report file older than the run start time produces a `warning` status (stale), not a coverage percentage.
