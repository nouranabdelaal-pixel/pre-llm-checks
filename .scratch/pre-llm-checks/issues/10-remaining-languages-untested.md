# 10: Remaining languages as untested entries

**What to build:** `languages.toml` entries for all languages in scope beyond Java, Kotlin, JS/TS, and Python — each marked `verification = "untested"`. The script will detect and run these projects using the defined rules; the `[untested]` tag in the terminal table and JSON signals to users that the rules have not yet been validated against real fixtures. No fixtures are required for this ticket; that work happens per-language in future tickets.

**Blocked by:** 01 (CLI skeleton + languages.toml loading + --version).

**Status:** ready-for-agent

- [ ] **Go** (`go.mod`): extensions `.go`; build → `go build ./...`; lint → `config_trigger` for `golangci-lint` (`.golangci.yml`/`.golangci.toml`/`.golangci.yaml`); tests → `go test ./...`; coverage → `go test -coverprofile`; `output_pattern` for coverage percentage; `dependency_check.error_patterns` for `cannot find module`, `no required module`.
- [ ] **C#/.NET** (`.sln` > `.csproj`): extensions `.cs`, `.fs`, `.vb`; build → `dotnet build`; lint → `config_trigger` for `dotnet-format` (`.editorconfig`) and Roslyn analyzers; tests → `dotnet test`; coverage → Cobertura XML via `--collect:"XPlat Code Coverage"`; `dependency_check.error_patterns` for `Unable to find package`.
- [ ] **Rust** (`Cargo.toml`): extensions `.rs`; build → `cargo build`; lint → `cargo clippy` (always available, no config trigger needed); tests → `cargo test`; coverage → `cargo tarpaulin` when configured (`tarpaulin.toml`); `dependency_check.error_patterns` for `error[E0432]`, `no matching package`.
- [ ] **PHP** (`composer.json`): extensions `.php`; build → `composer install` excluded (installs deps), build stage absent by default; lint → `config_trigger` for phpcs (`phpcs.xml`/`.phpcs.xml`) and phpstan (`phpstan.neon`/`phpstan.neon.dist`); tests → `vendor/bin/phpunit` when `phpunit.xml` present; `dependency_check.filesystem` → `vendor/` directory.
- [ ] **Ruby** (`Gemfile`): extensions `.rb`; build → absent; lint → `config_trigger` for RuboCop (`.rubocop.yml`); tests → `bundle exec rspec` when `spec/` dir present or `bundle exec rake test`; `dependency_check.filesystem` → `vendor/bundle/` or error pattern `Could not find gem`.
- [ ] **Swift** (`Package.swift`): extensions `.swift`; build → `swift build`; lint → `config_trigger` for SwiftLint (`.swiftlint.yml`); tests → `swift test`; `dependency_check.error_patterns` for `error: no such module`.
- [ ] **C/C++** (`CMakeLists.txt`, `Makefile`): extensions `.c`, `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`; build → `cmake --build .` or `make`; lint → `config_trigger` for clang-tidy (`.clang-tidy`); tests → `ctest` or `make test`; `dependency_check.error_patterns` for `No such file or directory`, `fatal error:`.
- [ ] All entries have `verification = "untested"`.
- [ ] Each entry has a `dependency_check` section with at least `error_patterns` defined.
- [ ] All entries load without validation errors (ticket 01 validation passes).
- [ ] Running `--dry-run` on a directory containing one of these language's project files discovers the Project, lists its planned commands, and shows `[untested]` in the table.
