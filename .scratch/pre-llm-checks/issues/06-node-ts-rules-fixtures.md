# 06: Node/TS rules + fixtures → mark tested

**What to build:** The complete `languages.toml` entry for JavaScript/TypeScript (package.json projects) plus the full fixture suite that verifies it end-to-end. When this ticket is done, the Node/TS language entry is promoted from `verification = "untested"` to `verification = "tested"` and every fixture in `tests/fixtures/EXPECTED.md` for this language passes.

**Blocked by:** 05 (Report JSON + terminal table + exit codes).

**Status:** ready-for-agent

- [ ] `languages.toml` entry for JS/TS defines: extensions (`.js`, `.ts`, `.jsx`, `.tsx`, `.mjs`, `.cjs`), project file (`package.json`), stage script matching (exact names and `build:*`, `lint:*`, `test:*`, `coverage` prefixes), exclude patterns, and `config_triggers` for ESLint (`.eslintrc*`, `eslint.config.*`) and TypeScript (`tsconfig.json`).
- [ ] `dependency_check` for Node uses a filesystem check: absence of `node_modules/` triggers `dependencies_missing`.
- [ ] `dependency_check` also includes `error_patterns` for npm install errors seen in output (e.g. `Cannot find module`).
- [ ] Runner is `npm run <script>`; no wrapper preference needed (npm is always the runner).
- [ ] `tests/fixtures/node/ok/`: a minimal `package.json` with passing build, lint, and test scripts using inline Node one-liners (e.g. `"test": "node -e \"process.exit(0)\""`); no `npm install` required. Running the script exits 0, table shows all `pass`.
- [ ] `tests/fixtures/node/build-fail/`: build script uses `node -e "process.exit(1)"`; lint and tests are skipped; exit code 1.
- [ ] `tests/fixtures/node/test-fail/`: build passes, test script uses `node -e "process.exit(1)"`; exit code 1.
- [ ] `tests/fixtures/node/lint-fail/`: build passes, lint script uses `node -e "process.exit(1)"`; exit code 1.
- [ ] `tests/fixtures/node/no-tests/`: no test script present; tests stage is `SKIP`; exit code 0.
- [ ] All fixture scripts use the real `npm run` runner and real Node; no stubs or mocks. Fixtures are dependency-free (no `node_modules` needed) because the scripts contain only inline `node -e` expressions.
- [ ] All fixture results match `tests/fixtures/EXPECTED.md`.
- [ ] `languages.toml` entry for JS/TS has `verification = "tested"` after all applicable fixtures pass.
