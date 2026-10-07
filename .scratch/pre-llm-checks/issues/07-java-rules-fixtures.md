# 07: Java (Maven, Gradle) rules + fixtures → mark tested

**What to build:** The complete `languages.toml` entries for Java (Maven and Gradle) plus the full fixture suite that verifies both build systems end-to-end. Covers wrapper preference (`mvnw`/`gradlew` over global), built-in lifecycle phases, plugin-based tool discovery (Checkstyle, PMD, SpotBugs, JaCoCo), and the Kotlin/Gradle entry as a sub-case. When done, Java and Kotlin entries are promoted to `verification = "tested"`.

**Blocked by:** 05 (Report JSON + terminal table + exit codes).

**Status:** ready-for-agent

- [ ] `languages.toml` entry for Java (Maven) defines: extensions (`.java`), project file (`pom.xml`), built-in phases for each stage (`compile` for build; `checkstyle:check`, `pmd:check`, `spotbugs:check` for lint when plugins present; `test` for tests; `jacoco:report` for coverage), `config_triggers` for Checkstyle (`checkstyle.xml`), PMD (`pmd.xml`), SpotBugs (`spotbugs*.xml`).
- [ ] `languages.toml` entry for Java (Gradle) defines: extensions (`.java`), project files (`build.gradle`, `build.gradle.kts`), built-in tasks (`compileJava` for build; `checkstyleMain`, `pmdMain`, `spotbugsMain` for lint when configured; `test` for tests; `jacocoTestReport` for coverage).
- [ ] `languages.toml` entry for Kotlin (Gradle) defines: extensions (`.kt`, `.kts`), project files (`build.gradle.kts`), built-in tasks analogous to Java/Gradle.
- [ ] Runner preference: `mvnw` / `mvnw.cmd` over `mvn`; `gradlew` / `gradlew.bat` over `gradle`; missing both → `tool_not_installed` warning.
- [ ] Plugin-based tools (Checkstyle, PMD, SpotBugs, JaCoCo) are only included when their plugin or config trigger is detected in the project file.
- [ ] `dependency_check` for Maven includes `error_patterns` for unresolved dependency errors (e.g. `Could not resolve dependencies`, `Artifact * not found`).
- [ ] `tests/fixtures/java-maven/ok/`: minimal `pom.xml` with passing compile and test phases using stub scripts; exits 0, all stages `pass`.
- [ ] `tests/fixtures/java-maven/build-fail/`: compile phase exits non-zero; test skipped; exit code 1.
- [ ] `tests/fixtures/java-maven/test-fail/`: compile passes, test exits non-zero; exit code 1.
- [ ] `tests/fixtures/java-maven/lint-fail/`: Checkstyle plugin detected, lint exits non-zero; exit code 1.
- [ ] `tests/fixtures/java-maven/no-tests/`: no test phase configured; tests stage is `SKIP`; exit code 0.
- [ ] `tests/fixtures/java-gradle/ok/`: analogous for Gradle; exits 0.
- [ ] All fixture results match `tests/fixtures/EXPECTED.md`.
- [ ] Java (Maven), Java (Gradle), and Kotlin entries in `languages.toml` have `verification = "tested"` after all fixtures pass.
