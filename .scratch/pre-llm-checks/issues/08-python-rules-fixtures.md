# 08: Python rules + fixtures → mark tested

**What to build:** The complete `languages.toml` entry for Python (pyproject.toml and requirements.txt projects) plus the full fixture suite. Key specifics: no filesystem dependency check (Python environments vary widely — global, conda, virtualenv at any path); dependency errors are detected solely via output patterns. `config_triggers` cover pytest, ruff, flake8, mypy, and black (black is excluded as a formatter). Coverage via `pytest-cov` with Cobertura or lcov output. When done, the Python entry is promoted to `verification = "tested"`.

**Blocked by:** 05 (Report JSON + terminal table + exit codes).

**Status:** ready-for-agent

- [ ] `languages.toml` entry for Python defines: extensions (`.py`), project files (`pyproject.toml`, `requirements.txt`) in that priority order, `verification = "untested"` initially.
- [ ] Stage matching: `build` stage is absent (Python has no compile step by default); `lint` matches scripts named `lint`, `lint:*`, and `config_triggers` for ruff (`ruff.toml`, `[tool.ruff]` in pyproject.toml), flake8 (`.flake8`), mypy (`mypy.ini`, `[tool.mypy]` in pyproject.toml); `tests` matches `test`, `test:*`, and `config_triggers` for pytest (`pytest.ini`, `[tool.pytest.ist]` in pyproject.toml, `setup.cfg`).
- [ ] Black is listed in `exclude_tools` (formatter); any script invoking black is added to `skipped_scripts` with reason `"modifies files"`.
- [ ] `dependency_check` for Python uses `error_patterns` only (no filesystem check): patterns include `ModuleNotFoundError`, `No module named`, `ImportError`, `cannot import name`.
- [ ] When a command's output matches a dependency error pattern, its result status is mapped to `dependencies_missing` instead of `fail`; the Project's remaining stages are skipped.
- [ ] Runner: commands are the raw command strings defined in the project's scripts section or `languages.toml`; launched as argument lists from the project directory.
- [ ] `tests/fixtures/python/ok/`: minimal `pyproject.toml` with passing lint and test scripts (stubs); exits 0, lint and tests `pass`, build `SKIP`.
- [ ] `tests/fixtures/python/test-fail/`: test script exits non-zero; exit code 1.
- [ ] `tests/fixtures/python/lint-fail/`: lint script exits non-zero; exit code 1.
- [ ] `tests/fixtures/python/no-tests/`: no test configuration; tests stage is `SKIP`; exit code 0.
- [ ] `tests/fixtures/python/missing-deps/`: test script outputs `ModuleNotFoundError`; result is `dependencies_missing` warning, not `fail`; exit code 0.
- [ ] All fixture results match `tests/fixtures/EXPECTED.md`.
- [ ] Python has no `build-fail` fixture because it has no build stage; promotion requires only the applicable fixtures (`ok`, `test-fail`, `lint-fail`, `no-tests`, `missing-deps`) to pass.
- [ ] Python entry in `languages.toml` has `verification = "tested"` after all applicable fixtures pass.
