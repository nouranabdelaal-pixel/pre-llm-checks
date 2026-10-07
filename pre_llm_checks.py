#!/usr/bin/env python3
"""pre-llm-checks — run build/lint/tests/coverage before handing code to an LLM."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    "node_modules",
    ".git",
    ".next",
    "target",
    "build",
    "dist",
    ".venv",
    "graphify-out",
    ".ua",
    ".pre-llm",
}

EXCLUDE_SUFFIXES = (":fix", ":watch", ":dev", ":serve", ":e2e", ":docker", ":deploy")
FILE_MODIFYING_FLAGS = ("--fix", "--write")

ALL_STAGES = ["build", "lint", "tests", "coverage"]

# ---------------------------------------------------------------------------
# Secret masking
# ---------------------------------------------------------------------------

SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"(api[_\-]?key|apikey)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(
        r"(token|access[_\-]?token|auth[_\-]?token)\s*[:=]\s*\S+", re.IGNORECASE
    ),
    re.compile(r"(password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(secret|client[_\-]?secret)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(connection[_\-]?string|conn[_\-]?str)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9_\-]{32,}={0,2}\b"),
]

_SECRET_REPLACEMENT = "***"


def mask_secrets(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(_SECRET_REPLACEMENT, text)
    return text


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class PlannedCommand:
    command_str: str
    scripts: list[str]
    source: str
    stage: str


@dataclasses.dataclass
class Project:
    path: Path  # absolute path to project dir
    language: str
    verification: str  # "tested" | "untested"
    build_files: list[Path]
    planned_commands: dict[str, list[PlannedCommand]]  # stage -> commands
    skipped_scripts: list[dict]  # {script, stage, reason}


@dataclasses.dataclass
class Warning:
    type: str
    extension: str = ""
    folders: list[str] = dataclasses.field(default_factory=list)
    count: int = 0
    files: list[str] = dataclasses.field(default_factory=list)
    more: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class CommandResult:
    command_str: str
    scripts: list[str]
    source: str
    status: str  # "pass" | "fail" | "timeout" | "skipped" | "warning" | "planned"
    duration_s: float
    output_tail: list[str]
    log_path: str
    exit_code: int | None


@dataclasses.dataclass
class RunnerNotFound:
    runner_name: str


# ---------------------------------------------------------------------------
# Log path construction
# ---------------------------------------------------------------------------


def make_log_path(project_rel: str, stage: str, script: str, repo_root: Path) -> Path:
    rel_slug = project_rel.replace("/", "-").replace("\\", "-").strip("-") or "root"
    script_slug = script.replace(":", "-")
    filename = f"{rel_slug}--{stage}--{script_slug}.log"
    return repo_root / ".pre-llm" / "logs" / filename


# ---------------------------------------------------------------------------
# Process-tree kill (cross-platform)
# ---------------------------------------------------------------------------


def kill_process_tree(pid: int) -> None:
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Runner selection
# ---------------------------------------------------------------------------


def _find_wrapper(cwd: Path, names: list[str]) -> Path | None:
    for name in names:
        p = cwd / name
        if p.is_file():
            return p
    return None


def _on_path(name: str) -> bool:
    return shutil.which(name) is not None


def select_runner(
    language: str, cwd: Path, script: str, lang_config: dict
) -> list[str] | RunnerNotFound:
    lang_lower = language.lower()

    if lang_lower in {"node", "javascript", "typescript", "js", "ts", "js/ts"}:
        if not _on_path("npm"):
            return RunnerNotFound("npm")
        return ["npm", "run", script]

    if lang_lower in {"java_maven", "java-maven", "maven"}:
        wrapper = _find_wrapper(
            cwd, ["mvnw.cmd", "mvnw"] if sys.platform == "win32" else ["mvnw"]
        )
        if wrapper:
            return [str(wrapper), script]
        if _on_path("mvn"):
            return ["mvn", script]
        return RunnerNotFound("mvn")

    if lang_lower in {
        "java_gradle",
        "kotlin",
        "java-gradle",
        "kotlin-gradle",
        "gradle",
    }:
        wrapper = _find_wrapper(
            cwd, ["gradlew.bat", "gradlew"] if sys.platform == "win32" else ["gradlew"]
        )
        if wrapper:
            return [str(wrapper), script]
        if _on_path("gradle"):
            return ["gradle", script]
        return RunnerNotFound("gradle")

    runner_cmd = lang_config.get("runner")
    if runner_cmd:
        if isinstance(runner_cmd, list):
            return [str(t) for t in runner_cmd] + [script]
        return [str(runner_cmd), script]

    return [script]


# ---------------------------------------------------------------------------
# Core run_command()
# ---------------------------------------------------------------------------

_VERBOSE: bool = False


def run_command(
    cmd: list[str],
    cwd: Path,
    timeout_s: int,
    stage: str,
    scripts: list[str],
    source: str,
    log_path: Path,
    tail_lines: int,
    repo_root: Path,
) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command_str = " ".join(cmd)
    project_label = str(cwd.relative_to(repo_root)) if cwd != repo_root else "."
    script_label = scripts[0] if scripts else command_str
    start = time.monotonic()
    timed_out = False
    exit_code: int | None = None

    extra_kwargs: dict = {}
    if sys.platform != "win32":
        extra_kwargs["start_new_session"] = True

    with log_path.open("w", encoding="utf-8", errors="replace") as log_fh:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                shell=False,
                **extra_kwargs,
            )
        except FileNotFoundError as exc:
            duration_s = time.monotonic() - start
            msg = f"[runner not found] {exc}\n"
            log_fh.write(msg)
            return CommandResult(
                command_str=command_str,
                scripts=scripts,
                source=source,
                status="fail",
                duration_s=round(duration_s, 3),
                output_tail=[msg.rstrip()],
                log_path=str(log_path.relative_to(repo_root)),
                exit_code=None,
            )

        output_lines: list[str] = []
        _read_done = threading.Event()

        def _read_output() -> None:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace")
                log_fh.write(line)
                log_fh.flush()
                output_lines.append(line.rstrip("\n"))
                if _VERBOSE:
                    sys.stderr.write(line)
                    sys.stderr.flush()
            _read_done.set()

        reader = threading.Thread(target=_read_output, daemon=True)
        reader.start()

        def _progress_loop() -> None:
            while not _read_done.is_set():
                elapsed = time.monotonic() - start
                line = f"\r[{project_label}] {stage}: {script_label} ... running {elapsed:.0f}s"
                sys.stderr.write(line)
                sys.stderr.flush()
                _read_done.wait(timeout=1.0)
            sys.stderr.write("\r" + " " * 80 + "\r")
            sys.stderr.flush()

        if not _VERBOSE:
            progress_thread = threading.Thread(target=_progress_loop, daemon=True)
            progress_thread.start()

        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_process_tree(proc.pid)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

        _read_done.wait(timeout=5)
        reader.join(timeout=5)
        exit_code = proc.returncode

    duration_s = time.monotonic() - start
    status = "timeout" if timed_out else ("pass" if exit_code == 0 else "fail")
    tail = (
        output_lines[-tail_lines:] if len(output_lines) > tail_lines else output_lines
    )
    masked_tail = [mask_secrets(line) for line in tail]

    return CommandResult(
        command_str=command_str,
        scripts=scripts,
        source=source,
        status=status,
        duration_s=round(duration_s, 3),
        output_tail=masked_tail,
        log_path=str(log_path.relative_to(repo_root)),
        exit_code=exit_code,
    )


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

_PLAIN_INT_RE = re.compile(r"^\d+$")
_SECONDS_RE = re.compile(r"^(\d+)s$")
_MINUTES_RE = re.compile(r"^(\d+)m$")
_HOURS_RE = re.compile(r"^(\d+)h$")
_HM_RE = re.compile(r"^(\d+)h(\d+)m$")


def parse_duration(s: str) -> int:
    s = s.strip()
    if not s:
        raise ValueError("Empty duration string")
    if _PLAIN_INT_RE.match(s):
        return int(s)
    m = _SECONDS_RE.match(s)
    if m:
        return int(m.group(1))
    m = _MINUTES_RE.match(s)
    if m:
        return int(m.group(1)) * 60
    m = _HOURS_RE.match(s)
    if m:
        return int(m.group(1)) * 3600
    m = _HM_RE.match(s)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    raise ValueError(
        f"Invalid duration {s!r}. "
        "Expected a plain integer (seconds), or a format like 90s, 30m, 1h, 1h30m."
    )


# ---------------------------------------------------------------------------
# Config loading & validation
# ---------------------------------------------------------------------------

REQUIRED_LANGUAGE_FIELDS = {"extensions", "project_files", "verification"}


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        _exit2(f"Config file not found: {config_path}")
    data: dict = {}
    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        _exit2(f"Invalid TOML in {config_path}: {exc}")
    languages: dict = data.get("languages", {})
    for lang_name, lang_entry in languages.items():
        if not isinstance(lang_entry, dict):
            _exit2(
                f"languages.{lang_name} must be a table, got {type(lang_entry).__name__}"
            )
        missing = REQUIRED_LANGUAGE_FIELDS - lang_entry.keys()
        if missing:
            _exit2(
                f"languages.{lang_name} is missing required fields: "
                + ", ".join(sorted(missing))
            )
    return data


# ---------------------------------------------------------------------------
# Scan & Project discovery
# ---------------------------------------------------------------------------


def _normalise(ext: str) -> str:
    """Ensure extension starts with a dot and is lowercase."""
    ext = ext.lower()
    return ext if ext.startswith(".") else f".{ext}"


def scan_directory(
    root: Path,
    languages: dict,
    ignore_extensions: list[str],
) -> tuple[list[Project], list[Warning]]:
    """Walk *root*, discover Projects, assign source files, produce warnings."""

    ignore_exts = {_normalise(e) for e in ignore_extensions}

    # Build lookup: extension -> list of language names that claim it
    ext_to_langs: dict[str, list[str]] = {}
    for lang_name, lang_cfg in languages.items():
        for ext in lang_cfg.get("extensions", []):
            n = _normalise(ext)
            ext_to_langs.setdefault(n, []).append(lang_name)

    # Build lookup: project_file_basename -> list of (lang_name, priority_index)
    # We need to handle globs like "*.sln" too
    pf_to_langs: dict[str, list[tuple[str, int]]] = {}
    pf_globs: dict[str, list[tuple[str, int]]] = {}  # glob pattern -> langs
    for lang_name, lang_cfg in languages.items():
        for idx, pf in enumerate(lang_cfg.get("project_files", [])):
            if "*" in pf:
                pf_globs.setdefault(pf, []).append((lang_name, idx))
            else:
                pf_to_langs.setdefault(pf, []).append((lang_name, idx))

    # First pass: find all project directories
    # dir_path -> {lang_name -> (priority_index, [matched_files])}
    dir_projects: dict[Path, dict[str, tuple[int, list[Path]]]] = {}

    all_files: list[Path] = []  # all non-skipped files

    def _walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return
        subdirs = []
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    subdirs.append(entry)
            elif entry.is_file():
                all_files.append(entry)
                fname = entry.name
                # Check exact project file matches
                if fname in pf_to_langs:
                    dp = dir_projects.setdefault(directory, {})
                    for lang_name, priority in pf_to_langs[fname]:
                        if lang_name not in dp or priority < dp[lang_name][0]:
                            if lang_name in dp:
                                _, existing_files = dp[lang_name]
                                existing_files.append(entry)
                            else:
                                dp[lang_name] = (priority, [entry])
                        else:
                            dp[lang_name][1].append(entry)
                # Check glob patterns
                for pattern, lang_list in pf_globs.items():
                    import fnmatch

                    if fnmatch.fnmatch(fname, pattern):
                        dp = dir_projects.setdefault(directory, {})
                        for lang_name, priority in lang_list:
                            if lang_name not in dp:
                                dp[lang_name] = (priority, [entry])
                            else:
                                dp[lang_name][1].append(entry)
        for subdir in subdirs:
            _walk(subdir)

    _walk(root)

    # Build Project objects
    projects: list[Project] = []
    # Map: (dir, lang) -> Project for nearest-ancestor lookup
    project_map: dict[tuple[Path, str], Project] = {}

    for dir_path, lang_map in sorted(dir_projects.items()):
        for lang_name, (_, matched_files) in lang_map.items():
            lang_cfg = languages[lang_name]
            planned = _discover_tools(dir_path, lang_name, lang_cfg)
            proj = Project(
                path=dir_path,
                language=lang_name,
                verification=lang_cfg.get("verification", "untested"),
                build_files=matched_files,
                planned_commands=planned["commands"],
                skipped_scripts=planned["skipped"],
            )
            projects.append(proj)
            project_map[(dir_path, lang_name)] = proj

    # Second pass: assign source files to projects, collect warnings
    warnings = _collect_warnings(
        root,
        all_files,
        projects,
        project_map,
        ext_to_langs,
        ignore_exts,
        languages,
    )

    # nothing_to_run warnings
    for proj in projects:
        if not any(cmds for cmds in proj.planned_commands.values()):
            warnings.append(
                Warning(
                    type="nothing_to_run",
                    folders=[str(proj.path.relative_to(root))],
                    reason=f"No runnable scripts or tasks found in project {proj.path.name}",
                )
            )

    # gitignore check
    gitignore_warn = _check_gitignore(root)
    if gitignore_warn:
        warnings.append(gitignore_warn)

    return projects, warnings


def _discover_tools(
    project_dir: Path,
    lang_name: str,
    lang_cfg: dict,
) -> dict:
    """Return {"commands": {stage: [PlannedCommand]}, "skipped": [...]}."""
    stages_cfg = lang_cfg.get("stages", {})
    commands: dict[str, list[PlannedCommand]] = {s: [] for s in ALL_STAGES}
    skipped: list[dict] = []

    # Read scripts from build file (e.g. package.json)
    declared_scripts: dict[str, str] = _read_declared_scripts(
        project_dir, lang_name, lang_cfg
    )

    # For each stage, collect runnable commands
    for stage in ALL_STAGES:
        stage_cfg = stages_cfg.get(stage, {})
        if not stage_cfg:
            continue

        exact: list[str] = stage_cfg.get("exact", [])
        prefixes: list[str] = stage_cfg.get("prefixes", [])
        excludes: list[str] = stage_cfg.get("excludes", [])
        builtins: list[str] = stage_cfg.get("builtin", [])
        config_triggers: list[str] = stage_cfg.get("config_triggers", [])

        seen_commands: dict[
            str, PlannedCommand
        ] = {}  # normalised cmd -> PlannedCommand

        # Check declared scripts
        for script_name, script_cmd in declared_scripts.items():
            matched_stage = _matches_stage(script_name, exact, prefixes)
            if not matched_stage:
                continue

            # Check excludes
            if any(script_name.endswith(ex) for ex in EXCLUDE_SUFFIXES) or any(
                script_name.endswith(ex) for ex in excludes
            ):
                skipped.append(
                    {
                        "script": script_name,
                        "stage": stage,
                        "reason": "excluded pattern",
                    }
                )
                continue

            # Check file-modifying flags
            if any(flag in script_cmd for flag in FILE_MODIFYING_FLAGS):
                skipped.append(
                    {"script": script_name, "stage": stage, "reason": "modifies files"}
                )
                continue

            norm_cmd = " ".join(script_cmd.split())
            if norm_cmd in seen_commands:
                seen_commands[norm_cmd].scripts.append(script_name)
            else:
                pc = PlannedCommand(
                    command_str=script_cmd,
                    scripts=[script_name],
                    source=f"{_project_file_name(lang_cfg)} script",
                    stage=stage,
                )
                seen_commands[norm_cmd] = pc
                commands[stage].append(pc)

        # Built-in tasks (Maven/Gradle phases, go build, etc.)
        for builtin_task in builtins:
            norm_cmd = " ".join(builtin_task.split())
            if norm_cmd not in seen_commands:
                pc = PlannedCommand(
                    command_str=builtin_task,
                    scripts=[builtin_task],
                    source="built-in task",
                    stage=stage,
                )
                seen_commands[norm_cmd] = pc
                commands[stage].append(pc)

        # Config triggers
        for trigger_file in config_triggers:
            trigger_path = project_dir / trigger_file
            if trigger_path.exists() and not commands[stage]:
                # Config trigger enables the stage even without explicit scripts
                # The tool name is derived from the trigger file
                tool_name = trigger_file.split(".")[0].lstrip(".")
                pc = PlannedCommand(
                    command_str=f"[{tool_name} via {trigger_file}]",
                    scripts=[tool_name],
                    source=trigger_file,
                    stage=stage,
                )
                commands[stage].append(pc)

    return {"commands": commands, "skipped": skipped}


def _matches_stage(script_name: str, exact: list[str], prefixes: list[str]) -> bool:
    if script_name in exact:
        return True
    for prefix in prefixes:
        bare = prefix.rstrip("*").rstrip(":")
        if script_name == bare or script_name.startswith(bare + ":"):
            return True
    return False


def _read_declared_scripts(
    project_dir: Path, lang_name: str, lang_cfg: dict
) -> dict[str, str]:
    """Return {script_name: command_str} from the project's build file."""
    project_files = lang_cfg.get("project_files", [])
    if not project_files:
        return {}

    # package.json — parse scripts key
    if "package.json" in project_files:
        pkg_path = project_dir / "package.json"
        if pkg_path.exists():
            try:
                import json as _json

                pkg = _json.loads(pkg_path.read_text(encoding="utf-8"))
                return {
                    k: v
                    for k, v in pkg.get("scripts", {}).items()
                    if isinstance(v, str)
                }
            except Exception:
                pass

    # pyproject.toml — parse [project.scripts] or [tool.taskipy.tasks]
    if "pyproject.toml" in project_files:
        ppt = project_dir / "pyproject.toml"
        if ppt.exists():
            try:
                with ppt.open("rb") as fh:
                    data = tomllib.load(fh)
                scripts: dict[str, str] = {}
                # [project.scripts]
                for k, v in data.get("project", {}).get("scripts", {}).items():
                    if isinstance(v, str):
                        scripts[k] = v
                # [tool.taskipy.tasks]
                for k, v in (
                    data.get("tool", {}).get("taskipy", {}).get("tasks", {}).items()
                ):
                    if isinstance(v, str):
                        scripts[k] = v
                return scripts
            except Exception:
                pass

    return {}


def _project_file_name(lang_cfg: dict) -> str:
    pf = lang_cfg.get("project_files", ["build file"])
    return pf[0] if pf else "build file"


def _collect_warnings(
    root: Path,
    all_files: list[Path],
    projects: list[Project],
    project_map: dict[tuple[Path, str], Project],
    ext_to_langs: dict[str, list[str]],
    ignore_exts: set[str],
    languages: dict,
) -> list[Warning]:
    warnings: list[Warning] = []

    # Build set of all recognised extensions
    all_recognised_exts = set(ext_to_langs.keys())

    # Group unmatched files
    unsupported: dict[str, list[Path]] = {}  # ext -> files
    no_project: dict[tuple[str, str], list[Path]] = {}  # (ext, top_folder) -> files

    for f in all_files:
        ext = _normalise(f.suffix)
        if not f.suffix:
            continue
        if ext in ignore_exts:
            continue

        # Is this a project file itself? Skip it.
        fname = f.name
        is_project_file = False
        for lang_cfg in languages.values():
            if fname in lang_cfg.get("project_files", []):
                is_project_file = True
                break
        if is_project_file:
            continue

        if ext not in all_recognised_exts:
            unsupported.setdefault(ext, []).append(f)
            continue

        # Find nearest ancestor project for this file's language(s)
        langs_for_ext = ext_to_langs.get(ext, [])
        found_project = False
        for lang_name in langs_for_ext:
            ancestor = f.parent
            while True:
                if (ancestor, lang_name) in project_map:
                    found_project = True
                    break
                if ancestor == root:
                    break
                ancestor = ancestor.parent
            if found_project:
                break

        if not found_project and langs_for_ext:
            # Determine top-level folder
            try:
                rel = f.relative_to(root)
                top_folder = rel.parts[0] if len(rel.parts) > 1 else "."
            except ValueError:
                top_folder = "."
            key = (ext, top_folder)
            no_project.setdefault(key, []).append(f)

    # Emit unsupported_extension warnings (grouped by extension)
    for ext, files in sorted(unsupported.items()):
        folders = sorted({str(f.parent.relative_to(root)) for f in files})
        capped = [str(f.relative_to(root)) for f in files[:50]]
        warnings.append(
            Warning(
                type="unsupported_extension",
                extension=ext,
                folders=folders[:10],
                count=len(files),
                files=capped,
                more=max(0, len(files) - 50),
                reason=f"No language rule for extension {ext!r}",
            )
        )

    # Emit no_project warnings (grouped by ext + top folder)
    for (ext, top_folder), files in sorted(no_project.items()):
        capped = [str(f.relative_to(root)) for f in files[:50]]
        warnings.append(
            Warning(
                type="no_project",
                extension=ext,
                folders=[top_folder],
                count=len(files),
                files=capped,
                more=max(0, len(files) - 50),
                reason=f"Files with extension {ext!r} found in {top_folder!r} but no project file detected",
            )
        )

    return warnings


def _check_gitignore(root: Path) -> Warning | None:
    gitignore = root / ".gitignore"
    pre_llm_entry = ".pre-llm/"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8", errors="replace")
        lines = [l.strip() for l in content.splitlines()]
        if ".pre-llm" in lines or ".pre-llm/" in lines or ".pre-llm/*" in lines:
            return None
    return Warning(
        type="gitignore_missing",
        reason=f".pre-llm/ is not in .gitignore. Add this line: {pre_llm_entry}",
    )


def _apply_add_gitignore(root: Path) -> None:
    gitignore = root / ".gitignore"
    entry = ".pre-llm/\n"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8", errors="replace")
        lines = [l.strip() for l in content.splitlines()]
        if ".pre-llm" in lines or ".pre-llm/" in lines:
            return
        with gitignore.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    else:
        gitignore.write_text(entry, encoding="utf-8")


# ---------------------------------------------------------------------------
# Dependency detection
# ---------------------------------------------------------------------------


def check_dependencies(project: Project, lang_cfg: dict) -> bool:
    """Return True if dependencies appear to be available. False → emit warning."""
    dep_check = lang_cfg.get("dependency_check", {})
    filesystem = dep_check.get("filesystem")
    if filesystem:
        fs_path = project.path / filesystem
        if not fs_path.exists():
            return False
    return True


# ---------------------------------------------------------------------------
# Terminal table & dry-run output
# ---------------------------------------------------------------------------


def _status_cell(status: str) -> str:
    STATUS_MAP = {
        "pass": "PASS",
        "fail": "FAIL",
        "timeout": "TIMEOUT",
        "skipped": "SKIP",
        "warning": "WARN",
        "planned": "PLANNED",
        "error": "ERROR",
    }
    return STATUS_MAP.get(status, status.upper())


def print_dry_run_table(
    projects: list[Project], warnings: list[Warning], root: Path
) -> None:
    # Column widths
    col_project = (
        max((len(str(p.path.relative_to(root))) for p in projects), default=7) + 2
    )
    col_project = max(col_project, 9)
    col_lang = (
        max(
            (
                len(p.language) + (10 if p.verification == "untested" else 0)
                for p in projects
            ),
            default=8,
        )
        + 2
    )
    col_lang = max(col_lang, 10)
    col_stage = 9

    header = (
        f"{'Project':<{col_project}} {'Language':<{col_lang}} "
        f"{'Build':<{col_stage}} {'Lint':<{col_stage}} {'Tests':<{col_stage}} {'Coverage':<{col_stage}}"
    )
    print(header)
    print("-" * len(header))

    for proj in projects:
        rel = str(proj.path.relative_to(root))
        lang_label = proj.language
        if proj.verification == "untested":
            lang_label += " [untested]"
        row = (
            f"{rel:<{col_project}} {lang_label:<{col_lang}} "
            f"{'PLANNED':<{col_stage}} {'PLANNED':<{col_stage}} {'PLANNED':<{col_stage}} {'PLANNED':<{col_stage}}"
        )
        print(row)

    print()

    # Planned commands per project
    for proj in projects:
        rel = str(proj.path.relative_to(root))
        has_any = any(proj.planned_commands.get(s) for s in ALL_STAGES)
        if not has_any:
            print(f"  {rel}: (nothing to run)")
            continue
        print(f"  {rel}:")
        for stage in ALL_STAGES:
            cmds = proj.planned_commands.get(stage, [])
            if cmds:
                for pc in cmds:
                    print(f"    [{stage}] {', '.join(pc.scripts)} -> {pc.command_str}")
        if proj.skipped_scripts:
            for sk in proj.skipped_scripts:
                print(f"    [SKIP] {sk['script']} ({sk['stage']}): {sk['reason']}")
        print()

    # Warnings
    if warnings:
        print("Warnings:")
        for w in warnings:
            if w.type == "gitignore_missing":
                print(f"  [{w.type}] {w.reason}")
            elif w.type in ("unsupported_extension", "no_project"):
                examples = w.files[:3]
                more = w.count - len(examples)
                ex_str = ", ".join(examples)
                suffix = f" (+{more} more)" if more > 0 else ""
                print(
                    f"  [{w.type}] ext={w.extension} count={w.count}: {ex_str}{suffix}"
                )
            else:
                print(f"  [{w.type}] {w.reason}")
        print()


def build_dry_run_report(
    projects: list[Project],
    warnings: list[Warning],
    root: Path,
    steps: list[str],
) -> dict:
    return {
        "schema_version": "1.0",
        "mode": "dry-run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "status": "planned",
            "project_count": len(projects),
            "counts": {
                "planned": sum(
                    len(cmds) for p in projects for cmds in p.planned_commands.values()
                )
            },
            "warning_count": len(warnings),
        },
        "projects": [_project_to_dry_run_dict(p, root, steps) for p in projects],
        "warnings": [w.to_dict() for w in warnings],
    }


def _project_to_dry_run_dict(proj: Project, root: Path, steps: list[str]) -> dict:
    stages = {}
    for stage in ALL_STAGES:
        if stage not in steps:
            stages[stage] = {
                "status": "skipped",
                "commands": [],
                "note": "excluded by --steps",
            }
            continue
        cmds = proj.planned_commands.get(stage, [])
        stages[stage] = {
            "status": "planned",
            "commands": [
                {
                    "command": pc.command_str,
                    "scripts": pc.scripts,
                    "source": pc.source,
                    "status": "planned",
                }
                for pc in cmds
            ],
        }
    return {
        "name": str(proj.path.relative_to(root)),
        "language": proj.language,
        "verification": proj.verification,
        "build_files": [str(bf.relative_to(root)) for bf in proj.build_files],
        "skipped_scripts": proj.skipped_scripts,
        "stages": stages,
    }


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class StageResult:
    status: str  # "pass"|"fail"|"timeout"|"skipped"|"warning"
    commands: list[CommandResult]
    note: str = ""
    coverage_results: list[dict] = dataclasses.field(default_factory=list)


def run_project(
    proj: Project,
    lang_cfg: dict,
    args,
    repo_root: Path,
    run_start: float,
) -> dict[str, StageResult]:
    """Run all applicable stages for a project. Returns {stage: StageResult}."""
    steps: list[str] = args.steps
    timeouts = {
        "build": args.timeout_build,
        "lint": args.timeout_lint,
        "tests": args.timeout_tests,
        "coverage": args.timeout_coverage,
    }

    results: dict[str, StageResult] = {}
    build_failed = False

    # Dependency check (filesystem)
    if not check_dependencies(proj, lang_cfg):
        dep_name = lang_cfg.get("dependency_check", {}).get(
            "filesystem", "dependencies"
        )
        for stage in ALL_STAGES:
            results[stage] = StageResult(
                status="skipped",
                commands=[],
                note=f"dependencies_missing: {dep_name} not found",
            )
        return results

    for stage in ALL_STAGES:
        if stage not in steps:
            results[stage] = StageResult(
                status="skipped",
                commands=[],
                note="excluded by --steps",
            )
            continue

        # Build gate
        if build_failed and stage != "lint":
            results[stage] = StageResult(
                status="skipped",
                commands=[],
                note="build failed",
            )
            continue
        if build_failed and stage == "lint" and not args.lint_anyway:
            results[stage] = StageResult(
                status="skipped",
                commands=[],
                note="build failed (use --lint-anyway to override)",
            )
            continue

        planned_cmds = proj.planned_commands.get(stage, [])
        if not planned_cmds:
            results[stage] = StageResult(
                status="skipped", commands=[], note="no commands defined"
            )
            continue

        stage_results: list[CommandResult] = []
        stage_status = "pass"

        for pc in planned_cmds:
            # Build the actual argv
            runner = select_runner(proj.language, proj.path, pc.command_str, lang_cfg)
            if isinstance(runner, RunnerNotFound):
                # tool_not_installed — skip this command
                stage_results.append(
                    CommandResult(
                        command_str=pc.command_str,
                        scripts=pc.scripts,
                        source=pc.source,
                        status="skipped",
                        duration_s=0.0,
                        output_tail=[f"Runner not found: {runner.runner_name}"],
                        log_path="",
                        exit_code=None,
                    )
                )
                continue

            # For built-in tasks and generic runners, the command_str IS the full command
            # For npm run, runner already includes script name
            # Determine actual argv
            if proj.language == "node" and runner[0] == "npm":
                # runner is already ["npm", "run", script_name]
                argv = runner
            else:
                # For built-ins, split the command_str into argv
                argv = pc.command_str.split()

            script_name = pc.scripts[0] if pc.scripts else pc.command_str
            log_path = make_log_path(
                str(proj.path.relative_to(repo_root)),
                stage,
                script_name,
                repo_root,
            )

            result = run_command(
                cmd=argv,
                cwd=proj.path,
                timeout_s=timeouts[stage],
                stage=stage,
                scripts=pc.scripts,
                source=pc.source,
                log_path=log_path,
                tail_lines=args.tail_lines,
                repo_root=repo_root,
            )

            # Check dependency error patterns in output
            dep_patterns = lang_cfg.get("dependency_check", {}).get(
                "error_patterns", []
            )
            if result.status == "fail" and dep_patterns:
                output_text = "\n".join(result.output_tail)
                if any(pat in output_text for pat in dep_patterns):
                    result.status = "warning"
                    result.output_tail = [
                        f"[dependencies_missing] {result.output_tail[0] if result.output_tail else ''}"
                    ]

            stage_results.append(result)

            # Update stage status (worst wins)
            if result.status == "fail":
                stage_status = "fail"
            elif result.status == "timeout":
                stage_status = "timeout"
            elif result.status == "warning" and stage_status == "pass":
                stage_status = "warning"

        # Zero tests warning
        if stage == "tests" and stage_status == "pass":
            combined_output = "\n".join(
                line for r in stage_results for line in r.output_tail
            )
            if _zero_tests_detected(combined_output):
                stage_status = "warning"

        results[stage] = StageResult(status=stage_status, commands=stage_results)

        # Build gate: if build fails/times out, gate remaining stages
        if stage == "build" and stage_status in ("fail", "timeout"):
            build_failed = True

    return results


def _zero_tests_detected(output: str) -> bool:
    """Heuristic: detect 0 tests run from common test runner output."""
    patterns = [
        r"\b0 tests?\b",
        r"\bno tests?\b",
        r"Tests run: 0\b",
        r"0 passed",
        r"Ran 0 test",
    ]
    for pat in patterns:
        if re.search(pat, output, re.IGNORECASE):
            return True
    return False


# ---------------------------------------------------------------------------
# Coverage extraction (stubs for ticket 09)
# ---------------------------------------------------------------------------


def extract_coverage(
    stage_result: StageResult,
    lang_cfg: dict,
    project_path: Path,
    run_start: float,
) -> list[dict]:
    """Extract coverage percentage(s). Returns list of {tool, line_pct, branch_pct}."""
    coverage_cfg = lang_cfg.get("coverage", {})
    results: list[dict] = []

    # Try report files first
    for rf in coverage_cfg.get("report_files", []):
        report_path = project_path / rf["path"]
        if not report_path.exists():
            continue
        # Freshness check
        if report_path.stat().st_mtime < run_start:
            continue
        pct = _read_coverage_file(report_path, rf["format"])
        if pct is not None:
            results.append(
                {"tool": rf["format"], "line_pct": pct, "source": str(report_path)}
            )

    # Fallback: stdout regex
    if not results and "output_pattern" in coverage_cfg:
        pattern = re.compile(coverage_cfg["output_pattern"])
        for cmd_result in stage_result.commands:
            for line in cmd_result.output_tail:
                m = pattern.search(line)
                if m:
                    try:
                        pct = float(m.group(1))
                        results.append({"tool": "stdout-regex", "line_pct": pct})
                    except (IndexError, ValueError):
                        pass

    return results


def _read_coverage_file(path: Path, fmt: str) -> float | None:
    """Parse a coverage report file. Returns line coverage % or None."""
    try:
        if fmt == "istanbul-json-summary":
            import json as _json

            data = _json.loads(path.read_text(encoding="utf-8"))
            return data.get("total", {}).get("lines", {}).get("pct")
        if fmt in ("jacoco-xml", "cobertura-xml"):
            import xml.etree.ElementTree as ET

            tree = ET.parse(path)
            root_el = tree.getroot()
            if fmt == "jacoco-xml":
                # <counter type="LINE" missed="X" covered="Y"/>
                for counter in root_el.iter("counter"):
                    if counter.get("type") == "LINE":
                        missed = int(counter.get("missed", 0))
                        covered = int(counter.get("covered", 0))
                        total = missed + covered
                        if total > 0:
                            return round(covered / total * 100, 2)
            elif fmt == "cobertura-xml":
                line_rate = root_el.get("line-rate")
                if line_rate:
                    return round(float(line_rate) * 100, 2)
        if fmt == "lcov":
            lh = lf = 0
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("LH:"):
                    lh += int(line[3:])
                elif line.startswith("LF:"):
                    lf += int(line[3:])
            if lf > 0:
                return round(lh / lf * 100, 2)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def build_report(
    projects: list[Project],
    project_results: dict[str, dict[str, StageResult]],
    warnings: list[Warning],
    root: Path,
    steps: list[str],
    mode: str = "run",
    error_msg: str | None = None,
) -> dict:
    # Overall summary
    all_statuses = [
        r.status for stage_map in project_results.values() for r in stage_map.values()
    ]
    counts: dict[str, int] = {
        "pass": 0,
        "fail": 0,
        "timeout": 0,
        "skipped": 0,
        "warning": 0,
    }
    for s in all_statuses:
        if s in counts:
            counts[s] += 1

    if error_msg:
        summary_status = "error"
    elif counts["fail"] > 0 or counts["timeout"] > 0:
        summary_status = "fail"
    elif counts["warning"] > 0:
        summary_status = "warning"
    else:
        summary_status = "pass"

    report: dict = {
        "schema_version": "1.0",
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "status": summary_status,
            "project_count": len(projects),
            "counts": counts,
            "warning_count": len(warnings),
        },
        "projects": [],
        "warnings": [w.to_dict() for w in warnings],
    }

    if error_msg:
        report["error"] = error_msg

    for proj in projects:
        proj_key = str(proj.path.relative_to(root))
        stage_map = project_results.get(proj_key, {})
        stages_dict = {}
        for stage in ALL_STAGES:
            sr = stage_map.get(stage)
            if sr is None:
                stages_dict[stage] = {"status": "skipped", "commands": []}
                continue
            cmd_list = []
            for cr in sr.commands:
                cmd_list.append(
                    {
                        "command": cr.command_str,
                        "scripts": cr.scripts,
                        "source": cr.source,
                        "status": cr.status,
                        "duration_s": cr.duration_s,
                        "output_tail": cr.output_tail,
                        "log_path": cr.log_path,
                    }
                )
            stage_entry: dict = {"status": sr.status, "commands": cmd_list}
            if sr.note:
                stage_entry["note"] = sr.note
            if stage == "coverage" and sr.coverage_results:
                stage_entry["results"] = sr.coverage_results
            stages_dict[stage] = stage_entry

        report["projects"].append(
            {
                "name": proj_key,
                "language": proj.language,
                "verification": proj.verification,
                "build_files": [str(bf.relative_to(root)) for bf in proj.build_files],
                "skipped_scripts": proj.skipped_scripts,
                "stages": stages_dict,
            }
        )

    return report


# ---------------------------------------------------------------------------
# Terminal table (post-run)
# ---------------------------------------------------------------------------

WORST_STATUS_ORDER = ["fail", "timeout", "warning", "pass", "skipped"]


def _worst_status(statuses: list[str]) -> str:
    for s in WORST_STATUS_ORDER:
        if s in statuses:
            return s
    return "skipped"


def print_results_table(
    projects: list[Project],
    project_results: dict[str, dict[str, StageResult]],
    root: Path,
    verbose: bool,
) -> None:
    col_project = (
        max((len(str(p.path.relative_to(root))) for p in projects), default=7) + 2
    )
    col_project = max(col_project, 9)
    col_lang = (
        max(
            (
                len(p.language) + (10 if p.verification == "untested" else 0)
                for p in projects
            ),
            default=8,
        )
        + 2
    )
    col_lang = max(col_lang, 10)
    col_stage = 9

    header = (
        f"{'Project':<{col_project}} {'Language':<{col_lang}} "
        f"{'Build':<{col_stage}} {'Lint':<{col_stage}} {'Tests':<{col_stage}} {'Coverage':<{col_stage}}"
    )
    print(header)
    print("-" * len(header))

    for proj in projects:
        rel = str(proj.path.relative_to(root))
        lang_label = proj.language
        if proj.verification == "untested":
            lang_label += " [untested]"
        stage_map = project_results.get(rel, {})

        stage_cells = []
        for stage in ["build", "lint", "tests"]:
            sr = stage_map.get(stage)
            if sr is None or sr.status == "skipped":
                stage_cells.append("SKIP")
            else:
                stage_cells.append(_status_cell(sr.status))

        # Coverage cell
        cov_sr = stage_map.get("coverage")
        if cov_sr and cov_sr.coverage_results:
            pcts: list[float] = [
                float(r["line_pct"])
                for r in cov_sr.coverage_results
                if r.get("line_pct") is not None
            ]
            if pcts:
                lowest = min(pcts)
                count = len(pcts)
                cov_cell = f"{lowest:.1f}%({count})" if count > 1 else f"{lowest:.1f}%"
            else:
                cov_cell = _status_cell(cov_sr.status)
        elif cov_sr:
            cov_cell = (
                "SKIP" if cov_sr.status == "skipped" else _status_cell(cov_sr.status)
            )
        else:
            cov_cell = "SKIP"

        row = (
            f"{rel:<{col_project}} {lang_label:<{col_lang}} "
            f"{stage_cells[0]:<{col_stage}} {stage_cells[1]:<{col_stage}} "
            f"{stage_cells[2]:<{col_stage}} {cov_cell:<{col_stage}}"
        )
        print(row)

    print()

    # Detail lines for non-passing commands
    detail_printed = False
    for proj in projects:
        rel = str(proj.path.relative_to(root))
        stage_map = project_results.get(rel, {})
        for stage in ALL_STAGES:
            sr = stage_map.get(stage)
            if sr is None:
                continue
            for cr in sr.commands:
                if verbose or cr.status not in ("pass", "skipped"):
                    if not detail_printed:
                        print("Details:")
                        detail_printed = True
                    scripts_str = ", ".join(cr.scripts)
                    print(f"  {rel} › {stage} › {scripts_str}")
                    print(f"    status={cr.status} duration={cr.duration_s}s")
                    if cr.output_tail:
                        for line in cr.output_tail[-5:]:
                            print(f"    | {line}")
                    if cr.log_path:
                        print(f"    log: {cr.log_path}")
    if detail_printed:
        print()


def print_warnings_section(warnings: list[Warning]) -> None:
    if not warnings:
        return
    print("Warnings:")
    for w in warnings:
        if w.type == "gitignore_missing":
            print(f"  [{w.type}] {w.reason}")
        elif w.type in ("unsupported_extension", "no_project"):
            examples = w.files[:3]
            more = w.count - len(examples)
            ex_str = ", ".join(examples)
            suffix = f" (+{more} more)" if more > 0 else ""
            print(f"  [{w.type}] ext={w.extension} count={w.count}: {ex_str}{suffix}")
        else:
            print(f"  [{w.type}] {w.reason}")
    print()


# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------


def compute_exit_code(report: dict) -> int:
    status = report.get("summary", {}).get("status", "error")
    if status == "error":
        return 2
    if status in ("fail",):
        return 1
    counts = report.get("summary", {}).get("counts", {})
    if counts.get("timeout", 0) > 0:
        return 1
    if report.get("summary", {}).get("project_count", 0) == 0:
        return 3
    return 0


# ---------------------------------------------------------------------------
# Argument parsing helpers
# ---------------------------------------------------------------------------

VALID_STEPS = {"build", "lint", "tests", "coverage"}


class _DurationAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if not isinstance(values, str):
            parser.error(f"Expected a string for {self.dest}")
            return
        try:
            seconds = parse_duration(values)
        except ValueError as exc:
            parser.error(str(exc))
            return
        setattr(namespace, self.dest, seconds)


def _positive_int(value: str) -> int:
    if not _PLAIN_INT_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"--tail-lines requires a plain positive integer, got {value!r}"
        )
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError(
            f"--tail-lines must be a positive integer greater than 0, got {n}"
        )
    return n


def _parse_steps(value: str) -> list[str]:
    steps = [s.strip() for s in value.split(",") if s.strip()]
    unknown = sorted(set(steps) - VALID_STEPS)
    if unknown:
        raise argparse.ArgumentTypeError(
            f"Unknown step(s): {', '.join(unknown)}. "
            f"Valid steps are: {', '.join(sorted(VALID_STEPS))}"
        )
    if not steps:
        raise argparse.ArgumentTypeError("--steps cannot be empty")
    return steps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pre-llm-checks",
        description=(
            "Scan a repository, run build/lint/tests/coverage, and produce a "
            "structured report for LLM code review."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--path",
        metavar="FOLDER",
        default=".",
        help="Target directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default="pre-llm-report.json",
        help="Path for the JSON report (default: pre-llm-report.json).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect projects and tools without executing any commands.",
    )
    parser.add_argument(
        "--steps",
        metavar="LIST",
        type=_parse_steps,
        default=list(VALID_STEPS),
        help="Comma-separated subset of stages to run: build,lint,tests,coverage (default: all).",
    )
    parser.add_argument(
        "--lint-anyway", action="store_true", help="Run lint even when build fails."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Stream command output live instead of buffering.",
    )
    for stage, default_desc in [
        ("build", "10m"),
        ("lint", "5m"),
        ("tests", "15m"),
        ("coverage", "15m"),
    ]:
        parser.add_argument(
            f"--timeout-{stage}",
            metavar="DURATION",
            dest=f"timeout_{stage}",
            action=_DurationAction,
            default=parse_duration(default_desc),
            help=f"Timeout for the {stage} stage (default: {default_desc}).",
        )
    parser.add_argument(
        "--tail-lines",
        metavar="N",
        dest="tail_lines",
        type=_positive_int,
        default=50,
        help="Number of output lines to include in the report (default: 50).",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help="Path to an alternative languages.toml.",
    )
    parser.add_argument(
        "--add-gitignore",
        action="store_true",
        help="Append .pre-llm/ to .gitignore if it is missing.",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    global _VERBOSE
    parser = build_parser()
    args = parser.parse_args()

    _VERBOSE = args.verbose

    config_path = (
        Path(args.config) if args.config else Path(__file__).parent / "languages.toml"
    )
    config = load_config(config_path)

    ignore_extensions: list[str] = config.get("ignore_extensions", [])
    languages: dict = config.get("languages", {})

    target_path = Path(args.path).resolve()
    if not target_path.is_dir():
        _exit2(f"--path is not a directory: {target_path}")

    repo_root = target_path

    # Handle --add-gitignore
    if args.add_gitignore:
        _apply_add_gitignore(repo_root)

    # Scan
    projects, warnings = scan_directory(target_path, languages, ignore_extensions)

    if not projects:
        print("No supported projects found.", file=sys.stderr)
        # Still write report if --output given
        if args.output:
            report = {
                "schema_version": "1.0",
                "mode": "dry-run" if args.dry_run else "run",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "status": "planned" if args.dry_run else "pass",
                    "project_count": 0,
                    "counts": {},
                    "warning_count": len(warnings),
                },
                "projects": [],
                "warnings": [w.to_dict() for w in warnings],
            }
            Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        sys.exit(3)

    # --dry-run
    if args.dry_run:
        print_dry_run_table(projects, warnings, repo_root)
        if args.output:
            report = build_dry_run_report(projects, warnings, repo_root, args.steps)
            Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Report written to {args.output}")
        sys.exit(0)

    # Full run
    run_start = time.time()
    project_results: dict[str, dict[str, StageResult]] = {}

    for proj in projects:
        lang_cfg = languages.get(proj.language, {})
        proj_key = str(proj.path.relative_to(repo_root))
        stage_results = run_project(proj, lang_cfg, args, repo_root, run_start)

        # Extract coverage
        cov_sr = stage_results.get("coverage")
        if cov_sr and cov_sr.status not in ("skipped",):
            cov_results = extract_coverage(cov_sr, lang_cfg, proj.path, run_start)
            cov_sr.coverage_results = cov_results

        project_results[proj_key] = stage_results

    # Build report
    report = build_report(projects, project_results, warnings, repo_root, args.steps)

    # Print table
    print_results_table(projects, project_results, repo_root, args.verbose)
    print_warnings_section(warnings)

    # Summary line
    summary = report["summary"]
    print(
        f"Status: {summary['status'].upper()}  "
        f"Projects: {summary['project_count']}  "
        f"Warnings: {summary['warning_count']}  "
        f"Report: {args.output}"
    )

    # Write report
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")

    sys.exit(compute_exit_code(report))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exit2(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
