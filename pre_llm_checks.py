#!/usr/bin/env python3
"""pre-llm-checks — run build/lint/tests/coverage before handing code to an LLM."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(
    r"""
    ^
    (?:(\d+)h)?   # optional hours
    (?:(\d+)m)?   # optional minutes
    (\d+s?)?      # optional seconds (with or without trailing 's')
    $
    """,
    re.VERBOSE,
)

_PLAIN_INT_RE = re.compile(r"^\d+$")
_SECONDS_RE = re.compile(r"^(\d+)s$")
_MINUTES_RE = re.compile(r"^(\d+)m$")
_HOURS_RE = re.compile(r"^(\d+)h$")
_HM_RE = re.compile(r"^(\d+)h(\d+)m$")


def parse_duration(s: str) -> int:
    """Return duration in seconds from a string like 90s, 30m, 1h, 1h30m, or plain int."""
    s = s.strip()
    if not s:
        raise ValueError(f"Empty duration string")

    m = _PLAIN_INT_RE.match(s)
    if m:
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
    """Load and validate languages.toml; exit 2 on any problem."""
    if not config_path.exists():
        _exit2(f"Config file not found: {config_path}")

    data: dict = {}
    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        _exit2(f"Invalid TOML in {config_path}: {exc}")

    # Validate language entries
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
# Argument parsing helpers
# ---------------------------------------------------------------------------

VALID_STEPS = {"build", "lint", "tests", "coverage"}


class _DurationAction(argparse.Action):
    """Custom argparse action that converts a duration string to int (seconds)."""

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
    """Argparse type for a plain positive integer (used by --tail-lines)."""
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
    """Argparse type for --steps: comma-separated subset of build,lint,tests,coverage."""
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
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
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
        help=(
            "Comma-separated subset of stages to run: build,lint,tests,coverage "
            "(default: all)."
        ),
    )
    parser.add_argument(
        "--lint-anyway",
        action="store_true",
        help="Run lint even when build fails.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Stream command output live instead of buffering.",
    )

    # Timeout flags
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
            help=(
                f"Timeout for the {stage} stage (default: {default_desc}). "
                "Accepts 90s, 30m, 1h, 1h30m, or plain integer (seconds)."
            ),
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
    parser = build_parser()
    args = parser.parse_args()

    # Resolve config path
    if args.config is not None:
        config_path = Path(args.config)
    else:
        config_path = Path(__file__).parent / "languages.toml"

    # Load and validate config (exits 2 on failure)
    config = load_config(config_path)

    # Parse ignore_extensions from top level
    ignore_extensions: list[str] = config.get("ignore_extensions", [])

    # Resolve target path
    target_path = Path(args.path).resolve()
    if not target_path.is_dir():
        _exit2(f"--path is not a directory: {target_path}")

    # --- Stub: project discovery not yet implemented ---
    # Ticket 01 requirement: "no supported project found" → exit 3
    print(
        f"pre-llm-checks {__version__}: scanning {target_path}",
        file=sys.stderr,
    )
    print(
        "No supported projects found.",
        file=sys.stderr,
    )
    sys.exit(3)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exit2(message: str) -> None:
    """Print an error message to stderr and exit with code 2."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
