"""Fail unless dbt v2 strict static analysis really ran.

Usage:
    python check_strict.py correctness CORRECTNESS_DIR
    python check_strict.py runs RESULTS_RUNS_DIR

`correctness` checks correctness.sh logs: strict reports the seeded unknown column (dbt0227) in
default, cached and dirty modes, the same project compiles with exit 0 without strict, and the
clean project passes strict. `runs` checks bench.sh output: every strict run exits 0. Both fail if
any strict output matches FALLBACK_PATTERNS, which would mean strict analysis fell back or was off.
"""

import re
import sys
from pathlib import Path

FALLBACK_PATTERNS = (
    r"did not run",
    r"fall(?:s|ing)? ?back",
    r"\bbaseline\b",
    r"\blog ?in\b",
    r"authenticat",
    r"does not include the static analysis",
    r"requires the full dbt distribution",
    r"static_analysis'? to off",
    r"dbt1014",
    r"Skipping analysis",
)
FALLBACK_RE = re.compile("|".join(FALLBACK_PATTERNS), re.IGNORECASE)
# Parse-cache messages, such as a partial parse falling back to a full parse, aren't about analysis.
IGNORED_RE = re.compile(r"^\[partial-parse\]")
UNKNOWN_COLUMN = "UnresolvedIdentifier (dbt0227)"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def read(path: Path) -> str:
    return ANSI_RE.sub("", path.read_text(errors="replace"))


def fallback_lines(text: str) -> list[str]:
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if FALLBACK_RE.search(line) and not IGNORED_RE.match(line)]


def check_correctness(root: Path) -> list[str]:
    logs = root / "logs"
    errors: list[str] = []

    def result(name: str) -> tuple[int, str]:
        log = logs / f"{name}.log"
        if not log.exists():
            errors.append(f"{name}: missing log")
            return -1, ""
        return int((logs / f"{name}.rc").read_text()), read(log)

    for name in (
        "column.v2_strict",
        "column.v2_strict_remote",
        "column.v2_strict_cached_warm",
        "column.v2_strict_dirty_warm",
    ):
        rc, text = result(name)
        if rc == 0 or UNKNOWN_COLUMN not in text:
            errors.append(f"{name}: expected a non-zero exit with {UNKNOWN_COLUMN}, got rc={rc}")
    for name in (
        "column.v2_compile",
        "clean.v2_strict",
        "clean.v2_strict_remote",
        "clean.v2_strict_cached_cold",
        "clean.v2_strict_dirty_cold",
    ):
        rc, _text = result(name)
        if rc != 0:
            errors.append(f"{name}: expected exit 0, got rc={rc}")
    for log in sorted(logs.glob("*strict*.log")):
        errors += [f"{log.name}: {line}" for line in fallback_lines(read(log))]
    return errors


def check_runs(root: Path) -> list[str]:
    errors: list[str] = []
    runs = sorted(root.glob("*strict*.rc"))
    if not runs:
        errors.append("no strict runs found")
    for rc_path in runs:
        stem = str(rc_path)[: -len(".rc")]
        rc = int(rc_path.read_text())
        if rc != 0:
            errors.append(f"{Path(stem).name}: exit code {rc}")
        text = read(Path(stem + ".out")) + read(Path(stem + ".err"))
        errors += [f"{Path(stem).name}: {line}" for line in fallback_lines(text)]
    return errors


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in ("correctness", "runs"):
        sys.exit(__doc__)
    mode, root = sys.argv[1], Path(sys.argv[2])
    errors = check_correctness(root) if mode == "correctness" else check_runs(root)
    if errors:
        print("dbt v2 strict static analysis check failed:")
        print("\n".join(f"- {error}" for error in errors))
        sys.exit(1)
    print(f"dbt v2 strict static analysis check passed ({mode}).")


if __name__ == "__main__":
    main()
